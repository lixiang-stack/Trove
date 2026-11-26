#!/usr/bin/env bash
# Run a continuous background/lockscreen playback acceptance check.
#
# Preconditions:
# - debug APK is installed and its Host URL is http://127.0.0.1:8765
# - the phone is connected over USB and can reach the Mac through adb reverse
# - ffmpeg and sqlite3 are available
#
# The script clones the current Host DB/config into a throwaway home, adds a
# silent audio Item of --seconds length, points 8765 at that clone, drives the
# app, locks the screen, waits, then verifies MediaSession and Host progress.
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
adb="$root/scripts/android/adb.sh"
ui="$root/scripts/android/ui-dump.py"
python="$root/.venv/bin/python"
trove="$root/.venv/bin/trove"
source_home="$HOME/Trove"
seconds=300
port=8767
work=""
server_pid=""
original_reverse=""
original_screen_timeout=""
passed=0

usage() {
  echo "usage: $0 [--source-home DIR] [--seconds N] [--port N]" >&2
  exit 2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --source-home) source_home=$2; shift 2 ;;
    --seconds) seconds=$2; shift 2 ;;
    --port) port=$2; shift 2 ;;
    *) usage ;;
  esac
done

fail() {
  echo "FAIL: $*" >&2
  exit 1
}

media_session() {
  "$adb" shell dumpsys media_session | grep -A40 'package=dev.trove.app' | head -60
}

cleanup() {
  set +e
  "$adb" shell input keyevent 85 >/dev/null 2>&1 || true
  if [ -n "$server_pid" ]; then
    kill "$server_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$original_reverse" ]; then
    "$adb" reverse tcp:8765 "$original_reverse" >/dev/null 2>&1 || true
  else
    "$adb" reverse --remove tcp:8765 >/dev/null 2>&1 || true
  fi
  if [ -n "$original_screen_timeout" ]; then
    "$adb" shell settings put system screen_off_timeout "$original_screen_timeout" >/dev/null 2>&1 || true
  fi
  "$adb" shell am force-stop dev.trove.app >/dev/null 2>&1 || true
  "$adb" shell am start -n dev.trove.app/.MainActivity >/dev/null 2>&1 || true
  if [ "$passed" -eq 1 ] && [ -n "$work" ]; then
    rm -rf "$work"
  elif [ -n "$work" ]; then
    echo "work dir kept for diagnostics: $work" >&2
  fi
}
trap cleanup EXIT

[ "$seconds" -ge 10 ] || fail "--seconds must be >= 10"
[ -f "$source_home/trove.db" ] || fail "missing $source_home/trove.db"
[ -f "$source_home/config.toml" ] || fail "missing $source_home/config.toml"
[ -f "$source_home/state.toml" ] || fail "missing $source_home/state.toml"
[ -x "$python" ] || fail "missing .venv/bin/python; run uv sync"
[ -x "$trove" ] || fail "missing .venv/bin/trove; run uv sync"
command -v sqlite3 >/dev/null || fail "sqlite3 is required"
command -v ffmpeg >/dev/null || fail "ffmpeg is required"

"$adb" devices | grep -qE '\sdevice$' || fail "no adb device"
"$adb" shell dumpsys deviceidle whitelist +dev.trove.app >/dev/null 2>&1 || true

work=$(mktemp -d "${TMPDIR:-/tmp}/trove-playback.XXXXXX")
chmod 700 "$work"
sqlite3 "$source_home/trove.db" ".backup '$work/trove.db'"
cp "$source_home/config.toml" "$work/config.toml"
cp "$source_home/state.toml" "$work/state.toml"

"$python" "$root/scripts/android/seed_playback.py" --home "$work" \
  --seconds "$seconds" --title "后台播放验收 ${seconds}s $(date +%s)" > "$work/seed.out"
item_id=$(sed -n '1p' "$work/seed.out")
title=$(sed -n '2p' "$work/seed.out")
[ -n "$item_id" ] || fail "failed to seed playback Item"

