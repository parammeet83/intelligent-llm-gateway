import json
import logging

import pytest

from app.core.logging import REDACTED, JsonFormatter, redact_text


@pytest.mark.parametrize(
    "secret",
    [
        "gsk_abcdefghijklmnop1234",
        "sk-or-v1-abcdef1234567890",
        "sk-proj-abcdefghijklmnopqrstu",
        "rw_k3j9x2ab_AbCdEfGhIjKlMnOpQrStUvWxYz012345",
        "Bearer eyJhbGciOiJIUzI1NiJ9.payload.sig",
    ],
)
def test_credential_patterns_are_masked(secret: str) -> None:
    out = redact_text(f"calling provider with {secret} now")
    assert secret not in out
    assert REDACTED in out


def test_connection_string_password_is_masked_but_host_kept() -> None:
    out = redact_text("connect postgresql://neondb_owner:s3cr3tP@ss@ep-x.neon.tech/neondb failed")
    assert "s3cr3tP" not in out
    assert "ep-x.neon.tech" in out


def _format(record_extra: dict[str, object], *, log_content: bool = False) -> dict[str, object]:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
    for key, value in record_extra.items():
        setattr(record, key, value)
    parsed: dict[str, object] = json.loads(JsonFormatter(log_content=log_content).format(record))
    return parsed


def test_sensitive_field_names_are_redacted() -> None:
    out = _format({"authorization": "anything", "api_key": "x", "nested": {"password": "p"}})
    assert out["authorization"] == REDACTED
    assert out["api_key"] == REDACTED
    assert out["nested"] == {"password": REDACTED}


def test_content_fields_dropped_by_default() -> None:
    out = _format({"prompt": "my private medical question", "tenant": "acme"})
    assert out["prompt"] == REDACTED
    assert out["tenant"] == "acme"


def test_content_fields_logged_only_when_enabled() -> None:
    out = _format({"prompt": "hello"}, log_content=True)
    assert out["prompt"] == "hello"


def test_exception_text_is_redacted() -> None:
    try:
        raise RuntimeError("auth failed for gsk_abcdefghijklmnop1234")
    except RuntimeError:
        import sys

        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    rendered = JsonFormatter().format(record)
    assert "gsk_abcdefghijklmnop1234" not in rendered
