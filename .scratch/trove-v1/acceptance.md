# V1 acceptance sweep

- Ticket: [22 — V1 验收总检查](issues/22-v1-acceptance-sweep.md)
- Status: closed 2026-11-16 — automated M3 complete; device-only gates pending
- Decision: **BLOCKED**

This is a release checklist, not a feature backlog. Evidence links are repo paths or
ticket comments, not claims.

## Automated gates

| Gate | Command | Result |
| ---- | ------- | ------ |
| Host full tests | `./scripts/check.sh --full` | PASS 2026-11-16 — 388 collected; docs check included |
| Host fast CI | `./scripts/check.sh --fast` | PASS 2026-11-16 |
| Docs | `python3 scripts/check-docs.py` | PASS — 84 files |
| Android build/JVM/Compose/lint | `:app:assembleProdDebug :app:testProdDebugUnitTest :app:lintProdDebug :core:testDebugUnitTest :core:lintDebug :playback:testDebugUnitTest :playback:lintDebug :reader:testDebugUnitTest :reader:lintDebug` | PASS — 66 app tests, 90 core tests, 1 playback test, 3 reader tests |
| Release R8/resource shrink | `:app:assembleProdRelease` | PASS (signed and unsigned variants) |
| Signed release check | `scripts/android/release-check.sh` | PASS — signed, not debuggable, permissions allowlist, 9 MiB |
| LAN debug build | `:app:assembleLanDebug` | PASS |
| Instrumented core + platform manifest | `scripts/android/device-check.sh` | PASS — Xiaomi 13, API 36 |
| OpenAPI/contract fixtures | `uv run pytest -q tests/test_api_contract.py tests/test_contract_fixtures.py` | PASS |

## Real-device evidence

Xiaomi 13 (`2211133C`, Android 16 / API 36). The device was reconnected during the
final sweep; wireless playback/download evidence from M1/M2 is reused below and
the M3 checks below were run on the attached device.

| Area | Evidence | Result |
| ---- | -------- | ------ |
| Toolchain/cold start | [01](issues/01-android-toolchain-smoke.md) | PASS |
| Login/token/revocation | [09](issues/09-android-onboarding-auth.md) | PASS — debug localhost / adb reverse |
| Library initial/incremental/tombstone/revive | [10](issues/10-android-library-initial-sync.md) | PASS |
| Media3 session/notification/local playback | [11](issues/11-android-playback-service.md) | PASS with exceptions — 60-min run, Bluetooth, audio focus pending |
| Downloads/foreground/resume/remove | [12](issues/12-android-downloads-offline.md) | PASS with exceptions — storage-full not exercised |
| Transcript reading/search | [13](issues/13-android-transcript-reading.md) | PASS |
| EPUB reader/offline/search/position | [14](issues/14-android-epub-reader.md) | PASS with exceptions — images/footnotes not device-verified |
| Local/online search and 1k p95 | [15](issues/15-android-local-search.md) | PASS — FTS5 p95 <1s on device |
| Continue/tags/LWW conflict | [16](issues/16-android-continue-consumption-tags.md) | PASS — offline tag + canonical conflict |
| Add/share/podcast/retry | [17](issues/17-android-add-share-podcast.md) | PASS |
| Settings/notifications/battery/logout/clear | [18](issues/18-android-settings-sync-storage.md) | PASS with exceptions — OEM soak pending |
| Release APK install/R8 | manual adb install of signed `prodRelease` | PASS for install/launch; full R8 flow pending HTTPS login |
| Release cleartext rejection | manual login with `http://10.91.104.87:8767` | PASS — “正式版本只允许 HTTPS Host” |
| Reinstall Library/progress | uninstall + install `prodDebug` + login | PASS — 6 Items and Continue 40% restored |
| Caddy user CA / Tailscale HTTPS | — | **NOT VERIFIED** — Tailscale MagicDNS did not resolve on device; CA install requires device PIN |
| `lan` flavor device connection/warning | build only | **NOT VERIFIED** on device |
| Offline progress queue -> Web canonical | — | Automated only |

## Manual loop

| Step | Result |
| ---- | ------ |
| Share link -> Host -> download -> airplane playback >=60 min -> lock screen/notification/Bluetooth/speed/resume | **BLOCKED** — earlier media session/download PASS; 60-min/Bluetooth/audio focus pending |
| Download EPUB -> offline read/chapters/images/footnotes/in-book search/position | **PARTIAL** — reader/offline/search/position PASS; images/footnotes pending |
| Offline search downloaded content, Chinese two-character query, open match | **PASS** — FTS5 device test + ticket 15 |
| Offline Tag/progress/status -> reconnect -> Web canonical | **PARTIAL** — offline Tag/conflict PASS; offline progress/Web check pending |
| Host delete -> tombstone; re-add revive; reinstall Library/progress | **PASS** for tombstone/revive and reinstall Library/progress; download selection exception tracked in 24 |
| Download interrupt/resume/sha/quota; token revoke; password change | **PARTIAL** — interrupt/resume/sha/remove/revoke PASS; quota/password change pending |
| Caddy/Tailscale HTTPS, user CA, release/lan flavor | **BLOCKED** |

## Known issues and follow-ups

| Issue | Impact | Follow-up |
| ----- | ------ | --------- |
| No adb device during part of final sweep | release install/R8 smoke and remaining P0 checks unverified until device reconnected; reinstall/launch now PASS | [23](issues/23-v1-release-device-acceptance.md) |
| 60-min background/lockscreen playback, Bluetooth, headphone/call audio focus | P0 playback acceptance incomplete | [23](issues/23-v1-release-device-acceptance.md) |
| Caddy user CA / Tailscale HTTPS / release cleartext rejection on device | security acceptance incomplete | [23](issues/23-v1-release-device-acceptance.md) |
| Download selection is not persisted across reinstall | ticket 19 AC5 cannot be fully met without a contract change | [24](issues/24-reinstall-download-selection.md) |
| EPUB images/footnotes not device-verified | reader acceptance partial | ticket 14 follow-up |
| Storage-full/quota, password change, Chinese IME search path | manual coverage gaps | [23](issues/23-v1-release-device-acceptance.md) |
| First-sync/play/download timing not measured | performance acceptance partial; search p95 is measured | [23](issues/23-v1-release-device-acceptance.md) |
| OEM periodic-sync soak under Xiaomi background limits | reliability risk | [23](issues/23-v1-release-device-acceptance.md) |

## Scope audit

- No Play Store listing, signing hosting, iOS, tablet/TV/Wear, PDF, TTS, annotation,
  semantic search, queue/Up Next, sleep timer, or multi-user sync was added.
- Download-selection persistence is explicitly deferred to issue 24; no new contract
  was added in this sweep.
- Release signing is local/env-based; the keystore is not committed.

## Release decision

- [ ] RELEASE
- [x] **BLOCKED** — automated M3 hardening, API contract, LAN/release configuration,
  and static APK checks are complete, but the device-only P0 gates are not verified.
  The blockers are explicit and tracked in issues 23/24; this is not a feature gap.

```text
BLOCKED — 2026-11-16
Complete: Host/Android automated suites, OpenAPI/contract fixtures, release R8 build,
          signed APK static checks, LAN flavor build, sync hardening app-seam tests.
Pending:  release install/R8 smoke, 60-min background playback, Bluetooth/audio focus,
          Caddy/Tailscale HTTPS + user CA, reinstall recovery, download-selection restore.
Follow-up: issues 23 (device acceptance) and 24 (selection persistence).
```
