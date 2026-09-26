import main
from sqlalchemy import create_engine


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_ok(client):
    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_db_returns_503_when_database_unreachable(client, monkeypatch):
    unreachable = create_engine(
        "postgresql+psycopg://nobody:nopass@127.0.0.1:1/none", connect_args={"connect_timeout": 2}
    )
    monkeypatch.setattr(main, "engine", unreachable)
    response = client.get("/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}


class TestCors:
    """Phase 16: a packaged Tauri build's frontend loads from http://tauri.localhost, not
    Vite's dev-server origin - both need to work, since the same backend binary serves
    both a dev checkout and a real install."""

    def test_the_vite_dev_origin_is_allowed(self, client):
        response = client.get("/health", headers={"Origin": "http://localhost:1420"})
        assert response.headers["access-control-allow-origin"] == "http://localhost:1420"

    def test_the_packaged_tauri_origin_is_allowed(self, client):
        response = client.get("/health", headers={"Origin": "http://tauri.localhost"})
        assert response.headers["access-control-allow-origin"] == "http://tauri.localhost"

    def test_an_unrelated_origin_is_not_allowed(self, client):
        response = client.get("/health", headers={"Origin": "http://evil.example.com"})
        assert "access-control-allow-origin" not in response.headers
