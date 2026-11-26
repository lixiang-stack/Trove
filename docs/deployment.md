# Deployment

Trove supports two self-hosted paths with the same CLI, configuration, content
packages, and `/api/health` contract:

- Docker Compose on Linux or macOS for a reproducible install.
- Native launchd on macOS for the existing Apple Silicon deployment.

Docker is not required; launchd remains fully supported.

## Docker Compose

The base image contains Python, `uv`-installed dependencies, FFmpeg/ffprobe, and
`yt-dlp`. It runs as the non-root `trove` user with `TROVE_HOME=/data`; the
`trove-data` named volume holds the database, library, cache, logs, settings, and
backups.

### Quick start

```bash
TROVE_PASSWORD='your-password' docker compose up -d --build
open http://127.0.0.1:8765
```

`init` applies migrations before `api` and `worker` start. The API publishes only
on `127.0.0.1` by default. Override the host port with `TROVE_HOST_PORT`; bind
another interface only behind a trusted reverse proxy.

All configuration lives in `~/.config/trove` inside the containers, persisted in
the `trove-config` volume; there is no `.env` file. On first start `TROVE_PASSWORD`
is written to `~/.config/trove/password` (mode `0600`) and the entrypoint exports
`TROVE_PASSWORD_FILE`; the app hashes it into `/data/config.toml` only when it
changes. Later `up` calls reuse the file, so the environment variable is only
needed when changing the password. Changing it invalidates existing sessions and
device tokens. Verify inside the container:

```bash
docker compose exec api trove doctor --json
```

Services:

| Service | Command | Purpose |
| --- | --- | --- |
| `init` | `trove db upgrade` (+ `trove setup` for ASR images) | one-shot migration/model job |
| `api` | `trove serve --no-worker --host 0.0.0.0` | HTTP API and web shell |
| `worker` | `trove worker` | default `all` pool |
| `worker-download` | `trove worker --pool download` | acquisition/extraction pool |
| `worker-asr` | `trove worker --pool asr` | transcription pool |
| `worker-llm` | `trove worker --pool llm` | organization pool |
| `worker-index` | `trove worker --pool index` | single-writer index pool |
| `caddy` | Caddy 2 | optional TLS terminator (`caddy` profile) |

The split pool services are in the `pools` profile. Stop the default worker
before starting them, otherwise both claim tasks:

```bash
docker compose stop worker
docker compose --profile pools up -d \
  worker-download worker-asr worker-llm worker-index
```

### ASR

ASR is enabled by default. The first `init` downloads the Paraformer models
(about 1.25 GB) into `/data/models` on the `trove-data` volume; later starts
reuse them. `trove doctor` inside the ASR container reports the model as present.

To build the smaller book-only image without transcription:

```bash
TROVE_INSTALL_ASR=false docker compose build
docker compose up -d
```

### LLM configuration

The `trove-config` volume is mounted at `~/.config/trove` and starts with an
`llm.toml` containing `enabled = false`, so the Host runs without organization
until configured. Copy the host file into the volume, then restart both
processes:

```bash
install -d -m 700 ~/.config/trove
${EDITOR:-vi} ~/.config/trove/llm.toml
docker compose exec -T worker sh -c \
  'cat > /home/trove/.config/trove/llm.toml' < ~/.config/trove/llm.toml
docker compose restart api worker
```

To inspect or update the container copy directly:

```bash
docker compose exec worker cat /home/trove/.config/trove/llm.toml
```

To run without organization, set `enabled = false` before copying.

### TLS with Caddy

The default compose file does not expose TLS. The optional profile starts Caddy
with `deploy/Caddyfile`:

```bash
docker compose --profile caddy up -d caddy
```

