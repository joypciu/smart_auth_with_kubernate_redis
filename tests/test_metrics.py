from fastapi.testclient import TestClient

from app.main import app


def test_metrics_endpoint_returns_prometheus_output() -> None:
    client = TestClient(app)
    response = client.get("/metrics")

    assert response.status_code == 200
    assert "smart_auth_http_requests_total" in response.text
