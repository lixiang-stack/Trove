# macOS deployment: launchd + Caddy HTTPS

MVP deployment targets the user's own Apple Silicon Mac. The API and worker run as
two native launchd LaunchAgents; there is no Docker, cloud host, or public reverse
proxy. The API binds `127.0.0.1` and phones reach it through Caddy with an internal
CA. Tailscale Serve remains documented as an optional alternative, but its
acceptance is skipped by user decision (2026-11-13).

See [ADR-0006](adr/0006-native-launchd-tailscale.md) for the decision.

## Prerequisites

```bash
brew install uv ffmpeg
# Optional: install the Tailscale app and sign in.
```

Python 3.12 is managed by `uv`. A clean checkout plus the commands below is enough.

## First install

```bash
git clone <repo> ~/src/Trove
cd ~/src/Trove
uv sync --extra asr
uv run trove db upgrade
uv run trove auth set-password
uv run trove setup          # downloads the FunASR models (~1.25 GB) and checks tools
uv run trove doctor
```

`trove setup` and `trove doctor` check FFmpeg/ffprobe, `yt-dlp`, SQLite FTS5, data
directory permissions, the database revision, the login password, the ASR model,
and whether the listen port is free. `trove doctor` is safe to rerun at any time.

Install the agents:

```bash
scripts/install-launchd.sh
```

The script applies migrations, renders two plists under `~/Library/LaunchAgents`,
and loads them with `launchctl`:

| Agent             | Command                                  | Log                              |
| ----------------- | ---------------------------------------- | -------------------------------- |
| `com.trove.api`   | `uv run trove serve --no-worker --host 127.0.0.1` | `~/Trove/logs/com.trove.api.log` |
| `com.trove.worker`| `uv run trove worker`                    | `~/Trove/logs/com.trove.worker.log` |

Both use `RunAtLoad` and `KeepAlive`, so they start at login and restart after a
crash. `TROVE_HOME` defaults to `~/Trove`; override it with `TROVE_HOME=/path
scripts/install-launchd.sh`. Use `scripts/install-launchd.sh --dry-run` to render
and validate the plists without loading them.

Verify:

```bash
launchctl print gui/$(id -u)/com.trove.api | head -20
launchctl print gui/$(id -u)/com.trove.worker | head -20
curl http://127.0.0.1:8765/api/health
```

Open <http://127.0.0.1:8765>, sign in, and add a test item. Killing either process
should make launchd restart it; queued and running Runs recover from SQLite.

## Worker leases and recovery

`trove worker` claims one StageTask at a time. It renews a 25-second lease every
5 seconds and a reaper thread checks for expired leases every 5 seconds. If a
worker dies, its task is requeued once the lease expires and only that stage is
retried; completed earlier stages are kept. After three attempts the task becomes
`dead`, the Run fails with `run.dead`, and the Item needs a manual retry.

Tune the defaults with `TROVE_WORKER_LEASE_SECONDS`,
`TROVE_WORKER_HEARTBEAT_SECONDS`, and `TROVE_WORKER_REAPER_INTERVAL_SECONDS`.
The Host refuses to start when the lease is not longer than the heartbeat.

## Optional: Tailscale Serve (acceptance skipped)

> Tailscale Serve remains documented as an alternative, but its acceptance is
> skipped by user decision (2026-11-13). Use the Caddy path below for the accepted
> HTTPS setup.

Keep Trove bound to loopback. Tailscale terminates TLS and forwards from the tailnet:

```bash
tailscale serve --bg 8765
tailscale serve status
```

The phone opens the `https://<machine>.<tailnet>.ts.net` URL shown by Tailscale.
HTTPS gives Media Session and PWA installation a secure context. Do not use
`trove serve --lan` for daily use; it is only for a trusted LAN without HTTPS and
does not promise Media Session/PWA behavior.

### Caddy HTTPS (accepted path)

```bash
brew install caddy
```

`~/Caddyfile`:

```caddyfile
https://trove.local {
  tls internal
  reverse_proxy 127.0.0.1:8765
}
```

```bash
caddy trust
caddy start --config ~/Caddyfile
```

Install Caddy's internal root certificate on the phone and use
`https://trove.local` with local DNS/mDNS resolution. On Android, install the root
as a user CA under Settings → Security → Encryption & credentials → Install a
certificate → CA certificate; the app's network security config trusts user CAs.
Tailscale with a public certificate is simpler if you do not want a user CA. Caddy
is only a TLS terminator; authentication, CSP, and Range handling still come from
Trove. See [android.md](android.md) for the Android steps.

## Upgrade

```bash
cd ~/src/Trove
git pull
uv sync --locked --extra asr
uv run trove db upgrade
launchctl kickstart -k gui/$(id -u)/com.trove.api
launchctl kickstart -k gui/$(id -u)/com.trove.worker
```

`trove db upgrade` is repeatable. Content packages are written before database
commits, so a crash during upgrade leaves either the old or the new state. Run
`uv run trove doctor` after upgrading.

## Re-run ASR

Use this after changing the ASR model or when an Item's transcript needs to be
regenerated. The existing audio artifact is reused; Trove does not download or
extract media again. The new run executes `transcribing`, `organizing`, and
`indexing`; the old `transcript.json` is overwritten and the AI summary/tags are
regenerated from the new transcript.

Prerequisite: the running worker must be on the checkout that contains the ASR
change. Restart the worker after deploying the new code. Do not run two workers
against the same `~/Trove`.

