# Code map

Read `GLOSSARY.md` for domain terms and `docs/adr/` for decisions. This file is
only the "where does this change go?" map.

## Productization roadmap

- [Backend productization spec](../../.scratch/productization/spec.md) — phases,
  SLOs, service-extraction gates, and non-goals.
- [ADR 0014](../adr/0014-single-tenant-self-hosted-python.md) — single-tenant
  self-hosted Host, Python core, no Go rewrite, stage-oriented pools.
- [API contract](../api-contract.md) — v1 compatibility, request ids,
  idempotency, and error envelope.

## Android app

`android/` — native Android client. Read `android/AGENTS.md` before changing it.

```text
android/
├── app/        Compose routes/screens, AppContainer, Add/Search/Settings/Player wiring
├── core/       network, Room db, sync, download, search FTS5, reading/book JSON, settings
├── playback/   Media3 MediaSessionService + PlayerGateway
└── reader/     Readium ReaderActivity/Fragment + locator mapping
```

| Change | Where |
|---|---|
| New Compose screen or navigation route | `android/app/src/main/kotlin/dev/trove/app/<feature>/` + `TroveApp.kt` |
| API DTO/client contract | `android/core/.../network/`; keep `contract/*.json` in sync |
| Room table/migration/query | `android/core/.../db/` |
| Sync push/pull/LWW | `android/core/.../sync/SyncEngine.kt` |
| Local FTS5 index/query | `android/core/.../search/` |
| EPUB/book JSON/locator | `android/core/.../reading/` + `android/reader/` |
| Download worker/files | `android/core/.../download/` + `storage/` |
| Device acceptance tooling | `scripts/android/` (`check.sh`, `acceptance-host.sh`, `use-real-host.sh`, `acceptance-playback.sh`, `diagnostics.sh`, `device-check.sh`, `release-check.sh`, `seed_acceptance.py`, `seed_playback.py`, `ui-dump.py`) |

## HTTP surface

```text
src/trove/web/
├── routes.py      # router assembly only
├── html/          # Host Console HTML: library, items, add, collections, export, auth
├── shell.py       # Consumer Web Shell HTML: listen, read, continue, transcript
├── api/           # JSON API by resource
├── schemas.py     # request models
├── deps.py        # render, filters, export responses
├── security.py    # auth, CSRF, CSP, middleware
├── errors.py      # exception handlers
└── media.py       # audio/cover responses
```

`html/`, `shell.py`, and `api/` are sibling HTTP adapters over the same services.
`shell.py` is the Consumer Shell from `GLOSSARY.md` / ADR 0002; it is not a
separate protocol. `api/runs.py` is the one remaining handler that reads
`Run` / `Item` directly instead of going through a service.

## Layers

| Change | Where |
|---|---|
| New HTML page or form action | `web/html/` (Host Console) or `web/shell.py` (consumption) |
| New JSON endpoint | `web/api/<resource>.py` |
| Processing stage handler / artifact install | `services/stages/` + `services/artifacts.py`; `services/run_coordinator.py` owns Run and StageTask lifecycle, leases, and reaping |
| Stage retry policy / backoff / dead letters | `domain/retry.py` + `services/run_coordinator.py` |
| External-call cache (LLM/ASR) | `domain/cache.py` + `services/stages/organize.py` + `services/stages/transcribe.py`; keys live in `ai.json`/`transcript.json` and `AiResult` |
| Link classification / inspection | `domain/urls.py` + `domain/links.py` + `services/inspect.py` + `adapters/video_inspect.py` |
| Collection aggregate / membership | `services/collections.py` + `db/models.py` (Collection, Item.collection_*) |
| EPUB URL intake | `domain/items.py` (`EPUB_URL`) + `adapters/downloader.py` + `services/intake.py` |
| Business workflow / transaction | `services/` |
| LLM organization (prompts, map-reduce, limits) | `services/organization.py` + `domain/organization_prompts.py`; transport in `adapters/openai_chat.py` |
| Pure rule / value object | `domain/` |
| External system | `ports.py` + `adapters/` |
| DB model or schema | `db/models.py` + new Alembic migration |
| Content package layout / document / manifest | `content_package.py` + `services/package_documents.py` |
| FTS5 query / index | `adapters/search.py`; contract in `ports.py` |

HTTP handlers and services do not contain raw SQL. Raw SQL belongs to adapters
and `db/`; FTS5 SQL lives in `adapters/search.py`. The content package, not the
DB, is the source of truth for transcript and book content.

Layer dependencies are enforced by import-linter (`uv run lint-imports`, part of
`./scripts/check.sh --fast`). `domain` cannot import `services`, `adapters`,
`web`, or `db`; `services` cannot import `web` or `adapters`; `adapters` cannot
import `services` or `web`; `web` cannot import `adapters` directly; and
`domain`/`services`/`adapters` cannot import entry points or composition
(`app`, `cli`, `composition`, `worker`, `deploy`, ...). `web` may read the DB only
at the two documented boundaries in `pyproject.toml` (`api/health.py`,
`api/runs.py`); remove those baselines when the handlers move behind services
(tracked by [issue 21](../../.scratch/productization/issues/21-remove-web-db-baselines.md)).
