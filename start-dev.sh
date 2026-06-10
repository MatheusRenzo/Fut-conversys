#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")"
BACKEND_PORT="${BACKEND_PORT:-8000}"
FRONTEND_PORT="${FRONTEND_PORT:-3000}"

check_port() {
  local port="$1"
  local label="$2"

  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "$label port $port is already in use."
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
    echo ""
    echo "Stop the process above or run with custom ports, for example:"
    echo "BACKEND_PORT=8010 FRONTEND_PORT=3010 fut-dev"
    exit 1
  fi
}

if [ ! -d "$BACKEND_DIR/venv" ]; then
  echo "Backend virtualenv not found at: $BACKEND_DIR/venv"
  echo "Create it first or install the backend dependencies."
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend dependencies not found. Running npm install..."
  (cd "$FRONTEND_DIR" && npm install)
fi

check_port "$BACKEND_PORT" "Backend"
check_port "$FRONTEND_PORT" "Frontend"

echo "Starting Conversys Fut..."
echo "Backend:  http://localhost:$BACKEND_PORT"
echo "Frontend: http://localhost:$FRONTEND_PORT"
if [ "$LAN_IP" != "localhost" ] && [ -n "$LAN_IP" ]; then
  echo "Network:  http://$LAN_IP:$FRONTEND_PORT"
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
  if [ -f ".env" ]; then
    set -a
    source ".env"
    set +a
  fi
  export MICROSOFT_REDIRECT_URI="http://$LAN_IP:$FRONTEND_PORT/api/auth/callback/microsoft"
  uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  export NEXT_PUBLIC_API_URL="http://$LAN_IP:$BACKEND_PORT"
  export BACKEND_API_URL="http://localhost:$BACKEND_PORT"
  export NEXT_ALLOWED_DEV_ORIGINS="$LAN_IP:$FRONTEND_PORT,localhost:$FRONTEND_PORT,127.0.0.1:$FRONTEND_PORT"
  npm run dev -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait "$BACKEND_PID" "$FRONTEND_PID"
