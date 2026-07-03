#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

LOCK_FILE="/tmp/fut-conversys-deploy.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "ERRO: outro deploy já está em andamento (lock: $LOCK_FILE)."
  echo "Aguarde o GitHub Actions ou um deploy.sh anterior terminar."
  exit 1
fi

echo "=== Fut-Conversys — Deploy de Produção ==="

# Garante que o que vai pro ar é EXATAMENTE o que está no git (origin), e não
# arquivos soltos/esquecidos na pasta. O reset --hard mexe só nos arquivos
# versionados; .env, certificados (nginx/ssl/*, *.tar.gz) e demais arquivos
# ignorados pelo .gitignore são preservados.
BRANCH="${DEPLOY_BRANCH:-main}"
echo "[0/5] Sincronizando com o git (origin/$BRANCH)..."
git fetch --prune origin "$BRANCH"
git checkout -q "$BRANCH" 2>/dev/null || git checkout -q -B "$BRANCH" "origin/$BRANCH"
git reset --hard "origin/$BRANCH"
echo "  -> deploy a partir do commit $(git rev-parse --short HEAD)"

if [ ! -f .env ]; then
  echo "ERRO: arquivo .env não encontrado. Crie-o antes de continuar."
  exit 1
fi

echo "[1/5] Preparando certificado SSL..."
chmod +x nginx/install-ssl.sh nginx/generate-selfsigned.sh
./nginx/install-ssl.sh

# Build ANTES de derrubar: se o build falhar (ex.: instabilidade de rede pra
# baixar a imagem base), o site CONTINUA no ar — o set -e aborta aqui sem tocar
# nos containers em execução. Só troca pras imagens novas se o build der certo.
echo "[2/4] Construindo imagens (site segue no ar durante o build)..."
docker compose build

echo "[3/4] Subindo serviços (troca pras imagens novas, sem down prévio)..."
docker compose up -d --remove-orphans

echo "[4/4] Aguardando serviços ficarem prontos..."
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
echo "  Interno:  https://${APP_SERVER_IP:-localhost}"
echo "  Externo:  https://fut.conversys.global:9443  (firewall WAN 9443 → nginx 443)"
echo ""
echo "Certificado oficial: ~/conversys-wildcard-cert.tar.gz → ./nginx/install-ssl.sh && docker compose restart nginx"
