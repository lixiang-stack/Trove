# Trove

Trove is a personal long-content library: audio is the primary way to consume, text is the substrate for organization and retrieval.

## Run

```bash
uv sync --extra asr
uv run trove db upgrade
uv run trove auth set-password
uv run trove setup
uv run trove doctor
uv run trove serve
```

`funasr` is the optional `asr` extra. `trove setup` downloads the local FunASR Paraformer-zh model (about 1.25GB: 953MB ASR, 292MB punctuation, 4MB VAD) on first use. Without the extra, transcription fails with `asr.not_configured` and the `uv sync --extra asr` hint; without the model it fails with `asr.model_missing` and the `trove setup` hint. The ASR runs on CPU; no GPU is required. See [ADR 0013](docs/adr/0013-paraformer-local-asr.md) for the benchmark against the previous `mlx-whisper` setup.

Open <http://127.0.0.1:8765>. `trove serve` also starts a built-in processing worker child process. For two-process deployment (or debugging), run only the API and start the worker separately:

```bash
uv run trove serve --no-worker
uv run trove worker
```

Data lives in `~/Trove` by default. Override it with `TROVE_HOME`.

For auto-start at login, Caddy/Tailscale HTTPS, upgrades, backups, and uninstall,
follow [docs/deployment.md](docs/deployment.md). Android build/signing/CA notes are
in [docs/android.md](docs/android.md). The security regression checklist is in
[docs/security.md](docs/security.md); dependency licenses are listed in
[docs/licenses.md](docs/licenses.md).

## Docker

For a reproducible self-hosted install on Linux or macOS:

```bash
docker compose up -d --build
docker compose exec api trove auth set-password
open http://127.0.0.1:8765
```

Data lives in the `trove-data` named volume. The default image has no ASR stack;
build with `TROVE_INSTALL_ASR=true docker compose build` to transcribe. Split
worker pools, ASR, TLS, backups, and cleanup are covered in
[docs/deployment.md#docker-compose](docs/deployment.md#docker-compose).

## Re-run ASR

Existing Items keep their stored transcripts until you queue a new transcribing run. A re-run reuses the existing `audio.m4a`; it does not download or extract audio again.

Single Item: open the Item page and click **重新转写（不重新下载）**. The API equivalent is `POST /api/items/<item_id>/reprocess` with `{"from_stage": "transcribing"}`.

Whole Collection:

```bash
uv run trove collection reprocess <collection_id> --from-stage transcribing
```

The run is executed by the worker, so the worker must be running the same code/model. `--from-stage organizing` only refreshes summaries/tags and does not re-transcribe. See [Re-run ASR](docs/deployment.md#re-run-asr) for ID lookup, prerequisites, and caveats.

## Configuration

Application secrets live in `~/Trove/.env`; Trove creates the file with `0600` permissions on first run. LLM settings live separately in `~/.config/trove/llm.toml`.

### LLM configuration

Trove reads LLM settings only from `~/.config/trove/llm.toml`. `model` and `base_url` are required; `api_key` is required for OpenAI-compatible providers.

```bash
install -d -m 700 ~/.config/trove
${EDITOR:-vi} ~/.config/trove/llm.toml
chmod 600 ~/.config/trove/llm.toml
```

```toml
model = "deepseek-flash"
base_url = "https://api.deepseek.com/v1"
api_key = "sk-your-key"
```

Any OpenAI-compatible endpoint works. For a local Ollama server:

```toml
model = "qwen3.5:4b"
base_url = "http://localhost:11434/v1"
api_key = "ollama"
```

Organization always requests `response_format = {"type": "json_object"}` and `reasoning_effort = "none"`, so thinking models return the final JSON directly.

Other fields have code defaults and may be omitted: `enabled`, `chunk_chars`, `max_calls_per_item`, `max_output_tokens_per_call`, `max_input_tokens_per_item`, `input_cost_per_million`, `output_cost_per_million`, and `timeout_seconds`. Values in the file override the defaults. An existing `~/.config/trove/llm_api_key` file is no longer read; move its contents into `api_key`.

The file is read at startup, so restart `uv run trove serve` after editing it. Without a complete configuration, processing still produces and keeps the audio and transcript, but the `organizing` stage fails with `llm.not_configured`. Set the settings and retry the Processing Run from the Item page to finish organization. Transcript and book text are sent to the configured LLM in chunks while organizing; audio and source files stay on the Mac.

To disable organization entirely, set `enabled = false` in `~/.config/trove/llm.toml`.

## Test

```bash
./scripts/check.sh --fast   # 实现/CI：ruff + mypy + 非浏览器、非 FFmpeg 测试
./scripts/check.sh          # 提交/推送前：完整 pytest + 文档检查
```

`--fast` skips browser tests, real FFmpeg integration tests, and docs; GitHub Actions uses this mode. The full mode requires `ffmpeg`/`ffprobe` on the host and Playwright's bundled Chromium headless shell (`uv run playwright install chromium` once). Tests run with 4 xdist workers by default; set `PYTEST_WORKERS=0` to run serially. Both modes skip network tests; run them explicitly with `uv run pytest -m network`.

Diagnose search and index coverage from the terminal:

```bash
uv run trove search "道德经"
uv run trove search "道德经" --json
uv run trove index status
uv run trove index status --json
```

Rebuild the FTS search index from stored content with `uv run trove index rebuild`.

After changing tag generation, or to collapse a long-lived collection tag list, re-run organization for every episode in a collection:

```bash
uv run trove collection reprocess <collection_id> --reset-ai-tags
```

`--reset-ai-tags` deletes the collection's AI tags before queueing the `organizing` runs; user-added tags are kept. The worker must be running to process the queued runs.
