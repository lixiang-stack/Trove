#!/usr/bin/env bash
# Guardrail: lint, types, tests, and documentation checks.
# Usage: ./scripts/check.sh [--fast|--full]
# --fast skips browser tests and docs for the implementation loop; pre-push runs full.
set -euo pipefail

cd "$(dirname "$0")/.."

mode=${1:-full}
case "$mode" in
  fast|--fast)
    uv run ruff check src tests
    uv run mypy
    uv run pytest -q -m "not browser and not network and not slow"
    ;;
  full|--full)
    uv run ruff check src tests
    uv run mypy
    uv run pytest -q
    python3 scripts/check-docs.py
    ;;
  *)
    echo "usage: $0 [--fast|--full]" >&2
    exit 2
    ;;
esac
