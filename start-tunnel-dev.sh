#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
TUNNEL_LOG="$(mktemp -t fut-conversys-cloudflared.XXXXXX.log)"
BACKEND_PORT="${BACKEND_PORT:-8010}"
FRONTEND_PORT="${FRONTEND_PORT:-3010}"

check_port() {
  local port="$1"
  local label="$2"

  if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "$label port $port is already in use."
    lsof -nP -iTCP:"$port" -sTCP:LISTEN
    echo ""
    echo "Stop the process above or run with custom ports, for example:"
    echo "BACKEND_PORT=8011 FRONTEND_PORT=3011 fut-dev"
    exit 1
  fi
}

if ! command -v cloudflared >/dev/null 2>&1; then
  echo "cloudflared não encontrado. Instale com: brew install cloudflared"
  exit 1
fi

if [ ! -d "$BACKEND_DIR/venv" ]; then
  echo "Backend virtualenv not found at: $BACKEND_DIR/venv"
  exit 1
fi

if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
  echo "Frontend dependencies not found. Running npm install..."
  (cd "$FRONTEND_DIR" && npm install)
fi

check_port "$BACKEND_PORT" "Backend"
check_port "$FRONTEND_PORT" "Frontend"

cleanup() {
  echo ""
  echo "Stopping tunnel and servers..."
  kill "${TUNNEL_PID:-}" "${BACKEND_PID:-}" "${FRONTEND_PID:-}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Opening Cloudflare Tunnel..."
cloudflared tunnel --url "http://localhost:$FRONTEND_PORT" --no-autoupdate >"$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

PUBLIC_URL=""
for _ in $(seq 1 60); do
  PUBLIC_URL="$(
    grep -Eo 'https://[-a-zA-Z0-9]+\.trycloudflare\.com' "$TUNNEL_LOG" \
      | grep -v '^https://api\.trycloudflare\.com$' \
      | head -n 1 \
      || true
  )"
  if [ -n "$PUBLIC_URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$PUBLIC_URL" ]; then
  echo "Não consegui capturar a URL do Cloudflare Tunnel."
  echo "Log: $TUNNEL_LOG"
  exit 1
fi

MICROSOFT_TUNNEL_REDIRECT_URI="$PUBLIC_URL/api/auth/callback/microsoft"

echo "Starting Conversys Fut with Cloudflare Tunnel..."
echo "Backend local:  http://localhost:$BACKEND_PORT"
echo "Frontend local: http://localhost:$FRONTEND_PORT"
echo "Frontend: $PUBLIC_URL"
echo "Azure Redirect URI:"
echo "$MICROSOFT_TUNNEL_REDIRECT_URI"
echo ""
echo "Copie essa Redirect URI e cadastre no Microsoft Entra ID."
echo "Press Ctrl+C to stop tunnel and servers."

(
  cd "$BACKEND_DIR"
  source "venv/bin/activate"
  if [ -f ".env" ]; then
    set -a
    source ".env"
    set +a
  fi
  export MICROSOFT_REDIRECT_URI="$MICROSOFT_TUNNEL_REDIRECT_URI"
  uvicorn main:app --reload --host 0.0.0.0 --port "$BACKEND_PORT"
) &
BACKEND_PID=$!

(
  cd "$FRONTEND_DIR"
  export BACKEND_API_URL="http://localhost:$BACKEND_PORT"
  export MICROSOFT_REDIRECT_URI="$MICROSOFT_TUNNEL_REDIRECT_URI"
  export PUBLIC_APP_URL="$PUBLIC_URL"
  export NEXT_PUBLIC_API_URL="$PUBLIC_URL"
  export NEXT_ALLOWED_DEV_ORIGINS="${PUBLIC_URL#https://}"
  npm run dev -- --port "$FRONTEND_PORT"
) &
FRONTEND_PID=$!

wait "$TUNNEL_PID" "$BACKEND_PID" "$FRONTEND_PID"
