#!/usr/bin/env bash
# Remove the Trove launchd LaunchAgents. User data in TROVE_HOME is untouched.
# Usage: scripts/uninstall-launchd.sh [--dry-run]
set -euo pipefail

root=${TROVE_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
home=${TROVE_HOME:-$HOME/Trove}
agents_dir=${TROVE_AGENTS_DIR:-$HOME/Library/LaunchAgents}
dry_run=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) dry_run="--dry-run" ;;
    *)
      echo "usage: $0 [--dry-run]" >&2
      exit 2
      ;;
  esac
done

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "launchd is only available on macOS." >&2
  exit 1
fi

cd "$root"
exec uv run trove service uninstall \
  --home "$home" \
  --agents-dir "$agents_dir" \
  $dry_run
