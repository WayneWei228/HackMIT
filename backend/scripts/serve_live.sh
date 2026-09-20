#!/usr/bin/env bash
# Restart the backend, with the model live when a token file exists.
# The token lives outside the repo (one line, chmod 600) and is never written here.
set -euo pipefail

TOKEN_FILE="${TRUEUP_TOKEN_FILE:-$HOME/.config/trueup/bedrock-token}"
cd "$(dirname "$0")/.."

# The world the demo runs in. The late-amendment world tells the Mintlify story where the fee rise
# is not on file at close. For the generator's default world: TRUEUP_SEED_DIR="$PWD/seed" serve_live.sh
export TRUEUP_SEED_DIR="${TRUEUP_SEED_DIR:-$PWD/seed_late_amendment}"
echo "world: $(basename "$TRUEUP_SEED_DIR")"

if [ -r "$TOKEN_FILE" ]; then
  AWS_BEARER_TOKEN_BEDROCK="$(tr -d '[:space:]' < "$TOKEN_FILE")"
  export AWS_BEARER_TOKEN_BEDROCK
  echo "model: live (token read from $TOKEN_FILE)"
elif [ -n "${OPENAI_API_KEY:-}" ] || [ -n "${AWS_BEARER_TOKEN_BEDROCK:-}" ]; then
  # A key already exported by the caller, e.g. `set -a; source <your .env>; set +a` first.
  echo "model: live (key from the environment, model ${MODEL_ID:-the gateway default})"
else
  echo "model: offline (no token file at $TOKEN_FILE and no key in the environment)"
fi

listeners="$(lsof -nP -iTCP:8000 -sTCP:LISTEN -t || true)"
if [ -n "$listeners" ]; then
  # shellcheck disable=SC2086
  kill $listeners
  sleep 1
fi

exec uv run python scripts/serve.py