Edit `deploy/Caddyfile` to use your hostname; Caddy obtains certificates
automatically when ports 80/443 are reachable. Keep the API published only on
loopback or remove its `ports` entry when Caddy is the only entry point. For
Tailscale, point `reverse_proxy` at the API container or use
[Tailscale Serve](#optional-tailscale-serve-acceptance-skipped).

### Image version, size, and architecture

Tag the image with the `trove --version` value so deployments and `/api/health`
agree:

```bash
TROVE_IMAGE_TAG="$(uv run trove --version | cut -d' ' -f2)" docker compose build
```

`docker-compose.yml` forwards `TROVE_BUILD_COMMIT` and `TROVE_BUILD_TIME` as
build args; they appear in `/api/health` under `build`.

Dependency layers are cached independently of README/source changes, so
switching worktrees and rebuilding only refreshes the final layers as long as
`pyproject.toml` and `uv.lock` are unchanged. Do not run `docker image prune` if
you want to keep that cache, and use `docker compose up -d` without `--build`
when the current image already matches the checkout. The Dockerfile is
architecture-neutral and builds natively on ARM64 (Apple
Silicon, arm64 Linux) and AMD64 (x86_64 Linux). Multi-arch manifests are not
published; build on the target architecture. The default ASR image is about
3.5 GB because it includes the PyTorch/FunASR stack; `INSTALL_ASR=false` produces
the roughly 230 MB book-only image. Exact sizes depend on the PyTorch wheel for
the target platform.

### Data, backups, and cleanup

`docker compose down` removes containers but keeps the `trove-data` and
`trove-config` volumes. `docker compose down -v` permanently deletes both,
including settings, the password, LLM config, and the library. Back up the
database with a SQLite online backup while the Host is running; the database path
inside the container is `/data/trove.db` and the library is `/data/library`.

Run the Docker smoke test with:

```bash
scripts/docker-smoke.sh
```

It builds the base image, processes an EPUB fixture, restarts the containers,
removes/recreates them without deleting the volume, and then cleans up.

## macOS launchd

The original deployment targets the user's own Apple Silicon Mac. The API and
worker run as two native launchd LaunchAgents; no Docker, cloud host, or public
reverse proxy is required. The API binds `127.0.0.1` and phones reach it through
Caddy with an internal CA. Tailscale Serve remains documented as an optional
alternative, but its acceptance is skipped by user decision (2026-11-13).

See [ADR-0006](adr/0006-native-launchd-tailscale.md) for the decision.

### Prerequisites

```bash
brew install uv ffmpeg
# Optional: install the Tailscale app and sign in.
```

Python 3.12 is managed by `uv`. A clean checkout plus the commands below is enough.

### First install

```bash
git clone <repo> ~/src/Trove
cd ~/src/Trove
uv sync --extra asr
uv run trove db upgrade
uv run trove auth set-password
uv run trove setup          # downloads the FunASR models (~1.25 GB) and checks tools
uv run trove doctor
```

To avoid the interactive password step, export `TROVE_PASSWORD` or point
`TROVE_PASSWORD_FILE` at a secret before the first command; startup hashes it
into `config.toml` and only rewrites it when the value changes.

`trove setup` and `trove doctor` check FFmpeg/ffprobe, `yt-dlp`, SQLite FTS5, data
directory permissions, the database revision, the login password, the ASR model,
and whether the listen port is free. `trove doctor` is safe to rerun at any time.

Install the agents:

```bash
scripts/install-launchd.sh
```

The script applies migrations, renders the plists under `~/Library/LaunchAgents`,
and loads them with `launchctl`:

| Agent             | Command                                  | Log                              |
| ----------------- | ---------------------------------------- | -------------------------------- |
| `com.trove.api`   | `uv run trove serve --no-worker --host 127.0.0.1` | `~/Trove/logs/com.trove.api.log` |
| `com.trove.worker`| `uv run trove worker`                    | `~/Trove/logs/com.trove.worker.log` |

To split resource classes, render named agents instead of the default `all`
worker:

```bash
uv run trove service install --pool all --pool asr
```

Named agents use `com.trove.worker.<pool>` and run `trove worker --pool <pool>`;
the `asr` agent is `com.trove.worker.asr` with its own log file. Re-run the
command with the same `--pool` values to update them, and pass the same values to
`trove service uninstall` to remove them.

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

### Worker leases, retries, and dead letters

Workers claim StageTasks by pool. The default `trove worker` runs the `all` pool
as one serial claimer, so existing installs keep their behavior. Named pools
separate resource classes:

| Pool       | Stages                                        | Default concurrency |
| ---------- | --------------------------------------------- | ------------------- |
| `all`      | every stage                                   | 1                   |
| `download` | downloading, extracting audio/text            | 3                   |
| `asr`      | transcribing                                  | 1                   |
| `llm`      | organizing                                    | 2                   |
| `index`    | indexing                                      | 1 (always)          |

```bash
uv run trove worker --pool asr                  # only transcription
uv run trove worker --pool download --pool asr  # two independent claim loops
uv run trove worker --pool download --concurrency 4
uv run trove worker --stages downloading,extracting_audio
```

Repeat `--pool` to run several pools in one process. `--concurrency` applies to
each selected pool. Indexing is serialized inside a worker process, including
`all` and custom stage sets, but the lock is process-local: run only one worker
process whose pools include `indexing` (prefer the dedicated `index` agent) so
SQLite/FTS5 writes stay single-writer. `--stages` builds a custom pool and cannot
be combined with `--pool`. Unknown pools or stages fail at startup with the valid
choices.

Set defaults with `TROVE_WORKER_POOLS` (comma-separated, default `all`) and
`TROVE_DOWNLOAD_CONCURRENCY`, `TROVE_ASR_CONCURRENCY`, `TROVE_LLM_CONCURRENCY`,
or `TROVE_INDEX_CONCURRENCY`. Empty or non-positive concurrency values fail
startup. Each pool worker renews a 25-second lease every 5 seconds, and a shared
reaper thread checks for expired leases every 5 seconds. If a worker dies, its
task is requeued once the lease expires; only that stage is retried and completed
earlier stages are kept.

On SIGTERM the worker stops claiming new tasks and waits up to
`TROVE_WORKER_SHUTDOWN_TIMEOUT_SECONDS` (default 30) for in-flight tasks to
commit. Tasks still running after the timeout stop renewing their lease; the next
worker's reaper requeues them once the lease expires. `/api/health` lists each pool's `concurrency`, `active`
count, `queued` depth, claimed `stages`, and current `run_id` under
`worker.pools`. Each worker process writes its own heartbeat file so split pool
processes aggregate instead of overwriting one another.

Stage failures follow `domain/retry.py`:

- Retryable errors (`download.network`, `llm.failed`, and transient
  `storage.error`) back off with jitter instead of blocking the worker:
  30s, 2m, then 10m, written to the task's `available_at`.
- Permanent errors (login/region restrictions, unsupported input, EPUB/DRM
  failures, missing LLM/ASR configuration) fail immediately and do not consume
  a retry.
- ASR `asr.failed` is not retried automatically by default because the
  `transcribing` stage allows one attempt. Raise `TROVE_STAGE_MAX_ATTEMPTS` for
  that stage only when your ASR failures are known to be transient.
- A failed or cancelled Run no longer retries automatically.
- Per-stage attempt limits default to 3 for downloading, extracting, and
  organizing, 1 for transcribing, and 2 for indexing. Override them with
  `TROVE_STAGE_MAX_ATTEMPTS`, for example
  `TROVE_STAGE_MAX_ATTEMPTS="downloading=4,transcribing=2"`.
- Exhausting the budget moves the task to `dead`, fails the Run with
  `run.dead`, keeps the last error on the task, and leaves the Item waiting for
  a manual retry. Lease expiry always allows one crash recovery, even for a
  one-attempt stage such as transcribing.

Tune lease timing with `TROVE_WORKER_LEASE_SECONDS`,
`TROVE_WORKER_HEARTBEAT_SECONDS`, and `TROVE_WORKER_REAPER_INTERVAL_SECONDS`.
The Host refuses to start when the lease is not longer than the heartbeat.

### External-call cache

Automatic retries and worker reclaims reuse completed external work:

- AI results in `ai.json`/`AiResult` carry `input_sha256`. A matching
  `(Item, prompt version, model, input hash)` is reused with no LLM call and no
  new cost.
- Transcripts in `transcript.json` carry the audio artifact's `input_sha256` and
  the ASR model. A matching `(audio hash, model)` is reused with no ASR call.
- `POST /api/items/{id}/reprocess`, the Item page's "重新整理/重新转写" buttons,
  and `trove collection reprocess --reset-ai-tags` are explicit reruns: they
  bypass the cache by setting the Run's `force` flag.
- `POST /api/items/{id}/retry` and worker recovery are not explicit reruns;
  they reuse matching cached results. Old `ai.json`/transcript files without a
  hash are treated as cache misses and regenerate normally.

### Optional: Tailscale Serve (acceptance skipped)

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

#### Caddy HTTPS (accepted path)

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

### Upgrade, backup, and rollback

`trove db upgrade` is repeatable. Before applying migrations it writes an online
SQLite backup to `TROVE_HOME/backups/trove-<revision>-<UTC timestamp>.db` with
mode `0600`. Backups are created only when the database is non-empty and not
already at the target revision; the newest five are kept. On failure the CLI
prints the error and the exact restore command, and the database stays at the old
revision. Content packages are written before database commits, so a crash leaves
either the old or the new state.

Native upgrade:

```bash
cd ~/src/Trove
git pull
uv sync --locked --extra asr
uv run trove db upgrade
uv run trove doctor
launchctl kickstart -k gui/$(id -u)/com.trove.api
launchctl kickstart -k gui/$(id -u)/com.trove.worker
```

Docker upgrade (the `init` service applies migrations):

```bash
git pull
TROVE_IMAGE_TAG="$(uv run trove --version | cut -d' ' -f2)" docker compose build
docker compose up -d
docker compose exec api trove doctor
```

Rollback steps:

1. Stop the API and worker so no process holds the database:
   `launchctl bootout gui/$(id -u)/com.trove.api` and the worker label, or
   `docker compose stop api worker`.
2. Restore the pre-upgrade backup and remove stale WAL files:

   ```bash
   cp ~/Trove/backups/trove-0008_run_force-20261126T000000Z.db ~/Trove/trove.db
   rm -f ~/Trove/trove.db-wal ~/Trove/trove.db-shm
   ```

   For Docker, restore from the backup stored on the same volume:

   ```bash
   docker compose run --rm --no-deps --entrypoint sh api -c \
     'cp /data/backups/trove-0008_run_force-20261126T000000Z.db /data/trove.db && \
      rm -f /data/trove.db-wal /data/trove.db-shm'
   ```
3. Check out the previous tag/image and reinstall that version:
   `git checkout v<previous>` + `uv sync --locked --extra asr`, or
   `TROVE_IMAGE_TAG=<previous> docker compose up -d`.
4. Start the API and worker and run `trove doctor`. The old version reads
   existing content packages.

If a content package `manifest.json` has a newer `schema_version` than the
running code, `serve` and `worker` refuse to start with an upgrade/restore
message instead of writing a partial package. Restore the compatible backup or
upgrade Trove first.

### Doctor JSON

`trove doctor --json` is stable and jq-parseable. The exit code is `0` exactly
when `ok` is true:

```json
{
  "ok": true,
  "checks": [
    {
      "name": "database_revision",
      "status": "ok",
      "message": "Database migration: 0009_external_call_cache",
      "fix": ""
    }
  ],
  "versions": {
    "trove": "0.1.0",
    "python": "3.12.14",
    "ffmpeg": "ffmpeg version 7.1",
    "ffprobe": "ffprobe version 7.1",
    "yt_dlp": "2026.10.26",
    "sqlite": "3.54.1",
    "asr_model": "paraformer-zh"
  }
}
```

`status` is `ok`, `warn`, or `fail`; `warn` does not fail the command. Missing
tools, a missing ASR model, an unmigrated database, an occupied port, unsupported
content-package schemas, and a low disk fail. A stale or missing worker heartbeat
and 100 MB–1 GB of free disk warn. `fix` contains only a command or documentation
link. Every check is still emitted when earlier checks fail.

`GET /api/health` adds a `build` object next to the existing fields:

```json
"build": {
  "version": "0.1.0",
  "commit": "abc123def456",
  "build_time": "2026-11-26T00:00:00Z"
}
```

The fields are additive; Android and CLI clients keep using `api_version` and the
existing `host`, `database`, and `worker` objects.

### Release checklist

`scripts/release-check.sh` runs the read-only gates. A release also needs:

1. Bump the version in `pyproject.toml` and `src/trove/__init__.py`; write the
   release notes for the tag.
2. Run `./scripts/check.sh --full` and the migration test from an older revision
   to head on a temporary `TROVE_HOME`.
3. Run `uv run trove doctor --json` against the staging Host; require `ok: true`.
4. Build and tag the image with the same version and build metadata:

   ```bash
   VERSION="$(uv run trove --version | cut -d' ' -f2)"
   TROVE_IMAGE_TAG="$VERSION" \
     TROVE_BUILD_COMMIT="$(git rev-parse --short=12 HEAD)" \
     TROVE_BUILD_TIME="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
     docker compose build
   ```

5. Tag the commit (`git tag "v$VERSION"`) and publish the image with the same tag.
6. Deploy with `launchctl kickstart -k` or `docker compose pull`/`up -d`, then
   confirm `/api/health` has the new `build.commit` and a fresh worker heartbeat.
7. Keep the pre-upgrade database backup until the new version has processed a
   test Item and the rollback steps above have been exercised.

### Re-run ASR

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

### Backups

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

### Android devices and resync

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

### Logs and sleep

The application log rotates at 10 MB with five backups:
`~/Trove/logs/trove.log`. Per-Run logs live in `~/Trove/logs/runs/<run-id>.log` and
are tailed on the Item page. launchd stdout/stderr files only receive process
startup messages.

To keep the Mac awake while a long Run is processing:

```bash
caffeinate -i -w "$(pgrep -f 'trove.cli worker' | head -1)"
```

This is optional; launchd and SQLite recovery handle sleep/restart safely.

### Uninstall

```bash
scripts/uninstall-launchd.sh
```

This removes only the two plists and stops the agents. It does not delete
`~/Trove`, content packages, uploads, logs, the database, or any original file.
If you also want to remove the application checkout, do that manually after
confirming your backups.

### Deployment checklist

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

### Troubleshooting

- `trove doctor` lists missing tools, model, FTS5, permissions, migration, and
  port problems with the command or documentation link to fix each. For a busy
  port, stop the other process or choose another `TROVE_PORT`; a running Trove
  is reported separately and is not a failure.
- If the worker restarts repeatedly, inspect
  `~/Trove/logs/com.trove.worker.log` and `~/Trove/logs/trove.log`; tasks whose
  worker died are requeued after their lease expires, and items fail with
  `run.dead` after three attempts.
- PWA installation is optional and its acceptance is skipped; HTTPS/Caddy is still
  required for Media Session and normal browser use.
- If the app is reachable locally but not over Caddy, check the Caddy reverse proxy
  and that the API is still bound to `127.0.0.1`. Tailscale troubleshooting is
  optional and its acceptance is skipped.
