"""JSON structured logging with secret redaction.

Two layers of protection:
1. Fields whose *name* looks sensitive (authorization, api_key, password, ...) are replaced.
2. Values that *look* like credentials (provider keys, RouteWise keys, bearer tokens,
   connection strings with passwords) are masked wherever they appear in a message.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

REDACTED = "[REDACTED]"

_SENSITIVE_FIELD = re.compile(
    r"(authorization|api[_-]?key|password|passwd|secret|token|pepper|database_url|cookie)",
    re.IGNORECASE,
)

# Content fields are dropped unless LOG_CONTENT is enabled.
CONTENT_FIELDS = frozenset({"prompt", "messages", "content", "completion", "response_text"})

_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bgsk_[A-Za-z0-9]{8,}"),  # Groq
    re.compile(r"\bsk-or-[A-Za-z0-9-]{8,}"),  # OpenRouter
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),  # generic OpenAI-style
    re.compile(r"\brw_[a-z0-9]{8}_[A-Za-z0-9_-]{16,}"),  # RouteWise tenant keys
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"(?i)(postgres(?:ql)?(?:\+\w+)?://[^:/\s]+:)[^@\s]+(@)"),  # URL password
)


def redact_text(text: str) -> str:
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 2:
            text = pattern.sub(rf"\1{REDACTED}\2", text)
        else:
            text = pattern.sub(REDACTED, text)
    return text


def redact_value(key: str, value: Any, *, log_content: bool) -> Any:
    if _SENSITIVE_FIELD.search(key):
        return REDACTED
    if key in CONTENT_FIELDS and not log_content:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {k: redact_value(str(k), v, log_content=log_content) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact_value(key, v, log_content=log_content) for v in value]
    return value


_RESERVED_ATTRS = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"}
)


class JsonFormatter(logging.Formatter):
    def __init__(self, *, log_content: bool = False) -> None:
        super().__init__()
        self.log_content = log_content

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED_ATTRS and not key.startswith("_"):
                payload[key] = redact_value(key, value, log_content=self.log_content)
        if record.exc_info:
            payload["exc"] = redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", *, log_content: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(log_content=log_content))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # httpx logs full request URLs at INFO; keep it quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
