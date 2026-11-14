"""Error envelope (BR-ERR-01): every error leaves as {"error": {"code", "message", "details"}}.

Adapted from the Quality Opportunities backend: stable codes the frontend can branch on, every
validation error (made JSON-safe), and a 500 that carries the request id instead of a stack trace.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.logging_setup import request_id

log = logging.getLogger("api")


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str, details: dict | None = None):
        super().__init__(status_code=status_code, detail={"code": code, "message": message, "details": details or {}})


def envelope(code: str, message: str, details: dict | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def internal_error_response() -> JSONResponse:
    """BR-ERR-01: unexpected failures answer 500 with the request id, never with internals."""
    rid = request_id.get()
    return JSONResponse(
        status_code=500,
        content=envelope("internal_error", "Unexpected error. Report the request id.", {"request_id": rid}),
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = {"error": {"details": {}, **exc.detail}}
        else:
            body = envelope(f"http_{exc.status_code}", str(exc.detail))
        return JSONResponse(status_code=exc.status_code, content=body, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # exc.errors() can carry the original exception of a custom validator in `ctx`, which is not
        # JSON-serialisable; jsonable_encoder turns it into text so the client gets the promised 422.
        errors = jsonable_encoder(exc.errors())
        first = errors[0] if errors else {}
        where = ".".join(str(p) for p in first.get("loc", []))
        return JSONResponse(
            status_code=422,
            content=envelope("invalid_request", f"{where}: {first.get('msg', 'invalid value')}", {"errors": errors}),
        )
