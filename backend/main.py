"""FastAPI application entrypoint."""

import traceback

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.api.router import api_router
from backend.schemas.vivian import ErrorResponse, HealthResponse, ServiceInfoResponse

API_V1_PREFIX = "/v1"
DEFAULT_ERROR_RESPONSES = {
    422: {
        "model": ErrorResponse,
        "description": "Request validation error",
    },
    500: {
        "model": ErrorResponse,
        "description": "Internal server error",
    },
}
load_dotenv()


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
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Return request validation failures in a stable shape."""
    payload = ErrorResponse(error="validation_error", detail=exc.errors())
    return JSONResponse(status_code=422, content=payload.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    """Return handled HTTP failures in a stable shape."""
    payload = ErrorResponse(error="http_error", detail=exc.detail)
    return JSONResponse(status_code=exc.status_code, content=payload.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Return unexpected failures without exposing raw tracebacks."""
    print("[backend] Unhandled exception:")
    traceback.print_exc()
    payload = ErrorResponse(
        error="internal_error",
        detail=f"{type(exc).__name__}: {exc}",
    )
    return JSONResponse(status_code=500, content=payload.model_dump())
