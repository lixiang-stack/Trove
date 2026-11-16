#!/usr/bin/env bash
# Create a .worktree/<name> checkout on a new branch.
set -euo pipefail

usage() {
  echo "usage: $0 <name> [base]" >&2
  exit 2
}

name=${1:-}
base=${2:-main}
[ -n "$name" ] || usage
if ! printf '%s' "$name" | grep -Eq '^[A-Za-z0-9][A-Za-z0-9._-]*$'; then
  echo "invalid worktree name: $name" >&2
  exit 2
fi

common=$(git rev-parse --git-common-dir)
main_root=$(cd "$(dirname "$common")" && pwd)
target="$main_root/.worktree/$name"
if [ -e "$target" ]; then
  echo "worktree already exists: $target" >&2
  exit 1
fi

git worktree add "$target" -b "$name" "$base"

# Android builds need a local SDK pointer; keep it out of git like the main checkout.
sdk_dir="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
if [ -d "$sdk_dir" ] && [ ! -f "$target/android/local.properties" ]; then
  printf 'sdk.dir=%s\n' "$sdk_dir" > "$target/android/local.properties"
fi

printf '%s\n' "$target"
