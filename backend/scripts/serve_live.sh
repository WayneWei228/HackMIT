#!/usr/bin/env bash
# Restart the backend, with the model live when a token file exists.
# The token lives outside the repo (one line, chmod 600) and is never written here.
set -euo pipefail

TOKEN_FILE="${TRUEUP_TOKEN_FILE:-$HOME/.config/trueup/bedrock-token}"
cd "$(dirname "$0")/.."

if [ -r "$TOKEN_FILE" ]; then
  AWS_BEARER_TOKEN_BEDROCK="$(tr -d '[:space:]' < "$TOKEN_FILE")"
  export AWS_BEARER_TOKEN_BEDROCK
  echo "model: live (token read from $TOKEN_FILE)"
else
  echo "model: offline (no token file at $TOKEN_FILE)"
fi

listeners="$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t || true)"
if [ -n "$listeners" ]; then
  # shellcheck disable=SC2086
  kill $listeners
  sleep 1
fi

exec uv run python scripts/serve.py
