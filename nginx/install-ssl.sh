#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSL_DIR="$ROOT/nginx/ssl"
ARCHIVE="$ROOT/conversys-wildcard-cert.tar.gz"
if [[ ! -f "$ARCHIVE" && -f "$HOME/conversys-wildcard-cert.tar.gz" ]]; then
  cp "$HOME/conversys-wildcard-cert.tar.gz" "$ARCHIVE"
fi
FULLCHAIN="$SSL_DIR/fullchain.pem"
PRIVKEY="$SSL_DIR/privkey.pem"

mkdir -p "$SSL_DIR"

if [[ -f "$ARCHIVE" ]]; then
  echo "Extraindo $ARCHIVE..."
  tmp_dir="$(mktemp -d)"
  tar -xzf "$ARCHIVE" -C "$tmp_dir"

  cert_file=""
  key_file=""
  while IFS= read -r file; do
    case "${file,,}" in
      *priv*|*.key) key_file="$file" ;;
      *chain*|*full*|*.crt|*.pem)
        if [[ "$file" != *priv* && "$file" != *.key ]]; then
          cert_file="${cert_file:-$file}"
        fi
        ;;
    esac
  done < <(find "$tmp_dir" -type f \( -iname '*.pem' -o -iname '*.crt' -o -iname '*.key' \) | sort)

  if [[ -z "$cert_file" || -z "$key_file" ]]; then
    echo "ERRO: não encontrei certificado/chave dentro do tarball."
    find "$tmp_dir" -type f | sed 's/^/  /'
    rm -rf "$tmp_dir"
    exit 1
  fi

  cp "$cert_file" "$FULLCHAIN"
  cp "$key_file" "$PRIVKEY"
  chmod 644 "$FULLCHAIN"
  chmod 600 "$PRIVKEY"
  rm -rf "$tmp_dir"

  cert_count="$(grep -c 'BEGIN CERTIFICATE' "$FULLCHAIN" || true)"
  if [[ "$cert_count" -lt 2 ]]; then
    aia_url="$(openssl x509 -in "$FULLCHAIN" -noout -text 2>/dev/null | sed -n 's/^[[:space:]]*CA Issuers - URI:\(.*\)/\1/p' | head -1)"
    if [[ -n "$aia_url" ]]; then
      echo "Montando cadeia completa (intermediário Sectigo)..."
      tmp_ca="$(mktemp)"
      curl -fsS -o "$tmp_ca" "$aia_url"
      openssl x509 -in "$tmp_ca" -out "${tmp_ca}.pem" -outform PEM 2>/dev/null || cp "$tmp_ca" "${tmp_ca}.pem"
      cat "$FULLCHAIN" "${tmp_ca}.pem" > "${FULLCHAIN}.new"
      mv "${FULLCHAIN}.new" "$FULLCHAIN"
      rm -f "$tmp_ca" "${tmp_ca}.pem"
    fi
  fi

  echo "Certificado wildcard instalado em nginx/ssl/"
  exit 0
fi

if [[ -f "$FULLCHAIN" && -f "$PRIVKEY" ]]; then
  echo "Certificado já presente em nginx/ssl/."
  exit 0
fi

echo "Tarball não encontrado. Gerando certificado autoassinado temporário..."
"$ROOT/nginx/generate-selfsigned.sh"
