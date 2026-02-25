"""Pydantic models for backend job state."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_core import PydanticCustomError


class JobStatus(str, Enum):
    """Finite set of lifecycle states for a backend job."""

    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class JobInfo(BaseModel):
    """In-memory representation of a single job."""

    job_id: str
    status: JobStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    log_path: str
    output_path: str | None
    error: str | None


class StartJobRequest(BaseModel):
    """Input required to start one backend pipeline job."""

    scene_json_path: str = Field(min_length=1)
    views_manifest_path: str | None = None
    scene_dir: str = Field(min_length=1)
    start_pipeline: bool = True
    only_scene_analysis: bool = False
    use_mock_scene_analysis: bool = False

    @field_validator("views_manifest_path", mode="before")
    @classmethod
    def reject_null_views_manifest_path(cls, value: Any) -> Any:
        """Reject explicit null for views_manifest_path while allowing omission."""
        if value is None:
            raise PydanticCustomError(
                "views_manifest_path_null",
                "views_manifest_path must not be null when provided.",
            )
        return value


class StartJobResponse(BaseModel):
    """Response returned immediately after accepting a job."""

    job_id: str
    status: JobStatus


class JobStatusResponse(BaseModel):
    """State response for status polling."""

    job_id: str
    status: JobStatus
    error: str | None


class JobLogsResponse(BaseModel):
    """Incremental log chunk response."""

    job_id: str
    status: JobStatus
    chunk: str
    next_offset: int


class JobResultResponse(BaseModel):
    """Final result contract for finished jobs."""

    job_id: str
    status: JobStatus
    output_path: str | None
    error: str | None


class CancelJobResponse(BaseModel):
    """Response sent after cancellation is requested."""

    job_id: str
    status: JobStatus
    message: str
