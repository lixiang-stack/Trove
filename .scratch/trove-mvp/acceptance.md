# MVP acceptance sweep

Ticket: [29 — MVP 验收总检查](issues/29-mvp-acceptance-sweep.md)  
Status: pending manual execution

This is a release checklist, not a feature backlog. Record evidence links, not
claims. If something fails, open a follow-up issue instead of expanding this sweep.

Acceptance exception (2026-11-13): all PWA and Tailscale Serve acceptance items
are **SKIPPED** by user decision and are not release gates. Caddy/localhost HTTPS
remains the accepted HTTPS path.

## Automated gates

| Gate | Command | Result |
| ---- | ------- | ------ |
| Lint | `uv run ruff check src tests` | |
| Types | `uv run mypy` | |
| Fast tests | `./scripts/check.sh --fast` | |
| Full tests | `./scripts/check.sh` | |
| Playwright | `uv run pytest -m browser` | |
| Docs | `python3 scripts/check-docs.py` | |
| Network excluded by default | `uv run pytest` | |

## Manual gates

| Gate | Evidence | Result |
| ---- | -------- | ------ |
| Q10 week | [q10-log.md](q10-log.md) | |
| Performance/storage | [benchmarks.md](benchmarks.md) | |
| Search evaluation | [search-evaluation.md](search-evaluation.md) | |
| Source/Tag quality | [source-quality.md](source-quality.md) | |
| Security checklist | [docs/security.md](../../docs/security.md) | |
| Deployment checklist | [docs/deployment.md](../../docs/deployment.md) | |
| Restart/cancel/resume | Host tests + real restart | |
| P0/P1 scope audit | spec + issue evidence | |
| No unannounced P2/P3 | spec review | |
| PWA / Tailscale acceptance | user decision 2026-11-13 | SKIPPED |

## P0 evidence

| P0 area | Implementation | Automated test | Manual evidence |
| ------- | -------------- | -------------- | --------------- |
| Host skeleton, setup, doctor, restart recovery | | | |
| Single-user auth and session | | | |
| Library Item CRUD, dedupe, edit, delete | | | |
| Bilibili/YouTube single-video intake | | | |
| Local audio/video and EPUB intake | | | |
| Podcast feed preview and episode intake | | | |
| Processing queue, stages, retry, cancel, resume | | | |
| Audio playback, progress, Media Session | | | |
| Transcript reading and search | | | |
| EPUB parsing and thin reader | | | |
| Unified CJK search, filters, grouped evidence | | | |
| DeepSeek summary/Tags and AI metadata | | | |
| Consume state, Continue, tag editing | | | |
| Content package, export zip, index rebuild | | | |
| Security: SSRF, uploads, paths, HTML, CSP | | | |
| JSON API / OpenAPI / Range / ETag | | | |
| launchd auto-start (Tailscale skipped) | | | |

## P1 shortlist evidence

| P1 item | Implementation | Automated test | Manual evidence |
| ------- | -------------- | -------------- | --------------- |
| Transcript reading | | | |
| Reading progress | | | |
| Continue | | | |
| Filters | | | |
| Tag editing | | | |
| Search result paragraph targeting | | | |
| Export zip | | | |
| Cancel running Run | | | |
| PWA install (optional) | | | SKIPPED |
| Consumer Web Shell | | | Q10 |

## Known issues and limits

| Issue | Impact | Follow-up |
| ----- | ------ | --------- |
| DNS rebinding residual in SSRF validation | loopback/Tailscale only | security follow-up if intake becomes multi-user |
| PWA/Tailscale acceptance skipped | known issues stay non-blocking | user decision 2026-11-13 |
| | | |

## Release decision

- [ ] RELEASE — all P0/P1 gates have evidence; known issues are documented.
- [ ] BLOCKED — list the blocking gate and owner below.

```text

```

PWA and Tailscale Serve are excluded from the release decision; see the
exception at the top of this file.
