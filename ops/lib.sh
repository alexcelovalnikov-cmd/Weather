#!/bin/sh
set -eu

BASE=/opt/weather-bridge
UID_NUM="$(id -u)"
XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$UID_NUM}"
PATH="/home/weather/bin:/usr/local/bin:/usr/bin:/bin"
DOCKER_HOST="unix://$XDG_RUNTIME_DIR/docker.sock"
COMPOSE_FILE=$BASE/runtime/compose.production.yaml
BIND_PORT=8789
LOCK_FILE=$BASE/runtime/deploy.lock
OPS_LOG=$BASE/logs/operations.log
export XDG_RUNTIME_DIR PATH DOCKER_HOST

lock_deploy() {
  exec 9>"$LOCK_FILE"
  if ! flock -n 9; then
    echo "DEPLOY_LOCKED: another Weather Bridge operation is running" >&2
    exit 75
  fi
}

log_event() {
  printf "%s %s\n" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$OPS_LOG"
}

compose() {
  (
    cd "$BASE"
    WEATHER_IMAGE="$WEATHER_IMAGE" WEATHER_BIND_PORT="$BIND_PORT" \
      docker compose -p weather-bridge -f "$COMPOSE_FILE" "$@"
  )
}

require_release() {
  VERSION="$1"
  [ -d "$BASE/releases/$VERSION" ] || {
    echo "Release not found: $VERSION" >&2
    exit 2
  }
}

ensure_image() {
  VERSION="$1"
  IMAGE="weather-bridge:$VERSION"
  if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    docker build -t "$IMAGE" "$BASE/releases/$VERSION"
  fi
}

wait_health() {
  n=0
  while [ "$n" -lt 30 ]; do
    if curl -fsS "http://127.0.0.1:$BIND_PORT/health" >/dev/null 2>&1; then
      return 0
    fi
    n=$((n+1))
    sleep 1
  done
  echo "Health check failed on port $BIND_PORT" >&2
  return 1
}
