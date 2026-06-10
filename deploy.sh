#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== Fut-Conversys — Deploy de Produção ==="

if [ ! -f .env ]; then
  echo "ERRO: arquivo .env não encontrado. Crie-o antes de continuar."
  exit 1
fi

echo "[1/5] Preparando certificado SSL..."
chmod +x nginx/install-ssl.sh nginx/generate-selfsigned.sh
./nginx/install-ssl.sh

echo "[2/5] Parando containers antigos..."
docker compose down --remove-orphans 2>/dev/null || true

echo "[3/5] Construindo imagens..."
docker compose build

echo "[4/5] Subindo serviços..."
docker compose up -d

echo "[5/5] Aguardando serviços ficarem prontos..."
sleep 8

echo ""
echo "--- Status dos containers ---"
docker compose ps

echo ""
echo "--- Teste de saúde (HTTPS local :443) ---"
for i in $(seq 1 12); do
  if curl -kfsS https://localhost/api/backend/api/health > /dev/null 2>&1; then
    echo "HTTPS OK (nginx :443)"
    break
  fi
  echo "Aguardando nginx... ($i/12)"
  sleep 5
done

echo ""
echo "=== Deploy concluído! ==="
echo "  Interno:  https://<REDACTED-IP>"
echo "  Externo:  https://fut.conversys.global:9443  (firewall WAN 9443 → nginx 443)"
echo ""
echo "Certificado oficial: ~/conversys-wildcard-cert.tar.gz → ./nginx/install-ssl.sh && docker compose restart nginx"
