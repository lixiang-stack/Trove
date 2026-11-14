# MVP acceptance sweep

- Ticket: [29 — MVP 验收总检查](issues/29-mvp-acceptance-sweep.md)
- Status: closed 2026-11-13 — desktop MVP released with exceptions
- Decision: **RELEASE (desktop)** — Host Console Core and desktop Consumer Web Shell accepted. Q10 phone web is **not accepted**; PWA/Tailscale acceptance is skipped; search/source quality evaluation is deferred to V1; launchd/Caddy manual deployment is deferred.

This is a release checklist, not a feature backlog. Record evidence links, not
claims. If something fails, open a follow-up issue instead of expanding this sweep.

## Automated gates

| Gate | Command | Result |
| ---- | ------- | ------ |
| Lint | `uv run ruff check src tests` | PASS 2026-11-13 |
| Types | `uv run mypy` | PASS 2026-11-13 |
| Full tests | `./scripts/check.sh --full` | PASS — 323 tests, including FFmpeg and Playwright |
| Network excluded by default | `uv run pytest` | PASS — network tests excluded |
| Docs | `python3 scripts/check-docs.py` | PASS — 57 files |

## Real evidence

Collected on the real Host (`~/Trove`, Apple M1 Pro, macOS 14.6.1):

- **Real content:** 3 Items completed end-to-end — 2 Bilibili videos (15:02 and 13:21) and 1 EPUB. All 3 Processing Runs are `completed`; audio, transcript, book, AI summary and Tags are present.
- **ASR:** `mlx-community/whisper-large-v3-turbo`; transcribing stages took 36.0 s and 34.9 s for the two videos. Active stages total about 46–48 s per video, roughly 2.4–2.6 min per audio hour, far below the 20 min/h target.
- **Organization:** `deepseek-flash` summaries and Tags generated for all 3 Items; recorded cost about `$0.0007–0.0019` per Item.
- **Search performance:** 1,000 seeded Items, 9 queries × 5 repeats, p95 **11.12 ms**, 2,000 index rows. Seed data is simpler than real transcripts, so a real 1k library still needs a spot check; it is far below the 1 s target and close to the 100 ms goal.
- **Storage:** real library 14 MB for 28.4 min of audio plus 1 book; audio extrapolates to about 2.8 GB per 100 h. 100 h + 100 books is likely under 5 GB, but the full 1 h/100-item benchmark was not run.
- **Security/API:** tickets [21](issues/21-security-hardening.md) and [22](issues/22-api-openapi-range-etag.md) were manually accepted on the real Host: 12/12 security checks and 4/4 + 8/8 API contract checks PASS.

## Manual gates

| Gate | Evidence | Result |
| ---- | -------- | ------ |
| Q10 week | [archive/q10-log.md](archive/q10-log.md) | **NOT ACCEPTED** — closed 2026-11-13; desktop consumption; V1 Android next |
| Performance/storage | [archive/benchmarks.md](archive/benchmarks.md) | PARTIAL PASS — real 15-min samples + 1k seed; 1 h sample optional |
| Search evaluation | [archive/search-evaluation.md](archive/search-evaluation.md) | DEFERRED — real library has 3 Items; 50+ corpus not available |
| Source/Tag quality | [archive/source-quality.md](archive/source-quality.md) | PARTIAL — Bilibili 2/2, EPUB 1/1; YouTube/podcast/local unverified |
| Security checklist | [docs/security.md](../../docs/security.md), ticket 21 | PASS — 12/12 manual checks |
| Deployment checklist | [docs/deployment.md](../../docs/deployment.md) | PARTIAL — local health OK; launchd/Caddy not verified |
| Restart/cancel/resume | Host tests + automated suite | PASS (automated); real launchd restart not verified |
| P0/P1 scope audit | spec + tests below | PASS with exceptions |
| No unannounced P2/P3 | spec review | PASS |
| PWA / Tailscale acceptance | user decision 2026-11-13 | SKIPPED |

## P0 evidence

