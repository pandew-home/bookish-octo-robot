"""Tests for standard API error envelope helpers."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

from middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware, get_request_id
from utils.error_handler import (
    INTERNAL_ERROR,
    RBAC_FORBIDDEN,
    VALIDATION_ERROR,
    api_error,
    error_envelope,
    normalize_agent_errors,
)


async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    detail = exc.detail
    rid = get_request_id()
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        body = detail
    else:
        message = detail if isinstance(detail, str) else str(detail)
        body = error_envelope(
            code=RBAC_FORBIDDEN if exc.status_code == 403 else INTERNAL_ERROR,
            message=message,
            recoverable=exc.status_code != 401,
            request_id=rid,
        )
    headers = {REQUEST_ID_HEADER: rid, "X-Error-Code": body["error"]["code"]}
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


async def _validation_handler(request: Request, exc: RequestValidationError):
    rid = get_request_id()
    body = error_envelope(
        code=VALIDATION_ERROR,
        message="Invalid request. Check your input.",
        details=exc.errors(),
        recoverable=True,
        request_id=rid,
    )
    return JSONResponse(
        status_code=422,
        content=body,
        headers={REQUEST_ID_HEADER: rid, "X-Error-Code": VALIDATION_ERROR},
    )


async def _unhandled_handler(request: Request, exc: Exception):
    rid = get_request_id()
    body = error_envelope(
        code=INTERNAL_ERROR,
        message="An unexpected error occurred. Please try again.",
        recoverable=True,
        request_id=rid,
    )
    return JSONResponse(
        status_code=500,
        content=body,
        headers={REQUEST_ID_HEADER: rid, "X-Error-Code": INTERNAL_ERROR},
    )


def _mini_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(Exception, _unhandled_handler)

    @app.get("/boom")
    def boom():
        raise api_error(RBAC_FORBIDDEN, "Access denied.", 403, recoverable=True)

    @app.get("/unhandled")
    def unhandled():
        raise RuntimeError("secret internal detail")

    from pydantic import BaseModel

    class Body(BaseModel):
        query: str

    @app.post("/validate")
    def validate(body: Body):
        return body

    return app


def test_error_envelope_shape():
    body = error_envelope(code="x", message="hi", request_id="abc")
    assert body["detail"] == "hi"
    assert body["error"]["code"] == "x"
    assert body["error"]["request_id"] == "abc"
    assert body["error"]["recoverable"] is True


def test_normalize_agent_errors():
    out = normalize_agent_errors(
        ["Stop condition reached: no progress", {"code": "agent_error", "message": "x"}]
    )
    assert out[0]["code"] == "agent_stop"
    assert out[1]["message"] == "x"


def test_api_error_response_envelope_and_request_id():
    client = TestClient(_mini_app())
    resp = client.get("/boom", headers={REQUEST_ID_HEADER: "testid1234"})
    assert resp.status_code == 403
    assert resp.headers.get(REQUEST_ID_HEADER) == "testid1234"
    data = resp.json()
    assert data["error"]["code"] == RBAC_FORBIDDEN
    assert data["error"]["message"] == "Access denied."
    assert data["detail"] == "Access denied."
    assert data["error"]["recoverable"] is True


def test_unhandled_hides_internal_detail():
    client = TestClient(_mini_app(), raise_server_exceptions=False)
    resp = client.get("/unhandled")
    assert resp.status_code == 500
    data = resp.json()
    assert data["error"]["code"] == "internal_error"
    assert "secret" not in data["error"]["message"].lower()
    assert data["error"]["recoverable"] is True


def test_validation_error_envelope():
    client = TestClient(_mini_app())
    resp = client.post("/validate", json={})
    assert resp.status_code == 422
    data = resp.json()
    assert data["error"]["code"] == VALIDATION_ERROR
    assert "Invalid request" in data["error"]["message"]
