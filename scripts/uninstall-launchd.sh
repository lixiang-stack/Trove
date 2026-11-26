#!/usr/bin/env bash
# Remove the Trove launchd LaunchAgents. User data in ~/Trove is untouched.
# Usage: scripts/uninstall-launchd.sh [--dry-run] [--home DIR]
set -euo pipefail

root=${TROVE_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}
home="$HOME/Trove"
agents_dir=${TROVE_AGENTS_DIR:-$HOME/Library/LaunchAgents}
dry_run=""

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run="--dry-run"; shift ;;
    --home) home=$2; shift 2 ;;
    *)
      echo "usage: $0 [--dry-run] [--home DIR]" >&2
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
