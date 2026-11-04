from pathlib import Path

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings


def test_health_reports_simulated_only(database_url: str) -> None:
    with TestClient(create_app(make_settings(database_url))) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["providers"] == ["mock"]
    assert body["simulated_only"] is True
    assert response.headers["X-Request-ID"]


def test_ready_when_database_migrated(database_url: str) -> None:
    with TestClient(create_app(make_settings(database_url))) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "migrations": "ok"},
    }


def test_not_ready_when_schema_missing(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'empty.db').as_posix()}"
    with TestClient(create_app(make_settings(url))) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"


def test_not_ready_response_leaks_no_connection_details() -> None:
    url = "postgresql://owner:hunter2@127.0.0.1:1/neondb?sslmode=disable"
    with TestClient(create_app(make_settings(url))) as client:
        response = client.get("/api/v1/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"
    for secret in ("hunter2", "owner", "127.0.0.1"):
        assert secret not in response.text


def test_unknown_route_uses_error_envelope(tmp_path: Path) -> None:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'x.db').as_posix()}"
    with TestClient(create_app(make_settings(url))) as client:
        response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "NOT_FOUND"
    assert error["request_id"] == response.headers["X-Request-ID"]


def test_docs_disabled_in_production() -> None:
    # Production refuses SQLite and weak secrets; the engine is lazy, so no DB is contacted.
    settings = make_settings(
        "postgresql://u:p@127.0.0.1:1/db",
        app_env="production",
        api_key_pepper="p" * 40,
        admin_token="a" * 40,
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/docs").status_code == 404
