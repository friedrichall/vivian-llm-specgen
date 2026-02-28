"""Tests for backend job API endpoints."""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.router import job_manager
from backend.jobs.models import (
    JobPhase,
    JobStatus,
    SceneReviewPayload,
)
from backend.main import app

client = TestClient(app)
START_JOB_BASE = {"group_path": "output_group"}


@pytest.fixture(autouse=True)
def _reset_job_manager_state() -> None:
    """Reset shared in-memory manager state between tests."""
    job_manager.current_job = None
    job_manager._jobs.clear()  # pylint: disable=protected-access
    job_manager.active_job_id = None
    job_manager.active_stream_result = None
    job_manager._cancel_requested_job_id = None  # pylint: disable=protected-access
    job_manager._scene_reviews.clear()  # pylint: disable=protected-access
    job_manager._scene_review_states.clear()  # pylint: disable=protected-access
    job_manager._scene_review_queues.clear()  # pylint: disable=protected-access


def test_health_endpoint() -> None:
    """Health endpoint should return a stable OK payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_start_poll_logs_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start, poll logs, and read result for one job lifecycle."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "QUEUED"
    job_id = payload["job_id"]

    response = client.get(f"/v1/jobs/{job_id}/result")
    assert response.status_code == 409

    job = job_manager.assert_job_exists(job_id)
    Path(job.log_path).write_text("line-1\nline-2\n", encoding="utf-8")
    job.status = JobStatus.SUCCEEDED
    job.started_at = datetime.now(timezone.utc)
    job.finished_at = datetime.now(timezone.utc)
    job.output_path = str(Path("generated_specs/Fake/FunctionalSpecification").resolve())
    job.error = None

    status = client.get(f"/v1/jobs/{job_id}/status")
    assert status.status_code == 200
    assert status.json()["status"] == "SUCCEEDED"
    assert status.json()["phase"] == "QUEUED"

    logs_first = client.get(f"/v1/jobs/{job_id}/logs", params={"offset": 0, "max_bytes": 5})
    assert logs_first.status_code == 200
    first_payload = logs_first.json()
    assert first_payload["status"] in {"RUNNING", "SUCCEEDED"}
    assert first_payload["chunk"] != ""

    logs_second = client.get(
        f"/v1/jobs/{job_id}/logs",
        params={"offset": first_payload["next_offset"], "max_bytes": 65536},
    )
    assert logs_second.status_code == 200
    second_payload = logs_second.json()
    assert second_payload["next_offset"] >= first_payload["next_offset"]

    result = client.get(f"/v1/jobs/{job_id}/result")
    assert result.status_code == 200
    result_payload = result.json()
    assert result_payload["status"] == "SUCCEEDED"
    assert result_payload["output_path"] is not None
    assert result_payload["error"] is None


def test_start_rejects_second_job_while_active(monkeypatch: pytest.MonkeyPatch) -> None:
    """A second start request should be rejected while one job is active."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    first = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert first.status_code == 202
    first_job_id = first.json()["job_id"]

    second = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert second.status_code == 409
    job_manager.assert_job_exists(first_job_id).status = JobStatus.SUCCEEDED


def test_unknown_job_returns_404() -> None:
    """Unknown job IDs should return 404."""
    response = client.get("/v1/jobs/does-not-exist/status")
    assert response.status_code == 404


def test_cancel_endpoint_accepts_active_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancel endpoint should cancel the active stream result."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    first = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert first.status_code == 202
    job_id = first.json()["job_id"]

    cancelled = {"called": False}

    class FakeStreamResult:
        def cancel(self, mode: str = "immediate") -> None:
            assert mode == "immediate"
            cancelled["called"] = True

    job = job_manager.assert_job_exists(job_id)
    job.status = JobStatus.RUNNING
    job_manager.active_job_id = job_id
    job_manager.active_stream_result = FakeStreamResult()

    cancel = client.post(f"/v1/jobs/{job_id}/cancel")
    assert cancel.status_code == 202
    payload = cancel.json()
    assert payload["job_id"] == job_id
    assert payload["status"] == "RUNNING"
    assert cancelled["called"] is True


def test_can_start_new_job_after_cancelled_job(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new job should be startable after cancellation cleanup."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    first = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert first.status_code == 202
    first_job_id = first.json()["job_id"]

    class FakeStreamResult:
        def cancel(self, mode: str = "immediate") -> None:
            assert mode == "immediate"

    first_job = job_manager.assert_job_exists(first_job_id)
    first_job.status = JobStatus.RUNNING
    job_manager.active_job_id = first_job_id
    job_manager.active_stream_result = FakeStreamResult()

    cancel = client.post(f"/v1/jobs/{first_job_id}/cancel")
    assert cancel.status_code == 202

    first_job.status = JobStatus.CANCELLED
    first_job.finished_at = datetime.now(timezone.utc)
    first_job.error = "Cancelled by user."
    job_manager.clear_active_runtime(first_job_id)

    second = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert second.status_code == 202


def test_start_job_request_uses_flag_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defaults should be persisted for omitted optional flags."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = job_manager.assert_job_exists(job_id)

    meta_path = Path(job.log_path).parent / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    request = meta["request"]

    assert request["start_pipeline"] is True
    assert request["only_scene_analysis"] is False
    assert request["use_mock_scene_analysis"] is False
    assert "extra" not in request


def test_start_job_request_accepts_explicit_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit flag values should be persisted unchanged."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    response = client.post(
        "/v1/jobs/start",
        json={
            **START_JOB_BASE,
            "start_pipeline": False,
            "only_scene_analysis": True,
            "use_mock_scene_analysis": True,
        },
    )
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    job = job_manager.assert_job_exists(job_id)

    meta_path = Path(job.log_path).parent / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    request = meta["request"]

    assert request["start_pipeline"] is False
    assert request["only_scene_analysis"] is True
    assert request["use_mock_scene_analysis"] is True


