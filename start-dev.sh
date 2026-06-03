#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")"

if [ ! -d "$BACKEND_DIR/venv" ]; then
  echo "Backend virtualenv not found at: $BACKEND_DIR/venv"
  echo "Create it first or install the backend dependencies."
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend dependencies not found. Running npm install..."
  (cd "$FRONTEND_DIR" && npm install)
fi

echo "Starting Conversys Fut..."
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:3000"
if [ "$LAN_IP" != "localhost" ] && [ -n "$LAN_IP" ]; then
  echo "Network:  http://$LAN_IP:3000"
fi
echo ""
echo "Press Ctrl+C to stop both servers."

cleanup() {
  echo ""
  echo "Stopping servers..."
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

(
  cd "$BACKEND_DIR"
  source "venv/bin/activate"
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  export NEXT_PUBLIC_API_URL="http://$LAN_IP:8000"
  export BACKEND_API_URL="http://localhost:8000"
  npm run dev
) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
