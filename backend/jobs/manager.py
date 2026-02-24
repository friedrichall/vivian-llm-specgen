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

    async def start_job(self, request_data: Mapping[str, Any]) -> JobInfo:
        """Create and register a new job if no active job is running."""
        if self.lock.locked():
            raise HTTPException(status_code=409, detail="A job is already running.")

        async with self.lock:
            if self.current_job and self.current_job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
                raise HTTPException(status_code=409, detail="A job is already running.")

            job_id = uuid4().hex
            job_dir = (self.base_dir / job_id).resolve()
            job_dir.mkdir(parents=True, exist_ok=True)

            log_path = job_dir / "run.log"
            log_path.touch(exist_ok=True)

            now = datetime.now(timezone.utc)
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
