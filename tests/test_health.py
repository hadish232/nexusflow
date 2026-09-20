from fastapi.testclient import TestClient

from nexusflow.main import app


client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200

    data = response.json()

    assert data["name"] == "NexusFlow"
    assert data["version"] == "0.2.0"
    assert data["status"] == "running"


def test_liveness() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200

    assert response.json() == {
        "status": "alive",
    }


def test_request_id() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200

    assert "X-Request-ID" in response.headers

    assert "X-Process-Time" in response.headers


def test_custom_request_id() -> None:
    request_id = "integration-test-001"

    response = client.get(
        "/api/v1/health/live",
        headers={
            "X-Request-ID": request_id,
        },
    )

    assert response.status_code == 200

    assert response.headers["X-Request-ID"] == request_id
