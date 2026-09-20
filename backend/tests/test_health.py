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
