#!/usr/bin/env bash
# Device-only smoke tests for the production Android SQLite/FTS5 path.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export PATH="$ANDROID_HOME/platform-tools:$PATH"
"$root/scripts/android/adb.sh" devices
(cd "$root/android" && ./gradlew :core:connectedDebugAndroidTest "$@")