```bash
cd ~/src/Trove
uv sync --locked --extra asr
uv run trove doctor          # funasr: OK and ASR model: paraformer-zh
launchctl kickstart -k gui/$(id -u)/com.trove.api
launchctl kickstart -k gui/$(id -u)/com.trove.worker
```

Find the Item or Collection id:

```bash
sqlite3 ~/Trove/trove.db "select id, title from items order by updated_at desc limit 20;"
sqlite3 ~/Trove/trove.db "select id, title from collections;"
```

Single Item:

- Web: open the Item page and click **重新转写（不重新下载）**.
- API: `POST /api/items/<item_id>/reprocess` with `{"from_stage": "transcribing"}`.
- Scripted, using the Host runtime (queues the run; the worker executes it):

```bash
uv run python - <<'PY'
from trove.composition import build_runtime
from trove.config import load_config

runtime = build_runtime(load_config())
runtime.processing.reprocess("<item_id>", "transcribing")
PY
```

Whole Collection:

```bash
uv run trove collection reprocess <collection_id> --from-stage transcribing
```

`--from-stage organizing` only refreshes AI summaries/tags and does not re-run
ASR. `--from-stage transcribing` is rejected for EPUB Items; they do not have an
ASR stage. Watch progress on the Item page; per-Run logs are linked there and
stored under `~/Trove/logs/runs/<run-id>.log`.

Expected cost on the M1 Pro reference host: about 2.8GB peak RSS, one CPU core,
and roughly 7–8x realtime (about 8 minutes per audio hour). If the audio artifact
is missing, the run fails with an ASR error; re-ingest the Item instead. To keep
the old transcript for comparison, copy it before queueing:

```bash
cp ~/Trove/library/<item_id>/transcript.json \
  /tmp/trove-transcript-<item_id>.json
```

If the LLM is not configured, the new transcript is still written and indexed,
but the `organizing` stage fails; configure the LLM and retry the Item.

## Backups

Trove does not run cloud sync. Back up what you cannot rebuild:

```bash
# SQLite online backup (safe while the Host is running).
sqlite3 ~/Trove/trove.db ".backup '$HOME/Trove-backup/trove-$(date +%F).db'"

# Portable content packages, transcripts, books, and AI results.
rsync -a --delete ~/Trove/library/ ~/Trove-backup/library/

# One-off zip export through the UI or API.
curl -OJ -b cookies.txt http://127.0.0.1:8765/api/export
```

The SQLite database holds metadata, processing state, progress, and the search
index. The content package under `~/Trove/library/<item-id>/` is the portable fact
source; `uv run trove index rebuild` rebuilds search from it. Original local files
are never moved or deleted by Trove.

## Android devices and resync

Android uses revocable device tokens instead of the browser session:

```bash
uv run trove device list
uv run trove device revoke <device-id>
```

Revoking a token takes effect on the next request; changing the Host password
invalidates every device token. After restoring an older database backup, rotate
the sync epoch so phones discard their cursors and perform a full resync:

```bash
uv run trove sync reset-epoch
```

The Host backfills `version`, `content_seq`, and `state_seq` for existing Items
during `trove db upgrade`, so back up the database before upgrading.

## Logs and sleep

The application log rotates at 10 MB with five backups:
`~/Trove/logs/trove.log`. Per-Run logs live in `~/Trove/logs/runs/<run-id>.log` and
are tailed on the Item page. launchd stdout/stderr files only receive process
startup messages.

To keep the Mac awake while a long Run is processing:

```bash
caffeinate -i -w "$(pgrep -f 'trove.cli worker' | head -1)"
```

This is optional; launchd and SQLite recovery handle sleep/restart safely.

## Uninstall

```bash
scripts/uninstall-launchd.sh
```

This removes only the two plists and stops the agents. It does not delete
`~/Trove`, content packages, uploads, logs, the database, or any original file.
If you also want to remove the application checkout, do that manually after
confirming your backups.

## Deployment checklist

Use this after installing or upgrading on the real Mac:

- [ ] `uv run trove doctor` exits 0 (or every warning has a fix).
- [ ] Both `launchctl print` commands show the agents running.
- [ ] `curl http://127.0.0.1:8765/api/health` returns `host`, `database`, and a
      fresh `worker` heartbeat.
- [ ] Sign in from the desktop, add a test item, and confirm the worker completes it.
- [ ] Kill the API process; launchd restarts it and `/api/health` recovers.
- [ ] Kill the worker process while idle; launchd restarts it and the heartbeat is
      fresh again.
- [ ] Reboot the Mac; both agents start at login and the queue is available.
- [ ] From the phone over Caddy HTTPS: sign in, play an item, seek, change speed,
      lock the screen, and confirm progress resumes. Tailscale is optional and skipped.
- [ ] Run a search from the phone and open a result to its transcript/book
      paragraph.
- [ ] Record the versions: `trove --version`, `caddy version`, `ffmpeg -version`.

## Troubleshooting

- `trove doctor` lists missing tools, model, FTS5, permissions, migration, and
  port problems with the command to fix each.
- If the worker restarts repeatedly, inspect
  `~/Trove/logs/com.trove.worker.log` and `~/Trove/logs/trove.log`; tasks whose
  worker died are requeued after their lease expires, and items fail with
  `run.dead` after three attempts.
- PWA installation is optional and its acceptance is skipped; HTTPS/Caddy is still
  required for Media Session and normal browser use.
- If the app is reachable locally but not over Caddy, check the Caddy reverse proxy
  and that the API is still bound to `127.0.0.1`. Tailscale troubleshooting is
  optional and its acceptance is skipped.
