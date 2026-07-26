"""
DevOps Chatbot v2.0 - Main FastAPI Application

This is the main entry point for the DevOps Chatbot backend API.
It initializes the FastAPI application and registers all API routers.

Requirements: 15.2, 16.6, 16.7, 17.5
"""
import asyncio
import logging
import os
import sys
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from startup_validator import get_validator, validate_startup
from api.credentials import router as credentials_router
from api.clusters import router as clusters_router
from api.weather import router as weather_router
from api.chat import router as chat_router
from utils.metrics import get_metrics
from utils.error_handler import (
    AUTH_REQUIRED,
    INTERNAL_ERROR,
    VALIDATION_ERROR,
    error_envelope,
    log_error,
)
from middleware.request_id import REQUEST_ID_HEADER, RequestIdMiddleware, get_request_id

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

STATIC_ROOT = Path("/var/www/html")
STATIC_ROOT_RESOLVED = STATIC_ROOT.resolve()

# Create FastAPI app
logger.info("Creating FastAPI application...")
app = FastAPI(
    title="DevOps Chatbot v2.0 API",
    description="Kubernetes troubleshooting assistant with K8sGPT integration",
    version="2.0.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Configure CORS
# ALLOWED_ORIGINS env var is a comma-separated list of allowed origins.
# Defaults to the Civo cluster ingress host; override in production.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # Auth uses X-Session-ID header, not cookies
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-ID", "X-Session-Id", REQUEST_ID_HEADER],
    expose_headers=[REQUEST_ID_HEADER, "X-Error-Code"],
)
# Request ID should wrap outer so all responses get the header.
app.add_middleware(RequestIdMiddleware)

# Register API routers
logger.info("Registering API routers...")
app.include_router(credentials_router)
app.include_router(clusters_router)
app.include_router(weather_router)
app.include_router(chat_router)

logger.info("API routers registered successfully")


