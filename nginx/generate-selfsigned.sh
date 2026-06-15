#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSL_DIR="$ROOT/nginx/ssl"
FULLCHAIN="$SSL_DIR/fullchain.pem"
PRIVKEY="$SSL_DIR/privkey.pem"
SERVER_IP="${APP_SERVER_IP:-127.0.0.1}"

mkdir -p "$SSL_DIR"

openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
  -keyout "$PRIVKEY" \
  -out "$FULLCHAIN" \
  -subj "/CN=*.conversys.global/O=Conversys/C=BR" \
  -addext "subjectAltName=DNS:*.conversys.global,DNS:conversys.global,DNS:localhost,IP:${SERVER_IP}" \
  2>/dev/null

chmod 644 "$FULLCHAIN"
chmod 600 "$PRIVKEY"
echo "Certificado autoassinado temporário criado (substitua pelo wildcard oficial)."
