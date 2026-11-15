"""Language-model client for any `/chat/completions` API compatible with OpenAI.

The provider is configuration, not code: LLM_BASE_URL + LLM_MODEL (+ LLM_FALLBACK_MODELS) select
Gemini, OpenAI, Groq, Cerebras, OpenRouter or any other compatible endpoint. Same design as the
client of the UNICODE backend:

- one total time budget per request (LLM_TIMEOUT_S), shared by all models in the chain;
- 429 / 5xx / network error / timeout -> next model in the chain;
- JSON mode and a low reasoning effort when the provider supports them (a 400 caused by either one is
  retried once without the optional parameters), and tolerant parsing (code fences, text around it);
- one pooled HTTP connection reused across requests (saves the TLS handshake on every call).
"""

from __future__ import annotations

import json
import logging
import re
import time

import httpx

log = logging.getLogger("api")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.S)


class LLMError(RuntimeError):
    pass


def parse_json_object(text: str) -> dict:
    text = _FENCE.sub("", text.strip())
    try:
        value = json.loads(text)
    except ValueError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise LLMError("the model did not return a JSON object") from None
        value = json.loads(text[start : end + 1])
    if not isinstance(value, dict):
        raise LLMError("the model did not return a JSON object")
    return value


class LLMClient:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        fallbacks: list[str] | None = None,
        timeout_s: float = 6.0,
        json_mode: bool = True,
        transport: httpx.BaseTransport | None = None,
        reasoning_effort: str | None = None,
    ):
        self.model = model
        self.chain = [model, *[m for m in (fallbacks or []) if m and m != model]]
        self.timeout_s = timeout_s
        self.json_mode = json_mode
        self.reasoning_effort = reasoning_effort or None
        self.provider = httpx.URL(base_url).host
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._http = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            transport=transport,
            timeout=timeout_s,
        )
        self.last_model: str | None = None

    def json(self, system: str, user: str, *, max_tokens: int = 400, temperature: float = 0.2) -> dict:
        deadline = time.monotonic() + self.timeout_s
        errors: list[str] = []
        for model in self.chain:
            remaining = deadline - time.monotonic()
            if remaining <= 0.2:
                errors.append(f"{model}: no time left")
                break
            body = {
                "model": model,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if self.json_mode:
                body["response_format"] = {"type": "json_object"}
            if self.reasoning_effort:
                body["reasoning_effort"] = self.reasoning_effort  # thinking models answer much sooner
            try:
                r = self._http.post(self._url, json=body, timeout=remaining)
                if r.status_code == 400 and ("response_format" in body or "reasoning_effort" in body):
                    # a model without JSON mode or reasoning control: ask again without the optional parameters
                    body.pop("response_format", None)
                    body.pop("reasoning_effort", None)
                    r = self._http.post(self._url, json=body, timeout=max(0.2, deadline - time.monotonic()))
            except httpx.HTTPError as exc:
                errors.append(f"{model}: {type(exc).__name__}")
                continue
            if r.status_code == 429 or r.status_code >= 500:
                errors.append(f"{model}: HTTP {r.status_code}")
                continue
            if r.status_code >= 400:
                errors.append(f"{model}: HTTP {r.status_code}")
                break  # bad key or bad request: the next model would fail the same way
            try:
                content = r.json()["choices"][0]["message"]["content"] or ""
                value = parse_json_object(content)
            except (KeyError, IndexError, ValueError, LLMError) as exc:
                errors.append(f"{model}: {exc}")
                continue
            self.last_model = model
            return value
        raise LLMError("; ".join(errors) or "no model answered")