def _http_exception_body(exc: StarletteHTTPException) -> dict:
    """Normalize HTTPException.detail into the standard envelope."""
    rid = get_request_id()
    detail = exc.detail
    if isinstance(detail, dict) and isinstance(detail.get("error"), dict):
        # Already an envelope (possibly nested under detail from api_error)
        body = detail
        if "detail" not in body and isinstance(body["error"].get("message"), str):
            body = {**body, "detail": body["error"]["message"]}
        return body
    if isinstance(detail, dict) and "message" in detail and "code" in detail:
        return error_envelope(
            code=str(detail.get("code") or INTERNAL_ERROR),
            message=str(detail.get("message")),
            details=detail.get("details"),
            recoverable=bool(detail.get("recoverable", exc.status_code != 401)),
            request_id=rid,
        )
    message = detail if isinstance(detail, str) else str(detail)
    code = AUTH_REQUIRED if exc.status_code == 401 else INTERNAL_ERROR
    if exc.headers and exc.headers.get("X-Error-Code"):
        code = exc.headers["X-Error-Code"]
    return error_envelope(
        code=code,
        message=message,
        recoverable=exc.status_code != 401,
        request_id=rid,
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    body = _http_exception_body(exc)
    rid = body.get("error", {}).get("request_id") or get_request_id()
    level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    logger.log(
        level,
        "request_id=%s status=%s path=%s code=%s",
        rid,
        exc.status_code,
        request.url.path,
        body.get("error", {}).get("code"),
    )
    headers = dict(exc.headers or {})
    headers[REQUEST_ID_HEADER] = rid
    if "X-Error-Code" not in headers:
        headers["X-Error-Code"] = body.get("error", {}).get("code", INTERNAL_ERROR)
    return JSONResponse(status_code=exc.status_code, content=body, headers=headers)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    rid = get_request_id()
    errs = exc.errors()
    fields = []
    for e in errs[:8]:
        loc = ".".join(str(x) for x in e.get("loc", []) if x != "body")
        fields.append(f"{loc}: {e.get('msg', 'invalid')}" if loc else str(e.get("msg")))
    message = "Invalid request. " + ("; ".join(fields) if fields else "Check your input.")
    body = error_envelope(
        code=VALIDATION_ERROR,
        message=message,
        details=errs,
        recoverable=True,
        request_id=rid,
    )
    logger.warning(
        "request_id=%s status=422 path=%s code=%s",
        rid,
        request.url.path,
        VALIDATION_ERROR,
    )
    return JSONResponse(
        status_code=422,
        content=body,
        headers={REQUEST_ID_HEADER: rid, "X-Error-Code": VALIDATION_ERROR},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    rid = get_request_id()
    log_error(exc, context=f"unhandled {request.method} {request.url.path}", severity="ERROR")
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


@app.get("/api/health")
async def health_check():
    """
    Health check endpoint for liveness probes.
    
    This endpoint always returns 200 OK to indicate the application is running.
    It does not check if the application is ready to serve requests.
    
    Requirements: 16.6
    
    Returns:
        Simple health status
    """
    logger.info("Health check endpoint called - returning healthy")
    return {"status": "healthy", "service": "devops-chatbot-v2"}


@app.get("/api/health/ready")
async def readiness_check():
    """
    Readiness check endpoint for readiness probes.
    
    This endpoint returns 200 only after all startup validation completes successfully.
    Returns 503 Service Unavailable if validation has not completed or failed.
    
    Requirements: 16.7
    
    Returns:
        Readiness status with validation details
    """
    from fastapi import Response
    from fastapi.responses import JSONResponse
    
    logger.info("Readiness check endpoint called")
    validator = get_validator()
    
    if not validator.is_ready():
        status = validator.get_status()
        logger.warning(f"Readiness check returning 503 - not ready: {status['errors']}")
        return JSONResponse(
            content={
                "status": "not_ready",
                "service": "devops-chatbot-v2",
                "validation_complete": status["validation_complete"],
                "errors": status["errors"],
                "warnings": status["warnings"]
            },
            status_code=503
        )
    
    logger.info("Readiness check returning 200 - ready")
    return {
        "status": "ready",
        "service": "devops-chatbot-v2",
        "validation_complete": True
    }


@app.get("/api/config")
async def frontend_config():
    """
    Frontend configuration endpoint.
    
    Serves runtime environment configuration to the frontend, including base paths
    for subpath deployment support. This allows the frontend to be built once and
    deployed to different subpaths without rebuilding.
    
    Returns:
        JSON config with PUBLIC_URL and API_BASE_URL for the frontend
    """
    public_url = os.getenv('REACT_APP_PUBLIC_URL', '/')
    api_base_url = os.getenv('REACT_APP_API_URL', '/api')
    
    config = {
        "publicUrl": public_url,
        "apiBaseUrl": api_base_url
    }
    
    # Return as JSON that frontend can injected into window.__CONFIG__
    return config


@app.get("/metrics")
async def metrics():
    """
    Prometheus metrics endpoint.
    
    Exposes metrics for query latency, error rates, and API call counts.
    
    Requirements: 17.5
    
    Returns:
        Prometheus metrics in text format
    """
    metrics_data, content_type = get_metrics()
    return Response(content=metrics_data, media_type=content_type)


@app.on_event("startup")
async def startup_event():
    """
    Startup event handler.
    
    Performs initialization tasks when the application starts.
    Runs startup validation and exits if critical checks fail.
    
    Requirements: 16.1, 16.2, 16.3, 16.4, 16.5
    """
    logger.info("=" * 80)
    logger.info("DevOps Chatbot v2.0 - Starting up")
    logger.info("=" * 80)
    
    # Debug: Log all environment variables (masked for security)
    logger.info("DEBUG: Environment variables check:")
    for key in ['LLM_API_KEY', 'OPENAI_API_KEY', 'LLM_PROVIDER', 'LLM_MODEL', 'DEFAULT_REGION']:
        value = os.getenv(key)
        if value:
            masked = value[:8] + "..." if len(value) > 8 else "***"
            logger.info(f"  {key}: {masked}")
        else:
            logger.warning(f"  {key}: NOT SET")
    
    # Run startup validation
    # This will exit with code 1 if validation fails
    logger.info("DEBUG: About to call validate_startup()")
    try:
        validate_startup()
        logger.info("DEBUG: validate_startup() completed successfully")
    except SystemExit as e:
        logger.error(f"DEBUG: validate_startup() called sys.exit({e.code})")
        raise
    except Exception as e:
        logger.error(f"DEBUG: validate_startup() raised exception: {e}")
        raise
    
    logger.info("Startup complete - ready to accept requests")

    from kube_policy import init_policy

    policy = init_policy()
    logger.info("KubeApiPolicy loaded: allowRead=%s allowMutate=%s", policy.allowRead, policy.allowMutate)

    # Periodic scrub of expired credentials + session K8s clients (P1).
    async def _credential_cleanup_loop() -> None:
        from api.credentials import credential_store

        while True:
            try:
                await asyncio.sleep(60)
                removed = credential_store.cleanup_expired()
                if removed:
                    logger.info("Expired credential cleanup removed %s session(s)", removed)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Credential cleanup loop error: %s", exc)

    app.state.credential_cleanup_task = asyncio.create_task(
        _credential_cleanup_loop(), name="credential-cleanup"
    )


@app.on_event("shutdown")
async def shutdown_event():
    """
    Shutdown event handler.
    
    Performs cleanup tasks when the application shuts down.
    """
    logger.info("=" * 80)
    logger.info("DevOps Chatbot v2.0 - Shutting down")
    logger.info("=" * 80)

    task = getattr(app.state, "credential_cleanup_task", None)
    if task is not None:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # Scrub remaining sessions (credentials + K8s clients) on process exit.
    try:
        from api.credentials import credential_store
        from api.clusters import clear_session_cluster

        stats = credential_store.get_stats()
        # Remove all active sessions via store.remove (scrubs + on_session_removed).
        # Collect ids without holding lock across clear.
        with credential_store._lock:
            session_ids = list(credential_store._store.keys())
        for sid in session_ids:
            credential_store.remove(sid)
            clear_session_cluster(sid)
        logger.info(
            "Shutdown scrubbed %s session(s) (was total=%s)",
            len(session_ids),
            stats.get("total"),
        )
    except Exception as exc:
        logger.warning("Shutdown session scrub failed: %s", exc)

    logger.info("Shutdown complete")


@app.get("/{full_path:path}")
async def spa_fallback(full_path: str):
    if not STATIC_ROOT.exists():
        return Response(status_code=404)

    requested_path = (STATIC_ROOT / full_path).resolve()
    if not requested_path.is_relative_to(STATIC_ROOT_RESOLVED):
        return Response(status_code=404)

    if requested_path.is_file():
        return FileResponse(requested_path)

    index_path = STATIC_ROOT / "index.html"
    if index_path.is_file():
        return FileResponse(index_path)

    return Response(status_code=404)


if __name__ == "__main__":
    import uvicorn
    
    logger.info("Starting uvicorn server...")
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


