#!/bin/sh
set -e

if [ -n "$DATABASE_URL" ]; then
  DB_HOST=$(echo "$DATABASE_URL" | sed 's|.*@||' | cut -d: -f1)
  DB_PORT=$(echo "$DATABASE_URL" | sed 's|.*@||' | cut -d: -f2 | cut -d/ -f1)
  DB_PORT=${DB_PORT:-5432}

  echo "Aguardando banco de dados em $DB_HOST:$DB_PORT..."
  for i in $(seq 1 30); do
    if nc -z "$DB_HOST" "$DB_PORT" 2>/dev/null; then
      echo "Banco disponível após $i tentativa(s)."
      break
    fi
    echo "  tentativa $i/30 — aguardando..."
    sleep 2
  done
fi

exec "$@"
