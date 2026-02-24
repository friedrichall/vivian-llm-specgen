from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api.router import job_manager
from backend.jobs.models import JobStatus
from backend.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def _reset_job_manager_state() -> None:
    job_manager.current_job = None
    job_manager._jobs.clear()  # pylint: disable=protected-access


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_start_poll_logs_and_result(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    response = client.post(
        "/v1/jobs/start",
        json={"scene_json_path": "scene.json"},
    )
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
    async def fake_run_job(job, request_data, manager) -> None:
        _ = (job, request_data, manager)
        return None

    monkeypatch.setattr("backend.api.router.run_job", fake_run_job)

    first = client.post("/v1/jobs/start", json={"scene_json_path": "scene.json"})
    assert first.status_code == 202
    first_job_id = first.json()["job_id"]

    second = client.post("/v1/jobs/start", json={"scene_json_path": "scene.json"})
    assert second.status_code == 409
    job_manager.assert_job_exists(first_job_id).status = JobStatus.SUCCEEDED


def test_unknown_job_returns_404() -> None:
    response = client.get("/v1/jobs/does-not-exist/status")
    assert response.status_code == 404
