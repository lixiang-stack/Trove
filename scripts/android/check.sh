#!/usr/bin/env bash
# Single source of truth for the Android debug build/test/lint gate.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
cd "$root/android"
exec ./gradlew \
  :app:assembleProdDebug :app:testProdDebugUnitTest :app:lintProdDebug \
  :core:testDebugUnitTest :core:lintDebug \
  :playback:testDebugUnitTest :playback:lintDebug \
  :reader:testDebugUnitTest :reader:lintDebug \
  "$@"
