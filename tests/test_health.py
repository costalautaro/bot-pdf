from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["commit"] == "local"
    assert body["region"] == "local"


def test_docs_disabled() -> None:
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
