#!/usr/bin/env bash
# Guardrail: lint, types, tests, and documentation checks.
# Usage: ./scripts/check.sh [--fast|--full]
# --fast skips browser tests, FFmpeg integration tests, and docs; CI uses this mode.
# Full mode runs everything and requires FFmpeg/ffprobe on the host.
set -euo pipefail

cd "$(dirname "$0")/.."

mode=${1:-full}
# 4 workers is the stable sweet spot for this suite on the dev Mac.
# Set PYTEST_WORKERS=0 to run serially.
workers=${PYTEST_WORKERS:-4}
case "$mode" in
  fast|--fast)
    uv run ruff check src tests
    uv run mypy
    uv run pytest -q -n "$workers" -m "not browser and not network and not slow and not ffmpeg"
    ;;
  full|--full)
    uv run ruff check src tests
    uv run mypy
    uv run pytest -q -n "$workers"
    python3 scripts/check-docs.py
    ;;
  *)
    echo "usage: $0 [--fast|--full]" >&2
    exit 2
    ;;
esac
