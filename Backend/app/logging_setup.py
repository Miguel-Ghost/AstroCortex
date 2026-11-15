"""Structured JSON logs with per-request and per-job correlation.

Adapted from the Quality Opportunities backend (same author). Render indexes JSON lines; with a
request_id in every line and in the X-Request-ID response header, an error the frontend reports
is found with one grep. Live-field jobs add their job_id and field_id.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

# ContextVars survive the jump from the request to the worker thread when copied explicitly.
request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
job_id: ContextVar[str | None] = ContextVar("job_id", default=None)

_RESERVED = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if (rid := request_id.get()) is not None:
            out["request_id"] = rid
        if (jid := job_id.get()) is not None:
            out["job_id"] = jid
        # extra fields passed as logger.info("...", extra={"key": value})
        out.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED})
        if record.exc_info:
            out["exception"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", json_lines: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        JsonFormatter() if json_lines else logging.Formatter("%(asctime)s %(levelname)-7s %(name)s  %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    # uvicorn brings its own handlers; route them through ours so everything has one format.
    for name in ("uvicorn", "uvicorn.error"):
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True
    # uvicorn's access log would repeat every request that the middleware already logs.
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = False
