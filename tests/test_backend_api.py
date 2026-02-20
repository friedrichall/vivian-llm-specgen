from fastapi.testclient import TestClient

from backend.main import app


client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_prepare_only_endpoint_returns_none_result() -> None:
    response = client.post(
        "/v1/pipeline/prepare-only",
        json={"user_input": "ping"},
    )
    assert response.status_code == 200
    assert response.json() == {"result_type": "none", "result": None}


def test_vivian_run_supports_flagged_prepare_mode() -> None:
    response = client.post(
        "/v1/vivian/run",
        json={
            "user_input": "ping",
            "start_pipeline": False,
            "only_scene_analysis": True,
            "use_mock_scene_analysis": True,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"result_type": "none", "result": None}


def test_validation_error_shape_for_missing_user_input() -> None:
    response = client.post("/v1/vivian/run", json={})
    assert response.status_code == 422
    payload = response.json()
    assert payload["error"] == "validation_error"
    assert isinstance(payload["detail"], list)
