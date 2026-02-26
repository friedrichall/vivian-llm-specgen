"""Single-job manager used by the REST API."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4

from fastapi import HTTPException

from backend.jobs.models import JobInfo, JobStatus

DEFAULT_JOBS_BASE_DIR = Path("./logs/backend/jobs")


class JobManager:
    """Tracks one active job and provides lookup helpers."""

    def __init__(self, base_dir: Path = DEFAULT_JOBS_BASE_DIR) -> None:
        self.base_dir = base_dir
        self.current_job: JobInfo | None = None
        self.lock = asyncio.Lock()
        self._jobs: dict[str, JobInfo] = {}
        self.active_job_id: str | None = None
        self.active_stream_result: Any | None = None
        self._cancel_requested_job_id: str | None = None

    async def start_job(self, request_data: Mapping[str, Any]) -> JobInfo:
        """Create and register a new job if no active job is running."""
        if self.lock.locked():
            raise HTTPException(status_code=409, detail="A job is already running.")

        async with self.lock:
            if self.current_job and self.current_job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                raise HTTPException(status_code=409, detail="A job is already running.")

            now = datetime.now(timezone.utc)
            job_id = uuid4().hex
            job_dir_name = f"{now.strftime('%Y%m%d-%H%M%S')}-{job_id}"
            job_dir = (self.base_dir / job_dir_name).resolve()
            job_dir.mkdir(parents=True, exist_ok=True)

            log_path = job_dir / "run.log"
            log_path.touch(exist_ok=True)

            job = JobInfo(
                job_id=job_id,
                status=JobStatus.QUEUED,
                created_at=now,
                started_at=None,
                finished_at=None,
                log_path=str(log_path),
                output_path=None,
                error=None,
            )

            self.current_job = job
            self._jobs[job_id] = job
            self.active_job_id = job_id
            self.active_stream_result = None
            self._cancel_requested_job_id = None
            self.write_meta(job=job, request_data=request_data)
            return job

    def get_job(self, job_id: str) -> JobInfo | None:
        """Return job info if known."""
        return self._jobs.get(job_id)

    def assert_job_exists(self, job_id: str) -> JobInfo:
        """Return job info or raise 404."""
        job = self.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail=f"Unknown job_id: {job_id}")
        return job

    def write_meta(self, job: JobInfo, request_data: Mapping[str, Any] | None = None) -> None:
        """Persist a small metadata snapshot for transparency/debugging."""
        meta_path = Path(job.log_path).parent / "meta.json"
        payload: dict[str, Any] = {"job": job.model_dump(mode="json")}
        if request_data is not None:
            payload["request"] = dict(request_data)
        meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def set_active_stream(self, job_id: str, stream_result: Any) -> None:
        """Register the current streamed run handle for cancellation."""
        if self.active_job_id == job_id:
            self.active_stream_result = stream_result

    def get_active_stream(self, job_id: str) -> Any | None:
        """Return active stream handle for a job if available."""
        if self.active_job_id != job_id:
            return None
        return self.active_stream_result

    def request_cancel(self, job_id: str) -> bool:
        """Mark an active job as cancellation-requested."""
        if self.active_job_id != job_id:
            return False
        self._cancel_requested_job_id = job_id
        return True

    def is_cancel_requested(self, job_id: str) -> bool:
        """Check whether cancellation was requested for a job."""
        return self._cancel_requested_job_id == job_id

    def clear_cancel_request(self, job_id: str) -> None:
        """Clear cancellation marker for job runtime cleanup."""
        if self._cancel_requested_job_id == job_id:
            self._cancel_requested_job_id = None

    def clear_active_runtime(self, job_id: str) -> None:
        """Release active runtime state once a job has reached terminal status."""
        if self.active_job_id == job_id:
            self.active_job_id = None
            self.active_stream_result = None
            self._cancel_requested_job_id = None
