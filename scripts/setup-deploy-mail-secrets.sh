#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.github/deploy-mail.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Arquivo não encontrado: $ENV_FILE"
  echo "Copie .github/deploy-mail.env.example → .github/deploy-mail.env e preencha."
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

for key in MAIL_USERNAME MAIL_PASSWORD NOTIFY_EMAIL; do
  if [ -z "${!key:-}" ]; then
    echo "ERRO: $key vazio em $ENV_FILE"
    exit 1
  fi
done

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI não encontrado. Instale ou configure os secrets manualmente no GitHub:"
  echo "  MAIL_USERNAME, MAIL_PASSWORD, NOTIFY_EMAIL"
  exit 1
fi

cd "$ROOT"
gh secret set MAIL_USERNAME --body "$MAIL_USERNAME"
gh secret set MAIL_PASSWORD --body "$MAIL_PASSWORD"
gh secret set NOTIFY_EMAIL --body "$NOTIFY_EMAIL"
echo "Secrets atualizados no repositório."
