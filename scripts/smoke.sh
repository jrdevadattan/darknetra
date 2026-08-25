#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${DARKNETRA_POSTGRES_RUNTIME_PASSWORD:-}" ]]; then
  export DARKNETRA_POSTGRES_RUNTIME_PASSWORD="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi

compose=(docker compose -f docker-compose.yml -f docker-compose.dev.yml)
cleanup() { "${compose[@]}" down -v --remove-orphans >/dev/null 2>&1 || true; }
finish() {
  status=$?
  if [ "$status" -ne 0 ]; then
    echo '--- docker compose ps (failure) ---' >&2
    "${compose[@]}" ps -a >&2 || true
    echo '--- docker compose logs (failure) ---' >&2
    "${compose[@]}" logs --no-color >&2 || true
  fi
  cleanup
  exit "$status"
}
trap finish EXIT

"${compose[@]}" up --build -d --wait
"${compose[@]}" ps

api_uid="$("${compose[@]}" exec -T api id -u)"
web_uid="$("${compose[@]}" exec -T web id -u)"
test "$api_uid" = "10001"
test "$web_uid" = "10001"

python - <<'PY'
import json
import urllib.request

with urllib.request.urlopen('http://localhost:8000/api/v1/health/live', timeout=5) as response:
    body = json.load(response)
assert body['status'] == 'ok', body

with urllib.request.urlopen('http://localhost:3000/dashboard', timeout=15) as response:
    sample = response.read(2048)
    assert response.status == 200
    assert sample
PY
