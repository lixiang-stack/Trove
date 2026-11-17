# V1 acceptance sweep

- Ticket: [22 — V1 验收总检查](issues/22-v1-acceptance-sweep.md)
- Status: closed 2026-11-17 — automated and device sweep complete; final 60-min run explicitly skipped by user
- Decision: **BLOCKED** — remaining P0/security gates are explicit exceptions, not silent passes

This is a release checklist, not a feature backlog. Evidence links are repo paths or
ticket comments, not claims.

## Automated gates

| Gate | Command | Result |
| ---- | ------- | ------ |
| Host full tests | `./scripts/check.sh --full` | PASS 2026-11-16 — 388 collected; docs check included |
| Host fast CI | `./scripts/check.sh --fast` | PASS 2026-11-16 |
| Docs | `python3 scripts/check-docs.py` | PASS — 87 files |
| Android build/JVM/Compose/lint | `:app:assembleProdDebug :app:testProdDebugUnitTest :app:lintProdDebug :core:testDebugUnitTest :core:lintDebug :playback:testDebugUnitTest :playback:lintDebug :reader:testDebugUnitTest :reader:lintDebug` | PASS — 66 app tests, 90 core tests, 1 playback test, 3 reader tests |
| Release R8/resource shrink | `:app:assembleProdRelease` | PASS (signed and unsigned variants) |
| Signed release check | `scripts/android/release-check.sh` | PASS — signed, not debuggable, permissions allowlist, 9 MiB |
| LAN debug build | `:app:assembleLanDebug` | PASS |
| Instrumented core + platform manifest | `scripts/android/device-check.sh` | PASS — Android, API 36 |
| OpenAPI/contract fixtures | `uv run pytest -q tests/test_api_contract.py tests/test_contract_fixtures.py` | PASS |

## Real-device evidence

Android (`test-device`, Android 16 / API 36). The device was reconnected during the
final sweep; wireless playback/download evidence from M1/M2 is reused below and
the M3 checks below were run on the attached device.

| Area | Evidence | Result |
| ---- | -------- | ------ |
| Toolchain/cold start | [01](issues/01-android-toolchain-smoke.md) | PASS |
| Login/token/revocation | [09](issues/09-android-onboarding-auth.md) | PASS — debug localhost / adb reverse |
| Library initial/incremental/tombstone/revive | [10](issues/10-android-library-initial-sync.md) | PASS |
| Media3 session/notification/local playback | [11](issues/11-android-playback-service.md) | PARTIAL — session/notification/local playback PASS; first 60-min run stopped at 32:06 when the phone was used; clean 60-min run skipped by user 2026-11-17 |
| Downloads/foreground/resume/remove | [12](issues/12-android-downloads-offline.md) | PASS with exceptions — storage-full not exercised; metered-only wait + toggle verified |
| Transcript reading/search | [13](issues/13-android-transcript-reading.md) | PASS |
| EPUB reader/offline/search/position | [14](issues/14-android-epub-reader.md) | PASS — chapter nav, position restore, local image placeholder, footnote text/link verified 2026-11-17 |
| Offline EPUB | manual airplane-mode reopen | PASS — chapter 2/50% restored from disk |
| Offline progress sync | clone Host + airplane play | PASS — 32-min offline progress (1926s/in_progress) reached Host canonical after reconnect; auto-sync needed app foreground |
| Local/online search and 1k p95 | [15](issues/15-android-local-search.md) | PASS — FTS5 p95 <1s on device |
| Continue/tags/LWW conflict | [16](issues/16-android-continue-consumption-tags.md) | PASS — offline tag + canonical conflict |
| Add/share/podcast/retry | [17](issues/17-android-add-share-podcast.md) | PASS |
| Settings/notifications/battery/logout/clear | [18](issues/18-android-settings-sync-storage.md) | PASS with exceptions — OEM soak pending |
| Release APK install/R8 | manual adb install of signed `prodRelease` | PASS for install/launch; full R8 flow pending HTTPS login |
| Release cleartext rejection | manual login with `http://10.91.104.87:8767` | PASS — “正式版本只允许 HTTPS Host” |
| Reinstall Library/progress | uninstall + install `prodDebug` + login | PASS — 6 Items and Continue 40% restored |
| Return to real Host | switch reverse to real Host, force-stop/start | PASS — 4 real Items restored; clone-only Items removed |
| 60-min background playback | first run 32:06, then phone use; clean run 2 skipped by user | **SKIPPED / NOT VERIFIED** |
| Caddy user CA / Tailscale HTTPS | — | **NOT VERIFIED** — Tailscale MagicDNS did not resolve on device; CA install requires device PIN |
| `lan` flavor device connection/warning | build only | **NOT VERIFIED** on device |
| Offline progress queue -> Web canonical | — | Automated only |

