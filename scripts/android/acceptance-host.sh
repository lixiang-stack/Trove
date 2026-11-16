#!/usr/bin/env bash
# Start a throwaway Host + adb reverse + debug app for Android acceptance.
#
# Usage: scripts/android/acceptance-host.sh [--port 8765] [--home DIR] [--no-worker] [--no-install]
# The server keeps running; stop it with: kill "$(cat "$home/server.pid")"
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
port=${PORT:-8765}
home=""
install_app=1
worker=1

while [ $# -gt 0 ]; do
  case "$1" in
    --port) port=$2; shift 2 ;;
    --home) home=$2; shift 2 ;;
    --no-worker) worker=0; shift ;;
    --no-install) install_app=0; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done

if curl -fsS -m 1 "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then
  echo "port ${port} already serves a Host; stop it or pass --port" >&2
  exit 1
fi

if [ -z "$home" ]; then
  home=$(mktemp -d "${TMPDIR:-/tmp}/trove-acceptance.XXXXXX")
fi
home=$(cd "$home" 2>/dev/null && pwd || { mkdir -p "$home"; cd "$home"; pwd; })

if [ ! -f "$home/trove.db" ]; then
  "$root/.venv/bin/python" "$root/scripts/android/seed_acceptance.py" "$home"
fi

worker_args=""
if [ "$worker" -eq 0 ]; then
  worker_args="--no-worker"
fi

TROVE_HOME="$home" TROVE_LOG_CONSOLE=0 \
  "$root/.venv/bin/trove" serve $worker_args --host 127.0.0.1 --port "$port" \
  >"$home/server.log" 2>&1 &
echo $! >"$home/server.pid"

for _ in $(seq 1 50); do
  if curl -fsS -m 1 "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1; then
    break
  fi
  sleep 0.2
done
curl -fsS -m 2 "http://127.0.0.1:${port}/api/health" >/dev/null

"$root/scripts/android/adb.sh" reverse "tcp:${port}" "tcp:${port}"

if [ "$install_app" -eq 1 ]; then
  apk="$root/android/app/build/outputs/apk/debug/app-debug.apk"
  (cd "$root/android" && ./gradlew :app:assembleDebug)
  "$root/scripts/android/adb.sh" install -r "$apk" >/dev/null
fi

cat <<MSG
Temporary Host is running.
  home:     $home
  log:      $home/server.log
  login:    http://127.0.0.1:${port}
  password: acceptance-pass
  stop:     kill "\$(cat $home/server.pid)"
The debug app is installed and adb reverse is set. Open the app and log in.
MSG
