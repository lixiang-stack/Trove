# Code map

Read `GLOSSARY.md` for domain terms and `docs/adr/` for decisions. This file is
only the "where does this change go?" map.

## HTTP surface

```text
src/trove/web/
├── routes.py      # router assembly only
├── html/          # Host Console HTML: library, items, add, export, auth
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
| Business workflow / transaction | `services/` |
| Pure rule / value object | `domain/` |
| External system | `ports.py` + `adapters/` |
| DB model or schema | `db/models.py` + new Alembic migration |
| Content package layout / document | `content_package.py` + `services/package_documents.py` |
| FTS5 query / index | `adapters/search.py`; contract in `ports.py` |

HTTP handlers and services do not contain raw SQL. Raw SQL belongs to adapters
and `db/`; FTS5 SQL lives in `adapters/search.py`. The content package, not the
DB, is the source of truth for transcript and book content.
