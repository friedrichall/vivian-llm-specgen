"""Pydantic models for backend job state."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


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
