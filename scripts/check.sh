#!/usr/bin/env bash
# Full local guardrail: lint, types, tests, and documentation checks.
set -euo pipefail

cd "$(dirname "$0")/.."

uv run ruff check src tests
uv run mypy
uv run pytest -q
python3 scripts/check-docs.py
