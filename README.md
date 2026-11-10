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

`mlx-whisper` is the optional `asr` extra. `trove setup` downloads the local model (`mlx-community/whisper-large-v3-turbo`, about 1.6GB) on first use. Without the extra, transcription fails with `asr.not_configured` and the `uv sync --extra asr` hint; without the model it fails with `asr.model_missing` and the `trove setup` hint.

Open <http://127.0.0.1:8765>. `trove serve` also starts a built-in processing worker child process. For two-process deployment (or debugging), run only the API and start the worker separately:

```bash
uv run trove serve --no-worker
uv run trove worker
```

Data lives in `~/Trove` by default. Override it with `TROVE_HOME`.

## Test

```bash
./scripts/check.sh --fast   # 实现/CI：ruff + mypy + 非浏览器、非 FFmpeg 测试
./scripts/check.sh          # 提交/推送前：完整 pytest + 文档检查
```

`--fast` skips browser tests, real FFmpeg integration tests, and docs; GitHub Actions uses this mode. The full mode requires `ffmpeg`/`ffprobe` on the host. Network tests are excluded by default: `uv run pytest -m network`.

Diagnose search and index coverage from the terminal:

```bash
uv run trove search "道德经"
uv run trove search "道德经" --json
uv run trove index status
uv run trove index status --json
```

Rebuild the FTS search index from stored content with `uv run trove index rebuild`.
