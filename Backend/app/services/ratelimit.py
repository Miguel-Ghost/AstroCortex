"""In-memory sliding-window limits for /api/agent (one Render instance, so memory is enough).

Two layers (BR-AGENT-04):
- a hard limit per client: beyond it the request is refused with 429 rate_limited;
- a language-model budget per client and a global daily one: beyond them the guide still answers,
  with the rule-based planner, so nobody can drain the provider quota and the demo never stops.
The global daily cap is what bounds the spend; per-client limits only spread it fairly.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import Request


def client_ip(request: Request) -> str:
    """The caller behind Render's proxy (Cloudflare header first, then X-Forwarded-For)."""
    for header in ("cf-connecting-ip", "true-client-ip"):
        if value := request.headers.get(header):
            return value.strip()
    if forwarded := request.headers.get("x-forwarded-for"):
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class SlidingWindow:
    def __init__(self, limit: int, window_s: float):
        self.limit, self.window_s = limit, window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float | None = None) -> bool:
        """Count a hit for `key` if it fits in the window; False (and no count) otherwise."""
        if self.limit <= 0:
            return False
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window_s:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True

    def retry_after(self, key: str, now: float | None = None) -> int:
        now = time.monotonic() if now is None else now
        hits = self._hits.get(key)
        return max(1, int(self.window_s - (now - hits[0])) + 1) if hits else 1


class AgentLimits:
    def __init__(self, requests_per_min: int, llm_per_min: int, llm_per_day: int, llm_daily_max: int):
        self.requests = SlidingWindow(requests_per_min, 60)
        self.llm_minute = SlidingWindow(llm_per_min, 60)
        self.llm_day = SlidingWindow(llm_per_day, 86400)
        self.llm_global = SlidingWindow(llm_daily_max, 86400)

    def allow_request(self, ip: str) -> bool:
        return self.requests.allow(ip)

    def allow_llm(self, ip: str) -> bool:
        """All three budgets must have room; checked in order so a refusal spends nothing after it."""
        return self.llm_minute.allow(ip) and self.llm_day.allow(ip) and self.llm_global.allow("*")
