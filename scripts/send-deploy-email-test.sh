#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${1:-$ROOT/.github/deploy-mail.env}"
STATUS="${2:-success}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Crie $ENV_FILE a partir de .github/deploy-mail.env.example"
  exit 1
fi

# shellcheck disable=SC1090
source "$ENV_FILE"

COMMIT_MSG="$(git -C "$ROOT" log -1 --pretty=%B 2>/dev/null | head -1)"
COMMIT_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || echo local)"
COMMIT_SHORT="$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo local)"

export DEPLOY_STATUS="$STATUS"
export COMMIT_MESSAGE="$COMMIT_MSG"
export COMMIT_SHA="$COMMIT_SHA"
export COMMIT_SHORT="$COMMIT_SHORT"
export BRANCH="$(git -C "$ROOT" branch --show-current 2>/dev/null || echo main)"
export ACTOR="$(whoami)"
export REPOSITORY="MatheusRenzo/Fut-conversys"
export RUN_URL="https://github.com/MatheusRenzo/Fut-conversys/actions"
export APP_URL="https://fut.conversys.global:9443/bolao"
export TIMESTAMP="$(date -u '+%Y-%m-%d %H:%M UTC')"
export ERROR_LOG="${ERROR_LOG:-Simulação de erro: container backend não subiu (teste).}"
export OUTPUT_FILE="/tmp/fut-deploy-email-test.html"

python3 "$ROOT/.github/scripts/build-deploy-email.py"

python3 - <<'PY'
import os, smtplib, ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

user = os.environ["MAIL_USERNAME"]
password = os.environ["MAIL_PASSWORD"]
to = os.environ.get("NOTIFY_EMAIL", user)
html = Path(os.environ["OUTPUT_FILE"]).read_text(encoding="utf-8")
ok = os.environ.get("DEPLOY_STATUS", "success") == "success"
subject = "✅ [TESTE] Deploy bolão — Fut Conversys" if ok else "❌ [TESTE] Falha deploy — Fut Conversys"

msg = MIMEMultipart("alternative")
msg["Subject"] = subject
msg["From"] = f"Fut Conversys Deploy <{user}>"
msg["To"] = to
msg.attach(MIMEText("Notificação de deploy Fut Conversys. Abra em HTML.", "plain", "utf-8"))
msg.attach(MIMEText(html, "html", "utf-8"))

with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
    smtp.starttls(context=ssl.create_default_context())
    smtp.login(user, password)
    smtp.sendmail(user, [to], msg.as_string())
print(f"E-mail de teste enviado para {to}")
PY
