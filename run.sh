#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$ROOT_DIR"

# Load local configuration if present. `.env` is git-ignored.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PYTHON_BIN="${PYTHON:-python3}"
if [ -x .venv/bin/python ]; then
  PYTHON_BIN=".venv/bin/python"
fi

mkdir -p data uploads frontend/dist
export PYTHONPATH="$ROOT_DIR${PYTHONPATH:+:$PYTHONPATH}"

HOST="${FORMPILOT_HOST:-127.0.0.1}"
PORT="${FORMPILOT_PORT:-8000}"

echo "Starting FormPilot on http://${HOST}:${PORT}"
exec "$PYTHON_BIN" -m uvicorn backend.main:app --host "$HOST" --port "$PORT"
