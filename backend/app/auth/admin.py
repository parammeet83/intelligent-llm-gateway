"""Administrator authentication.

Bootstrap: the operator sets ADMIN_TOKEN as a host secret (never committed, never in the
frontend bundle). Until it is set, every admin endpoint returns 401 ADMIN_NOT_CONFIGURED.

The dashboard never keeps the admin token: it exchanges it once at POST /admin/session for a
signed session token (HMAC-SHA256, short TTL). The signing key is derived from ADMIN_TOKEN, so
rotating the token invalidates every outstanding session.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections import defaultdict, deque

SESSION_PREFIX = "rws_"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _signing_key(admin_token: str) -> bytes:
    return hmac.new(admin_token.encode(), b"routewise-admin-session-v1", hashlib.sha256).digest()


def issue_session(admin_token: str, ttl_s: int, *, now: float | None = None) -> tuple[str, int]:
    issued = int(now if now is not None else time.time())
    expires = issued + ttl_s
    payload = {"iat": issued, "exp": expires, "nonce": secrets.token_urlsafe(8)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_signing_key(admin_token), body.encode(), hashlib.sha256).digest())
    return f"{SESSION_PREFIX}{body}.{sig}", expires


def verify_session(token: str, admin_token: str, *, now: float | None = None) -> bool:
    if not token.startswith(SESSION_PREFIX):
        return False
    try:
        body, sig = token[len(SESSION_PREFIX) :].split(".", 1)
        expected = _b64(hmac.new(_signing_key(admin_token), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expected):
            return False
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return False
    current = now if now is not None else time.time()
    exp = payload.get("exp")
    return isinstance(exp, int) and exp > current


def token_matches(presented: str, admin_token: str) -> bool:
    return hmac.compare_digest(presented.encode(), admin_token.encode())


class LoginThrottle:
    """At most `limit` admin login attempts per client per minute (in-memory)."""

    def __init__(self, limit: int = 5, window_s: float = 60.0) -> None:
        self.limit = limit
        self.window_s = window_s
        self._attempts: defaultdict[str, deque[float]] = defaultdict(deque)

    def allow(self, client: str, *, now: float | None = None) -> bool:
        current = now if now is not None else time.monotonic()
        attempts = self._attempts[client]
        while attempts and attempts[0] <= current - self.window_s:
            attempts.popleft()
        if len(attempts) >= self.limit:
            return False
        attempts.append(current)
        return True
