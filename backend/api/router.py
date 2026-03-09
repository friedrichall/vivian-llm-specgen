"""Top-level API router and job endpoints."""

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

from backend.jobs.manager import JobManager
from backend.jobs.models import (
    CancelJobResponse,
    JobLogsResponse,
    JobPhase,
    JobResultResponse,
    SceneReviewDecisionRequest,
    SceneReviewDecisionResponse,
    SceneReviewResponse,
    JobStatus,
    JobStatusResponse,
    StartJobRequest,
    StartJobResponse,
)
from backend.jobs.runner import run_job
from vivian_pipeline.context import SceneReviewDecision
from vivian_pipeline.pipeline_orchestrator import PipelineConfig, run_pipeline

MAX_LOG_CHUNK_BYTES = 64 * 1024

api_router = APIRouter()
job_manager = JobManager()
LOGGER_NAME = "backend.api.router"
LOGGER = logging.getLogger(LOGGER_NAME)


def _ensure_console_logging(logger_name: str) -> None:
    """Enable INFO logging via root logger so child loggers are visible."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    if root_logger.handlers:
        return

    handler = logging.StreamHandler()
    handler.setLevel(logging.INFO)
    root_logger.addHandler(handler)

_ensure_console_logging(LOGGER_NAME)

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
    LOGGER.info("POST /jobs/start")
    request_data = request.model_dump()
    job = await job_manager.start_job(request_data=request_data)
    task = asyncio.create_task(run_job(job=job, request_data=request_data, manager=job_manager))
    job_manager.set_active_task(job.job_id, task)
    return StartJobResponse(job_id=job.job_id, status=job.status)


@api_router.get("/jobs/{job_id}/status", response_model=JobStatusResponse, tags=["jobs"])
def get_job_status(job_id: str) -> JobStatusResponse:
    """Return current status for one job."""
    LOGGER.info("GET /jobs/%s/status", job_id)
    job = job_manager.assert_job_exists(job_id)
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        phase=job.phase,
        error=job.error,
    )


@api_router.get("/jobs/{job_id}/scene-review", response_model=SceneReviewResponse, tags=["jobs"])
def get_scene_review(job_id: str) -> SceneReviewResponse:
    """Return current scene-review payload/state for a job."""
    LOGGER.info("GET /jobs/%s/scene-review", job_id)
    job = job_manager.assert_job_exists(job_id)
    scene_review, review_state = job_manager.get_scene_review(job_id)
    return SceneReviewResponse(
        job_id=job.job_id,
        status=job.status,
        phase=job.phase,
        review_state=review_state,
        scene_review=scene_review,
        error=job.error,
    )


@api_router.post(
    "/jobs/{job_id}/scene-review",
    response_model=SceneReviewDecisionResponse,
    tags=["jobs"],
)
def submit_scene_review_decision(
    job_id: str,
    request: SceneReviewDecisionRequest,
) -> SceneReviewDecisionResponse:
    """Submit one scene-review decision for the current revision."""
    LOGGER.info("POST /jobs/%s/scene-review confirmed=%s", job_id, request.confirmed)
    job = job_manager.assert_job_exists(job_id)
    review_state = job_manager.submit_scene_decision(job_id, request)
    if request.confirmed:
        job.phase = JobPhase.PLANNING_INTERACTIONS
    job_manager.write_meta(job=job)
    return SceneReviewDecisionResponse(
        job_id=job.job_id,
        status=job.status,
        phase=job.phase,
        review_state=review_state,
        accepted_revision=request.revision,
        message="Scene review decision accepted.",
    )


@api_router.get("/jobs/{job_id}/logs", response_model=JobLogsResponse, tags=["jobs"])
def get_job_logs(
    job_id: str,
    offset: int = Query(default=0, ge=0),
    max_bytes: int = Query(default=MAX_LOG_CHUNK_BYTES, ge=1, le=MAX_LOG_CHUNK_BYTES),
) -> JobLogsResponse:
    """Return new log text since the provided byte offset."""
    LOGGER.info("GET /jobs/%s/logs offset=%d max_bytes=%d", job_id, offset, max_bytes)
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
    LOGGER.info("GET /jobs/%s/result", job_id)
    job = job_manager.assert_job_exists(job_id)
    if job.status in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Job is still running.")
    return JobResultResponse(
        job_id=job.job_id,
        status=job.status,
        success=(job.status == JobStatus.SUCCEEDED),
        successful_attempt=job.successful_attempt,
        output_path=job.output_path,
        error=job.error,
    )


@api_router.post("/jobs/{job_id}/cancel", response_model=CancelJobResponse, status_code=202, tags=["jobs"])
async def cancel_job(job_id: str) -> CancelJobResponse:
    """Cancel one active job via the streamed run handle."""
    LOGGER.info("POST /jobs/%s/cancel", job_id)
    job = job_manager.assert_job_exists(job_id)
    if job.status not in {JobStatus.QUEUED, JobStatus.RUNNING}:
        raise HTTPException(status_code=409, detail="Job is not active.")
    if not job_manager.request_cancel(job_id):
        raise HTTPException(status_code=409, detail="Only the active job can be cancelled.")

    job_manager.cancel_active_task(job_id)

    return CancelJobResponse(
        job_id=job.job_id,
        status=job.status,
        message="Cancellation requested.",
    )


@api_router.post("/orchestrator/test", tags=["debug"])
def run_orchestrator_test(
    max_attempts: int = Query(default=1, ge=1),
) -> dict[str, str | int | bool]:
    """Run the pipeline orchestrator directly for debugging."""
    LOGGER.info("POST /orchestrator/test max_attempts=%d", max_attempts)
    run_id = f"debug-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    def _publish_scene_review(revision: int, summary: str, scene_understanding: dict[str, object]) -> None:
        LOGGER.info(
            "orchestrator/test review published revision=%d summary_len=%d payload_keys=%d",
            revision,
            len(summary),
            len(scene_understanding),
        )

    async def _auto_confirm(revision: int) -> SceneReviewDecision:
        return SceneReviewDecision(revision=revision, confirmed=True, feedback=None)

    config = PipelineConfig.default(
        run_id=run_id,
        max_attempts=max_attempts,
        publish_scene_review=_publish_scene_review,
        await_scene_decision=_auto_confirm,
    )
    result = run_pipeline(config)
    return {
        "run_id": run_id,
        "success": result.success,
        "max_attempts": result.max_attempts,
        "attempts_completed": result.attempts_completed,
    }
