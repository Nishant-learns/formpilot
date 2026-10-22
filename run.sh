#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting FormPilot — AI Cyber Bhaiya "
echo "=========================================================="

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

# Ensure uploads and data directories exist
mkdir -p data uploads frontend/dist

# Set PYTHONPATH
export PYTHONPATH=.

# Start FastAPI backend (serving API, WebSockets, Gov Simulator, and Built Frontend UI)
echo "Launching FastAPI Unified Server on http://127.0.0.1:8000..."
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
