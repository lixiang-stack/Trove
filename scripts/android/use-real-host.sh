#!/usr/bin/env bash
# Point the latest debug app at the real local Host over USB.
#
# This does not create a temporary Host, copy the database, or seed data.
# Start the real Host first (data directory defaults to ~/Trove):
#   uv run trove serve
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
adb="$root/scripts/android/adb.sh"
port=8765
build_app=1
clear_data=0
launch_app=1

usage() {
  cat <<'EOF'
usage: scripts/android/use-real-host.sh [options]

Requires:
  - the real Host is serving on http://127.0.0.1:<port>
  - one Android device is connected over USB

Options:
  --port PORT     Host port and adb reverse port (default: 8765)
  --no-build      Install the existing prodDebug APK without rebuilding
  --clear-data    Clear app data before launch (deletes local downloads/token)
  --no-launch     Do not start the app after installing
  -h, --help      Show this help

This script never starts a Host and never uses acceptance-host.sh.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    --port) port=$2; shift 2 ;;
    --no-build) build_app=0; shift ;;
    --clear-data) clear_data=1; shift ;;
    --no-launch) launch_app=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! printf '%s' "$port" | grep -Eq '^[0-9]+$'; then
  echo "invalid port: $port" >&2
  exit 2
fi

if ! curl -fsS -m 2 "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then
  echo "no Host is serving on http://127.0.0.1:${port}" >&2
  echo "start the real Host first, for example:" >&2
  echo "  cd <checkout> && uv run trove serve" >&2
  echo "do not use acceptance-host.sh for real data" >&2
  exit 1
fi

if ! "$adb" devices | awk 'NR > 1 && $2 == "device" { found = 1 } END { exit !found }'; then
  echo "no adb device connected" >&2
  exit 1
fi

"$adb" reverse "tcp:${port}" "tcp:${port}"

if [ "$build_app" -eq 1 ]; then
  (cd "$root/android" && ./gradlew :app:assembleProdDebug)
fi

apk="$root/android/app/build/outputs/apk/prod/debug/app-prod-debug.apk"
if [ ! -f "$apk" ]; then
  echo "missing APK: $apk" >&2
  echo "run without --no-build or build :app:assembleProdDebug first" >&2
  exit 1
fi

"$adb" install -r "$apk" >/dev/null
if [ "$clear_data" -eq 1 ]; then
  "$adb" shell pm clear dev.trove.app >/dev/null
fi
if [ "$launch_app" -eq 1 ]; then
  "$adb" shell am force-stop dev.trove.app >/dev/null 2>&1 || true
  "$adb" shell am start -n dev.trove.app/.MainActivity >/dev/null
fi

cat <<MSG
Real Host: http://127.0.0.1:${port}
APK:       $apk
adb reverse and app install are ready.

Log in with the real Host password. If the app still has an old acceptance
token, rerun with --clear-data (this deletes local downloads) or clear app data
from Android settings.
MSG
