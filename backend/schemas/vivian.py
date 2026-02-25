"""Request and response schemas for Vivian backend endpoints."""

from typing import Any, Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """Health endpoint response."""

    status: Literal["ok"] = "ok"


class ServiceInfoResponse(BaseModel):
    """Service metadata for the root endpoint."""

    name: str
    version: str
    docs_url: str
    api_prefix: str


class ErrorResponse(BaseModel):
    """Standard API error response payload."""

    error: str
    detail: Any = None
