#!/usr/bin/env bash
# Compact device diagnostics for playback/sync acceptance.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
adb="$root/scripts/android/adb.sh"

"$adb" devices -l
echo
echo "== app process =="
"$adb" shell pidof dev.trove.app || echo "not running"
echo
echo "== media session =="
"$adb" shell dumpsys media_session | grep -A12 'package=dev.trove.app' | head -20 || true
echo
echo "== notification =="
"$adb" shell dumpsys notification --noredact \
  | grep -A8 -B2 'dev.trove.app' | head -40 || true
echo
echo "== doze whitelist =="
"$adb" shell dumpsys deviceidle whitelist | grep -i trove || echo "not whitelisted"
echo
echo "== recent logcat =="
"$adb" logcat -d -t 400 \
  | grep -E 'dev\.trove|Trove|MediaSession|AndroidRuntime|FATAL' | tail -60 || true
