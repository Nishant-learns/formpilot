#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." >/dev/null 2>&1 && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON:-python3}"

echo "Creating the Python environment in .venv"
"$PYTHON_BIN" -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python -m playwright install chromium

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example. Add TINYFISH_API_KEY to enable live search."
fi

echo "Installing and building the frontend"
npm ci --prefix frontend
npm run build --prefix frontend

echo
echo "Setup complete. Run ./run.sh and open http://127.0.0.1:8000"
