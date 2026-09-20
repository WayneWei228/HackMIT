#!/usr/bin/env bash
# Restart the backend, with the model live when a token file exists, then run the model preflight.
# The token lives outside the repo (one line, chmod 600) and is never written here.
# The region and the latest expiry come from the key itself; the preflight prints both.
set -euo pipefail

TOKEN_FILE="${TRUEUP_TOKEN_FILE:-$HOME/.config/trueup/bedrock-token}"
PORT="${TRUEUP_PORT:-8000}"
cd "$(dirname "$0")/.."

if [ -r "$TOKEN_FILE" ]; then
  AWS_BEARER_TOKEN_BEDROCK="$(tr -d '[:space:]' < "$TOKEN_FILE")"
  export AWS_BEARER_TOKEN_BEDROCK
  echo "model: live (token read from $TOKEN_FILE)"
else
  echo "model: offline (no token file at $TOKEN_FILE)"
fi

listeners_on_port() { lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true; }

listeners="$(listeners_on_port)"
if [ -n "$listeners" ]; then
  # shellcheck disable=SC2086
  kill $listeners
  sleep 1
fi

uv run python scripts/serve.py --port "$PORT" &
server=$!
stop_server() {
  # shellcheck disable=SC2046
  kill $(listeners_on_port) 2>/dev/null || true
  kill "$server" 2>/dev/null || true
}
trap stop_server EXIT INT TERM

for _ in $(seq 1 60); do
  if curl -fs "http://127.0.0.1:$PORT/api/health" > /dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

if [ -n "${AWS_BEARER_TOKEN_BEDROCK:-}" ]; then
  uv run python scripts/check_model.py \
    || echo "The server is up, but the model preflight failed: agents will use their rules."
fi

wait "$server"