| P0 area | Implementation | Automated test | Manual evidence |
| ------- | -------------- | -------------- | --------------- |
| Host skeleton, setup, doctor, restart recovery | `src/trove/deploy.py`, `src/trove/cli.py` | `test_host_skeleton.py`, `test_deployment.py`, `test_processing_recovery.py` | local `/api/health` OK; launchd deferred |
| Single-user auth and session | `src/trove/web/security.py`, auth services | `test_auth.py`, `test_security.py` | 21 security checks PASS |
| Library Item CRUD, dedupe, edit, delete | `src/trove/services/library.py` | `test_library.py`, `test_api_contract.py` | 21/22 PASS |
| Bilibili/YouTube single-video intake | video adapter + intake service | `test_video_intake.py` | Bilibili 2/2 real; YouTube unverified |
| Local audio/video and EPUB intake | intake service + EPUB adapter | `test_local_intake.py`, `test_reading.py` | EPUB 1/1 real; local audio/video unverified |
| Podcast feed preview and episode intake | feed adapter + intake service | `test_podcast_intake.py` | not verified with a real feed |
| Processing queue, stages, retry, cancel, resume | `src/trove/services/processing.py` | `test_processing.py`, `test_processing_recovery.py` | 3 real Runs completed |
| Audio playback, progress, Media Session | `src/trove/web/static/player.js`, shell | `test_playback.py`, `test_browser.py` | desktop browser PASS; phone Q10 not accepted |
| Transcript reading and search | `src/trove/web/shell.py` | `test_browser.py` | real transcripts generated and readable |
| EPUB parsing and thin reader | EPUB adapter + shell | `test_reading.py`, `test_browser.py` | real EPUB parsed |
| Unified CJK search, filters, grouped evidence | `src/trove/adapters/search.py`, web | `test_search.py`, `test_domain_search.py`, `test_browser.py` | real search smoke; 1k performance seed |
| DeepSeek summary/Tags and AI metadata | organization adapter | `test_organization.py` | 3 real AI results |
| Consume state, Continue, tag editing | consumption/tagging services | `test_continue.py`, `test_tagging.py`, `test_browser.py` | desktop browser PASS |
| Content package, export zip, index rebuild | `src/trove/content_package.py`, services | `test_content_package.py`, `test_export.py` | local content packages present |
| Security: SSRF, uploads, paths, HTML, CSP | web/security + adapters | `test_security.py` | 21 security checks PASS |
| JSON API / OpenAPI / Range / ETag | `src/trove/web/api/` | `test_api_contract.py` | 22 API checks PASS |
| launchd auto-start (Tailscale skipped) | `src/trove/deploy.py` | `test_deployment.py` | not verified; deferred |

## P1 shortlist evidence

| P1 item | Implementation | Automated test | Manual evidence |
| ------- | -------------- | -------------- | --------------- |
| Transcript reading | shell transcript view | `test_browser.py` | real transcripts readable |
| Reading progress | reader progress service | `test_browser.py` | real book locator stored |
| Continue | `src/trove/services/consumption.py` | `test_continue.py`, `test_browser.py` | desktop browser PASS |
| Filters | search/library filters | `test_search.py`, `test_browser.py` | desktop browser PASS |
| Tag editing | tagging service + HTML/API | `test_tagging.py`, `test_browser.py` | desktop browser PASS |
| Search result paragraph targeting | shell anchors | `test_browser.py` | desktop browser PASS |
| Export zip | export service + HTML/API | `test_export.py` | automated PASS |
| Cancel running Run | processing service | `test_processing.py` | automated PASS |
| PWA install (optional) | `src/trove/web/pwa.py`, `sw.js` | `test_pwa.py`, `test_browser.py` | SKIPPED |
| Consumer Web Shell | `src/trove/web/shell.py` | `test_browser.py` | Q10 not accepted; desktop only |

## Known issues and limits

| Issue | Impact | Follow-up |
| ----- | ------ | --------- |
| Q10 phone web not accepted | phone browser is not the listening acceptance device | V1 Android player; desktop remains accepted |
| PWA-6: filter chips visually cluttered on mobile | mobile web usability | V1/UI follow-up; non-blocking |
| PWA-7: search form sticky on mobile | mobile web usability | V1/UI follow-up; non-blocking |
| Search quality evaluation deferred | 50+ corpus quality unknown | V1 backlog; run a reduced evaluation first if search quality becomes a concern |
| YouTube/podcast/local-file real source matrix deferred | parser reliability for those sources unverified | V1 backlog; run a source smoke before relying on them |
| launchd/Caddy manual deployment not verified | auto-start and phone HTTPS unverified | V1/ops; local manual `trove serve` works |
| DNS rebinding residual in SSRF validation | loopback-only Host lowers impact | security follow-up if intake becomes multi-user |

## Release decision

- [x] RELEASE — desktop MVP accepted. Host Console Core and desktop Consumer Web Shell have implementation, automated tests, and manual evidence. The exceptions above are explicit and do not block V1.
- [ ] BLOCKED — no blocking gate remains for the desktop MVP.

```text
RELEASE (desktop) — 2026-11-13
Accepted: Host Console Core, desktop Consumer Web Shell, security, API contract.
Not accepted: Q10 phone web.
Skipped: PWA install, Tailscale Serve.
Deferred: 50+ search quality, full source/Tag matrix, launchd/Caddy manual deployment, 1 h benchmark.
```

## V1 handoff

The current web/API is the foundation for the V1 Android client:

- Content package is the source of truth; audio artifacts have sha256/size/mime and HTTP Range/ETag.
- JSON API and OpenAPI are implemented and contract-tested.
- V1 still needs `version`/`deleted_at`, manifest/cursor, tombstone, `device_id`, bearer-token support, and a V1 spec/ADR before implementation.
- Start V1 with a new spec/issues directory; do not carry the MVP acceptance scaffolding forward.
