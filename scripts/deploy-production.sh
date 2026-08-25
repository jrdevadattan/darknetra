#!/usr/bin/env bash
set -Eeuo pipefail

deploy_sha="${DARKNETRA_DEPLOY_SHA:-${GITHUB_SHA:-}}"
deploy_root="${DARKNETRA_DEPLOY_ROOT:-/opt/darknetra}"
project_name="${DARKNETRA_COMPOSE_PROJECT:-darknetra-prod}"

if [[ ! "$deploy_sha" =~ ^[0-9a-f]{40}$ ]]; then
  echo "DARKNETRA_DEPLOY_SHA must be a full Git commit SHA" >&2
  exit 2
fi

if [[ "$(git rev-parse HEAD)" != "$deploy_sha" ]]; then
  echo "checked-out commit does not match DARKNETRA_DEPLOY_SHA" >&2
  exit 2
fi

env_file="$deploy_root/shared/.env"
releases_root="$deploy_root/releases"
release="$releases_root/$deploy_sha"
current="$deploy_root/current"
short_sha="${deploy_sha:0:12}"

if [[ ! -r "$env_file" ]]; then
  echo "production environment file is missing or unreadable" >&2
  exit 2
fi

if ! grep -q '^DARKNETRA_POSTGRES_RUNTIME_PASSWORD=.' "$env_file"; then
  echo "DARKNETRA_POSTGRES_RUNTIME_PASSWORD is missing from production environment" >&2
  exit 2
fi

mkdir -p "$releases_root"

if [[ ! -d "$release" ]]; then
  staging="$(mktemp -d "$releases_root/.${deploy_sha}.XXXXXX")"
  cleanup_staging() {
    rm -rf -- "$staging"
  }
  trap cleanup_staging EXIT
  git archive --format=tar "$deploy_sha" | tar -xf - -C "$staging"
  printf '%s\n' "$deploy_sha" > "$staging/.deployed-sha"
  mv -- "$staging" "$release"
  trap - EXIT
fi

compose=(
  docker compose
  --env-file "$env_file"
  --project-name "$project_name"
  --file "$release/docker-compose.yml"
  --file "$release/docker-compose.prod.yml"
)

export DARKNETRA_BUILD_VERSION="$short_sha"
"${compose[@]}" config --quiet
"${compose[@]}" build api worker web migrate

previous=""
if [[ -L "$current" ]]; then
  previous="$(readlink -f "$current")"
fi

rollback() {
  exit_code=$?
  trap - ERR
  if [[ -n "$previous" && -d "$previous" ]]; then
    echo "deployment failed; restoring $(basename "$previous")" >&2
    old_compose=(
      docker compose
      --env-file "$env_file"
      --project-name "$project_name"
      --file "$previous/docker-compose.yml"
      --file "$previous/docker-compose.prod.yml"
    )
    DARKNETRA_BUILD_VERSION="$(basename "$previous" | cut -c1-12)" \
      "${old_compose[@]}" up -d --build --wait
    replacement="$deploy_root/.current.rollback.$$"
    ln -s "$previous" "$replacement"
    mv -Tf "$replacement" "$current"
  fi
  exit "$exit_code"
}
trap rollback ERR

"${compose[@]}" up -d --wait

api_uid="$("${compose[@]}" exec -T api id -u)"
worker_uid="$("${compose[@]}" exec -T worker id -u)"
[[ "$api_uid" == "10001" && "$worker_uid" == "10001" ]]

ready="$(curl --fail --silent --show-error --retry 12 --retry-delay 5 \
  "http://10.160.0.3:38001/api/v1/health/ready")"
python3 - "$ready" "$short_sha" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
assert payload["status"] == "ready", payload
assert payload["version"] == sys.argv[2], payload
PY

public_origin="$(sed -n 's/^DARKNETRA_PUBLIC_ORIGIN=//p' "$env_file" | tail -n 1)"
curl --fail --silent --show-error --retry 12 --retry-delay 5 \
  "$public_origin/auth/v2/login" >/dev/null

replacement="$deploy_root/.current.$deploy_sha"
ln -s "$release" "$replacement"
mv -Tf "$replacement" "$current"
trap - ERR

echo "deployed $deploy_sha to $public_origin"
