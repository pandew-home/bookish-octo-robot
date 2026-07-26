#!/bin/sh
# Start colocated Vestige; ensure a shared auth token for MCP HTTP.
set -eu

mkdir -p "${VESTIGE_DATA_DIR:-/data/vestige}" "${FASTEMBED_CACHE_PATH:-/data/vestige/model-cache}"

TOKEN_FILE="${VESTIGE_AUTH_TOKEN_FILE:-/tmp/vestige-auth-token}"

if [ -n "${VESTIGE_AUTH_TOKEN:-}" ]; then
  printf '%s' "$VESTIGE_AUTH_TOKEN" > "$TOKEN_FILE"
elif [ ! -s "$TOKEN_FILE" ]; then
  # Generate once per container lifetime; backend reads the same file.
  TOKEN=$(dd if=/dev/urandom bs=32 count=1 2>/dev/null | od -An -tx1 | tr -d ' \n')
  printf '%s' "$TOKEN" > "$TOKEN_FILE"
fi
export VESTIGE_AUTH_TOKEN
VESTIGE_AUTH_TOKEN=$(cat "$TOKEN_FILE")
export VESTIGE_AUTH_TOKEN

# CLI only accepts --port (binds for in-pod HTTP MCP; not published via Service).
exec /usr/local/bin/vestige serve --port 3928 --data-dir "${VESTIGE_DATA_DIR:-/data/vestige}"
