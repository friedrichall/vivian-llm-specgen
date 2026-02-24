"""Top-level API router and job endpoints."""

import asyncio
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.jobs.manager import JobManager
from backend.jobs.models import JobStatus
from backend.jobs.runner import run_job

MAX_LOG_CHUNK_BYTES = 64 * 1024


class StartJobRequest(BaseModel):
    """Input required to start one backend pipeline job."""

    scene_json_path: str = Field(min_length=1)
    views_manifest_path: str | None = None
    scene_dir: str | None = None
    extra: dict[str, Any] | None = None


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


api_router = APIRouter()
job_manager = JobManager()


def _read_log_chunk(log_path: Path, offset: int, max_bytes: int) -> tuple[str, int]:
    """Read one UTF-8 text chunk from a byte offset."""
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset must be >= 0")
    if max_bytes <= 0:
        raise HTTPException(status_code=400, detail="max_bytes must be > 0")

    if not log_path.exists():
        return "", 0

    file_size = log_path.stat().st_size
    safe_offset = min(offset, file_size)

    with log_path.open("rb") as handle:
        handle.seek(safe_offset)
        data = handle.read(max_bytes)
        next_offset = handle.tell()

    return data.decode("utf-8", errors="replace"), next_offset


@api_router.post("/jobs/start", response_model=StartJobResponse, status_code=202, tags=["jobs"])
async def start_job(request: StartJobRequest) -> StartJobResponse:
    """Create a job and schedule pipeline execution in the background."""
    request_data = request.model_dump()
    job = await job_manager.start_job(request_data=request_data)
    asyncio.create_task(run_job(job=job, request_data=request_data, manager=job_manager))
    return StartJobResponse(job_id=job.job_id, status=job.status)


@api_router.get("/jobs/{job_id}/status", response_model=JobStatusResponse, tags=["jobs"])
def get_job_status(job_id: str) -> JobStatusResponse:
    """Return current status for one job."""
    job = job_manager.assert_job_exists(job_id)
    return JobStatusResponse(job_id=job.job_id, status=job.status, error=job.error)


@api_router.get("/jobs/{job_id}/logs", response_model=JobLogsResponse, tags=["jobs"])
def get_job_logs(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    max_bytes: int = Query(default=MAX_LOG_CHUNK_BYTES, ge=1, le=MAX_LOG_CHUNK_BYTES),
) -> JobLogsResponse:
    """Return new log text since the provided byte offset."""
    job = job_manager.assert_job_exists(job_id)
    chunk, next_offset = _read_log_chunk(Path(job.log_path), offset=offset, max_bytes=max_bytes)
    return JobLogsResponse(
        job_id=job.job_id,
        status=job.status,
        chunk=chunk,
        next_offset=next_offset,
    )


@api_router.get("/jobs/{job_id}/result", response_model=JobResultResponse, tags=["jobs"])
def get_job_result(job_id: str) -> JobResultResponse:
    """Return final output path for finished jobs."""
    job = job_manager.assert_job_exists(job_id)
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Job is still running.")
    return JobResultResponse(
        job_id=job.job_id,
        status=job.status,
        output_path=job.output_path,
        error=job.error,
    )


@api_router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse, status_code=202, tags=["jobs"])
async def cancel_job(job_id: str) -> CancelJobResponse:
    """Cancel one active job via the streamed run handle."""
    job = job_manager.assert_job_exists(job_id)
    if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Job is not active.")
    if not job_manager.request_cancel(job_id):
        raise HTTPException(status_code=409, detail="Only the active job can be cancelled.")

    stream_result = job_manager.get_active_stream(job_id)
    if stream_result is not None:
        stream_result.cancel(mode="immediate")

    return CancelJobResponse(
        job_id=job.job_id,
        status=job.status,
        message="Cancellation requested.",
    )
