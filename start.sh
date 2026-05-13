#!/usr/bin/env bash
# Start both the FastAPI backend and the React frontend in one command.
# The backend runs with nohup so it survives if the terminal closes.
# Usage: ./start.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

# Kill any existing processes on our ports
lsof -ti:8000 2>/dev/null | xargs kill -9 2>/dev/null || true
lsof -ti:5173 2>/dev/null | xargs kill -9 2>/dev/null || true

cleanup() {
    echo ""
    echo "Shutting down…"
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}
trap cleanup INT TERM

export PYTHONIOENCODING=utf-8
export LC_ALL=en_US.UTF-8

echo "Starting FastAPI backend on http://localhost:8000 …"
echo "  Backend log: $LOG_DIR/backend.log"
UVICORN_BIN="$SCRIPT_DIR/.venv/bin/uvicorn"
if [ ! -x "$UVICORN_BIN" ]; then
    echo "Error: $UVICORN_BIN not found or not executable."
    echo "Create the virtualenv and install requirements first."
    exit 1
fi
nohup "$UVICORN_BIN" api:app --host 0.0.0.0 --port 8000 > "$LOG_DIR/backend.log" 2>&1 &
BACKEND_PID=$!

echo "Starting React frontend on http://localhost:5173 …"
cd frontend && npm run dev &
FRONTEND_PID=$!

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  SMRAG is running!"
echo "  Frontend → http://localhost:5173"
echo "  Backend  → http://localhost:8000"
echo ""
echo "  Backend runs independently — even if"
echo "  this terminal closes, processing continues."
echo "  Backend log: $LOG_DIR/backend.log"
echo "  Press Ctrl+C to stop both."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

wait
