#!/bin/sh
# Start FastAPI after a short delay so colocated Vestige can bind :3928.
set -eu

export PYTHONPATH="/app/backend${PYTHONPATH:+:$PYTHONPATH}"

# Pick up Vestige-generated HTTP auth token when not injected by Helm
for TOKEN_CAND in \
  "${VESTIGE_AUTH_TOKEN_FILE:-}" \
  /tmp/vestige-auth-token \
  /tmp/.local/share/core/auth_token
do
  if [ -z "${VESTIGE_AUTH_TOKEN:-}" ] && [ -n "$TOKEN_CAND" ] && [ -s "$TOKEN_CAND" ]; then
    VESTIGE_AUTH_TOKEN=$(cat "$TOKEN_CAND")
    export VESTIGE_AUTH_TOKEN
    echo "loaded vestige auth token from $TOKEN_CAND"
    break
  fi
done

# Brief settle time for vestige (supervisord starts both in parallel)
sleep "${VESTIGE_STARTUP_DELAY_SECS:-3}"

mkdir -p /data/conversations /data/vestige /data/vestige/model-cache

echo "starting uvicorn on :8080"
exec /opt/venv/bin/uvicorn app:app \
  --host 0.0.0.0 \
  --port 8080 \
  --workers 1
