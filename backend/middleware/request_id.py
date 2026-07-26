"""Request ID middleware for log ↔ UI correlation."""
from __future__ import annotations

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

REQUEST_ID_HEADER = "X-Request-Id"

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> str:
    """Return the current request id or a new ephemeral one."""
    rid = _request_id_var.get()
    if rid:
        return rid
    return uuid.uuid4().hex[:12]


def set_request_id(request_id: str) -> None:
    _request_id_var.set(request_id)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Ensure every request/response carries X-Request-Id."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER) or request.headers.get(
            "x-request-id"
        )
        request_id = (incoming or "").strip() or uuid.uuid4().hex[:12]
        set_request_id(request_id)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
