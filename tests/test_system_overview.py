from fastapi.testclient import TestClient

from app.main import app


def test_system_overview_returns_dashboard_payload() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/system/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["service"]["status"] == "healthy"
    assert "traffic" in body
    assert "links" in body