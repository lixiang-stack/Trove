# Trove

Trove is a personal long-content library: audio is the primary way to consume, text is the substrate for organization and retrieval.

## Run

```bash
uv sync
uv run trove db upgrade
uv run trove auth set-password
uv run trove doctor
uv run trove serve
```

Open <http://127.0.0.1:8765>. `trove serve` also starts a built-in processing worker child process. For two-process deployment (or debugging), run only the API and start the worker separately:

```bash
uv run trove serve --no-worker
uv run trove worker
```

Data lives in `~/Trove` by default. Override it with `TROVE_HOME`.

## Test

```bash
uv run pytest
uv run ruff check src tests
uv run mypy
python3 scripts/check-docs.py
```

Network tests are excluded by default: `uv run pytest -m network`.
