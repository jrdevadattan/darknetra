#!/bin/sh
set -eu
umask 077
mkdir -p "$CODEX_HOME"
if [ -f /run/secrets/codex_auth ]; then
  if [ ! -s "$CODEX_HOME/auth.json" ] || [ /run/secrets/codex_auth -nt "$CODEX_HOME/auth.json" ]; then
    cp /run/secrets/codex_auth "$CODEX_HOME/auth.json"
    chmod 600 "$CODEX_HOME/auth.json"
  fi
fi
exec node node_modules/next/dist/bin/next start --hostname 0.0.0.0
