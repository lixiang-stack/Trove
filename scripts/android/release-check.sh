#!/usr/bin/env bash
# Inspect a signed Trove release APK for permissions, signature and size.
#
# Usage: scripts/android/release-check.sh [APK]
# Defaults to android/app/build/outputs/apk/prod/release/app-prod-release.apk.
set -euo pipefail

root=$(cd "$(dirname "$0")/../.." && pwd)
apk=${1:-"$root/android/app/build/outputs/apk/prod/release/app-prod-release.apk"}
sdk=${ANDROID_HOME:-$HOME/Library/Android/sdk}
build_tools=$(find "$sdk/build-tools" -maxdepth 1 -type d -name '[0-9]*' | sort -V | tail -1)
aapt2="$build_tools/aapt2"
apksigner="$build_tools/apksigner"
max_bytes=$((35 * 1024 * 1024))

allowed=$(cat <<'EOF'
android.permission.INTERNET
android.permission.ACCESS_NETWORK_STATE
android.permission.WAKE_LOCK
android.permission.POST_NOTIFICATIONS
android.permission.FOREGROUND_SERVICE
android.permission.FOREGROUND_SERVICE_MEDIA_PLAYBACK
android.permission.FOREGROUND_SERVICE_DATA_SYNC
android.permission.RECEIVE_BOOT_COMPLETED
dev.trove.app.DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION
EOF
)

[ -f "$apk" ] || {
  echo "missing APK: $apk" >&2
  echo "build it with: cd android && ./gradlew :app:assembleProdRelease" >&2
  exit 1
}

echo "APK: $apk"
badging=$("$aapt2" dump badging "$apk")
echo "$badging" | head -1
if echo "$badging" | grep -q 'application-debuggable'; then
  echo "release APK is debuggable" >&2
  exit 1
fi

"$apksigner" verify --print-certs "$apk"
actual=$("$aapt2" dump permissions "$apk" | sed -n "s/^uses-permission: name='\(.*\)'$/\1/p")
unexpected=$(comm -23 <(printf '%s\n' "$actual" | sort -u) <(printf '%s\n' "$allowed" | sort -u))
if [ -n "$unexpected" ]; then
  echo "unexpected permissions:" >&2
  echo "$unexpected" >&2
  exit 1
fi

bytes=$(wc -c < "$apk" | tr -d ' ')
echo "size: $((bytes / 1024 / 1024)) MiB (${bytes} bytes)"
if [ "$bytes" -gt "$max_bytes" ]; then
  echo "release APK exceeds 35 MiB target" >&2
  exit 1
fi

echo "release checks passed"
