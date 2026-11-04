"""CLI commands against a temporary SQLite database (never the configured DATABASE_URL)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from app import cli
from app.core.config import get_settings
from tests.conftest import migrate


@pytest.fixture
def cli_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = f"sqlite+aiosqlite:///{(tmp_path / 'cli.db').as_posix()}"
    migrate(url)
    # Environment variables override .env, so the developer's real database is never touched.
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("API_KEY_PEPPER", "cli-test-pepper")
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    yield url
    get_settings.cache_clear()


def test_key_lifecycle_via_cli(cli_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["seed", "--no-demo"]) == 0
    assert "routing policy rw-2026.11-v1: recorded" in capsys.readouterr().out
    assert cli.main(["seed", "--no-demo"]) == 0
    assert "already recorded" in capsys.readouterr().out

    assert cli.main(["create-tenant", "acme", "Acme", "--rpm", "10", "--daily", "1.5"]) == 0
    assert cli.main(["create-tenant", "acme", "Again"]) == 2
    capsys.readouterr()

    assert cli.main(["create-api-key", "acme", "--json"]) == 0
    issued = json.loads(capsys.readouterr().out)
    assert issued["api_key"].startswith(issued["prefix"] + "_")

    assert cli.main(["list-api-keys", "acme"]) == 0
    listing = capsys.readouterr().out
    assert issued["prefix"] in listing and issued["api_key"] not in listing and "active" in listing

    assert cli.main(["rotate-api-key", issued["key_id"], "--json"]) == 0
    rotated = json.loads(capsys.readouterr().out)
    assert rotated["api_key"] != issued["api_key"]
    assert cli.main(["rotate-api-key", issued["key_id"]]) == 2  # old key no longer active

    assert cli.main(["revoke-api-key", rotated["key_id"]]) == 0
    assert cli.main(["revoke-api-key", "not-a-uuid"]) == 2
    assert cli.main(["create-api-key", "missing-tenant"]) == 2


def test_maintenance_commands(cli_db: str, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["reconcile"]) == 0
    assert "charged 0" in capsys.readouterr().out
    assert cli.main(["prune"]) == 0
    assert "deleted 0" in capsys.readouterr().out