def test_start_job_rejects_missing_group_path() -> None:
    """group_path is required and must be provided explicitly."""
    response = client.post(
        "/v1/jobs/start",
        json={},
    )
    assert response.status_code == 422


def test_start_job_rejects_blank_group_path() -> None:
    """group_path must not be blank."""
    response = client.post(
        "/v1/jobs/start",
        json={"group_path": "   "},
    )
    assert response.status_code == 422


def test_start_job_rejects_legacy_redundant_fields() -> None:
    """Legacy redundant path fields should be rejected."""
    response = client.post(
        "/v1/jobs/start",
        json={
            "group_path": "output_group",
            "scene_json_path": "scene.json",
            "views_manifest_path": "views_manifest.json",
        },
    )
    assert response.status_code == 422


def test_start_job_uses_datetime_prefixed_job_directory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Job artifact directory should be <date-time-jobId>."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job = job_manager.assert_job_exists(job_id)
    job_dir_name = Path(job.log_path).parent.name
    assert job_dir_name.endswith(f"-{job_id}")
    assert re.match(r"^\d{8}-\d{6}-[0-9a-f]{32}$", job_dir_name) is not None


def test_get_scene_review_without_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scene-review endpoint should return null payload before publication."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)
    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    review = client.get(f"/v1/jobs/{job_id}/scene-review")
    assert review.status_code == 200
    payload = review.json()
    assert payload["phase"] == "QUEUED"
    assert payload["review_state"] is None
    assert payload["scene_review"] is None


def test_submit_scene_review_rejects_wrong_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    """Decision submission should fail when job is not awaiting confirmation."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)
    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    submit = client.post(
        f"/v1/jobs/{job_id}/scene-review",
        json={"revision": 1, "confirmed": False, "feedback": "adjust mapping"},
    )
    assert submit.status_code == 409


def test_scene_review_flow_accepts_feedback_and_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scene-review API should accept feedback rounds and final confirmation."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)
    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job = job_manager.assert_job_exists(job_id)
    job.status = JobStatus.RUNNING
    job.phase = JobPhase.AWAITING_SCENE_CONFIRMATION
    job_manager.publish_scene_review(
        job_id=job_id,
        payload=SceneReviewPayload(
            revision=1,
            summary="Scene summary v1",
            scene_understanding={"scene_id": "Demo", "objects": []},
            updated_at=datetime.now(timezone.utc),
        ),
    )

    review = client.get(f"/v1/jobs/{job_id}/scene-review")
    assert review.status_code == 200
    review_payload = review.json()
    assert review_payload["review_state"] == "PENDING"
    assert review_payload["scene_review"]["revision"] == 1

    feedback = client.post(
        f"/v1/jobs/{job_id}/scene-review",
        json={
            "revision": 1,
            "confirmed": False,
            "feedback": "ButtonA controls LightB",
        },
    )
    assert feedback.status_code == 200
    feedback_payload = feedback.json()
    assert feedback_payload["review_state"] == "PROCESSING_FEEDBACK"
    assert feedback_payload["phase"] == "AWAITING_SCENE_CONFIRMATION"

    job_manager.publish_scene_review(
        job_id=job_id,
        payload=SceneReviewPayload(
            revision=2,
            summary="Scene summary v2",
            scene_understanding={"scene_id": "Demo", "objects": []},
            updated_at=datetime.now(timezone.utc),
        ),
    )
    job.phase = JobPhase.AWAITING_SCENE_CONFIRMATION

    confirm = client.post(
        f"/v1/jobs/{job_id}/scene-review",
        json={"revision": 2, "confirmed": True, "feedback": None},
    )
    assert confirm.status_code == 200
    confirm_payload = confirm.json()
    assert confirm_payload["review_state"] == "CONFIRMED"
    assert confirm_payload["phase"] == "GENERATING_SPECS"


def test_scene_review_rejects_revision_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Submission should fail when revision does not match current payload."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)
    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    job = job_manager.assert_job_exists(job_id)
    job.status = JobStatus.RUNNING
    job.phase = JobPhase.AWAITING_SCENE_CONFIRMATION
    job_manager.publish_scene_review(
        job_id=job_id,
        payload=SceneReviewPayload(
            revision=3,
            summary="Scene summary",
            scene_understanding={"scene_id": "Demo"},
            updated_at=datetime.now(timezone.utc),
        ),
    )

    submit = client.post(
        f"/v1/jobs/{job_id}/scene-review",
        json={"revision": 2, "confirmed": False, "feedback": "fix relation"},
    )
    assert submit.status_code == 409


def test_scene_review_rejects_empty_feedback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Validation should reject non-confirm decisions without feedback."""
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)
    response = client.post("/v1/jobs/start", json=START_JOB_BASE)
    assert response.status_code == 202
    job_id = response.json()["job_id"]

    submit = client.post(
        f"/v1/jobs/{job_id}/scene-review",
        json={"revision": 1, "confirmed": False, "feedback": "   "},
    )
    assert submit.status_code == 422
