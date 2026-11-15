#!/usr/bin/env bash
# Run adb from the Android SDK even when platform-tools is not on PATH.
set -euo pipefail

for candidate in \
  "${ANDROID_HOME:-}/platform-tools/adb" \
  "${ANDROID_SDK_ROOT:-}/platform-tools/adb" \
  "$HOME/Library/Android/sdk/platform-tools/adb"; do
  if [ -x "$candidate" ]; then
    exec "$candidate" "$@"
  fi
done

if command -v adb >/dev/null 2>&1; then
  exec adb "$@"
fi

echo "adb not found. Set ANDROID_HOME or install Android platform-tools." >&2
exit 127
