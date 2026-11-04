"""Shared HTTP logic for providers that speak the OpenAI chat-completions dialect.

Normalisation contract (every adapter, every outcome):
- Success  -> ProviderResponse with non-empty `content`, ints-or-None usage, latency in ms.
- Failure  -> ProviderError with a classified `kind`. Never a raw httpx/JSON exception.
- Messages from providers are truncated and passed through secret redaction; response bodies,
  prompts and request headers are never copied into errors or logs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime
from time import monotonic, perf_counter
from typing import Any, ClassVar

import httpx

from app.core.logging import redact_text
from app.providers.base import (
    Provider,
    ProviderError,
    ProviderErrorKind,
    ProviderRequest,
    ProviderResponse,
    ProviderUsage,
    RateLimitState,
)

logger = logging.getLogger(__name__)

_MAX_ERROR_MESSAGE = 200

DEFAULT_STATUS_MAP: dict[int, ProviderErrorKind] = {
    400: ProviderErrorKind.BAD_REQUEST,
    401: ProviderErrorKind.AUTH,
    403: ProviderErrorKind.AUTH,
    404: ProviderErrorKind.MODEL_NOT_FOUND,
    408: ProviderErrorKind.TIMEOUT,
    413: ProviderErrorKind.BAD_REQUEST,
    422: ProviderErrorKind.BAD_REQUEST,
    429: ProviderErrorKind.RATE_LIMITED,
}


def parse_retry_after(value: str | None, *, now: datetime | None = None) -> float | None:
    """Retry-After is either delta-seconds or an HTTP date (RFC 9110 §10.2.3)."""
    if not value:
        return None
    value = value.strip()
    try:
        seconds = float(value)
    except ValueError:
        try:
            when = parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=UTC)
        seconds = (when - (now or datetime.now(UTC))).total_seconds()
    return max(0.0, seconds)


_DURATION_PART = re.compile(r"(\d+(?:\.\d+)?)(ms|h|m|s)")


def parse_duration_s(value: str | None) -> float | None:
    """Groq-style durations such as "1m26.4s", "7.66s", "120ms", "2h"."""
    if not value:
        return None
    text = value.strip()
    parts = _DURATION_PART.findall(text)
    if not parts or "".join(n + u for n, u in parts) != text:
        try:
            return max(0.0, float(text))
        except ValueError:
            return None
    scale = {"h": 3600.0, "m": 60.0, "s": 1.0, "ms": 0.001}
    return sum(float(n) * scale[u] for n, u in parts)


def _int_header(headers: httpx.Headers, name: str) -> int | None:
    try:
        return int(headers[name]) if name in headers else None
    except ValueError:
        return None


def parse_rate_limit(headers: httpx.Headers, model_id: str) -> RateLimitState | None:
    if not any(k.lower().startswith("x-ratelimit-") for k in headers):
        return None
    return RateLimitState(
        model_id=model_id,
        observed_at=monotonic(),
        limit_requests=_int_header(headers, "x-ratelimit-limit-requests"),
        remaining_requests=_int_header(headers, "x-ratelimit-remaining-requests"),
        reset_requests_s=parse_duration_s(headers.get("x-ratelimit-reset-requests")),
        limit_tokens=_int_header(headers, "x-ratelimit-limit-tokens"),
        remaining_tokens=_int_header(headers, "x-ratelimit-remaining-tokens"),
        reset_tokens_s=parse_duration_s(headers.get("x-ratelimit-reset-tokens")),
    )


def safe_message(raw: object) -> str:
    text = raw if isinstance(raw, str) else ""
    return redact_text(text[:_MAX_ERROR_MESSAGE]) or "no message"


def _token_count(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _charge(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() and amount >= 0 else None


class OpenAICompatibleProvider(Provider):
    chat_path = "/chat/completions"
    models_path = "/models"
    status_map: ClassVar[dict[int, ProviderErrorKind]] = DEFAULT_STATUS_MAP

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        transport: httpx.AsyncBaseTransport | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        headers = {"Accept": "application/json", **(extra_headers or {})}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers=headers,
            transport=transport,
            follow_redirects=False,  # a redirect could send the API key somewhere unexpected
        )

    # --- hooks for provider subclasses -------------------------------------------------

    def build_payload(self, request: ProviderRequest) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": request.model_id,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "max_tokens": request.max_output_tokens,
            "temperature": request.temperature,
        }
        if request.response_format == "json":
            payload["response_format"] = {"type": "json_object"}
        return payload

    def classify_status(self, status: int) -> ProviderErrorKind:
        if status in self.status_map:
            return self.status_map[status]
        if status >= 500:
            return ProviderErrorKind.SERVER
        return ProviderErrorKind.BAD_REQUEST

    def parse_usage(self, usage: object) -> ProviderUsage:
        if not isinstance(usage, dict):
            return ProviderUsage(input_tokens=None, output_tokens=None)
        details = usage.get("completion_tokens_details")
        return ProviderUsage(
            input_tokens=_token_count(usage.get("prompt_tokens")),
            output_tokens=_token_count(usage.get("completion_tokens")),
            reasoning_tokens=_token_count(details.get("reasoning_tokens"))
            if isinstance(details, dict)
            else None,
        )

    def before_send(self, request: ProviderRequest) -> None:
        """Raise ProviderError(sent=False) to refuse a call locally."""

    def after_send(self) -> None:
        """Called once per request that actually reached the network."""

    # --- core ----------------------------------------------------------------------------

    def _error(
        self,
        kind: ProviderErrorKind,
        message: str,
        *,
        status: int | None = None,
        retry_after: float | None = None,
        usage: ProviderUsage | None = None,
        sent: bool = True,
    ) -> ProviderError:
        return ProviderError(
            kind=kind,
            message=message,
            provider=self.name,
            http_status=status,
            retry_after_s=retry_after,
            usage=usage,
            sent=sent,
        )

    async def generate(self, request: ProviderRequest) -> ProviderResponse:
        self.before_send(request)
        payload = self.build_payload(request)
        started = perf_counter()
        try:
            self.after_send()
            response = await self._client.post(
                self.chat_path, json=payload, timeout=request.timeout_s
            )
        except httpx.TimeoutException:
            raise self._error(
                ProviderErrorKind.TIMEOUT, f"no response within {request.timeout_s:g}s"
            ) from None
        except httpx.TransportError as exc:
            raise self._error(ProviderErrorKind.NETWORK, type(exc).__name__) from None
        latency_ms = int((perf_counter() - started) * 1000)
        state = parse_rate_limit(response.headers, request.model_id)
        if state is not None:
            self.last_rate_limit = state

        if 300 <= response.status_code < 400:
            # Not followed: the Authorization header must only ever go to the configured host.
            raise self._error(
                ProviderErrorKind.BAD_REQUEST,
                f"unexpected redirect (HTTP {response.status_code}) refused",
                status=response.status_code,
            )
        retry_after = parse_retry_after(response.headers.get("retry-after"))
        body = self._json(response)

        if response.status_code >= 400:
            raise self._error(
                self.classify_status(response.status_code),
                self._error_message(body) or f"HTTP {response.status_code}",
                status=response.status_code,
                retry_after=retry_after,
            )
        if not isinstance(body, dict):
            raise self._error(
                ProviderErrorKind.MALFORMED,
                "response is not a JSON object",
                status=response.status_code,
            )
        # Some providers (OpenRouter) commit HTTP 200 and report failure in the body.
        if body.get("error") and not body.get("choices"):
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            status = code if isinstance(code, int) and 400 <= code <= 599 else None
            raise self._error(
                self.classify_status(status) if status else ProviderErrorKind.SERVER,
                self._error_message(body) or "error in response body",
                status=status or response.status_code,
                retry_after=retry_after,
            )
        return self._parse_success(body, request, latency_ms)

    def _parse_success(
        self, body: dict[str, Any], request: ProviderRequest, latency_ms: int
    ) -> ProviderResponse:
        usage = self.parse_usage(body.get("usage"))
        choices = body.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        message = first.get("message") if isinstance(first, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        finish = first.get("finish_reason") if isinstance(first, dict) else None

        if not isinstance(content, str):
            raise self._error(
                ProviderErrorKind.MALFORMED, "missing choices[0].message.content", usage=usage
            )
        if not content.strip():
            # Typical for reasoning models that spend the whole token budget thinking.
            raise self._error(
                ProviderErrorKind.MALFORMED,
                f"empty completion (finish_reason={finish})",
                usage=usage,
            )
        return ProviderResponse(
            content=content,
            provider=self.name,
            model_id=str(body.get("model") or request.model_id),
            usage=usage,
            latency_ms=latency_ms,
            simulated=False,
            finish_reason=finish if isinstance(finish, str) else None,
        )

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    @staticmethod
    def _error_message(body: Any) -> str | None:
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                return safe_message(error.get("message"))
            if isinstance(error, str):
                return safe_message(error)
        return None

    async def list_model_ids(self) -> set[str] | None:
        try:
            response = await self._client.get(self.models_path, timeout=10.0)
        except httpx.HTTPError as exc:
            logger.warning(
                "model_catalog_unreachable",
                extra={"provider": self.name, "error_type": type(exc).__name__},
            )
            return None
        body = self._json(response)
        if response.status_code != 200 or not isinstance(body, dict):
            logger.warning(
                "model_catalog_error",
                extra={"provider": self.name, "http_status": response.status_code},
            )
            return None
        data = body.get("data")
        if not isinstance(data, list):
            return None
        return {str(m["id"]) for m in data if isinstance(m, dict) and "id" in m}

    async def aclose(self) -> None:
        await self._client.aclose()
