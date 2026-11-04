"""Tenant API keys: `rw_<8-char id>_<secret>`.

The `rw_<id>` part is the public prefix (stored, shown in dashboards). The full key is hashed
with HMAC-SHA256 and a server-side pepper. Keys carry ~190 bits of randomness, so a slow
password KDF adds latency without adding security.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import string
from dataclasses import dataclass

_ID_ALPHABET = string.ascii_lowercase + string.digits
_KEY_RE = re.compile(r"^(rw_[a-z0-9]{8})_[A-Za-z0-9_-]{32,}$")


@dataclass(frozen=True)
class GeneratedKey:
    plaintext: str  # shown to the user exactly once
    prefix: str
    key_hash: str


def hash_api_key(plaintext: str, pepper: str) -> str:
    return hmac.new(pepper.encode(), plaintext.encode(), hashlib.sha256).hexdigest()


def generate_api_key(pepper: str) -> GeneratedKey:
    key_id = "".join(secrets.choice(_ID_ALPHABET) for _ in range(8))
    prefix = f"rw_{key_id}"
    plaintext = f"{prefix}_{secrets.token_urlsafe(24)}"
    return GeneratedKey(
        plaintext=plaintext, prefix=prefix, key_hash=hash_api_key(plaintext, pepper)
    )


def parse_prefix(plaintext: str) -> str | None:
    """Return the public prefix if the key is well-formed, otherwise None."""
    match = _KEY_RE.match(plaintext)
    return match.group(1) if match else None


def verify_api_key(plaintext: str, stored_hash: str, pepper: str) -> bool:
    return hmac.compare_digest(hash_api_key(plaintext, pepper), stored_hash)
