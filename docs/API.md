# API

Base path `/api/v1`. Every response carries `X-Request-ID`, which is server-generated and is also the
`request_logs` primary key. Every error uses one envelope:

```json
{"error": {"code": "STRING_CODE", "message": "human text", "request_id": "uuid", "details": {}}}
```

## Authentication

| Caller | Header | Notes |
|---|---|---|
| Tenant | `Authorization: Bearer rw_<id>_<secret>` | Tenant API key. The tenant is derived from the key; a body `tenant_id` is rejected |
| Admin | `Authorization: Bearer <ADMIN_TOKEN>` or `Bearer rws_…` | Session token from `POST /admin/session`. Admin is disabled (401 `ADMIN_NOT_CONFIGURED`) until `ADMIN_TOKEN` is set |

All credential failures return `401 UNAUTHORIZED` "Invalid or missing credentials." See
[TENANCY_AND_SECURITY.md](TENANCY_AND_SECURITY.md).

## `POST /generate` (tenant)

| Field | Type | Default | Notes |
|---|---|---|---|
| `prompt` *or* `messages` | string / `[{role, content}]` | — | exactly one; ≤ 32k chars per message, ≤ 100k total, ≤ 50 messages, ≥ 1 `user` message |
| `task_type` | `classification` `extraction` `chat` `qa` `summarization` `creative` `code` `reasoning` | required | |
| `quality` | `low` `standard` `high` | `standard` | `high` = high-stakes → premium floor |
| `priority` | `low` `normal` `high` | `normal` | `high` ranks by observed p95 first |
| `preferred_tier` | `small` `medium` `premium` | — | raises the floor; lowers it only with `allow_downgrade` |
| `allow_downgrade` | bool | `false` | |
| `latency_target_ms` | 100–120000 | — | applied to **observed** p95 only (≥ 5 samples) |
| `max_cost_usd` | decimal 0–10 | — | worst-case **estimated list cost** cap; unpriced models excluded |
| `max_output_tokens` | 1–8192 | 512 | |
| `temperature` | 0–2 | 0 | |
| `response_format` | `text` `json` | `text` | `json` requires the `json_mode` capability |
| `request_id` | `[A-Za-z0-9._:-]{1,128}` | — | idempotency key, unique per tenant |
| `prompt_version` | string ≤ 64 | — | your template version, recorded in logs |
| `constraints.providers` / `.models` | lists | — | restrict to provider names / `provider/model` keys |

Unknown fields are rejected (422). Bodies over 512 KiB get 413.

```powershell
$headers = @{ Authorization = "Bearer $env:ROUTEWISE_KEY" }   # a tenant key, never committed
$body = @{ prompt = "Classify the sentiment: I love this phone."; task_type = "classification"; request_id = "demo-1" } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/api/v1/generate -Method Post -Headers $headers -ContentType "application/json" -Body $body
```

**Response 200** contains: `request_id`, `client_request_id`, `tenant`, `simulated`, `content`, `finish_reason`,
`provider`, `model`, `tier`, `routing` (policy version, score, computed/required tier, reason codes,
explanation, contributions, fallback chain, excluded candidates with reasons), `usage` (final attempt),
`latency_ms`, `provider_latency_ms`, `cost` (`actual_charge_usd` + `cost_status`, `estimated_list_cost_usd` +
`list_cost_status`, pricing date and source, plain-language note), and `fallback` (attempts with reason
codes and statuses, skipped candidates, count of failed attempts without usage). Real examples from
the mock provider are in the Playwright tests (`frontend/e2e/gateway.spec.ts`).

**Errors**

| Status | Code | When |
|---|---|---|
| 401 | `UNAUTHORIZED` | missing, malformed, unknown, revoked or expired key, or suspended tenant |
| 402 | `BUDGET_EXHAUSTED` | the tenant's daily or monthly shadow budget can't cover the request (logged `rejected_budget`) |
| 409 | `DUPLICATE_REQUEST_ID` | `request_id` reused by this tenant. `details` has the original ID and status. No provider is called |
| 413 | `PAYLOAD_TOO_LARGE` | body > 512 KiB |
| 422 | `INVALID_REQUEST` | validation (submitted text never echoed) |
| 422 | `NO_ELIGIBLE_MODEL` | no model passes the filters; `details.routing.excluded` lists why |
| 429 | `RATE_LIMITED` | tenant over `rate_limit_rpm`; `Retry-After` set; the `request_id` is not consumed |
| 502 | `ALL_PROVIDERS_FAILED` | every eligible model failed; `details.fallback.attempts` |
| 502 | `UPSTREAM_REJECTED_REQUEST` | provider returned a non-fallback error (bad request) |
| 503 | `NO_AVAILABLE_PROVIDER` | every candidate skipped locally (quota, health, budget cap) |
| 504 | `DEADLINE_EXCEEDED` | `REQUEST_DEADLINE_S` reached |

Duplicates are rejected rather than replayed, because response content isn't stored (privacy default).

## Tenant self-service (tenant key)

| Method | Path | Returns |
|---|---|---|
| GET | `/me` | tenant, rate limit, current budget periods (limit, spent, reserved, remaining), key prefix |
| GET | `/me/usage?days=1..90&bucket=hour\|day` | usage summary for this tenant only |
| GET | `/me/requests?limit&offset&status` | this tenant's requests (paginated) |
| GET | `/me/requests/{id}` | one request with decision and attempts; another tenant's ID → 404 |

## Admin (admin token or session)

| Method | Path | Purpose |
|---|---|---|
| POST | `/admin/session` `{"token"}` | exchange the admin token for a session token (5 attempts/min per client) |
| GET/POST | `/admin/tenants` | list (with budgets and key counts) / create `{slug, name, rate_limit_rpm, daily_budget_usd, monthly_budget_usd}` |
| PATCH | `/admin/tenants/{slug}` | update name, status, rate limit, budgets (`clear_daily_budget`, `clear_monthly_budget`) |
| GET/POST | `/admin/tenants/{slug}/keys` | list keys (prefix and status) / create (plaintext returned **once**) |
| POST | `/admin/keys/{id}/revoke` | revoke immediately |
| POST | `/admin/keys/{id}/rotate` `{"grace_s"}` | issue a replacement; old key revoked now or after the grace period |
| GET | `/admin/usage?days&bucket&tenant` | totals, by provider/model/tier/tenant, time series, latency histogram |
| GET | `/admin/requests?limit&offset&tenant&status&provider&tier&fallback&q&sort` | request log search (q = request ID, client request ID, or model) |
| GET | `/admin/requests/{id}` | full decision record and attempts |
| GET | `/admin/config` | routing policy and non-secret settings |
| GET | `/admin/evaluation/runs[/{id}]` | benchmark runs with summaries / per-case results |

## Public

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | liveness, version, environment, enabled providers, `simulated_only` |
| GET | `/ready` | DB reachable and migrations at head (503 otherwise) |
| GET | `/models` | registry: tiers, capabilities, list prices with sources, live health |
| GET | `/providers` | enabled providers, simulated flag, charge basis, retries, quota state |

None of these expose keys or internal URLs. Interactive docs (`/docs`) are disabled in production.
