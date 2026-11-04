"""Application settings, loaded from environment variables and the repo-root `.env` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"

_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1"}
_DEV_PEPPER = "dev-only-pepper-change-me"
MIN_PROD_SECRET_CHARS = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    # Prompt/response content is never logged unless this is explicitly enabled.
    log_content: bool = False

    database_url: SecretStr = SecretStr("sqlite+aiosqlite:///./routewise-dev.db")
    db_echo: bool = False

    # Bootstrap administrator credential. Admin endpoints are disabled (fail closed) until it is
    # set; the dashboard exchanges it for a short-lived session token.
    admin_token: SecretStr | None = None
    admin_session_ttl_s: int = Field(default=8 * 3600, ge=300, le=7 * 24 * 3600)
    # Brute-force protection for POST /admin/session, per client address.
    admin_login_attempts_per_min: int = Field(default=5, ge=1, le=1000)
    # Server-side secret mixed into API-key hashes (HMAC-SHA256). Changing it invalidates every
    # existing tenant key.
    api_key_pepper: SecretStr = SecretStr(_DEV_PEPPER)
    # Avoid a DB write on every request: last_used_at is refreshed at most this often.
    api_key_touch_interval_s: int = Field(default=60, ge=0)

    # NoDecode: accept a plain comma-separated env value instead of requiring JSON.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # Paid usage is out of scope for this project. The flag exists so the intent is explicit,
    # and the validator below refuses to start if anyone turns it on.
    allow_paid_models: bool = False

    mock_provider_enabled: bool = True

    groq_enabled: bool = False
    groq_api_key: SecretStr | None = None
    # The gateway can't see which Groq plan a key is on. "free" declares the Free plan
    # ($0, per Groq's plans page), which labels Groq charges `free_tier`; anything else
    # leaves them `unavailable`.
    groq_billing_plan: Literal["free", "unknown"] = "unknown"

    openrouter_enabled: bool = False
    openrouter_api_key: SecretStr | None = None
    # Documented free-model limits (https://openrouter.ai/docs/api-reference/limits).
    openrouter_free_rpm: int = Field(default=20, ge=1)
    openrouter_free_rpd: int = Field(default=50, ge=1)

    ollama_enabled: bool = False
    ollama_base_url: str = "http://localhost:11434"

    # Execution budget for one /generate call, across all retries and fallbacks.
    request_deadline_s: float = Field(default=60.0, gt=0, le=300)
    provider_timeout_s: float = Field(default=30.0, gt=0, le=120)
    retry_backoff_base_s: float = Field(default=0.5, ge=0)
    retry_backoff_cap_s: float = Field(default=4.0, ge=0)
    circuit_failure_threshold: int = Field(default=3, ge=1)
    circuit_open_s: float = Field(default=30.0, gt=0)
    # Pending requests older than this hold no valid reservation; `app.cli reconcile` charges them.
    stale_reservation_s: int = Field(default=600, ge=60)

    model_registry_path: Path = BACKEND_ROOT / "config" / "models.yaml"
    routing_policy_path: Path = BACKEND_ROOT / "config" / "routing_policy.yaml"
    # Fetch each provider's live model list at startup (models missing from it are excluded).
    verify_model_catalog: bool = True

    @field_validator("allow_paid_models")
    @classmethod
    def _paid_models_forbidden(cls, value: bool) -> bool:
        if value:
            raise ValueError(
                "ALLOW_PAID_MODELS=true is not supported: RouteWise only uses free-tier models."
            )
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def _safety_rules(self) -> Self:
        if self.is_production:
            pepper = self.api_key_pepper.get_secret_value()
            if pepper == _DEV_PEPPER or len(pepper) < MIN_PROD_SECRET_CHARS:
                raise ValueError(
                    f"production requires API_KEY_PEPPER of {MIN_PROD_SECRET_CHARS}+ characters"
                )
            token = self.admin_token.get_secret_value() if self.admin_token else ""
            if token and len(token) < MIN_PROD_SECRET_CHARS:
                raise ValueError(
                    f"ADMIN_TOKEN must be {MIN_PROD_SECRET_CHARS}+ characters in production"
                )
            if "sqlite" in self.database_url.get_secret_value().split(":", 1)[0]:
                raise ValueError("production requires a PostgreSQL DATABASE_URL")
        if self.ollama_enabled:
            if self.is_production:
                raise ValueError("Ollama is local-only and cannot be enabled in production")
            if urlsplit(self.ollama_base_url).hostname not in _LOOPBACK_HOSTS:
                raise ValueError("OLLAMA_BASE_URL must point at localhost")
        for name, enabled, key in (
            ("GROQ", self.groq_enabled, self.groq_api_key),
            ("OPENROUTER", self.openrouter_enabled, self.openrouter_api_key),
        ):
            if enabled and not (key and key.get_secret_value().strip()):
                raise ValueError(f"{name}_ENABLED=true requires {name}_API_KEY in .env")
        return self

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
