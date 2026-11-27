#!/usr/bin/env bash
# Write android/local.properties from the local Android SDK installation.
# Usage: scripts/android/sdk-properties.sh [--output PATH]
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
output="$root/android/local.properties"
if [ "${1:-}" = "--output" ]; then
  if [ "$#" -lt 2 ]; then
    echo "usage: $0 [--output PATH]" >&2
    exit 2
  fi
  output=$2
  shift 2
fi

sdk=${ANDROID_HOME:-${ANDROID_SDK_ROOT:-$HOME/Library/Android/sdk}}
if [ ! -d "$sdk" ]; then
  echo "Android SDK not found at $sdk" >&2
  echo "Set ANDROID_HOME or install the SDK, then rerun this script." >&2
  exit 1
fi
sdk=$(cd "$sdk" && pwd)

mkdir -p "$(dirname "$output")"
printf 'sdk.dir=%s\n' "$sdk" > "$output"
printf 'Wrote %s\n' "$output"
