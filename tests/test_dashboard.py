from fastapi.testclient import TestClient

from app.main import app


def test_dashboard_root_returns_html() -> None:
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Smart Auth Control Room" in response.text
