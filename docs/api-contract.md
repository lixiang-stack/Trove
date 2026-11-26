# Trove API Contract

Status: active
Applies to: `/api` (v1)
Last updated: 2026-11-25

This document defines the compatibility rules for the JSON API. The OpenAPI
schema at `/api/openapi.json` and the fixtures in `contract/` are the executable
part of this contract; this document explains the intent.

## Versioning

- The current contract is **v1**. The URL prefix remains `/api`; there is no
  `/api/v1` path yet.
- Within v1, changes must be additive: new optional response fields, new
  endpoints, new optional request fields, new error codes. Existing fields may
  not be removed, renamed, or change meaning.
- A breaking change requires a new path version (`/api/v2`) and a migration
  window. The old version must remain available for at least one minor release.
- `GET /api/health` reports `api_version` as the Host build version. It is not a
  semver guarantee for the HTTP contract; use the documented v1 rules and the
  OpenAPI schema for compatibility checks.
- Capability changes are advertised in `GET /api/health` under `capabilities`.
  Clients must tolerate unknown capability keys.

## Authentication

- Browser sessions use the `trove_session` cookie.
- Devices use `Authorization: Bearer <token>` obtained from
  `POST /api/auth/device-token`.
- Missing or invalid credentials return `401` with `auth.required` or the
  device-specific error code.
- Cookie-authenticated unsafe methods require same-origin/CSRF checks; Bearer
  requests are not subject to cookie CSRF rules.

## Request IDs

Every HTTP response includes `X-Request-ID`.

- A client may send `X-Request-ID` with 1–128 characters from
  `A-Z a-z 0-9 . _ : -`. A valid value is echoed unchanged.
- Missing or invalid values are replaced with a generated id.
- JSON error responses include the same value as `request_id`.
- Structured request logs include the same `request_id`.

## Error Envelope

JSON errors have this shape:

```json
{
  "code": "idempotency.key_reused",
  "message": "Idempotency-Key was already used for a different request",
  "details": null,
  "request_id": "b2f1c0a4d5e6477a9b0c1d2e3f4a5b6c"
}
```

- `code` is stable and machine-readable. Existing codes are listed in
  `src/trove/domain/items.py` and the API error handlers.
- `message` is human-readable and may change.
- `details` is optional and may contain structured context.
- `request_id` matches `X-Request-ID`.
- Clients must not depend on message text or on the absence of new fields.

## Idempotency

Creating requests accept an `Idempotency-Key` header. The first version covers
`POST /api/items`.

Sync mutations (`PUT /api/items/{item_id}/progress` and
`PUT /api/items/{item_id}/tags`) keep their existing device-scoped
idempotency behavior in `sync_mutations`; this document does not change it.

- Keys are scoped to the Host and the request method/path. Reusing a key with a
  different method, path, or JSON body returns `409 idempotency.key_reused`.
- A completed request returns the stored response with the original status code
  and body. The response includes `Idempotency-Replayed: true`.
- A request that is still executing returns `409 idempotency.in_progress`.
  Clients should retry after a short delay.
- Only successful responses are stored. Failed requests release the key so the
  client can retry.
- Completed keys are kept for 24 hours. In-progress keys expire after 5 minutes
  so a crashed request cannot block the key for a full day.
- A missing header keeps the existing behavior: duplicate `source_key` values
  still return the existing Item with `deduplicated: true`, but no response is
  cached.

Example:

```http
POST /api/items
Idempotency-Key: 6f0c2d7e-import-2026-11-25
Content-Type: application/json

{"kind": "url", "url": "https://www.youtube.com/watch?v=..."}
```

The first successful call returns `201`; a replay with the same key and body
returns the same `201` body and `Idempotency-Replayed: true`.

## Pagination and Filtering

- `GET /api/items` uses `limit` (1–200) and `offset` (≥0).
- `total` is the total number of matching Items; `count` is the page size.
- New filters may be added; unknown filters must not change existing behavior.
- Sorting values are stable strings; unknown sort values fall back to the
  documented default.

## Run Progress

- v1 clients poll `GET /api/items/{item_id}` or `GET /api/runs/{run_id}` for
  Processing State.
- SSE and webhooks are not part of v1. They may be added later as opt-in
  capabilities without changing polling semantics.

## Retry, Reprocess, and Cache

- `POST /api/items/{item_id}/retry` resumes a failed or cancelled Run. It keeps
  completed stages and reuses matching LLM/ASR results from automatic retries.
- `POST /api/items/{item_id}/reprocess` with `from_stage` is an explicit rerun.
  It bypasses the external-call cache so ASR/LLM work is performed again.
- `trove collection reprocess --reset-ai-tags` is also an explicit rerun and
  bypasses the cache.
- Cached AI results keep their original cost; a cache hit adds no tokens and no
  new AI cost. Cache keys include the Item, prompt version, model, and input
  hash for LLM, and the audio hash and model for ASR.
- Old content packages without cache hashes remain valid and are regenerated on
  the next run.

## Status Codes

- `200` successful read or deduplicated create.
- `201` new resource created.
- `202` accepted for asynchronous processing.
- `204` successful delete with no body.
- `400` malformed request that is not a validation error.
- `401` authentication required or invalid.
- `403` CSRF or authorization failure.
- `404` resource not found.
- `409` conflicting state, including idempotency conflicts.
- `422` request validation failed.
- `429` rate limited; honor `Retry-After`.
- `500` internal error.
- `503` Host not ready (database migration/FTS5/health failures).

## Compatibility Checklist

Before changing an endpoint:

- [ ] Existing response fields keep their names and meaning.
- [ ] New fields are optional or have defaults.
- [ ] Error codes are stable; new codes are documented.
- [ ] `contract/*.json` fixtures are updated only for additive changes.
- [ ] OpenAPI schema still matches the fixtures.
- [ ] Android client and CLI parsing are checked.
- [ ] A breaking change has a `/api/v2` plan and a migration window.
