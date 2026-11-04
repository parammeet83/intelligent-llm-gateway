import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_paid_models_cannot_be_enabled() -> None:
    with pytest.raises(ValidationError, match="ALLOW_PAID_MODELS"):
        Settings(_env_file=None, allow_paid_models=True)


def test_paid_models_disabled_by_default() -> None:
    assert Settings(_env_file=None).allow_paid_models is False


def test_safe_defaults() -> None:
    settings = Settings(_env_file=None)
    assert settings.log_content is False
    assert not (settings.groq_enabled or settings.openrouter_enabled or settings.ollama_enabled)


def test_cors_origins_accept_comma_separated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:5173, https://routewise.example")
    settings = Settings(_env_file=None)
    assert settings.cors_origins == ["http://localhost:5173", "https://routewise.example"]


def test_secrets_are_not_exposed_in_repr() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql://user:hunter2@host/db",
        groq_api_key="gsk_supersecretvalue123",
    )
    rendered = repr(settings) + str(settings.model_dump())
    assert "hunter2" not in rendered
    assert "gsk_supersecretvalue123" not in rendered


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({}, "API_KEY_PEPPER"),
        ({"api_key_pepper": "short"}, "API_KEY_PEPPER"),
        ({"api_key_pepper": "p" * 40, "admin_token": "too-short"}, "ADMIN_TOKEN"),
        (
            {"api_key_pepper": "p" * 40, "database_url": "sqlite+aiosqlite:///x.db"},
            "PostgreSQL",
        ),
    ],
)
def test_production_refuses_weak_configuration(overrides: dict[str, str], message: str) -> None:
    values = {"app_env": "production", "database_url": "postgresql://u:p@h/db", **overrides}
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **values)  # type: ignore[arg-type]


def test_production_accepts_strong_configuration() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        database_url="postgresql://u:p@h/db",
        api_key_pepper="p" * 40,
        admin_token="a" * 40,
    )
    assert settings.is_production
