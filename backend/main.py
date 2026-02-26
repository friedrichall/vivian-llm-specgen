"""FastAPI application entrypoint."""

import json
import logging
import traceback
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.router import api_router
from backend.schemas.vivian import ErrorResponse, HealthResponse, ServiceInfoResponse

API_V1_PREFIX = "/v1"
DEFAULT_ERROR_RESPONSES = {
    422: {
        "model-v1": ErrorResponse,
        "description": "Request validation error",
    },
    500: {
        "model-v1": ErrorResponse,
        "description": "Internal server error",
    },
}
load_dotenv()
logger = logging.getLogger("backend.api")


def _truncate(value: str, max_len: int = 4000) -> str:
    """Limit log payload size to keep console output readable."""
    if len(value) <= max_len:
        return value
    return f"{value[:max_len]}... <truncated {len(value) - max_len} chars>"


def _safe_json_dumps(value: Any) -> str:
    """Serialize values for logs with a resilient fallback."""
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return repr(value)


async def _request_body_for_log(request: Request) -> str:
    """Read request body once for diagnostics; never raise from logging helper."""
    try:
        body = await request.body()
    except Exception as exc:  # pragma: no cover - defensive logging
        return f"<failed to read body: {type(exc).__name__}: {exc}>"
    if not body:
        return "<empty>"
    return _truncate(body.decode("utf-8", errors="replace"))


def _format_validation_errors(errors: list[dict[str, Any]]) -> str:
    """Render validation errors in a concise, human-readable form."""
    lines: list[str] = []
    for idx, err in enumerate(errors, start=1):
        loc = ".".join(str(part) for part in err.get("loc", ()))
        msg = err.get("msg", "validation error")
        err_type = err.get("type", "unknown")
        raw_input = _safe_json_dumps(err.get("input"))
        lines.append(
            f"{idx}. loc={loc or '<root>'} type={err_type} msg={msg} input={_truncate(raw_input, 400)}"
        )
    return "\n".join(lines) if lines else "<no details>"


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Vivian LLM Spec Generator Backend",
        version="0.1.0",
        description=(
            "Backend API for scene analysis and functional specification "
            "generation using the Vivian multi-agent pipeline."
        ),
        responses=DEFAULT_ERROR_RESPONSES,
    )
    app.include_router(api_router, prefix=API_V1_PREFIX)
    return app


app = create_app()


@app.get("/", response_model=ServiceInfoResponse, tags=["system"])
async def root() -> ServiceInfoResponse:
    """Return high-level service metadata."""
    return ServiceInfoResponse(
        name=app.title,
        version=app.version,
        docs_url="/docs",
        api_prefix=API_V1_PREFIX,
    )


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """Return service health status."""
    return HealthResponse()


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return request validation failures in a stable shape."""
    body_for_log = await _request_body_for_log(request)
    details = exc.errors()
    logger.warning(
        "422 validation error\nmethod=%s path=%s query=%s\nbody=%s\nerrors:\n%s",
        request.method,
        request.url.path,
        _safe_json_dumps(dict(request.query_params)),
        body_for_log,
        _format_validation_errors(details),
    )
    payload = ErrorResponse(error="validation_error", detail=exc.errors())
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Return handled HTTP failures in a stable shape."""
    if exc.status_code >= 500:
        logger.error(
            "HTTPException %s at %s %s detail=%s",
            exc.status_code,
            request.method,
            request.url.path,
            _safe_json_dumps(exc.detail),
        )
    elif exc.status_code >= 400:
        logger.warning(
            "HTTPException %s at %s %s detail=%s",
            exc.status_code,
            request.method,
            request.url.path,
            _safe_json_dumps(exc.detail),
        )
    payload = ErrorResponse(error="http_error", detail=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return unexpected failures without exposing raw tracebacks."""
    logger.error(
        "Unhandled exception at %s %s: %s: %s",
        request.method,
        request.url.path,
        type(exc).__name__,
        exc,
    )
    traceback.print_exc()
    payload = ErrorResponse(
        error="internal_error",
        detail=f"{type(exc).__name__}: {exc}",
    )
    return JSONResponse(status_code=500, content=payload.model_dump())
