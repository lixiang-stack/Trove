#!/usr/bin/env bash
# Read-only release gates. Run from a clean checkout on the release machine.
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -n "$(git status --porcelain)" ]; then
  echo "release-check: working tree is not clean" >&2
  exit 1
fi

version=$(uv run trove --version | awk '{print $2}')
project_version=$(uv run python - <<'PY'
import tomllib
from pathlib import Path

print(tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
PY
)
if [ "$version" != "$project_version" ]; then
  echo "release-check: trove --version ($version) != pyproject.toml ($project_version)" >&2
  exit 1
fi
echo "Version: $version"

./scripts/check.sh --full

trove_home=${TROVE_HOME:-$HOME/Trove}
if [ -d "$trove_home" ]; then
  uv run trove doctor --json >/dev/null
else
  echo "release-check: doctor skipped; $trove_home does not exist"
fi

cat <<EOF
release-check: all gates passed for $version
Next:
  git tag v$version
  TROVE_IMAGE_TAG=$version docker compose build
EOF
