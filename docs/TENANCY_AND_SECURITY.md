# Tenancy and Security

## Identities

| Who | Credential | Where it lives | Can access |
|---|---|---|---|
| Tenant (client app) | API key `rw_<8-char id>_<secret>` | Issued once; the server stores only `key_prefix` and HMAC-SHA256(pepper, key) | `POST /generate`, `/me`, `/me/usage`, `/me/requests[/id]`, all scoped to its own tenant |
| Administrator | `ADMIN_TOKEN` (host secret) | Environment only, never in the repo or the frontend bundle | `/admin/*` |
| Dashboard session | `rws_…` HMAC-signed token, 8 h TTL | Browser `sessionStorage` (per tab, cleared on close) | `/admin/*` until expiry |

- **The tenant always comes from the key.** No endpoint accepts a tenant ID from the body or headers
  (requests with `tenant_id` are rejected as unknown fields).
- **Generic failures.** Every auth failure returns the same `401 UNAUTHORIZED`, "Invalid or missing
  credentials.", whether the key is malformed, unknown, wrong, revoked, or expired, or the tenant is
  suspended. Callers can't probe which keys exist.
- Key verification uses a prefix lookup, then a constant-time HMAC comparison (`hmac.compare_digest`).
  `last_used_at` is refreshed at most once a minute to avoid a write per request.

## Bootstrap (first administrator)

1. Generate secrets: `python -c "import secrets; print(secrets.token_urlsafe(48))"`. Set
   `ADMIN_TOKEN` and `API_KEY_PEPPER` as host secrets (or in local `.env`).
2. Until `ADMIN_TOKEN` is set, every admin endpoint returns `401 ADMIN_NOT_CONFIGURED` (fail closed).
3. **Production refuses to start** unless `API_KEY_PEPPER` is ≥ 32 characters and not the dev
   default, `ADMIN_TOKEN` (if set) is ≥ 32 characters, and the database is PostgreSQL.
4. Create tenants and keys with the CLI (`create-tenant`, `create-api-key`) or the admin API.
   Plaintext keys are printed or returned exactly once.

Changing `API_KEY_PEPPER` invalidates every tenant key. Changing `ADMIN_TOKEN` invalidates every
dashboard session, because the signing key is derived from it.

## Key lifecycle

| Action | CLI | API |
|---|---|---|
| Create (shown once) | `create-api-key TENANT [--name N] [--json]` | `POST /admin/tenants/{slug}/keys` |
| List (prefix and status only) | `list-api-keys TENANT` | `GET /admin/tenants/{slug}/keys` |
| Revoke (immediate) | `revoke-api-key KEY_ID` | `POST /admin/keys/{id}/revoke` |
| Rotate | `rotate-api-key KEY_ID [--grace-s N]` | `POST /admin/keys/{id}/rotate {"grace_s": N}` |

Rotation issues a new key. The old key is revoked immediately, or expires after `grace_s` so clients
can switch over. Only active keys can be rotated. Key hashes are never returned by any endpoint.

## Tenant isolation (tested in `tests/api/test_auth_and_tenancy.py`)

- Every tenant-facing query filters on the authenticated tenant's ID. Another tenant's request ID
  returns **404**, not 403, so existence isn't confirmed.
- Usage, budgets, request lists and details are per tenant. Tenant keys can't reach `/admin/*`.
- The idempotency key `request_id` is unique **per tenant**. The same value in two tenants is independent.
- Rate-limit windows and budget ledgers are keyed by tenant ID.

## Rate limits

Per tenant, `rate_limit_rpm` requests per UTC minute, using a DB-backed fixed window with one atomic
upsert per request. That's exact across processes, with no Redis. A rejection returns `429 RATE_LIMITED`
with `Retry-After` and is logged as `rejected_rate_limit`, feeding the rejection-rate metric. A
rejected request's `request_id` is **not** consumed, so the client can retry with the same ID.
Trade-off: a fixed window allows a burst of up to 2× across a minute boundary.

Admin login (`POST /admin/session`) is throttled to 5 attempts per client per minute (in-memory).

## Budgets (shadow budgets on estimated list cost)

Daily and monthly limits per tenant (`NULL` = no limit). Enforcement:

1. **Read** headroom = min over periods of `limit − spent − reserved`. The router excludes models
   whose worst-case cost exceeds it, and models with unknown prices (`PRICE_UNKNOWN`).
2. **Reserve** atomically: `UPDATE … SET reserved = reserved + :r WHERE spent + reserved + :r <= limit`,
   one per period, inside a SAVEPOINT (all or nothing). PostgreSQL re-checks the predicate after
   taking the row lock, so concurrent requests can't jointly overspend. The reservation is up to 3×
   the most expensive eligible model's worst case, capped by headroom, and is recorded on the request
   row in the same transaction.
3. **Execute** within the reservation. The executor never starts an attempt (including retries and
   fallbacks) whose worst case could push consumption past it.
4. **Settle** in the same transaction as the attempt rows: `spent += consumed`, reservation released.
   `consumed` counts known list costs, plus the **worst case** of any attempt whose usage is unknown
   (a timeout, a 5xx or a success without a usage block). Unknown usage is never counted as $0. If an
   attempt can't be bounded at all, the whole reservation counts as spent. Only rejections returned
   before any generation (429, 401, 400, 404) count as zero.
5. **Crash recovery:** `app.cli reconcile` settles reservations on pending requests older than
   `STALE_RESERVATION_S`. It charges the **whole hold** as spent, because the request may have called a
   provider before the process died, and marks them failed (`ABANDONED_RESERVATION_CHARGED`).

When the tenant budget is the binding limit, the API returns `402 BUDGET_EXHAUSTED` and logs
`rejected_budget`. Budgets are shadow figures: they limit *estimated list-price* spend, not money.

Known limits: charging unknown usage at its worst case (and abandoned requests at the full hold)
deliberately over-counts, so a tenant with many timeouts runs out of shadow budget sooner than its
real consumption warrants. The concurrency test (25 parallel reservations against a budget of 10) runs against
SQLite locally and PostgreSQL in CI; the CI run is pending the first push.

## Caching: not implemented (decision)

A response cache was considered and rejected for v1. Benchmark and typical gateway traffic at
temperature 0 rarely repeats exactly. A cache would need to store response content, which the
privacy default forbids. And tenant-scoped invalidation adds risk for little measured benefit. The
`response_cache` table was never created.

## Data minimisation and logging

- Prompts and responses are **not stored or logged**: only SHA-256 and character count. Benchmark
  runs store an output excerpt (≤ 600 chars) of *benchmark* prompts for scoring audit.
- The log formatter redacts sensitive field names and credential-shaped values (provider keys,
  RouteWise keys, bearer tokens, connection-string passwords). Provider error text is truncated to
  200 characters and redacted.
- Validation errors never echo submitted input.
- `/admin/config` returns non-secret settings only (tested to contain no keys, tokens, or pepper).

## Other controls

CORS allow-list (`CORS_ORIGINS`); request bodies over 512 KiB rejected; strict request schemas
(`extra=forbid`); provider base URLs fixed in code; redirects never followed; OpenRouter `:free`-only
guard; paid models rejected at startup, in routing, and in the executor; Ollama localhost-only and
refused in production; interactive API docs disabled in production.
