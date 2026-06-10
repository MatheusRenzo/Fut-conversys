#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "=== Fut-Conversys — Deploy de Produção ==="

if [ ! -f .env ]; then
  echo "ERRO: arquivo .env não encontrado. Crie-o antes de continuar."
  exit 1
fi

echo "[1/4] Parando containers antigos..."
docker compose down --remove-orphans 2>/dev/null || true

echo "[2/4] Construindo imagens..."
docker compose build --no-cache

echo "[3/4] Subindo serviços..."
docker compose up -d

echo "[4/4] Aguardando serviços ficarem prontos..."
sleep 8

echo ""
echo "--- Status dos containers ---"
docker compose ps

echo ""
echo "--- Teste de saúde do backend ---"
for i in $(seq 1 12); do
  if curl -sf http://localhost:2000/api/backend/api/health > /dev/null 2>&1; then
    echo "Backend OK"
    break
  fi
  echo "Aguardando backend... ($i/12)"
  sleep 5
done

echo ""
echo "=== Deploy concluído! Acesse: http://<REDACTED-IP>:2000 ==="
