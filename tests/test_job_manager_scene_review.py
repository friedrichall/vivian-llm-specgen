"""Tests for job-scoped scene review state in JobManager."""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.jobs.manager import JobManager
from backend.jobs.models import (
    JobPhase,
    SceneReviewDecisionRequest,
    SceneReviewPayload,
    SceneReviewState,
)


def _new_manager() -> JobManager:
    base_dir = Path("logs") / "test-job-manager-scene-review" / uuid4().hex
    base_dir.mkdir(parents=True, exist_ok=True)
    return JobManager(base_dir=base_dir)


def _start_job(manager: JobManager):
    return asyncio.run(manager.start_job({"group_path": "output_group"}))


def test_submit_and_await_scene_decision() -> None:
    """Accepted decisions should be queued and awaitable by revision."""
    manager = _new_manager()
    job = _start_job(manager)
    job.phase = JobPhase.AWAITING_SCENE_CONFIRMATION

    manager.publish_scene_review(
        job_id=job.job_id,
        payload=SceneReviewPayload(
            revision=1,
            summary="summary",
            scene_understanding={"scene_id": "SceneA"},
            updated_at=datetime.now(timezone.utc),
        ),
    )

    state = manager.submit_scene_decision(
        job_id=job.job_id,
        decision=SceneReviewDecisionRequest(
            revision=1,
            confirmed=False,
            feedback="Fix relation",
        ),
    )
    assert state == SceneReviewState.PROCESSING_FEEDBACK

    decision = asyncio.run(manager.await_scene_decision(job.job_id, expected_revision=1))
    assert decision.revision == 1
    assert decision.confirmed is False
    assert decision.feedback == "Fix relation"


def test_submit_scene_decision_rejects_revision_mismatch() -> None:
    """Submitting stale revisions should return HTTP 409."""
    manager = _new_manager()
    job = _start_job(manager)
    job.phase = JobPhase.AWAITING_SCENE_CONFIRMATION

    manager.publish_scene_review(
        job_id=job.job_id,
        payload=SceneReviewPayload(
            revision=2,
            summary="summary",
            scene_understanding={"scene_id": "SceneA"},
            updated_at=datetime.now(timezone.utc),
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        manager.submit_scene_decision(
            job_id=job.job_id,
            decision=SceneReviewDecisionRequest(
                revision=1,
                confirmed=True,
                feedback=None,
            ),
        )

    assert exc_info.value.status_code == 409


def test_clear_active_runtime_removes_scene_review_state() -> None:
    """Runtime cleanup should remove review payload/state/queue for the job."""
    manager = _new_manager()
    job = _start_job(manager)
    job.phase = JobPhase.AWAITING_SCENE_CONFIRMATION

    manager.publish_scene_review(
        job_id=job.job_id,
        payload=SceneReviewPayload(
            revision=1,
            summary="summary",
            scene_understanding={"scene_id": "SceneA"},
            updated_at=datetime.now(timezone.utc),
        ),
    )

    manager.clear_active_runtime(job.job_id)
    review_payload, review_state = manager.get_scene_review(job.job_id)
    assert review_payload is None
    assert review_state is None