## Manual loop

| Step | Result |
| ---- | ------ |
| Share link -> Host -> download -> airplane playback >=60 min -> lock screen/notification/Bluetooth/speed/resume | **SKIPPED by user 2026-11-17** — first run reached 32:06 then was interrupted by phone use; 60-min/Bluetooth/audio focus remain unverified |
| Download EPUB -> offline read/chapters/images/footnotes/in-book search/position | **PASS** — reader/chapters/offline/position; dot image and footnote text/link verified; in-book search covered by ticket 14 |
| Offline search downloaded content, Chinese two-character query, open match | **PASS** — FTS5 device test + ticket 15; UI IME path not scripted |
| Offline Tag/progress/status -> reconnect -> Web canonical | **PASS** for progress (clone Host canonical 1926s/in_progress); offline Tag/conflict covered by ticket 16 |
| Host delete -> tombstone; re-add revive; reinstall Library/progress | **PASS** for tombstone/revive and reinstall Library/progress; download selection exception tracked in 24 |
| Download interrupt/resume/sha/quota; token revoke; password change | **PARTIAL** — interrupt/resume/sha/remove/revoke PASS; quota/password change pending |
| Caddy/Tailscale HTTPS, user CA, release/lan flavor | **BLOCKED** |

## Known issues and follow-ups

| Issue | Impact | Follow-up |
| ----- | ------ | --------- |
| No adb device during part of final sweep | release install/R8 smoke and remaining P0 checks unverified until device reconnected; reinstall/launch now PASS | [23](issues/23-v1-release-device-acceptance.md) |
| 60-min background/lockscreen playback, Bluetooth, headphone/call audio focus | first run stopped at 32:06 when the phone was used; clean run was skipped by user decision | [23](issues/23-v1-release-device-acceptance.md) |
| Caddy user CA / Tailscale HTTPS / release full R8 flow | security/release acceptance incomplete | [23](issues/23-v1-release-device-acceptance.md) |
| Download selection is not persisted across reinstall | ticket 19 AC5 cannot be fully met without a contract change | [24](issues/24-reinstall-download-selection.md) |
| In-book search / Chinese IME UI path | covered by device FTS test, not scripted through IME | [23](issues/23-v1-release-device-acceptance.md) |
| Storage-full/quota, password change, Chinese IME search path | manual coverage gaps | [23](issues/23-v1-release-device-acceptance.md) |
| First-sync/play/download timing not measured | performance acceptance partial; search p95 is measured | [23](issues/23-v1-release-device-acceptance.md) |
| OEM periodic-sync soak under Xiaomi background limits | reliability risk | [23](issues/23-v1-release-device-acceptance.md) |

## Scope audit

- No Play Store listing, signing hosting, iOS, tablet/TV/Wear, PDF, TTS, annotation,
  semantic search, queue/Up Next, sleep timer, or multi-user sync was added.
- Download-selection persistence is explicitly deferred to issue 24; no new contract
  was added in this sweep.
- Release signing is local/env-based; the keystore is not committed.

## 2026-11-17 device sweep

- Verified the frozen-progress fix (`PositionTicker`) on device; UI position advances again after controller reconnect.
- Verified release-signed APK install/launch and release cleartext rejection.
- Verified reinstall restores Library/progress; returning to the real Host restores exactly its 4 Items and removes clone-only Items.
- Verified EPUB chapter navigation, local image placeholder, footnote text/link, offline reopen and position restore.
- Verified offline progress from a 32-minute airplane-mode run reached the Host canonical state after reconnect.
- Verified metered-only download waits for the “allow mobile network” switch.
- First 60-minute run stopped at 32:06 when the phone was unlocked/used; the user then explicitly skipped the clean 60-minute rerun on 2026-11-17.

## Release decision

- [ ] RELEASE
- [x] **BLOCKED** — automated M3 hardening, API contract, LAN/release configuration,
  static APK checks, and the device checks above are complete. The 60-minute P0 run
  was explicitly skipped by the user, and Caddy/Tailscale HTTPS plus a full release
  HTTPS business flow remain unverified. These are explicit release risks tracked in
  issues 23/24, not silent passes.

```text
BLOCKED — 2026-11-17
Complete: Host/Android automated suites, OpenAPI/contract fixtures, release R8 build,
          signed APK static checks, device install/launch/cleartext rejection,
          reinstall Library/progress, EPUB offline/image/footnote, offline progress sync.
Explicit exception: 60-minute background playback skipped by user (first run 32:06,
          interrupted by phone use); Bluetooth/audio focus unverified.
Pending:  Caddy/Tailscale HTTPS + user CA, full release HTTPS business flow,
          download-selection restore (issue 24).
Follow-up: issue 23 (device acceptance) and issue 24 (selection persistence).
```