"$trove" --home "$work" sync reset-epoch >/dev/null
"$trove" --home "$work" --no-log-console serve \
  --no-worker --host 127.0.0.1 --port "$port" > "$work/server.log" 2>&1 &
server_pid=$!
for _ in $(seq 1 50); do
  curl -fsS -m 1 "http://127.0.0.1:${port}/api/health" >/dev/null 2>&1 && break
  sleep 0.2
done
curl -fsS -m 2 "http://127.0.0.1:${port}/api/health" >/dev/null \
  || fail "clone Host did not start"

original_reverse=$("$adb" reverse --list | awk '$2 == "tcp:8765" {print $3}' | head -1)
"$adb" reverse tcp:8765 "tcp:$port" >/dev/null
"$adb" shell am force-stop dev.trove.app
sleep 1
"$adb" shell am start -n dev.trove.app/.MainActivity >/dev/null
sleep 2
# Clear any MediaSession left over from an interrupted previous run.
for _ in $(seq 1 10); do
  session=$(media_session || true)
  if echo "$session" | grep -q 'state=NONE' || echo "$session" | grep -q 'metadata: null'; then
    break
  fi
  "$adb" shell input keyevent 86 >/dev/null 2>&1 || true
  sleep 1
done
original_screen_timeout=$("$adb" shell settings get system screen_off_timeout | tr -d '\r')
"$adb" shell settings put system screen_off_timeout 2147483647 >/dev/null 2>&1 || true
"$adb" shell input keyevent 224 >/dev/null 2>&1 || true
"$adb" shell wm dismiss-keyguard >/dev/null 2>&1 || true
"$adb" shell input swipe 540 2000 540 600 300 >/dev/null 2>&1 || true
if "$adb" shell dumpsys window | grep -q 'mDreamingLockscreen=true'; then
  fail "device is locked; unlock it and rerun"
fi
"$ui" --tap-text "资料库" --timeout 10 >/dev/null 2>&1 || true
# The Library can restore a mid-list scroll position; go to the newest Item.
"$adb" shell input swipe 540 1400 540 2300 400 >/dev/null 2>&1 || true
"$adb" shell input swipe 540 1400 540 2300 400 >/dev/null 2>&1 || true

"$ui" --wait-text "$title" --timeout 60 >/dev/null
"$ui" --tap-text "$title" --timeout 10 >/dev/null
"$ui" --wait-text "正在听" --timeout 20 >/dev/null

# Playback length is wall-clock; force 1x before measuring.
speed=""
for _ in $(seq 1 5); do
  speed=$("$ui" 2>/dev/null | sed -n "s/.*text='\([0-9.]*×\)'.*/\1/p" | head -1)
  [ "$speed" = "1×" ] && break
  [ -n "$speed" ] || break
  "$ui" --tap-text "$speed" --timeout 5 >/dev/null
  sleep 0.5
done
[ "$speed" = "1×" ] || fail "could not set playback speed to 1x (current: ${speed:-unknown})"

# Downloads default to unmetered. Bring Wi-Fi up before trying.
if ! "$adb" shell dumpsys connectivity | grep -q 'WIFI.*CONNECTED'; then
  "$adb" shell svc wifi enable >/dev/null 2>&1 || true
  for _ in $(seq 1 15); do
    "$adb" shell dumpsys connectivity | grep -q 'WIFI.*CONNECTED' && break
    sleep 2
  done
fi
"$adb" shell dumpsys connectivity | grep -q 'WIFI.*CONNECTED' \
  || fail "Wi-Fi is not connected; enable Wi-Fi or allow metered downloads in Settings"

"$ui" --tap-text "下载" --timeout 20 >/dev/null
if ! "$ui" --wait-text "已下载 · 离线可用" --timeout 10 >/dev/null 2>&1; then
  if "$ui" --wait-text "等待下载" --timeout 1 >/dev/null 2>&1; then
    fail "download is waiting (metered/Wi-Fi constraint); enable Wi-Fi or allow metered downloads"
  fi
  "$ui" --wait-text "已下载 · 离线可用" --timeout 120 >/dev/null \
    || fail "download did not complete"
