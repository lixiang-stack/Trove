#!/usr/bin/env bash
# Docker smoke test: build, start, process an EPUB fixture, restart, and verify
# the named volume survives `docker compose down`.
# Usage: scripts/docker-smoke.sh
# Environment: TROVE_IMAGE_TAG (default smoke), TROVE_HOST_PORT (default 18765).
set -euo pipefail

root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"

project=${TROVE_SMOKE_PROJECT:-trove-smoke}
export TROVE_IMAGE_TAG=${TROVE_IMAGE_TAG:-smoke}
export TROVE_INSTALL_ASR=${TROVE_INSTALL_ASR:-false}
export TROVE_PUBLISH_ADDRESS=127.0.0.1
export TROVE_HOST_PORT=${TROVE_HOST_PORT:-18765}
base_url="http://127.0.0.1:${TROVE_HOST_PORT}"
password="trove-smoke-password"
cookie=$(mktemp)

compose=(docker compose -p "$project" -f docker-compose.yml)

cleanup() {
  "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true
  rm -f "$cookie"
}
trap cleanup EXIT

wait_for_health() {
  for _ in $(seq 1 120); do
    if curl --fail --silent "$base_url/api/health" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "API did not become healthy; recent logs:" >&2
  "${compose[@]}" logs --tail 80 api worker init >&2 || true
  return 1
}

wait_for_item() {
  local item_id=$1 payload state
  for _ in $(seq 1 120); do
    payload=$(curl --fail --silent -b "$cookie" "$base_url/api/items/$item_id")
    state=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["processing_state"])' <<<"$payload")
    case "$state" in
      completed) return 0 ;;
      failed|cancelled)
        echo "Item ended in $state: $payload" >&2
        return 1
        ;;
    esac
    sleep 1
  done
  echo "Item $item_id did not finish; recent logs:" >&2
  "${compose[@]}" logs --tail 80 worker >&2 || true
  return 1
}

login() {
  curl --fail --silent -c "$cookie" \
    -H 'content-type: application/json' \
    -d "{\"password\":\"$password\"}" \
    "$base_url/api/auth/login" >/dev/null
}

verify_item() {
  local item_id=$1
  curl --fail --silent -b "$cookie" "$base_url/api/items/$item_id" \
    | python3 -c 'import json,sys; item=json.load(sys.stdin); assert item["processing_state"] == "completed", item'
}

echo "Building and starting Trove (base image, EPUB smoke)..."
"${compose[@]}" up -d --build
wait_for_health
printf '%s\n' "$password" \
  | "${compose[@]}" exec -T api trove auth set-password --password-stdin

# Copy the EPUB through the Docker API so the test also works with a remote
# daemon.
"${compose[@]}" exec -T api mkdir -p /home/trove/Trove/fixtures
"${compose[@]}" cp tests/fixtures/aesop.epub \
  api:/home/trove/Trove/fixtures/aesop.epub
login

created=$(curl --fail --silent -b "$cookie" \
  -H 'content-type: application/json' \
  -d '{"kind":"path","path":"/home/trove/Trove/fixtures/aesop.epub"}' \
  "$base_url/api/items")
item_id=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["item"]["id"])' <<<"$created")
wait_for_item "$item_id"

worker_status=$(curl --fail --silent "$base_url/api/health" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["worker"]["status"])')
test "$worker_status" = "ok"

echo "Restarting containers and checking persistence..."
"${compose[@]}" restart api worker >/dev/null
wait_for_health
login
verify_item "$item_id"

echo "Removing containers without volumes and checking persistence..."
"${compose[@]}" down >/dev/null
"${compose[@]}" up -d >/dev/null
wait_for_health
login
verify_item "$item_id"

echo "Docker smoke passed: health, worker heartbeat, EPUB processing, restart, and named-volume persistence."