fi
sleep 2
if ! "$adb" shell run-as dev.trove.app find "files/$item_id" -name 'audio.*' -type f 2>/dev/null | grep -q .; then
  fail "download reported complete but local audio file is missing"
fi

"$ui" --tap-desc "播放" --timeout 20 >/dev/null 2>&1 || true
playing=0
for _ in $(seq 1 3); do
  for _ in $(seq 1 10); do
    session=$(media_session || true)
    if echo "$session" | grep -q 'state=PLAYING' &&
      echo "$session" | grep -Fq "$title"; then
      playing=1
      break
    fi
    sleep 1
  done
  [ "$playing" -eq 1 ] && break
  "$ui" --tap-desc "播放" --timeout 5 >/dev/null 2>&1 || true
done
if [ "$playing" -ne 1 ]; then
  "$ui" --all >&2 || true
  "$adb" shell dumpsys media_session >&2 || true
  fail "playback did not enter PLAYING"
fi
notification_seen=0
for _ in $(seq 1 10); do
  if "$adb" shell dumpsys notification --noredact | grep -q 'dev.trove.app'; then
    notification_seen=1
    break
  fi
  sleep 1
done
[ "$notification_seen" -eq 1 ] || fail "Trove media notification is missing"

"$adb" shell cmd connectivity airplane-mode enable
"$adb" shell input keyevent 3
"$adb" shell input keyevent 26
echo "Started locked background playback for ${seconds}s at $(date '+%H:%M:%S')"

interval=$((seconds / 10))
[ "$interval" -lt 2 ] && interval=2
[ "$interval" -gt 30 ] && interval=30
started=$(date +%s)
while true; do
  "$adb" devices | grep -qE '\sdevice$' || fail "device disconnected during playback"
  session=$(media_session || true)
  final_session=$(echo "$session" | grep 'state=' | head -1 || true)
  [ -n "$final_session" ] || fail "MediaSession disappeared during playback"
  echo "$session" | grep -Fq "$title" || fail "MediaSession is not the test Item"
  state=$(echo "$final_session" | sed -n 's/.*state=\([A-Z_]*\)(.*/\1/p')
  pos=$(echo "$final_session" | sed -n 's/.*position=\([0-9]*\).*/\1/p')
  elapsed=$(($(date +%s) - started))
  echo "media $state $((pos / 1000))s/${seconds}s after ${elapsed}s"
  if [ "$state" != "PLAYING" ]; then
    [ "$elapsed" -ge $((seconds - 5)) ] && break
    fail "playback left PLAYING early: $final_session"
  fi
  [ "$elapsed" -ge "$seconds" ] && break
  sleep "$interval"
done

"$adb" shell cmd connectivity airplane-mode disable >/dev/null 2>&1 || true
sleep 2
"$adb" shell am force-stop dev.trove.app
"$adb" shell am start -n dev.trove.app/.MainActivity >/dev/null
for _ in $(seq 1 30); do
  state=$(sqlite3 "$work/trove.db" \
    "select audio_position_sec || '|' || consumption_state from items where id='$item_id';")
  host_pos=${state%%|*}
  host_state=${state##*|}
  awk -v p="$host_pos" -v s="$seconds" 'BEGIN { exit !(p >= s * 0.95) }' && break
  [ "$host_state" = "finished" ] && break
  sleep 2
done
state=$(sqlite3 "$work/trove.db" \
  "select audio_position_sec || '|' || consumption_state from items where id='$item_id';")
host_pos=${state%%|*}
host_state=${state##*|}
awk -v p="$host_pos" -v s="$seconds" 'BEGIN { exit !(p >= s * 0.95) }' \
  || [ "$host_state" = "finished" ] \
  || fail "Host progress did not reach ${seconds}s: $state"

notification=$("$adb" shell dumpsys notification --noredact | grep -c 'dev.trove.app' || true)
[ "$notification" -gt 0 ] || echo "warning: notification was not present at final check" >&2
echo "PASS: MediaSession $final_session; Host state $state"
passed=1
