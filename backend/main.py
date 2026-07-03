import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import smtplib
import time as time_module
import unicodedata
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, inspect, or_, text
from sqlalchemy.orm import Session, joinedload, subqueryload

from database import Base, SessionLocal, engine, get_db
import models

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
VERIFIED_DOMAIN = "conversys.global"
PASSWORD_ITERATIONS = 260000
TOKEN_TTL_SECONDS = 60 * 60 * 8

_raw_secret = os.getenv("AUTH_SECRET") or os.getenv("SECRET_KEY")
if not _raw_secret:
    import sys
    # Sem segredo o token vira forjável (HMAC com chave conhecida). Falha de
    # forma segura por padrão; só libera fallback de dev com opt-in explícito.
    if os.getenv("ALLOW_INSECURE_AUTH_SECRET") == "1":
        print("AVISO: AUTH_SECRET ausente — usando segredo de dev inseguro.", file=sys.stderr)
        _raw_secret = "fut-conversys-dev-secret-insecure"
    else:
        print(
            "ERRO FATAL: AUTH_SECRET não definido. Defina no .env (ou ALLOW_INSECURE_AUTH_SECRET=1 só em dev).",
            file=sys.stderr,
        )
        sys.exit(1)
AUTH_SECRET = _raw_secret
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"[^a-z0-9._-]+")
OPENFOOTBALL_2026_CUP_URL = os.getenv(
    "WORLD_CUP_OPENFOOTBALL_URL",
    "https://raw.githubusercontent.com/openfootball/worldcup/master/2026--usa/cup.txt",
)
OPENFOOTBALL_2026_FINALS_URL = os.getenv(
    "WORLD_CUP_OPENFOOTBALL_FINALS_URL",
    "https://raw.githubusercontent.com/openfootball/worldcup/master/2026--usa/cup_finals.txt",
)
WIKIPEDIA_SQUADS_URL = os.getenv(
    "WORLD_CUP_SQUADS_URL",
    "https://en.wikipedia.org/w/api.php?action=parse&page=2026_FIFA_World_Cup_squads&prop=wikitext&format=json&formatversion=2",
)
# Fonte secundária de resultados para conferência cruzada (football-data.org)
# Sem a chave, o bolão segue funcionando só com o openfootball
FOOTBALL_DATA_API_KEY = os.getenv("FOOTBALL_DATA_API_KEY", "").strip()
FOOTBALL_DATA_MATCHES_URL = os.getenv(
    "FOOTBALL_DATA_MATCHES_URL",
    "https://api.football-data.org/v4/competitions/WC/matches",
)
# Gols ao vivo via API-Football (api-sports.io). O plano grátis não libera a
# temporada 2026 nos endpoints normais, mas o fixtures?live=all entrega os
# jogos em andamento com eventos de gol — usamos só durante as partidas,
# com orçamento diário para não estourar as 100 requisições/dia do plano.
# 2ª fonte de goleadores (grátis) — confirma os artilheiros da fonte paga
THESPORTSDB_KEY = os.getenv("THESPORTSDB_KEY", "123").strip()
THESPORTSDB_BASE = os.getenv("THESPORTSDB_BASE", "https://www.thesportsdb.com/api/v1/json")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
# SMTP para o e-mail de transparência (palpites enviados quando a aposta fecha).
# Aceita MAIL_USERNAME/MAIL_PASSWORD (mesmos secrets do deploy) ou SMTP_USER/SMTP_PASSWORD.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = (os.getenv("SMTP_USER") or os.getenv("MAIL_USERNAME") or "").strip()
SMTP_PASSWORD = (os.getenv("SMTP_PASSWORD") or os.getenv("MAIL_PASSWORD") or "").strip()
SMTP_FROM = (os.getenv("SMTP_FROM") or SMTP_USER).strip()
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Bolão Fut Conversys").strip()
PUBLIC_APP_URL = os.getenv("PUBLIC_APP_URL", "").strip()
OPENAI_CHAT_URL = os.getenv("OPENAI_CHAT_URL", "https://api.openai.com/v1/chat/completions")
# Pode ter VÁRIAS chaves da API-Football (cada uma 100/dia) — usamos a que
# tiver mais cota no dia, somando ~200+/dia e ficando bem mais ao vivo.
API_FOOTBALL_KEYS = [
    k.strip()
    for k in ",".join(
        filter(None, [os.getenv("API_FOOTBALL_KEY", ""), os.getenv("API_FOOTBALL_KEY_2", ""), os.getenv("API_FOOTBALL_KEY_3", "")])
    ).split(",")
    if k.strip()
]
API_FOOTBALL_KEY = API_FOOTBALL_KEYS[0] if API_FOOTBALL_KEYS else ""
API_FOOTBALL_LIVE_URL = os.getenv("API_FOOTBALL_LIVE_URL", "https://v3.football.api-sports.io/fixtures?live=all")
API_FOOTBALL_FIXTURE_URL = os.getenv("API_FOOTBALL_FIXTURE_URL", "https://v3.football.api-sports.io/fixtures")
API_FOOTBALL_LEAGUE_ID = int(os.getenv("API_FOOTBALL_LEAGUE_ID", "1"))
API_FOOTBALL_DAILY_BUDGET = int(os.getenv("API_FOOTBALL_DAILY_BUDGET", "100"))
# Reserva por chave: para de usar UMA chave quando restam só N req dela
API_FOOTBALL_DAILY_RESERVE = int(os.getenv("API_FOOTBALL_DAILY_RESERVE", "0"))
# Gap mínimo entre chamadas live=all (goleadores ao vivo). Com 2 chaves (200/dia)
# dá pra ser bem mais frequente; o PLACAR já vem da football-data a cada ciclo.
API_FOOTBALL_LIVE_GAP = max(120, int(os.getenv("API_FOOTBALL_LIVE_GAP_SECONDS", "240")))
# Piso do gap ao vivo: o PLACAR já vem grátis da football-data a cada ciclo, então
# não precisa torrar a cota buscando NOME de goleador a cada 75s. 180s é ao-vivo o
# bastante e deixa cota pra todos os jogos do dia.
API_FOOTBALL_LIVE_GAP_FLOOR = max(120, int(os.getenv("API_FOOTBALL_LIVE_GAP_FLOOR", "180")))
# Limite POR MINUTO da API-Football (plano grátis = 10/min). Usamos 9 pra ter
# folga e NUNCA estourar — protege contra rajada no cold-start (vários jogos a
# finalizar de uma vez). O que passar fica pro próximo ciclo (idempotente).
API_FOOTBALL_MINUTE_LIMIT = max(1, int(os.getenv("API_FOOTBALL_MINUTE_LIMIT", "9")))
# Limite POR CICLO da TheSportsDB (grátis, 30/min). Cada jogo conferido custa até
# ~4 chamadas (busca dia ±1 + timeline).
THESPORTSDB_CYCLE_LIMIT = max(1, int(os.getenv("THESPORTSDB_CYCLE_LIMIT", "4")))
# Limite POR MINUTO da TheSportsDB (30/min). Como o ciclo caiu pra 30s (2 ciclos/min),
# o teto por ciclo sozinho não basta — esta trava por janela de minuto garante que
# NUNCA passa de 30/min mesmo com vários ciclos rápidos seguidos.
THESPORTSDB_MINUTE_LIMIT = max(1, int(os.getenv("THESPORTSDB_MINUTE_LIMIT", "26")))
# Backoff por jogo na confirmação grátis: re-tenta a TheSportsDB no máx a cada 15min
# (em vez de todo ciclo de 30s), pra não consultar à toa jogos que ela ainda não tem.
THESPORTSDB_CONFIRM_BACKOFF = max(120, int(os.getenv("THESPORTSDB_CONFIRM_BACKOFF", "900")))
# Rede de segurança: depois disso desde o início, nenhum jogo (mesmo prorrogação +
# pênaltis ≈ 3h) ainda está rolando. Se nenhuma fonte confirmou o fim, encerra
# sozinho com o melhor placar — assim nenhum jogo fica "ao vivo" por horas.
WORLD_CUP_FORCE_FINISH_AFTER = timedelta(hours=int(os.getenv("WORLD_CUP_FORCE_FINISH_HOURS", "4")))
# AO VIVO EVENT-DRIVEN: a football-data (grátis) detecta o GOL (placar sobe) a cada
# ciclo; aí disparamos a busca do NOME na API paga NA HORA — ~1 chamada por gol em
# vez de polling cego. Reação rápida quando há gol sem goleador; poll de segurança
# espaçado quando não há (quase não gasta cota).
API_FOOTBALL_GOAL_GAP = max(40, int(os.getenv("API_FOOTBALL_GOAL_GAP", "60")))
API_FOOTBALL_SAFETY_GAP = max(300, int(os.getenv("API_FOOTBALL_SAFETY_GAP", "600")))
# Quantas vezes re-tenta a paga no MESMO gol novo até achar o goleador (ela às vezes
# demora a publicar o evento). Depois disso espera o próximo gol. ~60s entre tentativas.
API_FOOTBALL_LIVE_RETRY_MAX = max(2, int(os.getenv("API_FOOTBALL_LIVE_RETRY_MAX", "2")))
THESPORTSDB_LIVE_RETRY_MAX = max(1, int(os.getenv("THESPORTSDB_LIVE_RETRY_MAX", "2")))
# Re-confirmação grátis (TheSportsDB + openfootball + IA) roda após o fim
WORLD_CUP_RECONFIRM_AFTER = timedelta(minutes=int(os.getenv("WORLD_CUP_RECONFIRM_MINUTES", "10")))
WORLD_CUP_RECONFIRM_MAX_TRIES = max(1, int(os.getenv("WORLD_CUP_RECONFIRM_MAX_TRIES", "6")))
WORLD_CUP_RECONFIRM_RETRY_GAP = timedelta(minutes=int(os.getenv("WORLD_CUP_RECONFIRM_RETRY_MINUTES", "3")))
# Intervalo do loop: rápido quando há jogo ao vivo, lento quando não há. 15s deixa
# o PLACAR/GOL bem ao vivo (football-data 10/min aguenta: 1 chamada/ciclo = ~4/min) e
# faz o gatilho de goleador disparar logo após o gol; a cota paga é protegida à parte
# (event-driven por gol, não por ciclo). Antes era 30s; baixamos porque o board não
# atualiza mais o placar dentro do request — o ao vivo agora depende só deste loop.
WORLD_CUP_LIVE_INTERVAL = max(12, int(os.getenv("WORLD_CUP_LIVE_INTERVAL_SECONDS", "15")))
WORLD_CUP_IDLE_INTERVAL = max(120, int(os.getenv("WORLD_CUP_SYNC_INTERVAL_SECONDS", "600")))
# Schedule (openfootball/football-data) revalida no máximo a cada N segundos
WORLD_CUP_SCHEDULE_MIN_GAP = max(120, int(os.getenv("WORLD_CUP_SCHEDULE_MIN_GAP", "300")))
BOARD_LIVE_SCORE_GAP = max(10, int(os.getenv("BOARD_LIVE_SCORE_GAP", "12")))
# Wikipedia usa nomes diferentes do openfootball para algumas seleções
WIKIPEDIA_TEAM_ALIASES = {
    "United States": "USA",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
}
OPENFOOTBALL_SQUAD_ALIASES = {
    "United States": "USA",
    "Bosnia and Herzegovina": "Bosnia & Herzegovina",
    # Nomes oficiais FIFA usados pela football-data.org
    "Korea Republic": "South Korea",
    "Czechia": "Czech Republic",
    "Bosnia-Herzegovina": "Bosnia & Herzegovina",
    "Cape Verde Islands": "Cape Verde",
    "Côte d'Ivoire": "Ivory Coast",
    "Cote d'Ivoire": "Ivory Coast",
    "Türkiye": "Turkey",
    "Turkiye": "Turkey",
    "Cabo Verde": "Cape Verde",
    "Congo DR": "DR Congo",
    "IR Iran": "Iran",
}
PLACEHOLDER_TEAM_PATTERN = re.compile(
    r"^(?:[12][A-L]|W\d+|L\d+|3[A-L](?:/[A-L])+(?:/[A-L])*)$"
)
WORLD_CUP_YEAR = int(os.getenv("WORLD_CUP_YEAR", "2026"))
# Palpites fecham 1 hora antes do início de cada jogo
WORLD_CUP_BET_CUTOFF = timedelta(hours=1)
WC_GAME_EVENTS_PER_MATCH_MAX = int(os.getenv("WC_GAME_EVENTS_PER_MATCH_MAX", "60"))
WC_GAME_EVENTS_TOTAL_MAX = int(os.getenv("WC_GAME_EVENTS_TOTAL_MAX", "1200"))
MONTHS_EN = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}


def normalize_world_cup_team(team: str) -> str:
    cleaned = re.sub(r"\s+", " ", team or "").strip()
    return OPENFOOTBALL_SQUAD_ALIASES.get(cleaned, cleaned)


def is_placeholder_world_cup_team(team: str) -> bool:
    name = re.sub(r"\s+", " ", team or "").strip()
    if not name:
        return True
    if "/" in name:
        return True
    return bool(PLACEHOLDER_TEAM_PATTERN.fullmatch(name))


def is_bettable_world_cup_game(game: models.WorldCupGame) -> bool:
    return not is_placeholder_world_cup_team(game.home_team) and not is_placeholder_world_cup_team(game.away_team)


def world_cup_game_lock_passed(game: models.WorldCupGame) -> bool:
    # Mesma regra do fechamento de palpites: 1h antes do início (ou jogo já começou)
    if (game.status or "scheduled") != "scheduled":
        return True
    return bool(game.kickoff_at and game.kickoff_at - WORLD_CUP_BET_CUTOFF <= datetime.utcnow())


def squad_team_key(team: str) -> str:
    return normalize_world_cup_team(team)


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PASSWORD_ITERATIONS,
    ).hex()
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${password_hash}"


def verify_password(password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False

    try:
        algorithm, iterations, salt, stored_hash = password_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    candidate_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        int(iterations),
    ).hex()
    return hmac.compare_digest(candidate_hash, stored_hash)


def create_access_token(user_id: int) -> str:
    expires_at = int((datetime.utcnow() + timedelta(seconds=TOKEN_TTL_SECONDS)).timestamp())
    nonce = secrets.token_urlsafe(12)
    payload = f"{user_id}.{expires_at}.{nonce}"
    signature = hmac.new(AUTH_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"v1.{payload}.{signature}"


def get_user_id_from_token(token: str) -> int | None:
    parts = token.split(".")
    if len(parts) != 5 or parts[0] != "v1":
        return None

    try:
        user_id = int(parts[1])
        expires_at = int(parts[2])
    except ValueError:
        return None

    if datetime.utcnow().timestamp() > expires_at:
        return None

    payload = ".".join(parts[1:4])
    expected_signature = hmac.new(
        AUTH_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, parts[4]):
        return None

    return user_id


SAFE_URL_SCHEMES = ("http://", "https://")

def validate_url(value: str | None) -> str | None:
    if not value:
        return value
    stripped = value.strip()
    if not any(stripped.lower().startswith(scheme) for scheme in SAFE_URL_SCHEMES):
        raise HTTPException(status_code=400, detail="URL inválida: apenas http e https são permitidos")
    if len(stripped) > 2048:
        raise HTTPException(status_code=400, detail="URL muito longa")
    return stripped


MAX_IMAGE_DATA_URL_LENGTH = 4_000_000  # ~3 MB de imagem em base64


def validate_image_url(value: str | None) -> str | None:
    if not value:
        return value
    stripped = value.strip()
    if stripped.lower().startswith("data:image/"):
        if len(stripped) > MAX_IMAGE_DATA_URL_LENGTH:
            raise HTTPException(status_code=400, detail="Imagem muito grande — envie uma foto menor")
        return stripped
    return validate_url(stripped)


# Avatares/banners ficam no banco como data URI base64 (até ~200KB cada).
# Embutir isso em cada user_summary deixava o JSON do bolão com centenas de MB,
# então o JSON carrega só uma URL versionada e o navegador cacheia a imagem.
USER_MEDIA_FIELDS = {"avatar": "avatar_url", "banner": "banner_url"}
_user_media_versions: dict[tuple[int, str, int], str] = {}
DATA_URL_PATTERN = re.compile(r"^data:([^;,]+)?(;base64)?,(.*)$", re.DOTALL)
OWN_MEDIA_URL_PATTERN = re.compile(r"^/api/(?:backend/)?api/users/\d+/(?:avatar|banner)(?:\?.*)?$")


def user_media_public_url(user_id: int, kind: str, value: str | None) -> str | None:
    if not value or not value.startswith("data:"):
        return value
    key = (user_id, kind, len(value))
    version = _user_media_versions.get(key)
    if version is None:
        version = hashlib.md5(value.encode("utf-8")).hexdigest()[:12]
        _user_media_versions[key] = version
    return f"/api/backend/api/users/{user_id}/{kind}?v={version}"


def serve_user_media(db: Session, user_id: int, kind: str, if_none_match: str | None) -> Response:
    field = USER_MEDIA_FIELDS[kind]
    user = db.query(models.User).filter(models.User.id == user_id).first()
    value = getattr(user, field, None) if user else None
    if not value:
        raise HTTPException(status_code=404, detail="Imagem não encontrada")
    if not value.startswith("data:"):
        return RedirectResponse(value)
    match = DATA_URL_PATTERN.match(value)
    if not match:
        raise HTTPException(status_code=404, detail="Imagem inválida")
    mime = match.group(1) or "image/png"
    payload = match.group(3)
    try:
        raw = base64.b64decode(payload) if match.group(2) else urllib.parse.unquote_to_bytes(payload)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status_code=404, detail="Imagem inválida") from exc
    etag = '"' + hashlib.md5(value.encode("utf-8")).hexdigest() + '"'
    headers = {"Cache-Control": "public, max-age=604800, immutable", "ETag": etag}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return Response(content=raw, media_type=mime, headers=headers)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def normalize_username(value: str) -> str:
    username = USERNAME_PATTERN.sub("-", value.strip().lower())
    username = username.strip(".-_")
    return username[:32]


def validate_password_strength(password: str, email: str, name: str) -> None:
    password_lower = password.lower()
    rules = (
        (len(password) >= 8, "A senha precisa ter pelo menos 8 caracteres"),
        (any(char.islower() for char in password), "Inclua uma letra minúscula"),
        (any(char.isupper() for char in password), "Inclua uma letra maiúscula"),
        (any(char.isdigit() for char in password), "Inclua um número"),
        (any(not char.isalnum() for char in password), "Inclua um símbolo"),
    )
    for passed, message in rules:
        if not passed:
            raise HTTPException(status_code=400, detail=message)

    email_user = email.split("@", 1)[0].lower()
    name_parts = [part.lower() for part in name.split() if len(part) >= 3]
    if email_user and email_user in password_lower:
        raise HTTPException(status_code=400, detail="A senha não pode conter seu e-mail")
    if any(part in password_lower for part in name_parts):
        raise HTTPException(status_code=400, detail="A senha não pode conter seu nome")


def is_conversys_email(email: str | None) -> bool:
    return bool(email and email.lower().endswith(f"@{VERIFIED_DOMAIN}"))


def microsoft_env() -> dict[str, str]:
    return {
        "client_id": os.getenv("MICROSOFT_CLIENT_ID", ""),
        "tenant_id": os.getenv("MICROSOFT_TENANT_ID", ""),
        "client_secret": os.getenv("MICROSOFT_CLIENT_SECRET", ""),
        "redirect_uri": os.getenv(
            "MICROSOFT_REDIRECT_URI",
            "http://localhost:3000/api/auth/callback/microsoft",
        ),
    }


def microsoft_is_configured() -> bool:
    config = microsoft_env()
    return all(config.values())


def microsoft_authorize_url(state: str | None = None) -> str:
    config = microsoft_env()
    if not microsoft_is_configured():
        raise HTTPException(status_code=500, detail="Microsoft Auth não configurado")

    # O state é gerado e validado na camada Next (cookie de mesma origem) para
    # proteger contra login-CSRF; aqui só repassamos o valor recebido.
    query = urllib.parse.urlencode(
        {
            "client_id": config["client_id"],
            "response_type": "code",
            "redirect_uri": config["redirect_uri"],
            "response_mode": "query",
            "scope": "openid profile email User.Read",
            "state": state or secrets.token_urlsafe(24),
            "prompt": "select_account",
        }
    )
    return f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/authorize?{query}"


# Teto de leitura de respostas externas: evita estourar memória se uma fonte
# (ou um MITM) devolver um corpo gigante. 25 MB cobre folgado os maiores JSONs.
MAX_EXTERNAL_RESPONSE_BYTES = 25 * 1024 * 1024


def read_capped(response, limit: int = MAX_EXTERNAL_RESPONSE_BYTES) -> bytes:
    data = response.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(status_code=502, detail="Resposta da fonte externa excedeu o limite permitido")
    return data


def request_json(url: str, data: dict[str, str] | None = None, token: str | None = None) -> dict[str, Any]:
    encoded_data = urllib.parse.urlencode(data).encode("utf-8") if data else None
    request = urllib.request.Request(url, data=encoded_data)
    if data:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(read_capped(response).decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise HTTPException(status_code=400, detail=f"Falha Microsoft Auth: {body}") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível conectar ao Microsoft Entra") from exc


def request_microsoft_photo_data_url(token: str) -> str | None:
    request = urllib.request.Request("https://graph.microsoft.com/v1.0/me/photo/$value")
    request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            content_type = response.headers.get("Content-Type", "image/jpeg")
            photo = read_capped(response)
    except urllib.error.HTTPError as exc:
        if exc.code in {404, 403}:
            return None
        raise HTTPException(status_code=400, detail="Não foi possível buscar a foto do Microsoft Graph") from exc
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível conectar ao Microsoft Graph") from exc

    if not photo:
        return None

    encoded_photo = base64.b64encode(photo).decode("ascii")
    return f"data:{content_type};base64,{encoded_photo}"


def ensure_schema() -> None:
    Base.metadata.create_all(bind=engine)

    columns: dict[str, dict[str, str]] = {
        "users": {
            "email": "VARCHAR",
            "display_name": "VARCHAR",
            "title": "VARCHAR",
            "avatar_url": "VARCHAR",
            "banner_url": "VARCHAR",
            "banner_position_x": "INTEGER DEFAULT 50",
            "banner_position_y": "INTEGER DEFAULT 50",
            "profile_frame": "VARCHAR DEFAULT 'conversys'",
            "cosmetic_tier": "VARCHAR DEFAULT 'starter'",
            "animated_banner": "BOOLEAN DEFAULT FALSE",
            "profile_effect": "VARCHAR DEFAULT 'off'",
            "avatar_config": "TEXT",
            "player_rating": "INTEGER DEFAULT 78",
            "verified_domain": "BOOLEAN DEFAULT FALSE",
            "verified_enabled": "BOOLEAN DEFAULT FALSE",
            "show_verified_badge": "BOOLEAN DEFAULT TRUE",
            "is_admin": "BOOLEAN DEFAULT FALSE",
            "provider": "VARCHAR DEFAULT 'local'",
            "provider_subject": "VARCHAR",
            "tenant_id": "VARCHAR",
            "goals": "INTEGER DEFAULT 0",
            "assists": "INTEGER DEFAULT 0",
            "fouls": "INTEGER DEFAULT 0",
            "barbecue_score": "INTEGER DEFAULT 0",
            "created_at": "TIMESTAMP",
        },
        "matches": {
            "event_type": "VARCHAR DEFAULT 'pelada'",
            "status": "VARCHAR DEFAULT 'scheduled'",
            "cover_url": "VARCHAR",
            "created_at": "TIMESTAMP",
        },
        "match_rsvps": {
            "created_at": "TIMESTAMP",
        },
        "posts": {
            "title": "VARCHAR",
            "goals_scored": "INTEGER DEFAULT 0",
            "goal_status": "VARCHAR DEFAULT 'none'",
            "goal_reviewed_by_id": "INTEGER",
            "goal_reviewed_at": "TIMESTAMP",
        },
        "likes": {
            "reaction_type": "VARCHAR DEFAULT 'torcida'",
            "created_at": "TIMESTAMP",
        },
        "comments": {
            "parent_id": "INTEGER",
            "media_url": "VARCHAR",
            "media_type": "VARCHAR",
        },
        "world_cup_games": {
            "external_id": "VARCHAR",
            "match_number": "INTEGER",
            "home_team": "VARCHAR",
            "away_team": "VARCHAR",
            "group_label": "VARCHAR",
            "stage": "VARCHAR DEFAULT 'group-stage'",
            "venue": "VARCHAR",
            "kickoff_at": "TIMESTAMP",
            "status": "VARCHAR DEFAULT 'scheduled'",
            "home_score": "INTEGER",
            "away_score": "INTEGER",
            "scorers": "TEXT",
            "source": "VARCHAR",
            "api_fixture_id": "INTEGER",
            "scorers_final": "BOOLEAN DEFAULT FALSE",
            "api_mid_checked": "BOOLEAN DEFAULT FALSE",
            "scorers_confirmed": "BOOLEAN DEFAULT FALSE",
            "scorers_confirmations": "INTEGER DEFAULT 0",
            "confirmation_sources": "VARCHAR",
            "end_source": "VARCHAR",
            "halftime": "BOOLEAN DEFAULT FALSE",
            "home_penalties": "INTEGER",
            "away_penalties": "INTEGER",
            "live_period": "VARCHAR",
            "finished_at": "TIMESTAMP",
            "reconfirmed": "BOOLEAN DEFAULT FALSE",
            "created_at": "TIMESTAMP",
        },
        "world_cup_predictions": {
            "user_id": "INTEGER",
            "game_id": "INTEGER",
            "home_score": "INTEGER DEFAULT 0",
            "away_score": "INTEGER DEFAULT 0",
            "scorer_guess": "VARCHAR",
            "scorer_hit": "BOOLEAN DEFAULT FALSE",
            "points": "INTEGER DEFAULT 0",
            "status": "VARCHAR DEFAULT 'pending'",
            "created_at": "TIMESTAMP",
            "updated_at": "TIMESTAMP",
        },
    }

    inspector = inspect(engine)
    with engine.begin() as connection:
        for table_name, table_columns in columns.items():
            if table_name not in inspector.get_table_names():
                continue

            existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
            for column_name, column_type in table_columns.items():
                if column_name not in existing_columns:
                    connection.execute(
                        text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
                    )
        if "posts" in inspector.get_table_names():
            connection.execute(
                text(
                    """
                    UPDATE posts
                    SET goal_status = CASE
                        WHEN COALESCE(goals_scored, 0) > 0 THEN 'approved'
                        ELSE 'none'
                    END
                    WHERE goal_status IS NULL
                       OR goal_status = ''
                       OR (goal_status = 'none' AND COALESCE(goals_scored, 0) > 0)
                    """
                )
            )


ensure_schema()

app = FastAPI(title="Conversys Fut App API")


_sync_lock_handle = None


def world_cup_sync_leader() -> bool:
    global _sync_lock_handle
    lock_path = os.getenv("WORLD_CUP_SYNC_LOCK", "/tmp/fut-world-cup-sync.lock")
    try:
        handle = open(lock_path, "w")
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _sync_lock_handle = handle
        return True
    except BlockingIOError:
        return False


@app.on_event("startup")
def start_world_cup_auto_sync() -> None:
    if os.getenv("WORLD_CUP_AUTO_SYNC", "1") == "0":
        return
    if not world_cup_sync_leader():
        return

    def bootstrap_sync() -> None:
        try:
            session = SessionLocal()
            try:
                imported, updated = apply_world_cup_sync(session)
                print(
                    f"[world-cup-sync] bootstrap ok: imported={imported} updated={updated}",
                    flush=True,
                )
            finally:
                session.close()
        except Exception as exc:
            print(f"[world-cup-sync] bootstrap failed: {exc}", flush=True)
            record_world_cup_sync_failure(str(exc))

    threading.Thread(target=bootstrap_sync, daemon=True, name="world-cup-sync-bootstrap").start()
    thread = threading.Thread(target=world_cup_sync_loop, daemon=True, name="world-cup-sync")
    thread.start()

_cors_env = os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
_cors_origins = [o.strip() for o in _cors_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


# Tetos de tamanho fecham flood/DoS por texto gigante (rejeita com 422 na borda)
class RegisterRequest(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=160)
    password: str = Field(max_length=200)
    username: str | None = Field(default=None, max_length=40)


class MicrosoftCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class PostCreateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str = Field(max_length=5000)
    image_url: str | None = Field(default=None, max_length=4_200_000)
    match_id: int | None = None
    goals_scored: int | None = None


class CommentCreateRequest(BaseModel):
    text: str = Field(max_length=2000)
    parent_id: int | None = None
    media_url: str | None = Field(default=None, max_length=4_200_000)
    media_type: str | None = Field(default=None, max_length=20)


class ReactionRequest(BaseModel):
    reaction_type: str = "torcida"


class GoalReviewRequest(BaseModel):
    status: str


class VerifiedFeatureRequest(BaseModel):
    verified_enabled: bool


class RSVPRequest(BaseModel):
    status: str


class EventCreateRequest(BaseModel):
    title: str = Field(max_length=160)
    event_type: str = Field(default="pelada", max_length=40)
    location: str = Field(max_length=200)
    date: datetime
    description: str = Field(max_length=3000)
    max_players: int = 20
    cover_url: str | None = Field(default=None, max_length=4_200_000)


class WorldCupGameCreateRequest(BaseModel):
    home_team: str
    away_team: str
    kickoff_at: datetime
    group_label: str | None = None
    stage: str = "group-stage"
    venue: str | None = None
    match_number: int | None = None
    external_id: str | None = None
    source: str | None = None


class WorldCupGameResultRequest(BaseModel):
    home_score: int
    away_score: int
    status: str = "finished"
    scorers: str | None = None


class WorldCupPredictionRequest(BaseModel):
    home_score: int = Field(ge=0, le=99)
    away_score: int = Field(ge=0, le=99)
    scorer_guess: str | None = Field(default=None, max_length=80)


class WorldCupChampionPickRequest(BaseModel):
    team: str


class WorldCupChampionAnnounceRequest(BaseModel):
    team: str


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)
    title: str | None = Field(default=None, max_length=120)
    bio: str | None = Field(default=None, max_length=600)
    position: str | None = Field(default=None, max_length=60)
    favorite_team: str | None = Field(default=None, max_length=80)
    favorite_player: str | None = Field(default=None, max_length=80)
    avatar_url: str | None = Field(default=None, max_length=4_200_000)
    banner_url: str | None = Field(default=None, max_length=4_200_000)
    banner_position_x: int | None = None
    banner_position_y: int | None = None
    profile_frame: str | None = Field(default=None, max_length=40)
    cosmetic_tier: str | None = Field(default=None, max_length=40)
    animated_banner: bool | None = None
    profile_effect: str | None = Field(default=None, max_length=40)
    show_verified_badge: bool | None = None
    avatar_config: dict[str, Any] | None = None
    player_rating: int | None = None


SUPPORTED_REACTIONS = (
    "torcida",
    "golaco",
    "churras",
    "resenha",
    "midia",
    "bebedeira",
)
SUPPORTED_MEDIA_TYPES = ("image", "gif")
SUPPORTED_FRAMES = (
    "none",
    "conversys",
    "copa",
    "brasil",
    "argentina",
    "franca",
    "portugal",
    "espanha",
    "alemanha",
    "inglaterra",
    "eua",
    "mexico",
    "canada",
    "africa_sul",
    "coreia_sul",
    "tchequia",
    "bosnia",
    "qatar",
    "suica",
    "marrocos",
    "haiti",
    "escocia",
    "paraguai",
    "australia",
    "turquia",
    "curacao",
    "costa_marfim",
    "equador",
    "holanda",
    "japao",
    "suecia",
    "tunisia",
    "belgica",
    "egito",
    "ira",
    "nova_zelandia",
    "cabo_verde",
    "arabia_saudita",
    "uruguai",
    "senegal",
    "iraque",
    "noruega",
    "argelia",
    "austria",
    "jordania",
    "rd_congo",
    "uzbequistao",
    "colombia",
    "croacia",
    "gana",
    "panama",
    "nitro_plus",
    "pro",
    "legend",
    "world",
    "neon",
    "pulse",
    "champion",
)
SUPPORTED_TIERS = ("starter",)
SUPPORTED_EFFECTS = ("off", "pulse", "stadium", "orbit", "nitro")
GOAL_STATUSES = ("none", "pending", "approved", "rejected")
WORLD_CUP_GAME_STATUSES = ("scheduled", "live", "finished", "postponed")
WORLD_CUP_PREDICTION_STATUSES = ("pending", "scored")


def is_admin_user(user: models.User | None) -> bool:
    return bool(user and user.is_admin)


def has_verified_features(user: models.User | None) -> bool:
    return bool(user and user.verified_enabled)


def clear_verified_features(user: models.User) -> None:
    user.profile_frame = "none"
    user.profile_effect = "off"
    user.animated_banner = False
    user.show_verified_badge = False


def clamp_banner_position(value: int | None) -> int:
    if value is None:
        return 50
    return max(0, min(100, int(value)))


def profile_effect_value(user: models.User) -> str:
    if not has_verified_features(user):
        return "off"
    effect = user.profile_effect or "off"
    if effect in SUPPORTED_EFFECTS and effect != "off":
        return effect
    return "off"


def goal_status_for(post: models.Post) -> str:
    status_value = (post.goal_status or "").strip().lower()
    if status_value in GOAL_STATUSES:
        return status_value
    return "approved" if (post.goals_scored or 0) > 0 else "none"


def approved_goals_for_post(post: models.Post) -> int:
    if goal_status_for(post) != "approved":
        return 0
    return max(0, post.goals_scored or 0)


def approved_goals_for_user(user: models.User) -> int:
    return sum(approved_goals_for_post(post) for post in user.posts)


def default_avatar_config(user: models.User | None = None) -> dict[str, str]:
    position = (user.position or "").lower() if user else ""
    return {
        "body": "athletic",
        "presentation": "player",
        "skin": "medium",
        "hair": "short",
        "kit": "home",
        "shorts": "navy",
        "boots": "cyan",
        "gender": "neutral",
        "pose": "captain" if "admin" in position else "striker",
    }


def avatar_config(user: models.User) -> dict[str, Any]:
    if not user.avatar_config:
        return default_avatar_config(user)
    try:
        data = json.loads(user.avatar_config)
    except (TypeError, ValueError):
        return default_avatar_config(user)
    return {**default_avatar_config(user), **data}


def player_traits(user: models.User) -> dict[str, int]:
    reaction_totals = {key: 0 for key in SUPPORTED_REACTIONS}
    for post in user.posts:
        for like in post.likes:
            reaction_type = like.reaction_type or "torcida"
            if reaction_type not in reaction_totals:
                reaction_type = "torcida"
            reaction_totals[reaction_type] += 1

    post_goals = approved_goals_for_user(user)
    media_posts = len([post for post in user.posts if post.image_url])
    comments_received = sum(len(post.comments) for post in user.posts)
    comments_made = len(user.comments)
    media_comments = len([comment for comment in user.comments if comment.media_url])
    reactions_received = sum(reaction_totals.values())
    barbecue = user.barbecue_score or 0
    matches = len([rsvp for rsvp in user.rsvps if rsvp.status == "going"])

    # Retornos decrescentes: cada reação/ação dá um empurrão que vai diminuindo,
    # então ninguém vira "craque" com 1 like — subir exige atividade de verdade,
    # e conquistas reais (gol aprovado, presença) pesam mais que reação solta.
    def grow(base: float, *contribs: tuple[int, float]) -> int:
        total = base + sum(weight * (max(0, count) ** 0.5) for count, weight in contribs)
        return int(min(99, max(40, round(total))))

    # Todo mundo começa no PISO (40 = novato) e sobe só com atividade real.
    # Cada curtida soma pouco (retorno decrescente); gol/presença pesam mais.
    posts = len(user.posts)
    churrasco = grow(40, (barbecue, 7), (reaction_totals["churras"], 4), (matches, 4), (reaction_totals["bebedeira"], 2))
    bebedeira = grow(40, (reaction_totals["bebedeira"], 5), (reaction_totals["churras"], 3), (comments_received, 2), (matches, 2))
    golaco = grow(40, (post_goals, 12), (reaction_totals["golaco"], 4))  # gol vale muito mais que like
    resenha = grow(40, (posts, 4), (comments_received, 4), (comments_made, 2), (reaction_totals["resenha"], 4))
    midia = grow(40, (media_posts, 7), (reaction_totals["midia"], 4), (media_comments, 3))
    torcida = grow(40, (reaction_totals["torcida"], 4), (reactions_received, 2), (matches, 4))
    # Overall pondera mais o futebol de verdade (gol, garra, presença) que o social
    overall = round((golaco * 1.3 + torcida * 1.15 + churrasco * 1.1 + resenha + midia + bebedeira * 0.95) / 6.5)
    return {
        "overall": min(99, max(40, overall)),
        "churrasco": max(40, churrasco),
        "bebedeira": max(40, bebedeira),
        "golaco_score": max(40, golaco),
        "resenha": max(40, resenha),
        "midia": max(40, midia),
        "torcida": max(40, torcida),
        "reaction_torcida": reaction_totals["torcida"],
        "reaction_golaco": reaction_totals["golaco"],
        "reaction_churras": reaction_totals["churras"],
        "reaction_resenha": reaction_totals["resenha"],
        "reaction_midia": reaction_totals["midia"],
        "reaction_bebedeira": reaction_totals["bebedeira"],
        "post_goals": post_goals,
        "media_posts": media_posts,
        "comments_received": comments_received,
        "comments_made": comments_made,
        "media_comments": media_comments,
        "attack": max(40, golaco),
        "passing": max(40, resenha),
        "defense": max(40, torcida),
        "stamina": max(40, bebedeira),
        "skill": max(40, midia),
        "vibe": max(40, churrasco),
    }


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso ausente",
        )

    token = authorization.replace("Bearer ", "", 1)
    user_id = get_user_id_from_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de acesso inválido",
        )

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário não encontrado",
        )

    return user


def public_user_summary(user: models.User) -> dict[str, Any]:
    """Resposta pública: sem email, sem info de provider."""
    data = user_summary(user)
    data.pop("email", None)
    return data


def user_summary(user: models.User, include_rating: bool = True) -> dict[str, Any]:
    # include_rating=False evita o player_traits (que varre posts/likes/comentários/rsvps
    # do usuário) — usado em listas grandes, como o ranking do bolão, onde o rating não
    # é exibido. Assim não precisamos carregar o "grafo social" inteiro de cada usuário.
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "name": user.display_name or user.name,
        "display_name": user.display_name,
        "title": user.title,
        "bio": user.bio,
        "position": user.position,
        "favorite_team": user.favorite_team,
        "favorite_player": user.favorite_player,
        "avatar_url": user_media_public_url(user.id, "avatar", user.avatar_url),
        "banner_url": user_media_public_url(user.id, "banner", user.banner_url),
        "banner_position_x": clamp_banner_position(user.banner_position_x),
        "banner_position_y": clamp_banner_position(user.banner_position_y),
        "profile_frame": user.profile_frame if has_verified_features(user) else "none",
        "cosmetic_tier": "starter",
        "animated_banner": bool(user.animated_banner and has_verified_features(user)),
        "profile_effect": profile_effect_value(user),
        "show_verified_badge": bool(
            has_verified_features(user) and (user.show_verified_badge if user.show_verified_badge is not None else True)
        ),
        "avatar_config": avatar_config(user),
        "player_rating": player_traits(user)["overall"] if include_rating else None,
        "verified_domain": bool(user.verified_domain),
        "verified_enabled": has_verified_features(user),
        "is_admin": is_admin_user(user),
    }


def player_stats(user: models.User) -> dict[str, int]:
    going_rsvps = [rsvp for rsvp in user.rsvps if rsvp.status == "going"]
    account_age_days = 0
    if user.created_at:
        account_age_days = max(0, (datetime.utcnow() - user.created_at).days)
    return {
        "matches_played": len(going_rsvps),
        "goals": approved_goals_for_user(user),
        "assists": user.assists or 0,
        "fouls": user.fouls or 0,
        "barbecue_score": user.barbecue_score or 0,
        "posts": len(user.posts),
        "likes_received": sum(len(post.likes) for post in user.posts),
        "account_age_days": account_age_days,
        **player_traits(user),
    }


def match_response(match: models.Match, user: models.User | None = None) -> dict[str, Any]:
    going = [rsvp for rsvp in match.rsvps if rsvp.status == "going"]
    user_rsvp = None
    if user:
        user_rsvp = next((rsvp for rsvp in match.rsvps if rsvp.user_id == user.id), None)

    return {
        "id": match.id,
        "title": match.title,
        "event_type": match.event_type or "pelada",
        "location": match.location,
        "date": match.date.isoformat(),
        "description": match.description,
        "max_players": match.max_players,
        "status": match.status or "scheduled",
        "cover_url": match.cover_url,
        "confirmed_players": len(going),
        "user_has_rsvpd": bool(user_rsvp and user_rsvp.status == "going"),
        "user_rsvp_status": user_rsvp.status if user_rsvp else None,
        "attendees": [user_summary(rsvp.user) for rsvp in going],
    }


def to_utc_naive(value: datetime) -> datetime:
    if value.tzinfo and value.utcoffset():
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value.replace(tzinfo=None)


def clamp_prediction_score(value: int) -> int:
    return max(0, min(30, int(value)))


def iso_utc(value: datetime | None) -> str | None:
    # Datas são gravadas em UTC naive; o offset explícito evita que o navegador
    # interprete o horário como local (bug do horário UTC exibido como Brasília)
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc).isoformat()


def game_outcome(home_score: int, away_score: int) -> str:
    if home_score > away_score:
        return "home"
    if away_score > home_score:
        return "away"
    return "draw"


WORLD_CUP_POINTS_EXACT = 3
WORLD_CUP_POINTS_OUTCOME = 1
WORLD_CUP_POINTS_SCORER = 1
WORLD_CUP_POINTS_CHAMPION = 10


def effective_game_outcome(
    game_home: int,
    game_away: int,
    home_pens: int | None = None,
    away_pens: int | None = None,
) -> str:
    """Vencedor REAL da partida. No mata-mata, se o tempo normal/prorrogação empatou
    e foi pra pênaltis, quem vence os pênaltis é o vencedor (decide o ponto de Vencedor).
    Na fase de grupos (sem pênaltis) é só o placar normal."""
    base = game_outcome(game_home, game_away)
    if base == "draw" and home_pens is not None and away_pens is not None and home_pens != away_pens:
        return "home" if home_pens > away_pens else "away"
    return base


def world_cup_prediction_points(
    prediction_home: int,
    prediction_away: int,
    game_home: int | None,
    game_away: int | None,
    home_pens: int | None = None,
    away_pens: int | None = None,
) -> int:
    if game_home is None or game_away is None:
        return 0
    # Placar exato é sempre pelo tempo normal/prorrogação (pênaltis não contam pro placar)
    if prediction_home == game_home and prediction_away == game_away:
        return WORLD_CUP_POINTS_EXACT
    # Vencedor: no mata-mata decidido nos pênaltis, vale o vencedor dos pênaltis
    if game_outcome(prediction_home, prediction_away) == effective_game_outcome(
        game_home, game_away, home_pens, away_pens
    ):
        return WORLD_CUP_POINTS_OUTCOME
    return 0


def game_scorer_names(game: models.WorldCupGame) -> list[str]:
    if not game.scorers:
        return []
    parts = re.split(r"[,;\n]", game.scorers)
    return [name for name in (normalize_scorer_name(part) for part in parts) if name]


def score_world_cup_game(game: models.WorldCupGame) -> None:
    scorers = game_scorer_names(game)
    for prediction in game.predictions:
        points = world_cup_prediction_points(
            prediction.home_score or 0,
            prediction.away_score or 0,
            game.home_score,
            game.away_score,
            game.home_penalties,
            game.away_penalties,
        )
        hit = scorer_guess_matches(scorers, prediction.scorer_guess)
        if hit:
            points += WORLD_CUP_POINTS_SCORER
        prediction.scorer_hit = hit
        prediction.points = points
        prediction.status = "scored" if game.status == "finished" else "pending"
        prediction.updated_at = datetime.utcnow()


def world_cup_prediction_response(prediction: models.WorldCupPrediction) -> dict[str, Any]:
    return {
        "id": prediction.id,
        "game_id": prediction.game_id,
        "home_score": prediction.home_score or 0,
        "away_score": prediction.away_score or 0,
        "scorer_guess": prediction.scorer_guess,
        "scorer_hit": bool(prediction.scorer_hit),
        "points": prediction.points or 0,
        "status": prediction.status or "pending",
        "created_at": iso_utc(prediction.created_at),
        "updated_at": iso_utc(prediction.updated_at),
        "user": user_summary(prediction.user),
    }


def world_cup_game_response(game: models.WorldCupGame, user: models.User | None = None) -> dict[str, Any]:
    viewer_prediction = None
    if user:
        viewer_prediction = next((prediction for prediction in game.predictions if prediction.user_id == user.id), None)

    lock_passed = world_cup_game_lock_passed(game)
    sorted_predictions = sorted(
        game.predictions,
        key=lambda prediction: (-(prediction.points or 0), prediction.created_at or datetime.min),
    )

    return {
        "id": game.id,
        "external_id": game.external_id,
        "match_number": game.match_number,
        "home_team": game.home_team,
        "away_team": game.away_team,
        "group_label": game.group_label,
        "stage": game.stage or "group-stage",
        "venue": game.venue,
        "kickoff_at": iso_utc(game.kickoff_at),
        "status": game.status or "scheduled",
        "halftime": bool(game.halftime),
        "home_score": game.home_score,
        "away_score": game.away_score,
        "home_penalties": game.home_penalties,
        "away_penalties": game.away_penalties,
        "live_period": game.live_period,
        "is_knockout": (game.stage or "group-stage") != "group-stage",
        "scorers": game.scorers,
        "source": game.source,
        "predictions_count": len(game.predictions),
        "is_placeholder": not is_bettable_world_cup_game(game),
        "bettable": is_bettable_world_cup_game(game),
        "lock_passed": lock_passed,
        "viewer_prediction": world_cup_prediction_response(viewer_prediction) if viewer_prediction else None,
        # Quem já palpitou fica visível sempre; o palpite em si só depois do fechamento
        "bettors": [user_summary(prediction.user) for prediction in sorted_predictions],
        "predictions": [world_cup_prediction_response(prediction) for prediction in sorted_predictions]
        if lock_passed
        else [],
    }


def world_cup_leaderboard_response(db: Session, exclude_game_id: int | None = None) -> list[dict[str, Any]]:
    # Agregamos os pontos por usuário SEM dar JOIN do usuário nas predictions: o
    # avatar/banner é base64 e seria duplicado em cada uma das centenas de linhas,
    # estourando o tempo do request. Carregamos o objeto User só dos ~30 que entram
    # no ranking, depois de ordenar. Placar dos jogos vem num lookup leve por id.
    rows: dict[int, dict[str, Any]] = {}

    def empty_row() -> dict[str, Any]:
        return {
            "user_id": None,
            "points": 0,
            "predictions": 0,
            "scored_predictions": 0,
            "exact_scores": 0,
            "outcome_hits": 0,
            "scorer_hits": 0,
            "champion_team": None,
            "champion_points": 0,
        }

    game_scores = {
        gid: (home, away, hpen, apen)
        for gid, home, away, hpen, apen in db.query(
            models.WorldCupGame.id,
            models.WorldCupGame.home_score,
            models.WorldCupGame.away_score,
            models.WorldCupGame.home_penalties,
            models.WorldCupGame.away_penalties,
        ).all()
    }

    predictions = db.query(models.WorldCupPrediction).all()
    for prediction in predictions:
        # reconstrução "antes da rodada": ignora o jogo excluído por completo
        # (pontos E desempates), pra calcular a posição real anterior
        if exclude_game_id is not None and prediction.game_id == exclude_game_id:
            continue
        row = rows.setdefault(prediction.user_id, empty_row())
        row["user_id"] = prediction.user_id
        row["points"] += prediction.points or 0
        row["predictions"] += 1
        if prediction.status == "scored":
            row["scored_predictions"] += 1
            home_score, away_score, home_pens, away_pens = game_scores.get(
                prediction.game_id, (None, None, None, None)
            )
            if home_score is not None and away_score is not None:
                if prediction.home_score == home_score and prediction.away_score == away_score:
                    row["exact_scores"] += 1
                if game_outcome(prediction.home_score or 0, prediction.away_score or 0) == effective_game_outcome(
                    home_score, away_score, home_pens, away_pens
                ):
                    row["outcome_hits"] += 1
            if prediction.scorer_hit:
                row["scorer_hits"] += 1

    champion_picks = db.query(
        models.WorldCupChampionPick.user_id,
        models.WorldCupChampionPick.team,
        models.WorldCupChampionPick.points,
    ).all()
    # Palpite de campeã é público no ranking (é único e não pode ser trocado)
    for pick_user_id, pick_team, pick_points in champion_picks:
        row = rows.setdefault(pick_user_id, empty_row())
        row["user_id"] = pick_user_id
        row["champion_team"] = pick_team
        row["champion_points"] = pick_points or 0
        row["points"] += pick_points or 0

    # Só entra no ranking quem palpitou em jogos ou já pontuou; palpite de campeão sozinho não lista
    leaderboard = sorted(
        (row for row in rows.values() if row["predictions"] > 0 or row["points"] > 0),
        key=lambda item: (item["points"], item["exact_scores"], item["outcome_hits"], item["scorer_hits"], item["predictions"]),
        reverse=True,
    )[:30]

    # Só agora buscamos os usuários que de fato aparecem (no máximo 30), numa query só.
    user_ids = [row["user_id"] for row in leaderboard]
    users = (
        {user.id: user for user in db.query(models.User).filter(models.User.id.in_(user_ids)).all()}
        if user_ids
        else {}
    )
    leaderboard = [row for row in leaderboard if users.get(row["user_id"]) is not None]
    for index, row in enumerate(leaderboard, start=1):
        row["user"] = user_summary(users[row.pop("user_id")], include_rating=False)
        row["rank"] = index

    # Movimentação = posição ANTES da última rodada menos a posição agora (persistida
    # em wc_rank_movement pelo sync, que roda a cada ciclo). Sobrevive a reload e pega
    # a subida real ao longo da rodada — não só do "último jogo".
    raw_mv = get_app_setting(db, "wc_rank_movement")
    raw_gain = get_app_setting(db, "wc_rank_gain")
    try:
        moves = json.loads(raw_mv) if raw_mv else {}
    except json.JSONDecodeError:
        moves = {}
    try:
        gains = json.loads(raw_gain) if raw_gain else {}
    except json.JSONDecodeError:
        gains = {}
    for row in leaderboard:
        row["movement"] = int(moves.get(str(row["user"]["id"]), 0) or 0)
        row["round_gain"] = int(gains.get(str(row["user"]["id"]), 0) or 0)

    return leaderboard[:30]


def update_rank_movement(db: Session) -> None:
    """Atualiza a movimentação do ranking: guarda a posição de cada um ANTES da
    última rodada (snapshot que só avança quando um novo jogo encerra) e calcula o
    delta vs a posição atual. Chamado pelo sync (que faz commit)."""
    lb = world_cup_leaderboard_response(db)
    current = {str(row["user"]["id"]): row["rank"] for row in lb}
    current_pts = {str(row["user"]["id"]): row["points"] for row in lb}
    finished = db.query(models.WorldCupGame).filter(models.WorldCupGame.status == "finished").count()
    raw = get_app_setting(db, "wc_rank_state")
    try:
        state = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        state = None
    if not state:
        # 1ª vez: reconstrói a posição/pontos de ANTES da última rodada (tira os
        # pontos do último jogo encerrado) pra TODO MUNDO — assim o movimento e o
        # ganho real da última rodada já aparecem, em vez de zerar todos.
        last_game = (
            db.query(models.WorldCupGame)
            .filter(models.WorldCupGame.status == "finished")
            .order_by(models.WorldCupGame.kickoff_at.desc())
            .first()
        )
        # reconstrói o ranking REAL de antes do último jogo (exclui o jogo inteiro:
        # pontos e desempates) — assim quem virou de posição mostra a seta certa
        before_lb = world_cup_leaderboard_response(db, exclude_game_id=last_game.id) if last_game else lb
        prev = {str(e["user"]["id"]): e["rank"] for e in before_lb}
        prev_pts = {str(e["user"]["id"]): e["points"] for e in before_lb}
        state = {"prev": prev, "prev_pts": prev_pts, "curr": current, "curr_pts": current_pts, "games": finished}
    elif state.get("games", 0) < finished:
        # novo jogo encerrou → a posição/pontos "de antes" passam a ser os curr anteriores
        prev = state.get("curr", current)
        prev_pts = state.get("curr_pts", current_pts)
        state = {"prev": prev, "prev_pts": prev_pts, "curr": current, "curr_pts": current_pts, "games": finished}
    else:
        prev = state.get("prev", current)
        prev_pts = state.get("prev_pts", current_pts)
        state = {"prev": prev, "prev_pts": prev_pts, "curr": current, "curr_pts": current_pts, "games": finished}
    movement = {uid: int(prev.get(uid, rank)) - int(rank) for uid, rank in current.items()}
    # ganho de pontos na rodada (pega o seu +3 mesmo sem virar de posição)
    gain = {uid: int(pts) - int(prev_pts.get(uid, pts)) for uid, pts in current_pts.items()}
    set_app_setting(db, "wc_rank_state", json.dumps(state, ensure_ascii=False))
    set_app_setting(db, "wc_rank_movement", json.dumps(movement, ensure_ascii=False))
    set_app_setting(db, "wc_rank_gain", json.dumps(gain, ensure_ascii=False))


def world_cup_stage_from_section(section: str) -> tuple[str, str | None]:
    normalized = section.strip().lower()
    if normalized.startswith("group "):
        return "group-stage", section.replace("Group", "").strip()
    if "round of 32" in normalized:
        return "round-of-32", None
    if "round of 16" in normalized:
        return "round-of-16", None
    if "quarter" in normalized:
        return "quarter-finals", None
    if "semi" in normalized:
        return "semi-finals", None
    if "third" in normalized:
        return "third-place", None
    if "final" in normalized:
        return "final", None
    return "group-stage", None


def normalize_scorer_name(value: str | None) -> str:
    # Remove acentos para casar nomes entre fontes diferentes
    # (Wikipedia escreve "Jiménez", outras fontes às vezes "Jimenez")
    decomposed = unicodedata.normalize("NFKD", value or "")
    cleaned = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    cleaned = cleaned.replace(".", "").replace("-", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip().lower()
    return cleaned


def scorer_guess_matches(actual_names: list[str], guess: str | None) -> bool:
    normalized_guess = normalize_scorer_name(guess)
    if not normalized_guess or not actual_names:
        return False
    guess_tokens = normalized_guess.split(" ")
    for name in actual_names:
        if not name:
            continue
        if normalized_guess == name:
            return True
        if normalized_guess in name or name in normalized_guess:
            return True
        name_tokens = name.split(" ")
        overlap = {token for token in guess_tokens if len(token) > 2} & {
            token for token in name_tokens if len(token) > 2
        }
        # Só conta sobrenome em comum — prenome igual sozinho não basta
        # (palpite "Gabriel Martinelli" não pode pontuar com gol de "Gabriel Jesus")
        surname_overlap = {token for token in overlap if token != guess_tokens[0] or token != name_tokens[0]}
        if not surname_overlap:
            continue
        # Sobrenome igual mas prenomes começando diferente = jogadores distintos
        # (palpite "Thiago Silva" não pontua com gol de "Bernardo Silva")
        if (
            len(guess_tokens) > 1
            and len(name_tokens) > 1
            and guess_tokens[0] not in surname_overlap
            and name_tokens[0] not in surname_overlap
            and guess_tokens[0][0] != name_tokens[0][0]
        ):
            continue
        return True
    return False


def parse_openfootball_scorers_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith("(") or ")" not in stripped:
        return None
    if re.fullmatch(r"\(\d+\)", stripped):
        return None

    inner = stripped[1 : stripped.rfind(")")].strip()
    if not inner:
        return None

    names: list[str] = []
    for section in inner.split(";"):
        section = re.sub(r"\([^)]*\)", " ", section)
        for match in re.finditer(
            r"([A-Za-zÀ-ÿ'`.-]+(?:\s+[A-Za-zÀ-ÿ'`.-]+)*)\s+\d{1,2}(?:\+\d{1,2})?'",
            section,
        ):
            name = re.sub(r"\s+", " ", match.group(1)).strip(" ,")
            if name:
                names.append(name)

    if not names:
        return None

    seen: set[str] = set()
    ordered: list[str] = []
    for name in names:
        key = normalize_scorer_name(name)
        if key and key not in seen:
            seen.add(key)
            ordered.append(name)
    return ", ".join(ordered)


def parse_openfootball_matchup(matchup: str) -> tuple[str, str, int | None, int | None] | None:
    matchup = re.sub(r"\s+", " ", matchup).strip()
    versus_match = re.match(r"^(.+?)\s+v\s+(.+)$", matchup, re.IGNORECASE)
    if versus_match:
        return versus_match.group(1).strip(), versus_match.group(2).strip(), None, None

    cleaned = re.sub(r"\([^)]*\)", " ", matchup)
    cleaned = cleaned.replace("–", "-").replace("—", "-")  # normaliza traços
    cleaned = re.sub(r"\ba\.?e\.?t\.?", " ", cleaned, flags=re.IGNORECASE)
    # disputa de pênaltis em QUALQUER ordem: "3-4 pen." ou "pen. 3-4"
    cleaned = re.sub(r"\d{1,2}\s*-\s*\d{1,2}\s*pen\.?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"pen\.?\s*\d{1,2}\s*-\s*\d{1,2}", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[,;]", " ", cleaned)  # vírgula/; que sobra da anotação
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    score_match = re.match(r"^(.+?)\s+(\d{1,2})-(\d{1,2})\s+(.+)$", cleaned)
    if not score_match:
        return None
    return (
        score_match.group(1).strip(),
        score_match.group(4).strip(),
        int(score_match.group(2)),
        int(score_match.group(3)),
    )


def parse_openfootball_kickoff(
    current_date: tuple[int, int],
    hour: int,
    minute: int,
    offset_hours: int | None,
    year: int = WORLD_CUP_YEAR,
) -> datetime:
    month, day = current_date
    if offset_hours is None:
        return datetime(year, month, day, hour, minute)
    kickoff_local = datetime(
        year,
        month,
        day,
        hour,
        minute,
        tzinfo=timezone(timedelta(hours=offset_hours)),
    )
    return kickoff_local.astimezone(timezone.utc).replace(tzinfo=None)


def parse_openfootball_game_line(
    line: str,
    current_date: tuple[int, int] | None,
    match_counter: int,
    year: int = WORLD_CUP_YEAR,
) -> dict[str, Any] | None:
    if not current_date:
        return None

    utc_match = re.match(
        r"^(?:\((\d+)\)\s*)?(\d{1,2}:\d{2})\s+UTC([+-]\d{1,2})\s+(.+?)(?:\s+@\s+(.+))?$",
        line,
        re.IGNORECASE,
    )
    if utc_match:
        parsed = parse_openfootball_matchup(utc_match.group(4).strip())
        if not parsed:
            return None
        home_team, away_team, home_score, away_score = parsed
        hour, minute = [int(part) for part in utc_match.group(2).split(":", 1)]
        match_number = int(utc_match.group(1)) if utc_match.group(1) else match_counter
        return {
            "external_id": f"openfootball-{year}-{match_number}",
            "match_number": match_number,
            "home_team": normalize_world_cup_team(home_team),
            "away_team": normalize_world_cup_team(away_team),
            "kickoff_at": parse_openfootball_kickoff(current_date, hour, minute, int(utc_match.group(3)), year),
            "venue": re.sub(r"\s+", " ", utc_match.group(5)).strip() if utc_match.group(5) else None,
            "home_score": home_score,
            "away_score": away_score,
            "scorers": None,
            "source": "openfootball",
        }

    legacy_time_match = re.match(
        r"^(?:\((\d+)\)\s*)?(\d{1,2}:\d{2})\s+(.+?)(?:\s+@\s+(.+))?$",
        line,
    )
    if legacy_time_match and "UTC" not in line.upper():
        parsed = parse_openfootball_matchup(legacy_time_match.group(3).strip())
        if not parsed:
            return None
        home_team, away_team, home_score, away_score = parsed
        hour, minute = [int(part) for part in legacy_time_match.group(2).split(":", 1)]
        match_number = int(legacy_time_match.group(1)) if legacy_time_match.group(1) else match_counter
        return {
            "external_id": f"openfootball-{year}-{match_number}",
            "match_number": match_number,
            "home_team": normalize_world_cup_team(home_team),
            "away_team": normalize_world_cup_team(away_team),
            "kickoff_at": parse_openfootball_kickoff(current_date, hour, minute, None, year),
            "venue": re.sub(r"\s+", " ", legacy_time_match.group(4)).strip() if legacy_time_match.group(4) else None,
            "home_score": home_score,
            "away_score": away_score,
            "scorers": None,
            "source": "openfootball",
        }

    no_time_match = re.match(r"^(?:\((\d+)\)\s*)?(.+?)(?:\s+@\s+(.+))?$", line)
    if no_time_match and ":" not in no_time_match.group(2)[:5]:
        parsed = parse_openfootball_matchup(no_time_match.group(2).strip())
        if not parsed:
            return None
        home_team, away_team, home_score, away_score = parsed
        if home_score is None and away_score is None:
            return None
        match_number = int(no_time_match.group(1)) if no_time_match.group(1) else match_counter
        return {
            "external_id": f"openfootball-{year}-{match_number}",
            "match_number": match_number,
            "home_team": normalize_world_cup_team(home_team),
            "away_team": normalize_world_cup_team(away_team),
            "kickoff_at": parse_openfootball_kickoff(current_date, 12, 0, None, year),
            "venue": re.sub(r"\s+", " ", no_time_match.group(3)).strip() if no_time_match.group(3) else None,
            "home_score": home_score,
            "away_score": away_score,
            "scorers": None,
            "source": "openfootball",
        }

    return None


def parse_openfootball_world_cup(text_data: str, year: int = WORLD_CUP_YEAR) -> list[dict[str, Any]]:
    games: list[dict[str, Any]] = []
    stage = "group-stage"
    group_label = None
    current_date: tuple[int, int] | None = None
    match_counter = 1
    # Anotações de gols podem ocupar várias linhas, ex:
    #   (Hwang In-Beom 67' Oh Hyeon-Gyu 80';
    #     Ladislav Krejcí 59')
    pending_scorer_lines: list[str] = []

    for raw_line in text_data.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("="):
            continue

        if pending_scorer_lines:
            if line.startswith("▪") or re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s", line):
                pending_scorer_lines = []
            else:
                pending_scorer_lines.append(line)
                if ")" in line:
                    scorers = parse_openfootball_scorers_line(" ".join(pending_scorer_lines))
                    pending_scorer_lines = []
                    if scorers and games:
                        games[-1]["scorers"] = scorers
                continue

        if line.startswith("(") and ")" not in line:
            pending_scorer_lines = [line]
            continue

        if line.startswith("▪"):
            section = line.replace("▪", "", 1).strip()
            stage, group_label = world_cup_stage_from_section(section)
            continue

        date_match = re.match(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+([A-Za-z]+)\s+(\d{1,2})$", line)
        if date_match:
            month = MONTHS_EN.get(date_match.group(2)[:3].lower())
            if month:
                current_date = (month, int(date_match.group(3)))
            continue

        scorers = parse_openfootball_scorers_line(line)
        if scorers and games:
            games[-1]["scorers"] = scorers
            continue

        item = parse_openfootball_game_line(line, current_date, match_counter, year)
        if not item:
            continue

        item["group_label"] = group_label
        item["stage"] = stage
        games.append(item)
        match_counter = max(match_counter, (item["match_number"] or 0) + 1)

    return games


def fetch_openfootball_world_cup_games() -> list[dict[str, Any]]:
    try:
        with urllib.request.urlopen(OPENFOOTBALL_2026_CUP_URL, timeout=15) as response:
            group_stage_text = read_capped(response).decode("utf-8")
        with urllib.request.urlopen(OPENFOOTBALL_2026_FINALS_URL, timeout=15) as response:
            knockout_text = read_capped(response).decode("utf-8")
    except urllib.error.URLError as exc:
        raise HTTPException(status_code=400, detail="Não foi possível buscar a tabela openfootball") from exc

    games = parse_openfootball_world_cup(group_stage_text) + parse_openfootball_world_cup(knockout_text)
    if not games:
        raise HTTPException(status_code=400, detail="A fonte openfootball não retornou jogos válidos")
    return sorted(games, key=lambda item: item["match_number"])


def openfootball_scorers_for_game(
    game: models.WorldCupGame,
    of_games: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Artilheiros do jogo na fonte openfootball (grátis), independente do que já está gravado."""
    if of_games is None:
        try:
            of_games = fetch_openfootball_world_cup_games()
        except Exception:
            return []
    item = next((g for g in of_games if g.get("match_number") == game.match_number), None)
    if not item:
        home_key = normalize_scorer_name(normalize_world_cup_team(game.home_team))
        away_key = normalize_scorer_name(normalize_world_cup_team(game.away_team))
        for g in of_games:
            gh = normalize_scorer_name(normalize_world_cup_team(g.get("home_team") or ""))
            ga = normalize_scorer_name(normalize_world_cup_team(g.get("away_team") or ""))
            if gh == home_key and ga == away_key:
                item = g
                break
    raw = (item or {}).get("scorers") or ""
    return [n.strip() for n in re.split(r"[,;\n]", raw) if n.strip()]


def get_reconfirm_state(db: Session, game_id: int) -> dict[str, Any]:
    raw = get_app_setting(db, f"wc_reconfirm_{game_id}")
    try:
        state = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        state = {}
    return {
        "tries": int(state.get("tries") or 0),
        "last_at": state.get("last_at"),
    }


def set_reconfirm_state(db: Session, game_id: int, tries: int, last_at: str | None) -> None:
    set_app_setting(
        db,
        f"wc_reconfirm_{game_id}",
        json.dumps({"tries": tries, "last_at": last_at}, ensure_ascii=False),
    )


def clear_reconfirm_state(db: Session, game_id: int) -> None:
    set_app_setting(db, f"wc_reconfirm_{game_id}", None)


def fetch_world_cup_squads() -> dict[str, list[dict[str, Any]]]:
    request = urllib.request.Request(WIKIPEDIA_SQUADS_URL, headers={"User-Agent": "ConversysFut/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(read_capped(response).decode("utf-8"))
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Não foi possível buscar os elencos na Wikipedia") from exc

    text = payload.get("parse", {}).get("wikitext", "")
    squads: dict[str, list[dict[str, Any]]] = {}
    team: str | None = None
    for line in text.splitlines():
        header = re.match(r"^===([^=]+)===\s*$", line)
        if header:
            name = header.group(1).strip()
            team = WIKIPEDIA_TEAM_ALIASES.get(name, name)
            continue
        if not team or not re.match(r"^\{\{nat fs g? ?player", line, re.IGNORECASE):
            continue

        name_match = re.search(r"\|\s*name\s*=\s*\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", line)
        if not name_match:
            name_match = re.search(r"\|\s*name\s*=\s*([^|}\[]+)", line)
        if not name_match:
            continue
        number_match = re.search(r"\|\s*no\s*=\s*(\d+)", line)
        position_match = re.search(r"\|\s*pos\s*=\s*([A-Za-z]+)", line)
        club_match = re.search(r"\|\s*club\s*=\s*\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", line)
        squads.setdefault(team, []).append(
            {
                "name": re.sub(r"\s+", " ", name_match.group(1)).strip(),
                "number": int(number_match.group(1)) if number_match else None,
                "position": position_match.group(1).upper() if position_match else None,
                "club": club_match.group(1).strip() if club_match else None,
            }
        )

    return squads


def apply_world_cup_squads_sync(db: Session) -> tuple[int, int]:
    squads = fetch_world_cup_squads()
    if not squads:
        return 0, 0

    imported = 0
    updated = 0
    existing = {
        (player.team, player.name.lower()): player
        for player in db.query(models.WorldCupPlayer).all()
    }
    for team, players in squads.items():
        for item in players:
            key = (team, item["name"].lower())
            player = existing.get(key)
            if not player:
                player = models.WorldCupPlayer(team=team, name=item["name"], created_at=datetime.utcnow())
                db.add(player)
                existing[key] = player
                imported += 1
            else:
                updated += 1
            player.number = item["number"]
            player.position = item["position"]
            player.club = item["club"]

    set_app_setting(db, "world_cup_last_squad_sync", datetime.now(timezone.utc).isoformat())
    set_app_setting(
        db,
        "world_cup_squad_sync_status",
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "ok": True,
                "error": None,
                "imported": imported,
                "updated": updated,
                "teams": len(squads),
                "players": sum(len(players) for players in squads.values()),
            },
            ensure_ascii=False,
        ),
    )
    db.commit()
    return imported, updated


def world_cup_players_grouped(db: Session) -> dict[str, list[dict[str, Any]]]:
    players = (
        db.query(models.WorldCupPlayer)
        .order_by(models.WorldCupPlayer.team.asc(), models.WorldCupPlayer.number.asc().nulls_last())
        .all()
    )
    grouped: dict[str, list[dict[str, Any]]] = {}
    for player in players:
        grouped.setdefault(player.team, []).append(
            {
                "id": player.id,
                "name": player.name,
                "number": player.number,
                "position": player.position,
                "club": player.club,
            }
        )
    return grouped


def get_app_setting(db: Session, key: str) -> str | None:
    row = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    return row.value if row else None


def set_app_setting(db: Session, key: str, value: str | None) -> None:
    # db.get usa o identity map primeiro: se a MESMA chave já foi escrita nesta
    # transação (ex.: contador incrementado várias vezes no ciclo), reaproveita a
    # linha em vez de tentar um 2º INSERT da mesma PK (que dava UniqueViolation e
    # derrubava o ciclo inteiro). O flush ao criar deixa a linha visível pra leitura.
    row = db.get(models.AppSetting, key)
    if row is None:
        row = models.AppSetting(key=key)
        db.add(row)
        db.flush()
    row.value = value
    row.updated_at = datetime.utcnow()


def bump_daily_counter(db: Session, name: str, amount: int = 1) -> None:
    """Conta requisições do dia (UTC) por fonte — pro painel admin saber QUANTAS
    chamadas foram feitas em cada API hoje."""
    key = f"calls_{name}_{datetime.utcnow():%Y%m%d}"
    raw = get_app_setting(db, key)
    current = int(raw) if (raw or "").lstrip("-").isdigit() else 0
    set_app_setting(db, key, str(current + amount))


def daily_counter(db: Session, name: str) -> int:
    raw = get_app_setting(db, f"calls_{name}_{datetime.utcnow():%Y%m%d}")
    return int(raw) if (raw or "").lstrip("-").isdigit() else 0


def bump_thesportsdb_call(db: Session | None) -> None:
    """Conta uma chamada HTTP à TheSportsDB: contador do dia (painel) + janela de
    minuto (trava de 30/min)."""
    if db is None:
        return
    bump_daily_counter(db, "thesportsdb")
    minute_key = f"{datetime.utcnow():%Y%m%d%H%M}"
    raw = get_app_setting(db, "thesportsdb_minute_window") or ""
    cur, _, cnt = raw.partition(":")
    used = int(cnt) if cur == minute_key and cnt.isdigit() else 0
    set_app_setting(db, "thesportsdb_minute_window", f"{minute_key}:{used + 1}")


def bump_game_poll(db: Session, game_id: int, api: str) -> None:
    """Conta quantas vezes cada API foi consultada PARA ESTE JOGO (pro painel)."""
    key = f"gpoll_{api}_{game_id}"
    raw = get_app_setting(db, key)
    n = int(raw) if (raw or "").isdigit() else 0
    set_app_setting(db, key, str(n + 1))


def game_poll_count(db: Session, game_id: int, api: str) -> int:
    raw = get_app_setting(db, f"gpoll_{api}_{game_id}")
    return int(raw) if (raw or "").isdigit() else 0


def _game_score_str(game: models.WorldCupGame) -> str:
    return f"{game.home_score or 0}-{game.away_score or 0}"


def game_goal_total(game: models.WorldCupGame) -> int:
    return (game.home_score or 0) + (game.away_score or 0)


def get_last_processed_goal_total(db: Session, game_id: int) -> int:
    raw = get_app_setting(db, f"wc_last_goal_total_{game_id}")
    return int(raw) if (raw or "").isdigit() else 0


def mark_goal_total_processed(db: Session, game_id: int, total: int) -> None:
    if total < 0:
        return
    prev = get_last_processed_goal_total(db, game_id)
    if total > prev:
        set_app_setting(db, f"wc_last_goal_total_{game_id}", str(total))


def ensure_idle_goal_pipeline(db: Session, game: models.WorldCupGame) -> None:
    """Sem gol no placar: não dispara API paga/SportsDB ao vivo."""
    if game_goal_total(game) > 0:
        return
    pipe = get_goal_pipeline(db, game)
    score = _game_score_str(game)
    if goal_pipeline_pending(pipe):
        complete_goal_pipeline(db, game, {**pipe, "score": score})
    else:
        set_goal_pipeline(db, game.id, {"score": score, "stage": "done", "api_tries": 0, "tsd_tries": 0})
    mark_goal_total_processed(db, game.id, 0)


def get_goal_pipeline(db: Session, game: models.WorldCupGame) -> dict[str, Any]:
    """Estado do fluxo por gol: detectado → paga/tsd → IA → done."""
    raw = get_app_setting(db, f"wc_goal_pipe_{game.id}")
    if raw:
        try:
            pipe = json.loads(raw)
            if isinstance(pipe, dict) and pipe.get("score"):
                return pipe
        except json.JSONDecodeError:
            pass
    cur = _game_score_str(game)
    polled = get_app_setting(db, f"wc_live_polled_{game.id}") or ""
    parts = polled.split(":")
    score = parts[0] if parts else cur
    if parts and parts[-1] == "done":
        return {"score": score, "stage": "done", "api_tries": 0, "tsd_tries": 0}
    api_n = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    tsd_n = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    if score != cur:
        return {"score": cur, "stage": "detected", "api_tries": 0, "tsd_tries": 0}
    if api_n >= API_FOOTBALL_LIVE_RETRY_MAX:
        stage = "tsd" if tsd_n < THESPORTSDB_LIVE_RETRY_MAX else "ia"
    elif api_n > 0:
        stage = "detected"
    else:
        stage = "detected"
    pipe = {"score": score, "stage": stage, "api_tries": api_n, "tsd_tries": tsd_n}
    if game_goal_total(game) == 0 and stage == "detected" and api_n == 0 and tsd_n == 0:
        pipe["stage"] = "done"
    return pipe


def set_goal_pipeline(db: Session, game_id: int, pipe: dict[str, Any]) -> None:
    set_app_setting(db, f"wc_goal_pipe_{game_id}", json.dumps(pipe, ensure_ascii=False))
    score = pipe.get("score", "")
    stage = pipe.get("stage", "detected")
    api_n = int(pipe.get("api_tries") or 0)
    tsd_n = int(pipe.get("tsd_tries") or 0)
    if stage == "done":
        set_app_setting(db, f"wc_live_polled_{game_id}", f"{score}:done")
    else:
        set_app_setting(db, f"wc_live_polled_{game_id}", f"{score}:{api_n}:{tsd_n}")


def start_goal_pipeline(db: Session, game: models.WorldCupGame, score: str) -> None:
    """Novo gol: reinicia o fluxo obrigatório (paga/tsd → IA) para ESTE placar."""
    set_goal_pipeline(db, game.id, {"score": score, "stage": "detected", "api_tries": 0, "tsd_tries": 0})


def complete_goal_pipeline(db: Session, game: models.WorldCupGame, pipe: dict[str, Any]) -> None:
    set_goal_pipeline(db, game.id, {**pipe, "stage": "done"})
    mark_goal_total_processed(db, game.id, game_goal_total(game))


def goal_label(pipe: dict[str, Any]) -> str:
    score = pipe.get("score") or ""
    return f"Gol {score} — " if score else ""


def goal_pipeline_pending(pipe: dict[str, Any]) -> bool:
    return pipe.get("stage") != "done"


def _timeline_iso(game: models.WorldCupGame, offset_sec: int = 0) -> str:
    base = game.kickoff_at or game.finished_at or datetime.utcnow()
    if getattr(base, "tzinfo", None):
        base = base.replace(tzinfo=None)
    return (base + timedelta(seconds=offset_sec)).replace(tzinfo=timezone.utc).isoformat()



def _end_source_meta(end_source: str | None) -> tuple[str, str]:
    mapping = {
        "football-data": ("football-data", "API grátis"),
        "openfootball": ("openfootball", "openfootball"),
        "api-football": ("API-Football", "API paga"),
    }
    return mapping.get(end_source or "", ("football-data", "sistema"))


def _is_timeline_noise(action: str) -> bool:
    return bool(re.search(
        r"retry|nova tentativa|não achou|sem cota|esgotou|erro|aguardando|fixture direto|"
        r"jogo encerrou|jogo não encontrado|segue retry|failover|limite por minuto|passou para",
        action or "",
        re.I,
    ))


def _match_duration_sec(game: models.WorldCupGame) -> int:
    if game.kickoff_at and game.finished_at:
        return max(3600, int((game.finished_at - game.kickoff_at).total_seconds()))
    return 5400


def _theoretical_goal_scores(game: models.WorldCupGame) -> list[str]:
    """Placar progressivo plausível gol a gol (ex.: 3-1 → 1-0, 2-0, 3-0, 3-1)."""
    h, a = game.home_score or 0, game.away_score or 0
    home_left, away_left = h, a
    ch = ca = 0
    scores: list[str] = []
    while home_left + away_left > 0:
        if home_left >= away_left and home_left > 0:
            home_left -= 1
            ch += 1
        elif away_left > 0:
            away_left -= 1
            ca += 1
        scores.append(f"{ch}-{ca}")
    return scores


def _extract_monotonic_goal_marks(
    old: list[dict[str, Any]],
    total_goals: int,
) -> list[tuple[str, str]]:
    """Usa só detecções de gol válidas (sem spam) para horários reais quando existirem."""
    marks: list[tuple[str, str]] = []
    seen: set[str] = set()
    prev_total = 0
    for e in sorted(old, key=lambda x: x.get("at", "")):
        act = e.get("action", "")
        if _is_timeline_noise(act):
            continue
        if not re.search(r"gol detectado|placar virou", act, re.I):
            continue
        m = re.search(r"(\d+-\d+)", act)
        if not m:
            continue
        g_score = m.group(1)
        if g_score in seen:
            continue
        try:
            gh, ga = [int(x) for x in g_score.split("-", 1)]
        except ValueError:
            continue
        g_total = gh + ga
        if g_total <= prev_total or g_total > total_goals:
            continue
        seen.add(g_score)
        prev_total = g_total
        marks.append((e["at"], g_score))
    return marks


def _timeline_event(
    game: models.WorldCupGame,
    at: str,
    action: str,
    *,
    phase: str,
    api: str,
    ok: bool | None = None,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "at": at,
        "match_number": game.match_number,
        "game": f"{game.home_team} x {game.away_team}",
        "action": action,
        "phase": phase,
        "api": api,
    }
    if ok is not None:
        row["ok"] = ok
    return row


def _append_goal_flow(
    clean: list[dict[str, Any]],
    game: models.WorldCupGame,
    g_at: str,
    g_score: str,
    scorers_slice: str,
) -> tuple[int, int]:
    """Um gol completo: detectado → API paga → IA → concluído."""
    gl = f"Gol {g_score} — "
    mn = game.match_number
    gname = f"{game.home_team} x {game.away_team}"
    clean.append(_timeline_event(game, g_at, f"Gol detectado — placar {g_score}", phase="gratuito", api="football-data", ok=True))
    if not scorers_slice and game_goal_total(game) == 0:
        return 0, 0
    t_api = g_at
    clean.append(_timeline_event(game, t_api, f"{gl}API paga — consulta artilheiro", phase="ao_vivo", api="API-Football"))
    names = scorers_slice or "confirmado"
    clean.append(_timeline_event(game, t_api, f"{gl}API paga — achou: {names}", phase="ao_vivo", api="API-Football", ok=True))
    clean.append(_timeline_event(game, t_api, f"{gl}IA — consulta (API paga)", phase="ao_vivo", api="IA merge"))
    clean.append(_timeline_event(game, t_api, f"{gl}IA — resultado: {names}", phase="ao_vivo", api="IA merge", ok=True))
    clean.append(_timeline_event(game, t_api, f"{gl}fluxo do gol concluído", phase="ao_vivo", api="pipeline", ok=True))
    return 1, 1


def _append_canonical_closing(
    db: Session,
    clean: list[dict[str, Any]],
    game: models.WorldCupGame,
) -> None:
    """Fim + confirmação final + reconfirmação — fluxo teórico limpo, sem ler logs sujos."""
    score = _game_score_str(game)
    total = game_goal_total(game)
    scorers_txt = game.scorers or ""
    fim_at = (
        game.finished_at.replace(tzinfo=timezone.utc).isoformat()
        if game.finished_at
        else _timeline_iso(game, _match_duration_sec(game))
    )
    api_key, api_label = _end_source_meta(game.end_source)

    clean.append(_timeline_event(
        game, fim_at, f"Finalização — placar {score} ({api_label})",
        phase="fim", api=api_key, ok=True,
    ))

    if not game.scorers_final:
        return

    conf_at = fim_at
    if game.scorers or total == 0:
        clean.append(_timeline_event(game, conf_at, "Consulta API paga — confirmação final", phase="fim", api="API-Football"))
        if game.scorers:
            clean.append(_timeline_event(game, conf_at, f"API paga — achou: {scorers_txt}", phase="fim", api="API-Football", ok=True))
        clean.append(_timeline_event(game, conf_at, "IA — consulta (API paga)", phase="fim", api="IA merge"))
        if game.scorers:
            clean.append(_timeline_event(game, conf_at, f"IA — resultado: {scorers_txt}", phase="fim", api="IA merge", ok=True))

    n_sources = game.scorers_confirmations or len([s for s in (game.confirmation_sources or "").split(",") if s.strip()])
    conf_txt = f" · ✓ {n_sources} fonte(s)" if n_sources else ""
    gol_txt = f" · goleadores: {scorers_txt}" if game.scorers else " · sem goleador"
    clean.append(_timeline_event(
        game, conf_at, f"Confirmação final — {score}{conf_txt}{gol_txt}",
        phase="fim", api="API-Football", ok=True,
    ))

    if not game.reconfirmed:
        return

    reconf_at = (
        (game.finished_at + timedelta(minutes=10)).replace(tzinfo=timezone.utc).isoformat()
        if game.finished_at
        else _timeline_iso(game, _match_duration_sec(game) + 600)
    )
    of_names: list[str] = []
    try:
        of_names = openfootball_scorers_for_game(game, fetch_openfootball_world_cup_games())
    except Exception:
        of_names = []

    clean.append(_timeline_event(game, reconf_at, "Reconfirmação — iniciada", phase="reconfirmacao", api="pipeline"))
    if total == 0:
        clean.append(_timeline_event(
            game, reconf_at, "Reconfirmação — resultado: sem goleadores (0-0)",
            phase="reconfirmacao", api="pipeline", ok=True,
        ))
        return

    of_txt = ", ".join(of_names) if of_names else scorers_txt
    if of_names or scorers_txt:
        clean.append(_timeline_event(
            game, reconf_at, f"openfootball reconfirmação — achou: {of_txt}",
            phase="reconfirmacao", api="openfootball", ok=True,
        ))
    sources = (game.confirmation_sources or "").lower()
    if "thesportsdb" in sources or "sportsdb" in sources:
        clean.append(_timeline_event(
            game, reconf_at, f"SportsDB reconfirmação — achou: {scorers_txt}",
            phase="reconfirmacao", api="TheSportsDB", ok=True,
        ))
    clean.append(_timeline_event(game, reconf_at, "IA — consulta (reconfirmação)", phase="reconfirmacao", api="IA merge"))
    clean.append(_timeline_event(game, reconf_at, f"IA — resultado: {scorers_txt}", phase="reconfirmacao", api="IA merge", ok=True))
    result_txt = scorers_txt or "confirmado"
    clean.append(_timeline_event(
        game, reconf_at, f"Reconfirmação — resultado: {result_txt}",
        phase="reconfirmacao", api="pipeline", ok=True,
    ))


def _build_canonical_game_events(
    db: Session,
    game: models.WorldCupGame,
    old: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int, int]:
    """Monta timeline canônica em memória (sem gravar no banco)."""
    scorers_names = game_scorer_names(game)
    total = game_goal_total(game)
    duration = _match_duration_sec(game)

    kickoff_at = _timeline_iso(game, 0)
    for e in sorted(old, key=lambda x: x.get("at", "")):
        act = e.get("action", "")
        if not _is_timeline_noise(act) and re.search(r"início|começou", act, re.I):
            kickoff_at = e["at"]
            break

    clean: list[dict[str, Any]] = [
        _timeline_event(
            game, kickoff_at, "Início do jogo — palpites fechados",
            phase="gratuito", api="calendário", ok=True,
        ),
    ]

    had_ht = any(e.get("action", "").strip().lower() == "intervalo" for e in old)
    if had_ht or duration >= 4200:
        clean.append(_timeline_event(game, _timeline_iso(game, 2700), "Intervalo", phase="gratuito", api="football-data", ok=True))
        clean.append(_timeline_event(game, _timeline_iso(game, 2880), "2º tempo", phase="gratuito", api="football-data", ok=True))

    theoretical_scores = _theoretical_goal_scores(game)
    real_marks = _extract_monotonic_goal_marks(old, total)
    if len(real_marks) == len(theoretical_scores) and len(real_marks) > 0:
        goal_plan = list(real_marks)
    else:
        goal_plan = [
            (_timeline_iso(game, int(duration * (i + 1) / (total + 1))), sc)
            for i, sc in enumerate(theoretical_scores)
        ]

    af = ia = 0
    for i, (g_at, g_score) in enumerate(goal_plan):
        slice_names = ", ".join(scorers_names[: i + 1]) if scorers_names else (game.scorers or "")
        a, b = _append_goal_flow(clean, game, g_at, g_score, slice_names)
        af += a
        ia += b

    if game.status == "finished":
        _append_canonical_closing(db, clean, game)

    seen_actions: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []
    for e in clean:
        key = (e.get("phase") or "", e.get("action") or "")
        if key in seen_actions:
            continue
        seen_actions.add(key)
        deduped.append(e)
    clean = deduped
    clean.sort(key=lambda x: x["at"])
    return clean, af, ia


def _apply_canonical_game_settings(
    db: Session,
    game: models.WorldCupGame,
    clean: list[dict[str, Any]],
    af: int,
    ia: int,
) -> None:
    total = game_goal_total(game)
    scorers_names = game_scorer_names(game)
    gratis = sum(
        1 for e in clean
        if e.get("api") == "football-data" and re.search(r"gol detectado", e.get("action", ""), re.I)
    )
    reconf_ia = 1 if game.reconfirmed else 0
    fim_ia = 1 if game.scorers_final else 0
    set_app_setting(db, f"gpoll_af_{game.id}", str(af + fim_ia))
    set_app_setting(
        db, f"gpoll_tsd_{game.id}",
        str(1 if game.reconfirmed and total > 0 and "thesportsdb" in (game.confirmation_sources or "").lower() else 0),
    )
    set_app_setting(db, f"gpoll_ia_{game.id}", str(ia + fim_ia + reconf_ia))
    set_app_setting(db, f"gpoll_gratis_{game.id}", str(gratis))

    cur = _game_score_str(game)
    if game.status == "finished" or total == 0 or len(scorers_names) >= max(1, total - 1):
        set_app_setting(db, f"wc_live_polled_{game.id}", f"{cur}:done")
        set_goal_pipeline(db, game.id, {"score": cur, "stage": "done", "api_tries": 0, "tsd_tries": 0})
        mark_goal_total_processed(db, game.id, total)
    else:
        ensure_idle_goal_pipeline(db, game)


def rebuild_clean_game_timeline(db: Session, game: models.WorldCupGame) -> list[dict[str, Any]]:
    """Reconstrói timeline canônica: fluxo teórico real, ignora logs sujos/retry."""
    raw = get_app_setting(db, "wc_game_events")
    try:
        all_ev = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        all_ev = []
    old = [e for e in all_ev if e.get("match_number") == game.match_number]
    others = [e for e in all_ev if e.get("match_number") != game.match_number]

    clean, af, ia = _build_canonical_game_events(db, game, old)
    merged = trim_game_events(list(reversed(clean)) + others)
    set_app_setting(db, "wc_game_events", json.dumps(merged, ensure_ascii=False))
    _apply_canonical_game_settings(db, game, clean, af, ia)
    return list(reversed(clean))


def sanitize_all_finished_timelines(db: Session, *, before_match_number: int | None = None) -> list[dict[str, Any]]:
    """Sanitiza timelines de todos os jogos encerrados com fluxo canônico."""
    query = db.query(models.WorldCupGame).filter(models.WorldCupGame.status == "finished")
    if before_match_number is not None:
        query = query.filter(models.WorldCupGame.match_number <= before_match_number)
    games = query.order_by(models.WorldCupGame.match_number.asc()).all()

    raw = get_app_setting(db, "wc_game_events")
    try:
        all_ev = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        all_ev = []

    finished_mns = {g.match_number for g in games}
    others = [e for e in all_ev if e.get("match_number") not in finished_mns]

    merged_clean: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for game in games:
        old = [e for e in all_ev if e.get("match_number") == game.match_number]
        clean, af, ia = _build_canonical_game_events(db, game, old)
        _apply_canonical_game_settings(db, game, clean, af, ia)
        merged_clean.extend(reversed(clean))
        results.append({
            "match_number": game.match_number,
            "matchup": f"{game.home_team} x {game.away_team}",
            "events": len(clean),
        })

    merged = trim_game_events(merged_clean + others)
    set_app_setting(db, "wc_game_events", json.dumps(merged, ensure_ascii=False))
    return results


def trim_game_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mantém histórico por jogo — um match não apaga os logs dos outros."""
    if not events:
        return []
    counts: dict[str, int] = {}
    out: list[dict[str, Any]] = []
    for row in events:
        key = str(row.get("match_number") or row.get("game") or "?")
        seen = counts.get(key, 0)
        if seen >= WC_GAME_EVENTS_PER_MATCH_MAX:
            continue
        counts[key] = seen + 1
        out.append(row)
        if len(out) >= WC_GAME_EVENTS_TOTAL_MAX:
            break
    return out


def log_game_event(
    db: Session,
    game: models.WorldCupGame,
    action: str,
    *,
    phase: str | None = None,
    api: str | None = None,
    ok: bool | None = None,
    cached: bool | None = None,
) -> None:
    """Registra evento do jogo pro painel admin. phase: ao_vivo|fim|reconfirmacao|gratuito;
    api: football-data|API-Football|TheSportsDB|IA merge|calendário; ok: achou/falhou."""
    raw = get_app_setting(db, "wc_game_events")
    try:
        events = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        events = []
    row: dict[str, Any] = {
        "at": datetime.now(timezone.utc).isoformat(),
        "match_number": game.match_number,
        "game": f"{game.home_team} x {game.away_team}",
        "action": action,
    }
    if phase:
        row["phase"] = phase
    if api:
        row["api"] = api
    if ok is not None:
        row["ok"] = ok
    if cached:
        row["cached"] = True
    events.insert(0, row)
    set_app_setting(db, "wc_game_events", json.dumps(trim_game_events(events), ensure_ascii=False))


def refresh_world_cup_live_statuses(db: Session) -> bool:
    now = datetime.utcnow()
    changed = False
    games = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "scheduled")
        .filter(models.WorldCupGame.kickoff_at <= now)
        .all()
    )
    for game in games:
        game.status = "live"
        changed = True
        mark_goal_total_processed(db, game.id, game_goal_total(game))
        ensure_idle_goal_pipeline(db, game)
        log_game_event(db, game, "Início do jogo — palpites fechados", phase="gratuito", api="calendário", ok=True)
    return changed


def refresh_live_scores_if_due(db: Session) -> bool:
    """Atualiza placar/intervalo via football-data quando o board é consultado (throttle)."""
    if not world_cup_has_live_window(db):
        return False
    raw = get_app_setting(db, "world_cup_board_score_refresh_at")
    if raw:
        try:
            last = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if last.tzinfo:
                last = last.astimezone(timezone.utc).replace(tzinfo=None)
            if (datetime.utcnow() - last).total_seconds() < BOARD_LIVE_SCORE_GAP:
                return False
        except ValueError:
            pass
    cross_check_world_cup_results(db)
    set_app_setting(db, "world_cup_board_score_refresh_at", datetime.now(timezone.utc).isoformat())
    return True


def fetch_football_data_results(db: Session | None = None) -> list[dict[str, Any]]:
    # Fonte secundária: resultados oficiais da football-data.org (precisa de chave gratuita)
    request = urllib.request.Request(
        FOOTBALL_DATA_MATCHES_URL,
        headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY, "User-Agent": "ConversysFut/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(read_capped(response).decode("utf-8"))
    if db is not None:
        bump_daily_counter(db, "football_data")
    results: list[dict[str, Any]] = []
    for match in payload.get("matches", []):
        home = normalize_world_cup_team(((match.get("homeTeam") or {}).get("name")) or "")
        away = normalize_world_cup_team(((match.get("awayTeam") or {}).get("name")) or "")
        if not home or not away:
            continue
        full_time = ((match.get("score") or {}).get("fullTime")) or {}
        utc_date = match.get("utcDate")
        kickoff = None
        if utc_date:
            try:
                kickoff = datetime.fromisoformat(utc_date.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                kickoff = None
        results.append(
            {
                "home_team": home,
                "away_team": away,
                "kickoff_at": kickoff,
                "status": match.get("status"),
                "home_score": full_time.get("home"),
                "away_score": full_time.get("away"),
            }
        )
    return results


def cross_check_world_cup_results(db: Session) -> dict[str, Any]:
    """Confere os placares do openfootball contra a football-data.org.

    Preenche resultados que a fonte primária ainda não publicou e registra
    divergências para o admin revisar. Nunca derruba o sync principal."""
    status: dict[str, Any] = {
        "configured": bool(FOOTBALL_DATA_API_KEY),
        "ok": False,
        "matched": 0,
        "filled": 0,
        "conflicts": [],
        "error": None,
    }
    if not FOOTBALL_DATA_API_KEY:
        return status
    try:
        results = fetch_football_data_results(db)
    except Exception as exc:
        status["error"] = str(exc)
        return status
    status["ok"] = True

    by_teams: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in results:
        key = (normalize_scorer_name(item["home_team"]), normalize_scorer_name(item["away_team"]))
        by_teams.setdefault(key, []).append(item)

    for game in db.query(models.WorldCupGame).all():
        key = (
            normalize_scorer_name(normalize_world_cup_team(game.home_team)),
            normalize_scorer_name(normalize_world_cup_team(game.away_team)),
        )
        candidates = by_teams.get(key) or []
        # Mesmo confronto pode se repetir no mata-mata: casa pelo dia do jogo
        item = next(
            (
                candidate
                for candidate in candidates
                if not candidate["kickoff_at"]
                or not game.kickoff_at
                or abs(candidate["kickoff_at"] - game.kickoff_at) <= timedelta(days=2)
            ),
            None,
        )
        if not item:
            continue
        status["matched"] += 1
        remote_status = item["status"]
        has_score = item["home_score"] is not None and item["away_score"] is not None
        # AO VIVO: football-data dirige o placar parcial (fonte ilimitada, sem
        # gastar a cota da API-Football). IN_PLAY/PAUSED → live + placar.
        if remote_status in ("IN_PLAY", "PAUSED") and has_score:
            lh, la = int(item["home_score"]), int(item["away_score"])
            if game.status in ("scheduled", "live") or game.status is None:
                if game.home_score != lh or game.away_score != la or game.status != "live":
                    game.home_score = lh
                    game.away_score = la
                    game.status = "live"
                    status["filled"] += 1
                # GOL detectado pela football-data (placar subiu) → registra na timeline;
                # a busca do autor (API-Football/failover) é disparada no apply_api_football_live
                new_total = lh + la
                last_proc = get_last_processed_goal_total(db, game.id)
                if new_total > last_proc:
                    log_game_event(
                        db, game,
                        f"Gol detectado — placar {lh}-{la}",
                        phase="gratuito", api="football-data", ok=True,
                    )
                    bump_game_poll(db, game.id, "gratis")
                    set_app_setting(db, f"wc_goal_at_{game.id}", datetime.now(timezone.utc).isoformat())
                    start_goal_pipeline(db, game, f"{lh}-{la}")
                    mark_goal_total_processed(db, game.id, new_total)
                # INTERVALO: football-data manda PAUSED no intervalo
                was_ht = bool(game.halftime)
                game.halftime = (remote_status == "PAUSED")
                if game.halftime and not was_ht:
                    log_game_event(db, game, "Intervalo", phase="gratuito", api="football-data", ok=True)
                elif was_ht and not game.halftime:
                    log_game_event(db, game, "2º tempo", phase="gratuito", api="football-data", ok=True)
            continue
        finished_remote = remote_status in ("FINISHED", "AWARDED") and has_score
        if not finished_remote:
            continue
        official_h, official_a = int(item["home_score"]), int(item["away_score"])
        # A fonte oficial diz que ACABOU: confia nela. Sobrescreve placar parcial
        # do feed ao vivo (que pode ter congelado) e promove o jogo a "finished".
        already_finished = (game.status or "") == "finished"
        scores_differ = game.home_score != official_h or game.away_score != official_a
        if not already_finished or scores_differ:
            # Conflito real só quando JÁ estava encerrado com placar diferente
            if already_finished and scores_differ:
                status["conflicts"].append(
                    {
                        "match_number": game.match_number,
                        "game": f"{game.home_team} x {game.away_team}",
                        "antes": f"{game.home_score}-{game.away_score}",
                        "football_data": f"{official_h}-{official_a}",
                    }
                )
            was_finished = already_finished
            game.home_score = official_h
            game.away_score = official_a
            game.status = "finished"
            game.halftime = False
            game.end_source = "football-data"  # confirmação oficial de FIM
            # placar mudou → goleadores precisam ser refinalizados pela fonte definitiva
            if scores_differ:
                game.scorers_final = False
            status["filled"] += 1
            if not was_finished:
                game.finished_at = datetime.utcnow()  # marca o relógio pra re-confirmação de 10min
                log_game_event(db, game, f"Finalização — placar {official_h}-{official_a} (API grátis)", phase="fim", api="football-data", ok=True)
    return status


def api_football_budget_key() -> str:
    return "api_football_calls_" + datetime.utcnow().strftime("%Y%m%d")


def same_scorer(a: str, b: str) -> bool:
    """True se dois nomes são o mesmo jogador, tolerando abreviação
    ('J. Lukic' == 'Jovo Lukić': mesmo sobrenome e inicial do nome batem)."""
    an, bn = normalize_scorer_name(a), normalize_scorer_name(b)
    if not an or not bn:
        return False
    if an == bn or an in bn or bn in an:
        return True
    at, bt = an.split(" "), bn.split(" ")
    if at[-1] != bt[-1]:  # sobrenome diferente -> jogadores diferentes
        return False
    af, bf = at[0], bt[0]
    # primeiro nome igual, ou um é a inicial do outro
    return af == bf or (len(af) == 1 and bf.startswith(af)) or (len(bf) == 1 and af.startswith(bf))


def merge_scorers(existing: str | None, new_names: list[str]) -> tuple[str, bool]:
    """Une goleadores sem perder nenhum, preferindo o nome mais completo.

    Resolve o bug de um poll sobrescrever o anterior e perder gols: a união só
    cresce, e quando dois nomes são o mesmo jogador (inclusive abreviado) fica
    o mais completo (ex.: 'Jovo Lukić' vence 'J. Lukic')."""
    ordered: list[str] = []
    for raw in [n for n in re.split(r"[,;\n]", existing or "")] + list(new_names):
        name = re.sub(r"\s+", " ", raw or "").strip()
        if not normalize_scorer_name(name):
            continue
        match_idx = next((i for i, kept in enumerate(ordered) if same_scorer(kept, name)), None)
        if match_idx is None:
            ordered.append(name)
        elif len(name) > len(ordered[match_idx]):
            ordered[match_idx] = name  # mantém a versão mais completa
    merged = ", ".join(ordered)[:500]
    return merged, merged != (existing or "")


def world_cup_game_squad(db: Session, game: models.WorldCupGame) -> list[str]:
    """Nomes salvos dos jogadores dos DOIS times do jogo. Já conhecemos todos os
    elencos, então isso é a fonte de verdade pra validar/normalizar goleadores."""
    wanted = {
        normalize_scorer_name(normalize_world_cup_team(game.home_team)),
        normalize_scorer_name(normalize_world_cup_team(game.away_team)),
    }
    if not any(wanted):
        return []
    names: list[str] = []
    for player in db.query(models.WorldCupPlayer).all():
        if normalize_scorer_name(normalize_world_cup_team(player.team)) in wanted and player.name:
            names.append(player.name)
    return names


def snap_scorers_to_squad(names: list[str], squad: list[str]) -> tuple[list[str], list[str]]:
    """Encaixa cada goleador no nome EXATO do elenco salvo. Como o usuário aposta
    pelo dropdown do elenco, casar com o nome oficial deixa a pontuação à prova de
    bala (resolve 'J. Lukić' → 'Jovo Lukić'). Devolve (nomes_oficiais, sem_match).

    'sem_match' são gols cujo autor não está em nenhum dos dois elencos — sinal de
    revisão (nome novo/raro ou ruído da API); o nome original é mantido."""
    if not squad:
        return names, []
    official: list[str] = []
    unmatched: list[str] = []
    for raw in names:
        match = next((s for s in squad if same_scorer(s, raw)), None)
        chosen = match or raw
        if match is None:
            unmatched.append(raw)
        if not any(same_scorer(chosen, k) for k in official):
            official.append(chosen)
    return official, unmatched


def scorer_sets_agree(source_names: list[str], official: list[str]) -> bool:
    """True se uma fonte concorda com o conjunto final: cada goleador oficial
    aparece na fonte e vice-versa (tolerando abreviação). Vazia nunca concorda."""
    if not source_names or not official:
        return False
    every_official_in_source = all(any(same_scorer(o, s) for s in source_names) for o in official)
    every_source_in_official = all(any(same_scorer(s, o) for o in official) for s in source_names)
    return every_official_in_source and every_source_in_official


def scorer_source_corroborates(source_names: list[str], official: list[str]) -> bool:
    """A fonte CORROBORA o conjunto final se tudo que ela reportou está na lista
    final (subconjunto, sem contradição) — mesmo que ela seja parcial. É o que
    importa pra 'confirmar/re-confirmar' em jogos de muitos gols, onde uma fonte
    pode ter só parte dos goleadores mas não contradiz nenhum."""
    if not source_names or not official:
        return False
    return all(any(same_scorer(s, o) for o in official) for s in source_names)


def scorer_lists_equivalent(a: list[str], b: list[str]) -> bool:
    """Duas listas descrevem o mesmo conjunto de artilheiros (sem contradição)."""
    if not a or not b:
        return False
    return scorer_source_corroborates(a, b) and scorer_source_corroborates(b, a)


def extract_api_football_scorers(fixture: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for event in fixture.get("events") or []:
        if (event.get("type") or "") != "Goal":
            continue
        detail = (event.get("detail") or "").lower()
        # Pênalti perdido não é gol; gol contra não vale como artilheiro
        # (ninguém aposta num jogador pra fazer gol contra)
        if "missed" in detail or "own" in detail:
            continue
        player = (((event.get("player") or {}).get("name")) or "").strip()
        if player and player not in names:
            names.append(player)
    return names


def discover_api_fixture_ids(db: Session, status: dict[str, Any]) -> None:
    """Descobre o fixture_id de jogos encerrados que não o têm, via
    fixtures?date=. Permite finalizar goleadores mesmo de jogos que já tinham
    acabado quando o sistema subiu (cold-start)."""
    if not API_FOOTBALL_KEYS:
        return
    candidates = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.api_fixture_id.is_(None))
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(models.WorldCupGame.status.in_(("finished", "live")))
        .all()
    )
    # Só vale gastar chamada com jogo INCOMPLETO (os completos já têm tudo) e
    # recente (o plano grátis só libera data em ~hoje±1)
    cutoff = datetime.utcnow() - timedelta(days=2)
    missing = [
        g for g in candidates
        if g.kickoff_at >= cutoff and (g.status == "live" or not world_cup_scorers_complete(g))
    ]
    if not missing:
        return
    dates = sorted({g.kickoff_at.strftime("%Y-%m-%d") for g in missing})
    for date in dates[:3]:  # no máx 3 chamadas por ciclo (orçamento)
        if api_football_pick_key(db) is None:
            break
        payload = api_football_get(f"{API_FOOTBALL_FIXTURE_URL}?date={date}", db, status)
        if payload is None:
            status["error"] = None  # data fora da janela do plano: ignora e tenta a próxima
            continue
        by_teams: dict[tuple[str, str], int] = {}
        for item in payload.get("response", []):
            if ((item.get("league") or {}).get("id")) != API_FOOTBALL_LEAGUE_ID:
                continue
            teams = item.get("teams") or {}
            home = normalize_scorer_name(normalize_world_cup_team(((teams.get("home") or {}).get("name")) or ""))
            away = normalize_scorer_name(normalize_world_cup_team(((teams.get("away") or {}).get("name")) or ""))
            fid = ((item.get("fixture") or {}).get("id"))
            if home and away and fid:
                by_teams[(home, away)] = int(fid)
        for game in missing:
            if game.api_fixture_id or not game.kickoff_at:
                continue
            if game.kickoff_at.strftime("%Y-%m-%d") != date:
                continue
            fid = by_teams.get(
                (
                    normalize_scorer_name(normalize_world_cup_team(game.home_team)),
                    normalize_scorer_name(normalize_world_cup_team(game.away_team)),
                )
            )
            if fid:
                game.api_fixture_id = fid
                game.scorers_final = False  # força refinalização com a fonte definitiva


def ensure_api_football_quota_day(db: Session) -> None:
    """Zera contadores de cota internos à meia-noite UTC (igual ao fornecedor)."""
    today = f"{datetime.utcnow():%Y%m%d}"
    if get_app_setting(db, "api_football_quota_day") == today:
        return
    for index in range(len(API_FOOTBALL_KEYS)):
        raw = get_app_setting(db, f"api_football_remaining_{index}")
        if raw and not raw.startswith(f"{today}:"):
            set_app_setting(db, f"api_football_remaining_{index}", "")
    set_app_setting(db, "api_football_quota_day", today)


def api_football_key_remaining(db: Session, index: int) -> int | None:
    """Cota restante HOJE (UTC) de uma chave; None se desconhecida (tenta usar)."""
    today = f"{datetime.utcnow():%Y%m%d}"
    raw = get_app_setting(db, f"api_football_remaining_{index}")
    if raw and ":" in raw:
        day_part, _, val = raw.partition(":")
        if day_part == today and val.lstrip("-").isdigit():
            return int(val)
    return None


def fetch_thesportsdb_scorers(game: models.WorldCupGame, db: Session | None = None) -> list[str] | None:
    """Goleadores do jogo pela 2ª fonte (TheSportsDB, grátis) para CONFIRMAR.

    Casa o jogo pela data + times (ou pelo idAPIfootball) e lê a timeline de
    gols. Devolve a lista de nomes ou None se não achou."""
    if not game.kickoff_at:
        return None
    # Trava por minuto (30/min): este jogo gasta até ~4 req (dia ±1 + timeline).
    # Se não há headroom no minuto atual, pula — confirma no próximo ciclo.
    if db is not None:
        minute_key = f"{datetime.utcnow():%Y%m%d%H%M}"
        raw_min = get_app_setting(db, "thesportsdb_minute_window") or ""
        cur_min, _, cnt = raw_min.partition(":")
        used = int(cnt) if cur_min == minute_key and cnt.isdigit() else 0
        if used >= THESPORTSDB_MINUTE_LIMIT - 4:
            return None
    home_key = normalize_scorer_name(normalize_world_cup_team(game.home_team))
    away_key = normalize_scorer_name(normalize_world_cup_team(game.away_team))
    event_id = None
    # A TheSportsDB pode bucketar o jogo no dia anterior/seguinte (fuso). Tenta ±1.
    base = game.kickoff_at
    for delta in (0, -1, 1):
        date = (base + timedelta(days=delta)).strftime("%Y-%m-%d")
        try:
            with urllib.request.urlopen(
                f"{THESPORTSDB_BASE}/{THESPORTSDB_KEY}/eventsday.php?d={date}&s=Soccer", timeout=15
            ) as resp:
                day = json.loads(read_capped(resp).decode("utf-8"))
            bump_thesportsdb_call(db)
        except Exception:
            continue
        for ev in day.get("events") or []:
            if "world cup" not in (ev.get("strLeague") or "").lower():
                continue
            if game.api_fixture_id and str(ev.get("idAPIfootball") or "") == str(game.api_fixture_id):
                event_id = ev.get("idEvent")
                break
            eh = normalize_scorer_name(normalize_world_cup_team(ev.get("strHomeTeam") or ""))
            ea = normalize_scorer_name(normalize_world_cup_team(ev.get("strAwayTeam") or ""))
            if eh == home_key and ea == away_key:
                event_id = ev.get("idEvent")
                break
        if event_id:
            break
    if not event_id:
        return None
    try:
        with urllib.request.urlopen(
            f"{THESPORTSDB_BASE}/{THESPORTSDB_KEY}/lookuptimeline.php?id={event_id}", timeout=15
        ) as resp:
            tl = json.loads(read_capped(resp).decode("utf-8"))
        bump_thesportsdb_call(db)
    except Exception:
        return None
    names: list[str] = []
    for item in tl.get("timeline") or []:
        if (item.get("strTimeline") or "").lower() != "goal":
            continue
        if "own" in (item.get("strTimelineDetail") or "").lower():
            continue
        player = (item.get("strPlayer") or "").strip()
        if player and player not in names:
            names.append(player)
    return names


def api_football_pick_key(db: Session) -> tuple[int, str] | None:
    """Escolhe a chave com mais cota hoje. Pula chaves SUSPENSAS e as que estão
    no limite de reserva. None se nenhuma estiver utilizável."""
    best: tuple[int, str] | None = None
    best_rem = -1
    for index, key in enumerate(API_FOOTBALL_KEYS):
        if get_app_setting(db, f"api_football_suspended_{index}") == "1":
            continue  # conta suspensa pela API-Football — ignora de vez
        rem = api_football_key_remaining(db, index)
        if rem is not None and rem <= API_FOOTBALL_DAILY_RESERVE:
            continue
        effective = API_FOOTBALL_DAILY_BUDGET if rem is None else rem
        if effective > best_rem:
            best_rem = effective
            best = (index, key)
    return best


def api_football_total_remaining(db: Session) -> int:
    """Soma da cota disponível hoje entre as chaves ATIVAS (suspensa = 0)."""
    total = 0
    for index in range(len(API_FOOTBALL_KEYS)):
        if get_app_setting(db, f"api_football_suspended_{index}") == "1":
            continue
        rem = api_football_key_remaining(db, index)
        total += API_FOOTBALL_DAILY_BUDGET if rem is None else max(0, rem)
    return total


def api_football_active_keys(db: Session) -> int:
    return sum(
        1 for index in range(len(API_FOOTBALL_KEYS))
        if get_app_setting(db, f"api_football_suspended_{index}") != "1"
    )


def api_football_get(url: str, db: Session, status: dict[str, Any]) -> dict[str, Any] | None:
    """GET na API-Football com ROTAÇÃO de chaves: usa a que tem mais cota hoje,
    lê a folga real dos headers e guarda por chave (com a data UTC). Devolve o
    payload ou None (erro/sem cota em status)."""
    # Trava por minuto (plano grátis = 10/min): conta as chamadas no minuto UTC
    # atual e recusa antes de estourar. O excedente fica pro próximo ciclo.
    minute_key = f"{datetime.utcnow():%Y%m%d%H%M}"
    raw_min = get_app_setting(db, "api_football_minute_window") or ""
    cur_min, _, cnt = raw_min.partition(":")
    used_this_minute = int(cnt) if cur_min == minute_key and cnt.isdigit() else 0
    if used_this_minute >= API_FOOTBALL_MINUTE_LIMIT:
        status["skipped"] = f"limite de {API_FOOTBALL_MINUTE_LIMIT}/min atingido — segue no próximo ciclo"
        status["minute_throttled"] = True
        return None
    picked = api_football_pick_key(db)
    if not picked:
        status["skipped"] = "todas as chaves da API-Football no limite de reserva"
        return None
    index, key = picked
    set_app_setting(db, "api_football_minute_window", f"{minute_key}:{used_this_minute + 1}")
    request = urllib.request.Request(url, headers={"x-apisports-key": key, "User-Agent": "ConversysFut/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(read_capped(response).decode("utf-8"))
            day_remaining = response.headers.get("x-ratelimit-requests-remaining")
            day_limit = response.headers.get("x-ratelimit-requests-limit")
    except Exception as exc:
        status["error"] = str(exc)[:300]
        return None
    if day_remaining is not None and day_remaining.lstrip("-").isdigit():
        set_app_setting(db, f"api_football_remaining_{index}", f"{datetime.utcnow():%Y%m%d}:{int(day_remaining)}")
        if day_limit and day_limit.isdigit():
            status["daily_limit"] = int(day_limit) * len(API_FOOTBALL_KEYS)
    status["calls_made"] = status.get("calls_made", 0) + 1
    status["key_used"] = index + 1
    bump_daily_counter(db, "api_football")
    status["daily_remaining"] = api_football_total_remaining(db)
    if payload.get("errors"):
        errs = json.dumps(payload["errors"], ensure_ascii=False)
        status["error"] = errs[:300]
        # Conta suspensa/bloqueada → marca a chave pra rotação nunca mais usá-la
        # (o sistema cai pra outra chave e pra football-data sem travar)
        if "suspend" in errs.lower() or "access" in errs.lower():
            set_app_setting(db, f"api_football_suspended_{index}", "1")
            status["suspended_key"] = index + 1
        return None
    return payload


def apply_api_football_live(db: Session) -> dict[str, Any]:
    """Goleadores event-driven, exatamente no fluxo definido:

    AO VIVO  → o GOL é detectado de graça pela football-data; aí a API-Football
               (paga) roda SÓ pra pegar o nome (nunca por tempo), com retry até
               achar. Sem cota? failover na TheSportsDB. Nome normalizado no elenco.
    FIM      → quando a football-data marca FINISHED, a paga roda 1× e pega TODOS
               os goleadores (recupera os que faltaram no meio). É a confirmação final.
    +10min   → re-confirmação: openfootball + TheSportsDB + confirmação da API paga
               no fim → IA junta tudo e valida. Retry a cada N min se fontes
               grátis ainda não responderam ou IA não fechar o resultado.
    """
    status: dict[str, Any] = {
        "configured": bool(API_FOOTBALL_KEYS),
        "ok": False,
        "live_games": 0,
        "mid_checks": 0,
        "finalized": 0,
        "confirmed": 0,
        "reconfirmed": 0,
        "retries": 0,
        "conflicts": [],
        "scorers_updated": 0,
        "calls_made": 0,
        "daily_remaining": None,
        "daily_limit": API_FOOTBALL_DAILY_BUDGET * max(1, len(API_FOOTBALL_KEYS)),
        "games_today": 0,
        "active_today": 0,
        "per_game_cap": 0,
        "live_gap_seconds": API_FOOTBALL_GOAL_GAP,
        "reserve": API_FOOTBALL_DAILY_RESERVE,
        "ai_reconciles": 0,
        "tsd_calls": 0,
        "goal_pending": False,
        "skipped": None,
        "error": None,
    }
    now = datetime.utcnow()
    has_keys = bool(API_FOOTBALL_KEYS)
    if has_keys:
        ensure_api_football_quota_day(db)
        status["daily_remaining"] = api_football_total_remaining(db)

    def call(url: str) -> dict[str, Any] | None:
        if api_football_pick_key(db) is None:
            status["skipped"] = "cota no limite de reserva"
            return None
        return api_football_get(url, db, status)

    def normalize_live(
        game, raw_names, ai_sources, phase: str = "ao_vivo", source_label: str = "API paga",
    ) -> tuple[str, bool]:
        """IA reconcilia e grava. Retorna (scorers, ia_ok)."""
        squad = world_cup_game_squad(db, game)
        of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
        sources = dict(ai_sources)
        if of_names:
            sources["lista_atual"] = of_names
        total = (game.home_score or 0) + (game.away_score or 0)
        if total > 0 and (raw_names or of_names):
            rec = ai_reconcile_scorers(
                db, game, sources, status, squad=squad, phase=phase, source_label=source_label,
                corroborate_against=[n for lst in ai_sources.values() for n in lst],
            )
            if rec:
                official, _ = snap_scorers_to_squad([n for n in (s.strip() for s in rec) if n], squad)
                merged, _ = merge_scorers(game.scorers, official)
                return merged[:500], True
        union = merge_scorers(game.scorers, raw_names)[0].split(", ")
        official, _ = snap_scorers_to_squad([n for n in (s.strip() for s in union) if n], squad)
        merged, _ = merge_scorers(game.scorers, official)
        ia_ok = not OPENAI_API_KEY and bool(merged)
        return merged[:500], ia_ok

    # Jogos 0-0 não têm goleador pra confirmar: marca como final ANTES da seção paga,
    # pra não gastar descoberta/consulta da API-Football à toa e pra eles saírem da
    # fila de "incompletos" na hora (finalizam instantâneo, sem depender de cota).
    zero_finished = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(or_(models.WorldCupGame.scorers_final.is_(False), models.WorldCupGame.scorers_final.is_(None)))
        .filter((models.WorldCupGame.home_score == 0) & (models.WorldCupGame.away_score == 0))
        .all()
    )
    for game in zero_finished:
        game.scorers_final = True

    # ============ A) FIM: paga 1× → TODOS os goleadores (confirmação final) ============
    incomplete_finished = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(or_(models.WorldCupGame.scorers_final.is_(False), models.WorldCupGame.scorers_final.is_(None)))
        .all()
    )
    stuck_live = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "live")
        .filter(models.WorldCupGame.kickoff_at <= now - timedelta(hours=2, minutes=30))
        .all()
    )
    if has_keys and (incomplete_finished or stuck_live):
        discover_api_fixture_ids(db, status)
        db.flush()
    pending = [g for g in incomplete_finished if g.api_fixture_id] if has_keys else []
    seen = {g.id for g in pending}
    pending += [g for g in stuck_live if g.id not in seen and g.api_fixture_id] if has_keys else []

    for game in pending:
        log_game_event(db, game, "Consulta API paga — confirmação final", phase="fim", api="API-Football")
        payload = call(f"{API_FOOTBALL_FIXTURE_URL}?id={game.api_fixture_id}")
        if payload is None:
            log_game_event(db, game, "API paga — sem cota no fim", phase="fim", api="API-Football", ok=False)
            break
        bump_game_poll(db, game.id, "af")
        fixtures = payload.get("response") or []
        if not fixtures:
            game.scorers_final = True
            continue
        fixture = fixtures[0]
        short = (((fixture.get("fixture") or {}).get("status") or {}).get("short")) or ""
        if short not in ("FT", "AET", "PEN", "AWD", "WO"):
            continue
        goals = fixture.get("goals") or {}
        if goals.get("home") is not None and goals.get("away") is not None:
            game.home_score = int(goals["home"])
            game.away_score = int(goals["away"])
        # Mata-mata: guarda o resultado da disputa de pênaltis (decide o vencedor) e
        # marca como o jogo foi decidido (regular/prorrogação/pênaltis) pra exibição.
        score_obj = fixture.get("score") or {}
        pen = score_obj.get("penalty") or {}
        if pen.get("home") is not None and pen.get("away") is not None:
            game.home_penalties = int(pen["home"])
            game.away_penalties = int(pen["away"])
            game.live_period = "penalties"
        elif short == "AET" or (score_obj.get("extratime") or {}).get("home") is not None:
            game.live_period = "extra-time"
        else:
            game.live_period = "regular"
        game.status = "finished"
        game.halftime = False
        if not game.end_source:
            game.end_source = "api-football"
        if not game.finished_at:
            game.finished_at = now
        squad = world_cup_game_squad(db, game)
        api_names = extract_api_football_scorers(fixture)
        of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
        if not api_names:
            log_game_event(db, game, "API paga — não achou artilheiros", phase="fim", api="API-Football", ok=False)
        else:
            log_game_event(db, game, f"API paga — achou: {', '.join(api_names)}", phase="fim", api="API-Football", ok=True)
        # IA definitiva no fim: cruza paga + openfootball + elenco
        reconciled = ai_reconcile_scorers(
            db, game, {"API-Football": api_names, "lista_atual": of_names}, status, squad=squad, phase="fim",
            source_label="API paga",
            # Só a API-Football (paga, autoritativa) corrobora aqui; a lista acumulada não.
            corroborate_against=api_names,
        )
        candidate = (reconciled or []) + api_names + of_names
        official, unmatched = snap_scorers_to_squad([n for n in (s.strip() for s in candidate) if n], squad)
        new_scorers = ", ".join(official)[:500]
        if new_scorers != (game.scorers or ""):
            game.scorers = new_scorers
            status["scorers_updated"] += 1
        status["finalized"] += 1
        agreeing = [
            name for name, src in (("API-Football", api_names), ("openfootball", of_names))
            if scorer_source_corroborates(src, official)
        ]
        game.scorers_confirmations = max(game.scorers_confirmations or 0, len(agreeing))
        game.confirmation_sources = ", ".join(agreeing) or game.confirmation_sources
        if unmatched:
            status["conflicts"].append(
                {"game": f"{game.home_team} x {game.away_team}", "fora_do_elenco": unmatched, "api": api_names}
            )
        game.scorers_final = True  # paga FT é definitiva (lista distinta = verdade)
        complete_goal_pipeline(db, game, get_goal_pipeline(db, game))
        conf_txt = f" · ✓ {len(agreeing)} fonte(s)" if agreeing else ""
        gol_txt = f" · goleadores: {game.scorers}" if game.scorers else " · sem goleador"
        log_game_event(db, game, f"Confirmação final — {game.home_score}-{game.away_score}{conf_txt}{gol_txt}", phase="fim", api="API-Football", ok=True)

    # Rede de segurança: jogo "ao vivo" há tempo demais → encerra sozinho
    for game in stuck_live:
        if game.status == "live" and game.kickoff_at and game.kickoff_at <= now - WORLD_CUP_FORCE_FINISH_AFTER:
            game.status = "finished"
            game.halftime = False
            if not game.finished_at:
                game.finished_at = now
            if not game.end_source:
                game.end_source = "auto:tempo"
                log_game_event(db, game, f"Finalização automática — {game.home_score}-{game.away_score}", phase="fim", api="auto", ok=True)
            status["finalized"] += 1

    # ============ B) AO VIVO: fluxo OBRIGATÓRIO por gol (paga/tsd → IA → done) ============
    live_now_games = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "live")
        .filter(models.WorldCupGame.kickoff_at <= now - timedelta(minutes=2))
        .all()
    )

    paid_ok = has_keys and api_football_pick_key(db) is not None

    def run_ia_step(
        game: models.WorldCupGame,
        pipe: dict[str, Any],
        sources: dict[str, list[str]],
        *,
        phase: str,
        source_label: str,
    ) -> bool:
        gl = goal_label(pipe)
        raw_names = sources.get("API-Football") or sources.get("TheSportsDB") or []
        new_s, ia_ok = normalize_live(
            game, raw_names, sources, phase=phase, source_label=source_label,
        )
        if new_s != (game.scorers or ""):
            game.scorers = new_s
            status["scorers_updated"] += 1
        if ia_ok:
            complete_goal_pipeline(db, game, pipe)
            log_game_event(db, game, f"{gl}fluxo do gol concluído", phase="ao_vivo", api="pipeline", ok=True)
        else:
            set_goal_pipeline(db, game.id, {**pipe, "stage": "ia", "last_sources": sources})
        return ia_ok

    # Sem cota na paga → vai direto pro SportsDB neste gol
    for game in live_now_games:
        if game_goal_total(game) == 0:
            ensure_idle_goal_pipeline(db, game)
            continue
        pipe = get_goal_pipeline(db, game)
        if pipe.get("stage") == "detected" and goal_pipeline_pending(pipe) and not paid_ok:
            set_goal_pipeline(db, game.id, {
                **pipe,
                "stage": "tsd",
                "api_tries": API_FOOTBALL_LIVE_RETRY_MAX,
            })

    def api_pending(g: models.WorldCupGame) -> bool:
        if game_goal_total(g) == 0:
            return False
        pipe = get_goal_pipeline(db, g)
        if not goal_pipeline_pending(pipe):
            return False
        if _game_score_str(g) != pipe.get("score"):
            start_goal_pipeline(db, g, _game_score_str(g))
            pipe = get_goal_pipeline(db, g)
        return pipe.get("stage") == "detected" and paid_ok and int(pipe.get("api_tries") or 0) < API_FOOTBALL_LIVE_RETRY_MAX

    def tsd_pending(g: models.WorldCupGame) -> bool:
        if game_goal_total(g) == 0:
            return False
        pipe = get_goal_pipeline(db, g)
        if not goal_pipeline_pending(pipe):
            return False
        return pipe.get("stage") == "tsd" and int(pipe.get("tsd_tries") or 0) < THESPORTSDB_LIVE_RETRY_MAX

    def ia_pending(g: models.WorldCupGame) -> bool:
        if game_goal_total(g) == 0:
            return False
        pipe = get_goal_pipeline(db, g)
        return goal_pipeline_pending(pipe) and pipe.get("stage") == "ia"

    api_games = [g for g in live_now_games if api_pending(g)]
    tsd_games = [g for g in live_now_games if tsd_pending(g)]
    ia_games = [g for g in live_now_games if ia_pending(g)]
    status["goal_pending"] = bool(api_games or tsd_games or ia_games)

    if api_games and paid_ok:
        for game in api_games:
            pipe = get_goal_pipeline(db, game)
            gl = goal_label(pipe)
            api_n = int(pipe.get("api_tries") or 0)
            if api_n == 0:
                log_game_event(db, game, f"{gl}API paga — consulta artilheiro", phase="ao_vivo", api="API-Football")
            else:
                log_game_event(
                    db, game,
                    f"{gl}API paga — nova tentativa ({api_n + 1}/{API_FOOTBALL_LIVE_RETRY_MAX})",
                    phase="ao_vivo", api="API-Football",
                )
        payload = call(API_FOOTBALL_LIVE_URL)
        if payload is None:
            no_quota = api_football_pick_key(db) is None
            for game in api_games:
                pipe = get_goal_pipeline(db, game)
                gl = goal_label(pipe)
                pipe = {**pipe, "api_tries": int(pipe.get("api_tries") or 0) + 1}
                if no_quota or pipe["api_tries"] >= API_FOOTBALL_LIVE_RETRY_MAX:
                    pipe["stage"] = "tsd"
                    if no_quota:
                        log_game_event(db, game, f"{gl}API paga — sem cota", phase="ao_vivo", api="API-Football", ok=False)
                    else:
                        log_game_event(db, game, f"{gl}API paga — esgotou tentativas", phase="ao_vivo", api="API-Football", ok=False)
                elif status.get("minute_throttled"):
                    log_game_event(db, game, f"{gl}API paga — limite por minuto", phase="ao_vivo", api="API-Football", ok=False)
                else:
                    log_game_event(db, game, f"{gl}API paga — erro na resposta", phase="ao_vivo", api="API-Football", ok=False)
                set_goal_pipeline(db, game.id, pipe)
        if payload:
            by_teams: dict[tuple[str, str], dict[str, Any]] = {}
            for item in payload.get("response", []):
                if ((item.get("league") or {}).get("id")) != API_FOOTBALL_LEAGUE_ID:
                    continue
                teams = item.get("teams") or {}
                hk = normalize_scorer_name(normalize_world_cup_team(((teams.get("home") or {}).get("name")) or ""))
                ak = normalize_scorer_name(normalize_world_cup_team(((teams.get("away") or {}).get("name")) or ""))
                if hk and ak:
                    by_teams[(hk, ak)] = item
            status["live_games"] = len(by_teams)
            for game in api_games:
                pipe = get_goal_pipeline(db, game)
                gl = goal_label(pipe)
                item = by_teams.get((
                    normalize_scorer_name(normalize_world_cup_team(game.home_team)),
                    normalize_scorer_name(normalize_world_cup_team(game.away_team)),
                ))
                pipe = {**pipe, "api_tries": int(pipe.get("api_tries") or 0) + 1}
                if not item and game.api_fixture_id:
                    fix_payload = call(f"{API_FOOTBALL_FIXTURE_URL}?id={game.api_fixture_id}")
                    if fix_payload and fix_payload.get("response"):
                        item = fix_payload["response"][0]
                        log_game_event(
                            db, game,
                            f"{gl}API paga — fixture direto (jogo fora do ao vivo)",
                            phase="ao_vivo", api="API-Football", ok=True,
                        )
                if not item:
                    status["retries"] += 1
                    # Fora do endpoint live ≠ erro: jogo já encerrou ou fixture sumiu do ao vivo
                    if game.status == "finished" or game.api_fixture_id:
                        log_game_event(
                            db, game,
                            f"{gl}API paga — jogo encerrou (fora do ao vivo)",
                            phase="ao_vivo", api="API-Football", ok=True,
                        )
                    else:
                        log_game_event(
                            db, game,
                            f"{gl}API paga — jogo não encontrado",
                            phase="ao_vivo", api="API-Football", ok=False,
                        )
                    if pipe["api_tries"] >= API_FOOTBALL_LIVE_RETRY_MAX:
                        pipe["stage"] = "tsd"
                    set_goal_pipeline(db, game.id, pipe)
                    continue
                bump_game_poll(db, game.id, "af")
                fid = ((item.get("fixture") or {}).get("id"))
                if fid and not game.api_fixture_id:
                    game.api_fixture_id = int(fid)
                goals = item.get("goals") or {}
                if goals.get("home") is not None and goals.get("away") is not None:
                    game.home_score = int(goals["home"])
                    game.away_score = int(goals["away"])
                live_scorers = extract_api_football_scorers(item)
                of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
                if live_scorers:
                    log_game_event(db, game, f"{gl}API paga — achou: {', '.join(live_scorers)}", phase="ao_vivo", api="API-Football", ok=True)
                    sources = {"API-Football": live_scorers, "openfootball": of_names}
                    run_ia_step(game, pipe, sources, phase="ao_vivo", source_label="API paga")
                else:
                    status["retries"] += 1
                    log_game_event(
                        db, game,
                        f"{gl}API paga — não achou ({pipe['api_tries']}/{API_FOOTBALL_LIVE_RETRY_MAX})",
                        phase="ao_vivo", api="API-Football", ok=False,
                    )
                    if pipe["api_tries"] >= API_FOOTBALL_LIVE_RETRY_MAX:
                        pipe["stage"] = "tsd"
                    set_goal_pipeline(db, game.id, pipe)
                status["mid_checks"] += 1

    tsd_games = [g for g in live_now_games if tsd_pending(g)]

    if tsd_games:
        for game in tsd_games:
            pipe = get_goal_pipeline(db, game)
            gl = goal_label(pipe)
            tsd_n = int(pipe.get("tsd_tries") or 0)
            api_n = int(pipe.get("api_tries") or 0)
            if tsd_n == 0:
                motivo = "sem cota" if not paid_ok else ("API paga não achou" if api_n >= API_FOOTBALL_LIVE_RETRY_MAX else "API paga indisponível")
                log_game_event(
                    db, game,
                    f"{gl}SportsDB fallback — motivo: {motivo}",
                    phase="ao_vivo_failover", api="TheSportsDB",
                )
            if status["tsd_calls"] >= THESPORTSDB_CYCLE_LIMIT:
                break
            status["tsd_calls"] += 1
            bump_game_poll(db, game.id, "tsd")
            tsd = fetch_thesportsdb_scorers(game, db) or []
            of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
            pipe = {**pipe, "tsd_tries": tsd_n + 1}
            if tsd:
                log_game_event(db, game, f"{gl}SportsDB — achou: {', '.join(tsd)}", phase="ao_vivo_failover", api="TheSportsDB", ok=True)
                sources = {"TheSportsDB": tsd, "openfootball": of_names}
                run_ia_step(game, pipe, sources, phase="ao_vivo_failover", source_label="SportsDB")
            else:
                status["retries"] += 1
                log_game_event(
                    db, game,
                    f"{gl}SportsDB — não achou ({pipe['tsd_tries']}/{THESPORTSDB_LIVE_RETRY_MAX})",
                    phase="ao_vivo_failover", api="TheSportsDB", ok=False,
                )
                if pipe["tsd_tries"] >= THESPORTSDB_LIVE_RETRY_MAX:
                    log_game_event(db, game, f"{gl}SportsDB — passou para IA", phase="ao_vivo_failover", api="TheSportsDB", ok=False)
                    sources = {"openfootball": of_names, "lista_atual": of_names}
                    set_goal_pipeline(db, game.id, {**pipe, "stage": "ia", "last_sources": sources})
                else:
                    set_goal_pipeline(db, game.id, pipe)

    ia_games = [g for g in live_now_games if ia_pending(g)]
    for game in ia_games:
        pipe = get_goal_pipeline(db, game)
        of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
        sources = pipe.get("last_sources") or {"openfootball": of_names, "lista_atual": of_names}
        run_ia_step(game, pipe, sources, phase="ao_vivo", source_label="retry IA")

    status["goal_pending"] = any(
        goal_pipeline_pending(get_goal_pipeline(db, g)) for g in live_now_games
    )

    # ============ C) +10min: re-confirmação grátis → IA (openfootball + SportsDB + API paga) ============
    # Retry só se AS DUAS fontes grátis vazias, sem API paga no fim, ou IA não fechar.
    # Se uma grátis achou e a outra não → segue na hora (fonte vazia não entra em retry).
    reconfirm_candidates = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(models.WorldCupGame.finished_at.isnot(None))
        .filter(models.WorldCupGame.finished_at <= now - WORLD_CUP_RECONFIRM_AFTER)
        .filter(or_(models.WorldCupGame.reconfirmed.is_(False), models.WorldCupGame.reconfirmed.is_(None)))
        .filter(models.WorldCupGame.scorers_final.is_(True))
        .order_by(models.WorldCupGame.finished_at.desc())
        .all()
    )
    of_games_cache: list[dict[str, Any]] | None = None

    def _finish_scoreless_reconfirm(game: models.WorldCupGame) -> None:
        game.scorers_confirmed = True
        game.reconfirmed = True
        clear_reconfirm_state(db, game.id)
        status["reconfirmed"] += 1
        log_game_event(
            db, game,
            "Reconfirmação — resultado: sem goleadores (0-0)",
            phase="reconfirmacao", api="pipeline", ok=True,
        )

    # 0-0 não tem artilheiro — fecha reconfirmação sem exigir API paga no fim
    for game in (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(models.WorldCupGame.scorers_final.is_(True))
        .filter(or_(models.WorldCupGame.reconfirmed.is_(False), models.WorldCupGame.reconfirmed.is_(None)))
        .all()
    ):
        if game_goal_total(game) == 0:
            _finish_scoreless_reconfirm(game)

    for game in reconfirm_candidates:
        if game_goal_total(game) == 0:
            continue
        state = get_reconfirm_state(db, game.id)
        if state["tries"] >= WORLD_CUP_RECONFIRM_MAX_TRIES:
            continue
        if state["last_at"]:
            try:
                last_try = datetime.fromisoformat(state["last_at"].replace("Z", "+00:00"))
                if last_try.tzinfo:
                    last_try = last_try.replace(tzinfo=None)
                if now.replace(tzinfo=None) - last_try < WORLD_CUP_RECONFIRM_RETRY_GAP:
                    continue
            except ValueError:
                pass

        attempt = state["tries"] + 1
        set_reconfirm_state(db, game.id, attempt, now.replace(tzinfo=None).isoformat())
        log_game_event(
            db, game,
            "Reconfirmação — iniciada",
            phase="reconfirmacao", api="pipeline",
        )

        if of_games_cache is None:
            try:
                of_games_cache = fetch_openfootball_world_cup_games()
            except Exception:
                of_games_cache = []

        of_names = openfootball_scorers_for_game(game, of_games_cache)
        if of_names:
            log_game_event(
                db, game,
                f"openfootball reconfirmação — achou: {', '.join(of_names)}",
                phase="reconfirmacao", api="openfootball", ok=True,
            )
        else:
            log_game_event(
                db, game,
                f"openfootball reconfirmação — sem dados",
                phase="reconfirmacao", api="openfootball", ok=False,
            )

        squad = world_cup_game_squad(db, game)
        paid_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]

        def _reconfirm_sources_label(agreeing: list[str]) -> str:
            return "+".join(agreeing) if agreeing else "pipeline"

        def _finish_reconfirm(official: list[str], agreeing: list[str], api_label: str | None = None) -> None:
            prev = [s.strip() for s in (game.confirmation_sources or "").split(",") if s.strip()]
            for a in agreeing:
                if a not in prev:
                    prev.append(a)
            game.confirmation_sources = ", ".join(prev) or game.confirmation_sources
            game.scorers_confirmations = max(game.scorers_confirmations or 0, len(prev))
            game.scorers_confirmed = True
            game.reconfirmed = True
            clear_reconfirm_state(db, game.id)
            status["reconfirmed"] += 1
            log_game_event(
                db, game,
                f"Reconfirmação — resultado: {', '.join(official)}",
                phase="reconfirmacao",
                api=api_label or _reconfirm_sources_label(agreeing),
                ok=True,
            )

        tsd: list[str] = []
        if status["tsd_calls"] >= THESPORTSDB_CYCLE_LIMIT:
            log_game_event(
                db, game,
                f"SportsDB reconfirmação — adiada (cota do ciclo)",
                phase="reconfirmacao", api="TheSportsDB", ok=False,
            )
        else:
            status["tsd_calls"] += 1
            bump_game_poll(db, game.id, "tsd")
            tsd = fetch_thesportsdb_scorers(game, db) or []
            if tsd:
                log_game_event(db, game, f"SportsDB reconfirmação — achou: {', '.join(tsd)}", phase="reconfirmacao", api="TheSportsDB", ok=True)
            else:
                msg = "SportsDB reconfirmação — sem dados"
                log_game_event(db, game, msg, phase="reconfirmacao", api="TheSportsDB", ok=False)

        if not of_names and not tsd:
            log_game_event(
                db, game,
                f"Reconfirmação — aguardando próximo ciclo (openfootball e SportsDB sem dados)",
                phase="reconfirmacao", api="pipeline", ok=False,
            )
            continue

        if of_names and not tsd:
            log_game_event(
                db, game,
                "Reconfirmação — openfootball ok, SportsDB vazio (segue sem retry da fonte vazia)",
                phase="reconfirmacao", api="pipeline", ok=True,
            )
        elif tsd and not of_names:
            log_game_event(
                db, game,
                "Reconfirmação — SportsDB ok, openfootball vazio (segue sem retry da fonte vazia)",
                phase="reconfirmacao", api="pipeline", ok=True,
            )

        if not paid_names:
            log_game_event(
                db, game,
                f"Reconfirmação — aguardando confirmação da API paga no fim do jogo",
                phase="reconfirmacao", api="pipeline", ok=False,
            )
            continue

        sources: dict[str, list[str]] = {
            "openfootball": of_names,
            "TheSportsDB": tsd,
            # game.scorers acumulado — contexto, NÃO é fonte real que corrobora
            "lista_atual": paid_names,
        }
        reconciled = ai_reconcile_scorers(
            db, game, sources, status, squad=squad, phase="reconfirmacao", source_label="reconfirmação",
            # Só as fontes externas reais desta reconfirmação corroboram
            corroborate_against=list(of_names) + list(tsd),
        )
        if not reconciled:
            log_game_event(
                db, game,
                f"Reconfirmação — IA sem resultado",
                phase="reconfirmacao", api="IA merge", ok=False,
            )
            continue

        candidate = reconciled + tsd + of_names + paid_names
        official, _ = snap_scorers_to_squad([n for n in (s.strip() for s in candidate) if n], squad)
        new_scorers = ", ".join(official)[:500]
        chk = SimpleNamespace(home_score=game.home_score, away_score=game.away_score, scorers=new_scorers)
        if not world_cup_scorers_complete(chk):  # type: ignore[arg-type]
            log_game_event(
                db, game,
                f"Reconfirmação — artilheiros incompletos",
                phase="reconfirmacao", api="pipeline", ok=False,
            )
            continue

        if new_scorers != (game.scorers or ""):
            game.scorers = new_scorers
            status["scorers_updated"] += 1

        if tsd and of_names:
            extras = [t for t in tsd if not any(same_scorer(t, o) for o in of_names)]
            if extras:
                status["conflicts"].append(
                    {"game": f"{game.home_team} x {game.away_team}", "gratis_trouxe_a_mais": extras}
                )

        agreeing = [
            name for name, src in (
                ("openfootball", of_names),
                ("TheSportsDB", tsd),
                ("API paga", paid_names),
            )
            if src and scorer_source_corroborates(src, official)
        ]
        has_free = any(n in agreeing for n in ("openfootball", "TheSportsDB"))
        has_paid = "API paga" in agreeing
        if len(agreeing) < 2 or not has_free or not has_paid:
            log_game_event(
                db, game,
                f"Reconfirmação — fontes não batem com IA",
                phase="reconfirmacao", api="pipeline", ok=False,
            )
            continue

        _finish_reconfirm(official, agreeing, "IA+" + _reconfirm_sources_label(agreeing))

    # Varredura: jogo encerrado com goleadores completos vira 'final'
    leftover = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(or_(models.WorldCupGame.scorers_final.is_(False), models.WorldCupGame.scorers_final.is_(None)))
        .all()
    )
    for game in leftover:
        if world_cup_scorers_complete(game):
            game.scorers_final = True

    status["ok"] = status["error"] is None
    return status


def world_cup_scorers_complete(game: models.WorldCupGame) -> bool:
    """Os goleadores capturados cobrem todos os gols do jogo?

    Tolera gol contra (que pode não ter goleador nomeado): exige pelo menos
    (total de gols - 1) nomes, e nunca falha em 0x0."""
    total = (game.home_score or 0) + (game.away_score or 0)
    if total == 0:
        return True
    names = game_scorer_names(game)
    return len(names) >= max(1, total - 1)


def send_email(recipients: list[str], subject: str, html_body: str) -> tuple[bool, str | None]:
    """Envia 1 e-mail HTML com os destinatários em BCC (privacidade). Usa o SMTP
    configurado (Gmail por padrão). Nunca levanta — devolve (ok, erro)."""
    if not (SMTP_USER and SMTP_PASSWORD):
        return False, "SMTP não configurado (defina MAIL_USERNAME/MAIL_PASSWORD no .env)"
    bcc = sorted({r.strip() for r in recipients if r and EMAIL_PATTERN.match(r.strip())})
    if not bcc:
        return False, "sem destinatários válidos"
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))
    msg["To"] = formataddr((SMTP_FROM_NAME, SMTP_FROM))  # demais ficam em BCC (envelope)
    msg.attach(MIMEText("Abra no app pra ver os palpites do bolão.", "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as srv:
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASSWORD)
            srv.sendmail(SMTP_FROM, [SMTP_FROM] + bcc, msg.as_string())
        return True, None
    except Exception as exc:
        return False, str(exc)[:200]


def world_cup_bet_email_html(game: models.WorldCupGame, predictions: list[models.WorldCupPrediction]) -> str:
    """E-mail de transparência no estilo do bolão (dark + acento Conversys): lista
    TODOS os palpites trancados do jogo, pra todo mundo ver que ninguém mexe nada."""
    kickoff_brt = (game.kickoff_at - timedelta(hours=3)).strftime("%d/%m · %Hh%M") if game.kickoff_at else "a confirmar"
    mn = f"Jogo #{game.match_number}" if game.match_number else "Jogo"
    rows = []
    for i, p in enumerate(predictions):
        nome = (p.user.name if p.user else None) or "—"
        artil = (p.scorer_guess or "").strip()
        artil_html = (
            f"<span style='color:#39d98a;font-weight:700;'>⚽ {artil}</span>"
            if artil else "<span style='color:#5b6b86;'>—</span>"
        )
        bg = "#0e1729" if i % 2 == 0 else "#0a1120"
        rows.append(
            f"<tr style='background:{bg};'>"
            f"<td style='padding:12px 16px;color:#e8eefc;font-weight:700;font-size:14px;border-bottom:1px solid #16223d;'>{nome}</td>"
            f"<td style='padding:12px 10px;text-align:center;border-bottom:1px solid #16223d;'>"
            f"<span style='display:inline-block;background:#13203a;border:1px solid #243a63;border-radius:8px;padding:4px 11px;color:#ffffff;font-weight:800;font-size:14px;white-space:nowrap;'>{p.home_score or 0} <span style='color:#5b6b86;'>×</span> {p.away_score or 0}</span>"
            f"</td>"
            f"<td style='padding:12px 16px;font-size:13px;border-bottom:1px solid #16223d;'>{artil_html}</td>"
            f"</tr>"
        )
    rows_html = "".join(rows)
    cta = (
        f"<tr><td align='center' style='background:#0a1120;padding:6px 22px 22px;'>"
        f"<a href='{PUBLIC_APP_URL}/bolao' style='display:inline-block;background:#2b6cff;color:#ffffff;text-decoration:none;font-weight:800;font-size:14px;padding:12px 26px;border-radius:10px;'>Ver o bolão ao vivo →</a>"
        f"</td></tr>"
        if PUBLIC_APP_URL else ""
    )
    chip = "display:inline-block;background:#13203a;border:1px solid #243a63;border-radius:999px;padding:4px 12px;color:#aebfe0;font-size:12px;font-weight:700;margin:2px 3px;"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;background:#06090f;">
<div style="background:#06090f;padding:24px 12px;font-family:'Segoe UI',Arial,Helvetica,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;border-radius:18px;overflow:hidden;border:1px solid #1b2740;background:#0a1120;">
      <!-- barra de acento da marca -->
      <tr><td><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
        <td height="5" style="background:#2b6cff;font-size:0;line-height:0;">&nbsp;</td>
        <td height="5" style="background:#22d3ee;font-size:0;line-height:0;">&nbsp;</td>
        <td height="5" style="background:#39d98a;font-size:0;line-height:0;">&nbsp;</td>
      </tr></table></td></tr>

      <!-- header -->
      <tr><td style="background:#0d1426;padding:20px 24px 16px;">
        <div style="color:#6f86c4;font-size:11px;font-weight:800;letter-spacing:2px;text-transform:uppercase;">⚽ Bolão Fut Conversys · Copa 2026</div>
        <div style="color:#ffffff;font-size:22px;font-weight:900;margin-top:6px;">🔒 Apostas trancadas</div>
        <div style="color:#8fa3c8;font-size:13px;margin-top:4px;">Transparência total — todo mundo recebe os mesmos palpites no fechamento. Ninguém muda nada depois.</div>
      </td></tr>

      <!-- hero do jogo -->
      <tr><td style="background:#0a1120;padding:22px 24px 8px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td width="44%" align="right" style="color:#ffffff;font-size:19px;font-weight:900;">{game.home_team}</td>
          <td width="12%" align="center"><span style="display:inline-block;background:#2b6cff;color:#fff;font-size:12px;font-weight:900;padding:6px 10px;border-radius:999px;">VS</span></td>
          <td width="44%" align="left" style="color:#ffffff;font-size:19px;font-weight:900;">{game.away_team}</td>
        </tr></table>
        <div style="text-align:center;margin-top:12px;">
          <span style="{chip}">{mn}</span>
          <span style="{chip}">🕒 começa {kickoff_brt} (Brasília)</span>
          <span style="{chip}">🔒 {len(predictions)} palpites</span>
        </div>
      </td></tr>

      <!-- tabela de palpites -->
      <tr><td style="background:#0a1120;padding:14px 24px 6px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="border-radius:12px;overflow:hidden;border:1px solid #16223d;">
          <tr style="background:#101d36;">
            <td style="padding:10px 16px;color:#7f93bd;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;background:#101d36;">Jogador</td>
            <td style="padding:10px 10px;color:#7f93bd;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;text-align:center;background:#101d36;">Placar</td>
            <td style="padding:10px 16px;color:#7f93bd;font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:1px;background:#101d36;">Artilheiro</td>
          </tr>
          {rows_html}
        </table>
      </td></tr>

      {cta}

      <!-- rodapé -->
      <tr><td style="background:#0d1426;padding:16px 24px 20px;border-top:1px solid #16223d;">
        <div style="margin-bottom:8px;">
          <span style="{chip}">Placar exato · 3</span><span style="{chip}">Vencedor · 1</span><span style="{chip}">Artilheiro · +1</span><span style="{chip}">Campeã · 10</span>
        </div>
        <div style="color:#5b6b86;font-size:11px;line-height:1.6;">
          E-mail automático e transparente do <b style="color:#8fa3c8;">Bolão Fut Conversys</b> — enviado pra todos no momento exato em que a aposta fechou.
        </div>
      </td></tr>
    </table>
  </td></tr></table>
</div></body></html>"""


def send_locked_game_palpites_emails(db: Session) -> int:
    """Quando a aposta de um jogo FECHA (1h antes), manda os palpites de todo mundo
    por e-mail pra todos — transparência total. Roda 1× por jogo (idempotente),
    com retry a cada 10min se o SMTP falhar, e só pra jogos recentes (sem flood)."""
    if not (SMTP_USER and SMTP_PASSWORD):
        return 0
    now = datetime.utcnow()
    sent = 0
    games = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(models.WorldCupGame.kickoff_at >= now - timedelta(hours=3))  # só recentes (anti-flood)
        .filter(models.WorldCupGame.kickoff_at <= now + timedelta(hours=1))  # já passou o cutoff de 1h
        .all()
    )
    recipients: list[str] | None = None
    for game in games:
        if not is_bettable_world_cup_game(game) or not world_cup_game_lock_passed(game):
            continue
        if get_app_setting(db, f"wc_palpites_email_{game.id}") == "1":
            continue
        # backoff de retry: tenta no máx a cada 10min
        last_try = get_app_setting(db, f"wc_palpites_email_try_{game.id}")
        if last_try:
            try:
                t = datetime.fromisoformat(last_try)
                if t.tzinfo:
                    t = t.astimezone(timezone.utc).replace(tzinfo=None)
                if (now - t).total_seconds() < 600:
                    continue
            except ValueError:
                pass
        preds = sorted(game.predictions, key=lambda p: ((p.user.name if p.user else "") or "").lower())
        if not preds:
            set_app_setting(db, f"wc_palpites_email_{game.id}", "1")  # ninguém apostou → nada a enviar
            continue
        if recipients is None:
            recipients = [
                (u.email or "").strip()
                for u in db.query(models.User).filter(models.User.email.isnot(None)).all()
                if (u.email or "").strip() and not (u.email or "").lower().endswith("@example.com")
            ]
        set_app_setting(db, f"wc_palpites_email_try_{game.id}", datetime.now(timezone.utc).isoformat())
        ok, err = send_email(
            recipients,
            f"🔒 Apostas trancadas — {game.home_team} x {game.away_team}",
            world_cup_bet_email_html(game, preds),
        )
        if ok:
            set_app_setting(db, f"wc_palpites_email_{game.id}", "1")
            sent += 1
            log_game_event(db, game, f"📧 palpites enviados ({len(preds)} palpites → {len(recipients)} pessoas)")
        else:
            log_game_event(db, game, f"📧 falha no e-mail: {err} (tenta de novo em 10min)")
    return sent


def apply_world_cup_sync(db: Session) -> tuple[int, int]:
    imported = 0
    updated = 0
    # openfootball (tabela + backup de goleadores) muda devagar: revalida só a
    # cada poucos minutos. O placar ao vivo vem da football-data a cada ciclo.
    last_of_raw = get_app_setting(db, "openfootball_last_fetch_at")
    of_due = True
    if last_of_raw:
        try:
            last_of = datetime.fromisoformat(last_of_raw)
            if last_of.tzinfo:
                last_of = last_of.astimezone(timezone.utc).replace(tzinfo=None)
            of_due = (datetime.utcnow() - last_of).total_seconds() >= WORLD_CUP_SCHEDULE_MIN_GAP
        except ValueError:
            of_due = True
    openfootball_games = []
    if of_due:
        openfootball_games = fetch_openfootball_world_cup_games()
        set_app_setting(db, "openfootball_last_fetch_at", datetime.now(timezone.utc).isoformat())
    for item in openfootball_games:
        data = dict(item)
        home_score = data.pop("home_score", None)
        away_score = data.pop("away_score", None)
        scorers = data.pop("scorers", None)
        game = (
            db.query(models.WorldCupGame)
            .filter(models.WorldCupGame.external_id == data["external_id"])
            .first()
        )
        if not game:
            game = models.WorldCupGame(**data, status="scheduled", created_at=datetime.utcnow())
            db.add(game)
            imported += 1
        else:
            game.match_number = data["match_number"]
            game.home_team = data["home_team"]
            game.away_team = data["away_team"]
            game.group_label = data["group_label"]
            game.stage = data["stage"]
            if data["venue"]:
                game.venue = data["venue"]
            game.kickoff_at = data["kickoff_at"]
            game.source = data["source"]
            updated += 1

        if home_score is not None and away_score is not None:
            was_finished = (game.status or "") == "finished"
            game.home_score = home_score
            game.away_score = away_score
            game.status = "finished"
            game.halftime = False
            # openfootball também é uma fonte de FIM: registra quem encerrou e quando,
            # pra agendar a re-confirmação de +10min e mostrar a fonte no painel
            if not game.end_source:
                game.end_source = "openfootball"
            if not game.finished_at:
                game.finished_at = datetime.utcnow()
            if not was_finished:
                log_game_event(db, game, f"Finalização — placar {home_score}-{away_score} (openfootball)", phase="fim", api="openfootball", ok=True)
        if scorers:
            # União: o openfootball traz nomes oficiais, mas não pode apagar
            # goleadores que o feed ao vivo já tinha capturado
            merged, changed = merge_scorers(game.scorers, re.split(r"[,;\n]", scorers))
            if changed:
                game.scorers = merged

    db.flush()
    secondary = cross_check_world_cup_results(db)
    live_source = apply_api_football_live(db)
    refresh_world_cup_live_statuses(db)
    finished_games = db.query(models.WorldCupGame).filter(models.WorldCupGame.status == "finished").all()
    for game in finished_games:
        score_world_cup_game(game)
    db.flush()
    update_rank_movement(db)
    # E-mail de transparência: ao fechar a aposta, manda os palpites pra todo mundo.
    # Isolado: falha de e-mail nunca derruba o sync.
    try:
        send_locked_game_palpites_emails(db)
    except Exception as exc:
        print(f"[world-cup-sync] e-mail de palpites falhou: {exc}", flush=True)
    now_iso = datetime.now(timezone.utc).isoformat()
    set_app_setting(db, "world_cup_last_sync", now_iso)
    # marca quando os artilheiros mudaram pela última vez (pro painel/contagem)
    if (live_source or {}).get("scorers_updated"):
        set_app_setting(db, "world_cup_last_scorer_update", now_iso)
    status_payload = {
        "at": datetime.now(timezone.utc).isoformat(),
        "ok": True,
        "error": None,
        "imported": imported,
        "updated": updated,
        "finished_games": len(finished_games),
        "missing_scorers": [
            f"{game.home_team} x {game.away_team}"
            for game in finished_games
            # 0-0 não tem goleador: não é pendência (senão fica eternamente na lista)
            if not game.scorers and ((game.home_score or 0) + (game.away_score or 0)) > 0
        ],
        "secondary": secondary,
        "live_source": live_source,
    }
    set_app_setting(db, "world_cup_sync_status", json.dumps(status_payload, ensure_ascii=False))
    record_world_cup_sync_run(db, status_payload)
    db.commit()
    return imported, updated


def record_world_cup_sync_run(db: Session, payload: dict[str, Any]) -> None:
    # Mantém um histórico curto (últimas 30 execuções) para o painel admin
    raw = get_app_setting(db, "world_cup_sync_runs")
    try:
        runs = json.loads(raw) if raw else []
    except (json.JSONDecodeError, TypeError):
        runs = []
    live = payload.get("live_source") or {}
    secondary = payload.get("secondary") or {}
    runs.insert(
        0,
        {
            "at": payload.get("at"),
            "ok": payload.get("ok", False),
            "error": payload.get("error"),
            "imported": payload.get("imported", 0),
            "updated": payload.get("updated", 0),
            "finished": payload.get("finished_games", 0),
            "mid_checks": live.get("mid_checks", 0),
            "scorers_updated": live.get("scorers_updated", 0),
            "finalized": live.get("finalized", 0),
            "confirmed": live.get("confirmed", 0),
            "conflicts": len(live.get("conflicts", []) or []) + len(secondary.get("conflicts", []) or []),
            "api_calls": live.get("calls_made", 0),
            "api_remaining": live.get("daily_remaining"),
            "filled": secondary.get("filled", 0),
        },
    )
    set_app_setting(db, "world_cup_sync_runs", json.dumps(runs[:30], ensure_ascii=False))


def record_world_cup_sync_failure(error: str) -> None:
    # Mantém o último erro visível para o admin mesmo quando o sync quebra
    try:
        session = SessionLocal()
        try:
            previous_raw = get_app_setting(session, "world_cup_sync_status")
            previous = json.loads(previous_raw) if previous_raw else {}
        except (json.JSONDecodeError, TypeError):
            previous = {}
        try:
            previous.update(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "ok": False,
                    "error": error[:500],
                }
            )
            set_app_setting(session, "world_cup_sync_status", json.dumps(previous, ensure_ascii=False))
            record_world_cup_sync_run(session, {"at": previous["at"], "ok": False, "error": error[:500]})
            session.commit()
        finally:
            session.close()
    except Exception:
        pass


def world_cup_has_live_window(db: Session) -> bool:
    # Há jogo rolando ou prestes a rolar/encerrar? (define a cadência do loop)
    now = datetime.utcnow()
    return db.query(models.WorldCupGame).filter(
        or_(
            models.WorldCupGame.status == "live",
            and_(
                models.WorldCupGame.status == "scheduled",
                models.WorldCupGame.kickoff_at.isnot(None),
                models.WorldCupGame.kickoff_at <= now + timedelta(minutes=5),
                models.WorldCupGame.kickoff_at >= now - timedelta(hours=3, minutes=30),
            ),
            # Jogo que ACABOU de encerrar mas ainda não confirmou goleadores: mantém a
            # cadência rápida por ~20min pra a confirmação final/reconfirmação rodar
            # logo, em vez de esperar o próximo tick idle (10min) quando era o último
            # jogo do dia. Sai do modo rápido assim que fica final E reconfirmado.
            and_(
                models.WorldCupGame.status == "finished",
                models.WorldCupGame.finished_at.isnot(None),
                models.WorldCupGame.finished_at >= now - timedelta(minutes=20),
                or_(
                    models.WorldCupGame.scorers_final.is_(False),
                    models.WorldCupGame.scorers_final.is_(None),
                    models.WorldCupGame.reconfirmed.is_(False),
                    models.WorldCupGame.reconfirmed.is_(None),
                ),
            ),
        )
    ).first() is not None


def world_cup_squads_due(db: Session) -> bool:
    last_sync = get_app_setting(db, "world_cup_last_squad_sync")
    if not last_sync:
        return True
    try:
        last = datetime.fromisoformat(last_sync)
    except ValueError:
        return True
    if last.tzinfo:
        last = last.astimezone(timezone.utc).replace(tzinfo=None)
    return datetime.utcnow() - last >= timedelta(hours=24)


def run_world_cup_sync_with_retries(attempts: int = 3) -> None:
    """Executa um ciclo de sync com retry/backoff para resistir a falhas
    transitórias de rede (a fonte pode oscilar; o palpite não pode quebrar)."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            session = SessionLocal()
            try:
                imported, updated = apply_world_cup_sync(session)
                print(f"[world-cup-sync] ok imported={imported} updated={updated} (tentativa {attempt})", flush=True)
                return
            finally:
                session.close()
        except Exception as exc:
            last_error = exc
            print(f"[world-cup-sync] falhou tentativa {attempt}/{attempts}: {exc}", flush=True)
            if attempt < attempts:
                time_module.sleep(min(30, 2 ** attempt))
    if last_error is not None:
        record_world_cup_sync_failure(str(last_error))


def _brt_date_str(now: datetime | None = None) -> str:
    # Dia em horário de Brasília (UTC-3): a rotina diária vira junto da meia-noite local
    return ((now or datetime.utcnow()) - timedelta(hours=3)).strftime("%Y-%m-%d")


def world_cup_knockout_daily_due(db: Session) -> bool:
    return get_app_setting(db, "wc_knockout_daily_date") != _brt_date_str()


def world_cup_knockout_daily_check(db: Session) -> dict[str, Any]:
    """Rotina diária (meia-noite BRT): detecta confrontos do mata-mata que ganharam
    adversário (viraram apostáveis) desde a última checagem. O banco já é preenchido
    continuamente pelo sync (openfootball, a cada ciclo); aqui só registramos os novos
    confrontos pra aparecerem em destaque e ficar logado pro admin."""
    set_app_setting(db, "wc_knockout_daily_date", _brt_date_str())
    ko_games = db.query(models.WorldCupGame).filter(models.WorldCupGame.stage != "group-stage").all()
    bettable_now = {g.id for g in ko_games if is_bettable_world_cup_game(g)}
    raw = get_app_setting(db, "wc_knockout_known_bettable")
    try:
        known = set(json.loads(raw)) if raw else set()
    except json.JSONDecodeError:
        known = set()
    new_games = [g for g in ko_games if g.id in (bettable_now - known)]
    for g in new_games:
        log_game_event(
            db, g, f"Confronto definido — {g.home_team} x {g.away_team} ({g.stage})",
            phase="mata-mata", api="openfootball", ok=True,
        )
    set_app_setting(db, "wc_knockout_known_bettable", json.dumps(sorted(bettable_now)))
    summary = {
        "at": datetime.now(timezone.utc).isoformat(),
        "new": [f"{g.home_team} x {g.away_team}" for g in new_games],
        "bettable_total": len(bettable_now),
    }
    set_app_setting(db, "wc_knockout_last_daily", json.dumps(summary, ensure_ascii=False))
    if new_games:
        print(f"[world-cup-knockout] novos confrontos definidos: {summary['new']}", flush=True)
    return summary


def world_cup_sync_loop() -> None:
    last_schedule_at = 0.0
    while True:
        # Cadência adaptativa: rápido com jogo ao vivo, lento ocioso
        try:
            session = SessionLocal()
            try:
                live = world_cup_has_live_window(session)
            finally:
                session.close()
        except Exception:
            live = False
        interval = WORLD_CUP_LIVE_INTERVAL if live else WORLD_CUP_IDLE_INTERVAL
        time_module.sleep(interval)

        # O sync completo (openfootball + football-data + API-Football live +
        # finalização de goleadores + rescore) já é barato e idempotente; roda
        # a cada tick. A API-Football se autolimita por orçamento/intervalo.
        run_world_cup_sync_with_retries()

        # Elencos: no máximo 1x/dia
        try:
            session = SessionLocal()
            try:
                if world_cup_squads_due(session):
                    imported, updated = apply_world_cup_squads_sync(session)
                    print(f"[world-cup-sync] squads imported={imported} updated={updated}", flush=True)
            finally:
                session.close()
        except Exception as exc:
            print(f"[world-cup-sync] squads failed: {exc}", flush=True)

        # Mata-mata: rotina diária (meia-noite BRT) detecta novos confrontos definidos
        try:
            session = SessionLocal()
            try:
                if world_cup_knockout_daily_due(session):
                    world_cup_knockout_daily_check(session)
                    session.commit()
            finally:
                session.close()
        except Exception as exc:
            print(f"[world-cup-knockout] daily check failed: {exc}", flush=True)


def openai_calls_key() -> str:
    return "openai_calls_" + datetime.utcnow().strftime("%Y%m%d")


def openai_calls_today(db: Session) -> int:
    raw = get_app_setting(db, openai_calls_key())
    return int(raw) if (raw or "").isdigit() else 0


def openai_chat(system: str, user: str, max_tokens: int = 140, db: Session | None = None, temperature: float = 0.5) -> str | None:
    # Chamada enxuta à OpenAI (modelo leve) via REST; sem dependência extra.
    if not OPENAI_API_KEY:
        return None
    if db is not None:  # contabiliza a chamada do dia pro painel admin
        try:
            set_app_setting(db, openai_calls_key(), str(openai_calls_today(db) + 1))
        except Exception:
            pass
    body = json.dumps(
        {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        OPENAI_CHAT_URL,
        data=body,
        headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(read_capped(response).decode("utf-8"))
    except Exception as exc:
        print(f"[openai] erro: {exc}", flush=True)
        return None
    choices = payload.get("choices") or []
    if not choices:
        return None
    return (choices[0].get("message") or {}).get("content", "").strip() or None


def ai_reconcile_scorers(
    db: Session,
    game: models.WorldCupGame,
    sources: dict[str, list[str]],
    status: dict[str, Any],
    squad: list[str] | None = None,
    phase: str = "merge",
    source_label: str = "API paga",
    corroborate_against: list[str] | None = None,
) -> list[str] | None:
    """IA reconcilia goleadores das fontes. Sem cache — só chama quando precisa.

    corroborate_against: nomes vindos de fontes REAIS (APIs externas) desta chamada.
    Se informado, qualquer nome devolvido pela IA que NENHUMA fonte real tenha citado
    é descartado — barra alucinação (a IA preenchendo gols sem dono com craques do
    elenco, ex.: inventar Mbappé/Thuram). A lista acumulada do jogo NÃO corrobora."""
    if not OPENAI_API_KEY:
        log_game_event(db, game, "IA — não configurada", phase=phase, api="IA merge", ok=False)
        return None
    total = (game.home_score or 0) + (game.away_score or 0)
    if total == 0:
        return []
    log_game_event(db, game, f"IA — consulta ({source_label})", phase=phase, api="IA merge")
    bump_game_poll(db, game.id, "ia")
    fontes_txt = "; ".join(f"{name}: {', '.join(lst) if lst else '(vazio)'}" for name, lst in sources.items())
    squad_txt = ", ".join((squad or [])[:60])
    text = openai_chat(
        system=(
            "Você UNIFICA e NORMALIZA goleadores relatados por fontes diferentes. Recebe listas "
            "de goleadores de várias APIs (que divergem, abreviam nomes ou estão incompletas), o "
            "total de gols e o ELENCO oficial dos dois times. "
            "Sua tarefa é juntar e padronizar APENAS os nomes que as fontes relataram, usando a "
            "grafia exata do elenco (resolva abreviações/acentos). "
            "PROIBIDO inventar: NUNCA inclua um jogador que NENHUMA fonte citou, mesmo que falte "
            "goleador para algum gol — nesse caso deixe faltar. Pode devolver MENOS nomes que o "
            "total de gols. NÃO complete a lista até o total de gols. "
            "Se uma fonte citar alguém fora do elenco, mapeie para o jogador do elenco mais provável "
            "ENTRE OS QUE AS FONTES CITARAM. Ignore gols contra. "
            "Responda só o JSON, ex: [\"Nome Oficial A\",\"Nome Oficial B\"]."
        ),
        user=(
            f"Jogo {game.home_team} {game.home_score}x{game.away_score} {game.away_team} ({total} gols). "
            f"Fontes — {fontes_txt}. Elenco (use estes nomes): {squad_txt or '(indisponível)'}."
        ),
        max_tokens=220,
        db=db,
        temperature=0.1,
    )
    if not text:
        log_game_event(db, game, "IA — sem resposta", phase=phase, api="IA merge", ok=False)
        return None
    status["ai_reconciles"] = status.get("ai_reconciles", 0) + 1
    bump_daily_counter(db, "ai_reconcile")
    try:
        start, end = text.find("["), text.rfind("]")
        names = json.loads(text[start : end + 1]) if start >= 0 and end > start else None
    except json.JSONDecodeError:
        names = None
    if not isinstance(names, list):
        log_game_event(db, game, "IA — resposta inválida", phase=phase, api="IA merge", ok=False)
        return None
    names = [re.sub(r"\s+", " ", str(n)).strip() for n in names if str(n).strip()]

    # GUARD anti-alucinação: só mantém nomes corroborados por uma fonte real desta chamada.
    if corroborate_against:
        sq = squad or []
        src_snapped, _ = snap_scorers_to_squad([s for s in corroborate_against if s], sq)
        kept, dropped = [], []
        for n in names:
            n_snap, _ = snap_scorers_to_squad([n], sq)
            cand = n_snap[0] if n_snap else n
            if any(same_scorer(cand, s) for s in src_snapped):
                kept.append(n)
            else:
                dropped.append(n)
        if dropped:
            log_game_event(
                db, game,
                f"IA — descartados (nenhuma fonte citou): {', '.join(dropped)}",
                phase=phase, api="IA merge", ok=False,
            )
        names = kept

    log_game_event(
        db, game,
        f"IA — resultado: {', '.join(names) if names else 'vazio'}",
        phase=phase, api="IA merge", ok=True,
    )
    return names


def world_cup_next_open_game(db: Session) -> models.WorldCupGame | None:
    """Próximo jogo ainda aberto pra palpite (não passou o cutoff de 1h)."""
    now = datetime.utcnow()
    games = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "scheduled")
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(models.WorldCupGame.kickoff_at - WORLD_CUP_BET_CUTOFF > now)
        .order_by(models.WorldCupGame.kickoff_at.asc())
        .all()
    )
    for game in games:
        if is_bettable_world_cup_game(game):
            return game
    return None


def world_cup_ai_insight(db: Session) -> dict[str, Any]:
    """Insight da IA sobre o PRÓXIMO jogo aberto, com base nos palpites
    agregados da galera (anônimo — não revela palpite individual).

    Determinístico no que importa (contagens); a IA só escreve o texto.
    Cacheado por assinatura dos dados + 30 min para gastar pouquíssimo."""
    base: dict[str, Any] = {"available": False, "game_id": None, "matchup": None, "text": None}
    game = world_cup_next_open_game(db)
    if not game or not OPENAI_API_KEY:
        return base

    preds = list(game.predictions)
    total = len(preds)
    base["game_id"] = game.id
    base["matchup"] = f"{game.home_team} x {game.away_team}"
    if total < 4:  # precisa de massa pra ser interessante (e não vazar palpite)
        return base

    home_w = sum(1 for p in preds if (p.home_score or 0) > (p.away_score or 0))
    away_w = sum(1 for p in preds if (p.away_score or 0) > (p.home_score or 0))
    draws = sum(1 for p in preds if (p.home_score or 0) == (p.away_score or 0))
    score_counts: dict[str, int] = {}
    for p in preds:
        key = f"{p.home_score or 0}x{p.away_score or 0}"
        score_counts[key] = score_counts.get(key, 0) + 1
    top_score = max(score_counts.items(), key=lambda kv: kv[1])
    scorer_counts: dict[str, int] = {}
    for p in preds:
        guess = (p.scorer_guess or "").strip()
        if guess:
            scorer_counts[guess] = scorer_counts.get(guess, 0) + 1
    top_scorer = max(scorer_counts.items(), key=lambda kv: kv[1]) if scorer_counts else None

    signature = json.dumps(
        {"g": game.id, "n": total, "h": home_w, "a": away_w, "d": draws, "s": top_score, "sc": top_scorer},
        ensure_ascii=False,
    )
    cached_raw = get_app_setting(db, "world_cup_ai_insight")
    if cached_raw:
        try:
            cached = json.loads(cached_raw)
            fresh = False
            if cached.get("at"):
                ts = datetime.fromisoformat(cached["at"])
                if ts.tzinfo:
                    ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
                fresh = datetime.utcnow() - ts < timedelta(minutes=30)
            if cached.get("signature") == signature and fresh and cached.get("text"):
                base["available"] = True
                base["text"] = cached["text"]
                return base
        except (json.JSONDecodeError, ValueError):
            pass

    home, away = game.home_team, game.away_team
    if home_w > away_w and home_w >= draws:
        tend_result = f"intenção coletiva pende para vitória do {home}"
    elif away_w > home_w and away_w >= draws:
        tend_result = f"intenção coletiva pende para vitória do {away}"
    elif draws > home_w and draws > away_w:
        tend_result = "intenção coletiva pende para empate"
    else:
        tend_result = "intenção dividida no resultado"

    partes = [f"{home} x {away}", tend_result]
    if top_scorer:
        partes.append(f"artilheiro que mais circula na intenção (não revele quantos): {top_scorer[0]}")
    if top_score[1] >= max(2, total // 4):
        partes.append(f"placar que mais aparece na cabeça da galera (não revele quantos): {top_score[0]}")

    text = openai_chat(
        system=(
            "Você é um narrador esportivo brasileiro animado de um bolão de Copa. "
            "Escreva UMA frase curtíssima (pt-BR, MÁXIMO 110 caracteres) sobre a INTENÇÃO "
            "dos palpites: qual time a galera quer ver ganhando e qual artilheiro está na conversa. "
            "PROIBIDO: números, porcentagens, contagem de palpites, nomes de quem apostou, hashtags. "
            "Fale como tendência/vibe, não como estatística."
        ),
        user="Intenção dos palpites: " + "; ".join(partes) + ".",
        max_tokens=70,
        db=db,
        temperature=0.7,
    )
    if not text:
        return base
    bump_daily_counter(db, "ai_insight")  # conta a "resenha" separada do reconcile
    # Teto rígido pra nunca quebrar o card, independente do que a IA escrever
    text = text.strip().strip('"')
    if len(text) > 150:
        text = text[:147].rsplit(" ", 1)[0] + "…"
    set_app_setting(
        db,
        "world_cup_ai_insight",
        json.dumps({"signature": signature, "at": datetime.now(timezone.utc).isoformat(), "text": text}, ensure_ascii=False),
    )
    db.commit()
    base["available"] = True
    base["text"] = text
    return base


def world_cup_champion_lock_at(db: Session) -> datetime | None:
    # Palpite de campeão fica aberto até o fim da 1ª rodada da fase de grupos
    games = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(models.WorldCupGame.stage == "group-stage")
        .order_by(models.WorldCupGame.kickoff_at.asc())
        .all()
    )
    by_group: dict[str, list[models.WorldCupGame]] = {}
    for game in games:
        label = (game.group_label or "").strip()
        if not label:
            continue
        by_group.setdefault(label, []).append(game)
    if not by_group:
        return None

    round_two_starts = [
        group_games[2].kickoff_at
        for group_games in by_group.values()
        if len(group_games) >= 3
    ]
    if round_two_starts:
        return min(round_two_starts)

    round_one_ends = [
        game.kickoff_at
        for group_games in by_group.values()
        for game in group_games[:2]
    ]
    return max(round_one_ends) if round_one_ends else None


def world_cup_champion_locked(db: Session) -> bool:
    champion = get_app_setting(db, "world_cup_champion")
    if champion:
        return True
    lock_at = world_cup_champion_lock_at(db)
    return bool(lock_at and lock_at <= datetime.utcnow())


def world_cup_champion_pick_response(pick: models.WorldCupChampionPick) -> dict[str, Any]:
    return {
        "id": pick.id,
        "team": pick.team,
        "points": pick.points or 0,
        "status": pick.status or "pending",
        "user": user_summary(pick.user),
    }


def world_cup_champion_response(db: Session, user: models.User | None = None) -> dict[str, Any]:
    champion_team = get_app_setting(db, "world_cup_champion")
    locked = world_cup_champion_locked(db)
    picks = (
        db.query(models.WorldCupChampionPick)
        .options(joinedload(models.WorldCupChampionPick.user))
        .all()
    )
    viewer_pick = next((pick for pick in picks if user and pick.user_id == user.id), None)
    return {
        "team": champion_team,
        "locked": locked,
        "lock_at": iso_utc(world_cup_champion_lock_at(db)),
        "points_award": WORLD_CUP_POINTS_CHAMPION,
        "picks_count": len(picks),
        "viewer_pick": world_cup_champion_pick_response(viewer_pick) if viewer_pick else None,
        "picks": [world_cup_champion_pick_response(pick) for pick in picks] if locked else [],
    }


def world_cup_highlights_response(db: Session) -> dict[str, Any]:
    last_game = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .order_by(models.WorldCupGame.kickoff_at.desc())
        .first()
    )
    if not last_game:
        return {"last_game": None, "last_game_winners": []}
    winners = sorted(
        (prediction for prediction in last_game.predictions if (prediction.points or 0) > 0),
        key=lambda prediction: -(prediction.points or 0),
    )
    return {
        "last_game": world_cup_game_response(last_game),
        "last_game_winners": [world_cup_prediction_response(prediction) for prediction in winners[:5]],
    }


def post_response(post: models.Post, user: models.User | None = None) -> dict[str, Any]:
    viewer_reaction = None
    if user:
        viewer_reaction = next(
            (
                (like.reaction_type or "torcida")
                for like in post.likes
                if like.user_id == user.id
            ),
            None,
        )
    if viewer_reaction and viewer_reaction not in SUPPORTED_REACTIONS:
        viewer_reaction = "torcida"

    claimed_goals = max(0, post.goals_scored or 0)
    goal_status = goal_status_for(post)
    approved_goals = approved_goals_for_post(post)

    reactions = {key: 0 for key in SUPPORTED_REACTIONS}
    for like in post.likes:
        reaction_type = like.reaction_type or "torcida"
        if reaction_type not in reactions:
            reaction_type = "torcida"
        reactions[reaction_type] += 1

    return {
        "id": post.id,
        "title": post.title,
        "description": post.description,
        "image_url": post.image_url,
        "goals_scored": claimed_goals,
        "approved_goals": approved_goals,
        "goal_status": goal_status,
        "goal_reviewed_at": post.goal_reviewed_at.isoformat() if post.goal_reviewed_at else None,
        "can_review_goals": bool(user and is_admin_user(user) and claimed_goals > 0 and goal_status == "pending"),
        "created_at": post.created_at.isoformat(),
        "author": user_summary(post.user),
        "match": match_response(post.match, user) if post.match else None,
        "likes_count": len(post.likes),
        "reactions": reactions,
        "viewer_reaction": viewer_reaction,
        "comments_count": len(post.comments),
        "liked_by_user": bool(viewer_reaction),
        "comments": [
            {
                "id": comment.id,
                "text": comment.text,
                "parent_id": comment.parent_id,
                "media_url": comment.media_url,
                "media_type": comment.media_type,
                "created_at": comment.created_at.isoformat(),
                "author": user_summary(comment.user),
            }
            for comment in sorted(post.comments, key=lambda item: item.created_at)
        ],
    }


def seed_user(
    db: Session,
    username: str,
    email: str,
    name: str,
    title: str,
    position: str,
    favorite_player: str,
    avatar_url: str,
    banner_url: str,
    goals: int,
    assists: int,
    fouls: int,
    barbecue_score: int,
) -> models.User:
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user:
        user = models.User(username=username, password_hash=hash_password(secrets.token_urlsafe(24)))
        db.add(user)

    user.email = email
    user.name = name
    user.display_name = name
    user.title = title
    user.bio = f"{position} da pelada da firma. Presença confirmada na resenha."
    user.position = position
    user.favorite_team = "Conversys FC"
    user.favorite_player = favorite_player
    user.avatar_url = avatar_url
    user.banner_url = banner_url
    user.profile_frame = user.profile_frame or "conversys"
    user.cosmetic_tier = user.cosmetic_tier or "starter"
    user.animated_banner = bool(user.animated_banner)
    if not user.profile_effect:
        user.profile_effect = "off"
    user.avatar_config = user.avatar_config or json.dumps(default_avatar_config(user))
    user.player_rating = user.player_rating or 78
    user.verified_domain = is_conversys_email(email)
    user.verified_enabled = bool(user.verified_enabled)
    user.show_verified_badge = bool(user.show_verified_badge if user.show_verified_badge is not None else False)
    user.provider = user.provider or "local"
    user.goals = goals
    user.assists = assists
    user.fouls = fouls
    user.barbecue_score = barbecue_score
    return user


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        admin = db.query(models.User).filter(models.User.is_admin.is_(True)).first()
        if not admin:
            admin = db.query(models.User).filter(models.User.email == ADMIN_EMAIL).first()
        if not admin:
            admin = db.query(models.User).filter(models.User.username == ADMIN_USERNAME).first()

        created_bootstrap_admin = False
        if not admin:
            admin = models.User(username=ADMIN_USERNAME)
            db.add(admin)
            created_bootstrap_admin = True

        if created_bootstrap_admin:
            admin.email = ADMIN_EMAIL
            admin.password_hash = hash_password(ADMIN_PASSWORD)
            admin.name = "Matheus Renzo"
            admin.display_name = "Matheus Renzo"
            admin.title = "Admin"
            admin.bio = "Administrador do Fut Conversys."
            admin.position = "Admin"
            admin.favorite_team = "Conversys FC"
            admin.favorite_player = None
            admin.profile_frame = "nitro_plus"
            admin.cosmetic_tier = "starter"
            admin.animated_banner = False
            admin.profile_effect = "nitro"
            admin.avatar_config = json.dumps(
                {
                    "body": "athletic",
                    "presentation": "player",
                    "skin": "medium",
                    "hair": "short",
                    "kit": "home",
                    "shorts": "navy",
                    "boots": "cyan",
                    "gender": "neutral",
                    "pose": "captain",
                }
            )
            admin.player_rating = 87
            admin.provider = "local"
            admin.goals = 0
            admin.assists = 0
            admin.fouls = 0
            admin.barbecue_score = 0

        admin.is_admin = True
        admin.verified_domain = is_conversys_email(admin.email)
        admin.verified_enabled = True
        admin.show_verified_badge = bool(admin.show_verified_badge if admin.show_verified_badge is not None else True)
        db.commit()
    finally:
        db.close()


seed_demo_data()


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(request: LoginRequest, db: Session = Depends(get_db)):
    identifier = request.username.strip()
    user = db.query(models.User).filter(models.User.username == identifier).first()
    if not user:
        user = db.query(models.User).filter(models.User.email == normalize_email(identifier)).first()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuário ou senha inválidos",
        )

    return {
        "token": create_access_token(user.id),
        "user": user_summary(user),
    }


@app.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    name = request.name.strip()
    email = normalize_email(request.email)
    requested_username = normalize_username(request.username or "")

    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Informe seu nome")
    if not EMAIL_PATTERN.match(email):
        raise HTTPException(status_code=400, detail="Informe um e-mail válido")
    validate_password_strength(request.password, email, name)

    existing_email = db.query(models.User).filter(models.User.email == email).first()
    if existing_email:
        raise HTTPException(status_code=409, detail="Este e-mail já está cadastrado")

    if requested_username:
        if len(requested_username) < 3:
            raise HTTPException(status_code=400, detail="O usuário precisa ter pelo menos 3 caracteres")
        if db.query(models.User).filter(models.User.username == requested_username).first():
            raise HTTPException(status_code=409, detail="Este usuário já está em uso")
        username = requested_username
    else:
        base_username = normalize_username(email.split("@", 1)[0]) or "jogador"
        username = base_username
        suffix = 1
        while db.query(models.User).filter(models.User.username == username).first():
            suffix += 1
            username = f"{base_username}{suffix}"

    user = models.User(
        username=username,
        email=email,
        password_hash=hash_password(request.password),
        name=name,
        display_name=name,
        title="Jogador Conversys",
        bio="Novo perfil no Fut Conversys.",
        position="Jogador",
        favorite_team="Conversys FC",
        provider="local",
        profile_frame="conversys",
        profile_effect="off",
        cosmetic_tier="starter",
        animated_banner=False,
        player_rating=78,
        verified_domain=is_conversys_email(email),
        show_verified_badge=True,
        goals=0,
        assists=0,
        fouls=0,
        barbecue_score=0,
    )
    user.avatar_config = json.dumps(default_avatar_config(user))
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "token": create_access_token(user.id),
        "user": user_summary(user),
    }


@app.get("/api/auth/microsoft/config")
def microsoft_config():
    config = microsoft_env()
    return {
        "enabled": microsoft_is_configured(),
        "provider": "microsoft_entra",
        "required_env": [
            "MICROSOFT_CLIENT_ID",
            "MICROSOFT_TENANT_ID",
            "MICROSOFT_CLIENT_SECRET",
            "MICROSOFT_REDIRECT_URI",
        ],
        "redirect_uri": config["redirect_uri"],
        "verified_domain": VERIFIED_DOMAIN,
    }


@app.get("/api/auth/microsoft/start")
def microsoft_start(state: str | None = None):
    return RedirectResponse(microsoft_authorize_url(state))


@app.post("/api/auth/microsoft/callback")
def microsoft_callback(request: MicrosoftCallbackRequest, db: Session = Depends(get_db)):
    config = microsoft_env()
    if not microsoft_is_configured():
        raise HTTPException(status_code=500, detail="Microsoft Auth não configurado")

    token_url = f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/token"
    token_response = request_json(
        token_url,
        {
            "client_id": config["client_id"],
            "client_secret": config["client_secret"],
            "code": request.code,
            # redirect_uri sempre o do servidor (ignora valor do cliente) — fecha
            # o vetor de troca de código com redirect_uri controlado pelo atacante
            "redirect_uri": config["redirect_uri"],
            "grant_type": "authorization_code",
            "scope": "openid profile email User.Read",
        },
    )

    access_token = token_response.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Microsoft não retornou access_token")

    graph_user = request_json(
        "https://graph.microsoft.com/v1.0/me?$select=id,displayName,mail,userPrincipalName",
        token=access_token,
    )
    microsoft_avatar_url = request_microsoft_photo_data_url(access_token)

    provider_subject = graph_user.get("id")
    email = graph_user.get("mail") or graph_user.get("userPrincipalName")
    name = graph_user.get("displayName") or email or "Usuário Conversys"

    if not provider_subject or not email:
        raise HTTPException(status_code=400, detail="Perfil Microsoft sem id/email")

    if not is_conversys_email(email):
        raise HTTPException(
            status_code=403,
            detail="domain_not_allowed",
        )

    user = (
        db.query(models.User)
        .filter(models.User.provider == "microsoft_entra", models.User.provider_subject == provider_subject)
        .first()
    )
    if not user:
        user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        username = email.split("@", 1)[0]
        suffix = 1
        candidate = username
        while db.query(models.User).filter(models.User.username == candidate).first():
            suffix += 1
            candidate = f"{username}{suffix}"
        user = models.User(username=candidate, password_hash=hash_password(secrets.token_urlsafe(24)))
        db.add(user)

    user.email = email
    user.name = name
    user.display_name = user.display_name or name
    user.title = user.title or "Jogador Conversys"
    user.bio = user.bio or "Perfil conectado com Microsoft Entra."
    user.position = user.position or "Jogador"
    user.favorite_team = user.favorite_team or "Conversys FC"
    user.avatar_url = microsoft_avatar_url or user.avatar_url
    user.provider = "microsoft_entra"
    user.provider_subject = provider_subject
    user.tenant_id = config["tenant_id"]
    user.verified_domain = is_conversys_email(email)
    user.verified_enabled = bool(user.verified_enabled)
    if not has_verified_features(user):
        clear_verified_features(user)
    db.commit()
    db.refresh(user)

    return {
        "token": create_access_token(user.id),
        "user": user_summary(user),
    }


@app.get("/api/me")
def get_my_profile(user: models.User = Depends(get_current_user)):
    return {
        **user_summary(user),
        "stats": player_stats(user),
    }


@app.get("/api/search")
def global_search(
    q: str = "",
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    query = q.strip()
    if len(query) < 2:
        return {"profiles": [], "events": [], "posts": []}

    pattern = f"%{query}%"
    profiles = (
        db.query(models.User)
        .filter(
            or_(
                models.User.name.ilike(pattern),
                models.User.display_name.ilike(pattern),
                models.User.username.ilike(pattern),
                models.User.title.ilike(pattern),
                models.User.position.ilike(pattern),
            )
        )
        .order_by(models.User.name.asc())
        .limit(5)
        .all()
    )
    matches = (
        db.query(models.Match)
        .filter(
            or_(
                models.Match.title.ilike(pattern),
                models.Match.location.ilike(pattern),
                models.Match.description.ilike(pattern),
                models.Match.event_type.ilike(pattern),
            )
        )
        .order_by(models.Match.date.asc())
        .limit(5)
        .all()
    )
    posts = (
        db.query(models.Post)
        .filter(or_(models.Post.title.ilike(pattern), models.Post.description.ilike(pattern)))
        .order_by(models.Post.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "profiles": [user_summary(item) for item in profiles],
        "events": [match_response(item, user) for item in matches],
        "posts": [post_response(item, user) for item in posts],
    }


@app.put("/api/users/me/profile")
def update_my_profile(
    request: ProfileUpdateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    unverified_allowed_fields = {"avatar_url", "banner_url", "banner_position_x", "banner_position_y"}
    for field, value in request.model_dump(exclude_unset=True).items():
        if not has_verified_features(user) and field not in unverified_allowed_fields:
            raise HTTPException(status_code=403, detail="Edição completa precisa ser liberada pelo admin")
        if field == "profile_frame" and value not in SUPPORTED_FRAMES:
            raise HTTPException(status_code=400, detail="Moldura inválida")
        if field == "cosmetic_tier":
            user.cosmetic_tier = "starter"
            continue
        if field == "profile_effect":
            if value not in SUPPORTED_EFFECTS:
                raise HTTPException(status_code=400, detail="Efeito visual inválido")
            user.animated_banner = False
        if field == "animated_banner":
            user.animated_banner = False
            continue
        if field == "player_rating" and value is not None:
            value = max(40, min(99, int(value)))
        if field in {"banner_position_x", "banner_position_y"}:
            value = clamp_banner_position(value)
        if field == "avatar_config" and value is not None:
            value = json.dumps({**default_avatar_config(user), **value})
        if field in {"avatar_url", "banner_url"}:
            # URL da própria API ecoada de volta = imagem não mudou; mantém o base64 do banco
            if isinstance(value, str) and OWN_MEDIA_URL_PATTERN.match(value.strip()):
                continue
            value = validate_image_url(value)
        setattr(user, field, value)

    if not has_verified_features(user):
        clear_verified_features(user)
    db.commit()
    db.refresh(user)
    return {
        **user_summary(user),
        "stats": player_stats(user),
    }


@app.get("/api/users/{user_id}/avatar")
def user_avatar_media(
    user_id: int,
    db: Session = Depends(get_db),
    if_none_match: str | None = Header(default=None),
):
    return serve_user_media(db, user_id, "avatar", if_none_match)


@app.get("/api/users/{user_id}/banner")
def user_banner_media(
    user_id: int,
    db: Session = Depends(get_db),
    if_none_match: str | None = Header(default=None),
):
    return serve_user_media(db, user_id, "banner", if_none_match)


@app.get("/api/admin/users")
def admin_users(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode gerenciar verificados")

    users = db.query(models.User).order_by(models.User.name.asc()).all()
    return {"users": [user_summary(item) for item in users]}


@app.put("/api/admin/users/{user_id}/verified")
def set_user_verified(
    user_id: int,
    request: VerifiedFeatureRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode gerenciar verificados")

    target = db.query(models.User).filter(models.User.id == user_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")

    target.verified_enabled = request.verified_enabled
    if request.verified_enabled:
        target.show_verified_badge = True
        if not target.profile_frame or target.profile_frame == "none":
            target.profile_frame = "conversys"
    else:
        clear_verified_features(target)

    db.commit()
    db.refresh(target)
    return user_summary(target)


@app.get("/api/users/{user_id}")
def get_user_profile(user_id: int, db: Session = Depends(get_db), _viewer: models.User = Depends(get_current_user)):
    user = (
        db.query(models.User)
        .options(
            subqueryload(models.User.posts).subqueryload(models.Post.likes),
            subqueryload(models.User.posts).subqueryload(models.Post.comments).joinedload(models.Comment.user),
            subqueryload(models.User.posts).joinedload(models.Post.match),
            subqueryload(models.User.rsvps),
            subqueryload(models.User.comments),
        )
        .filter(models.User.id == user_id)
        .first()
    )
    if not user:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")

    return {
        **public_user_summary(user),
        "stats": player_stats(user),
        "posts": [
            post_response(post)
            for post in sorted(user.posts, key=lambda item: item.created_at, reverse=True)
        ],
    }


@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db), _user: models.User = Depends(get_current_user)):
    users = (
        db.query(models.User)
        .options(
            subqueryload(models.User.posts).subqueryload(models.Post.likes),
            subqueryload(models.User.rsvps),
            subqueryload(models.User.comments),
        )
        .all()
    )
    return {
        "top_scorers": [
            {**user_summary(user), "score": score}
            for user in sorted(users, key=approved_goals_for_user, reverse=True)
            if (score := approved_goals_for_user(user)) > 0
        ][:10],
        "top_barbecue": [
            {**user_summary(user), "score": user.barbecue_score or 0}
            for user in sorted(users, key=lambda item: item.barbecue_score or 0, reverse=True)[:5]
        ],
    }


@app.get("/api/world-cup/board")
def world_cup_board(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    # Apenas o "relógio" (vira scheduled->live no horário, fecha palpites) roda no
    # request: é uma query barata, sem rede. A atualização de placar via fonte
    # externa (football-data) NÃO entra no caminho do request — ela é cara e
    # bloqueante; quem mantém o placar fresco é o world_cup_sync_loop em background
    # (apply_world_cup_sync -> cross_check_world_cup_results, a cada ~30s ao vivo).
    if refresh_world_cup_live_statuses(db):
        db.commit()
    games = db.query(models.WorldCupGame).order_by(models.WorldCupGame.kickoff_at.asc()).all()
    return {
        "games": [world_cup_game_response(game, user) for game in games],
        "leaderboard": world_cup_leaderboard_response(db),
        "champion": world_cup_champion_response(db, user),
        "highlights": world_cup_highlights_response(db),
        "last_sync": get_app_setting(db, "world_cup_last_sync"),
        "rules": {
            "exact_score": WORLD_CUP_POINTS_EXACT,
            "correct_outcome": WORLD_CUP_POINTS_OUTCOME,
            "scorer_bonus": WORLD_CUP_POINTS_SCORER,
            "champion": WORLD_CUP_POINTS_CHAMPION,
            "locked_after_kickoff": True,
        },
    }


@app.get("/api/world-cup/games")
def list_world_cup_games(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    games = db.query(models.WorldCupGame).order_by(models.WorldCupGame.kickoff_at.asc()).all()
    return {"games": [world_cup_game_response(game, user) for game in games]}


@app.get("/api/world-cup/insight")
def world_cup_insight(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return world_cup_ai_insight(db)


@app.post("/api/world-cup/games")
def create_world_cup_game(
    request: WorldCupGameCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode cadastrar jogos do bolão")

    home_team = request.home_team.strip()
    away_team = request.away_team.strip()
    if not home_team or not away_team:
        raise HTTPException(status_code=400, detail="Informe as duas seleções")
    if home_team.lower() == away_team.lower():
        raise HTTPException(status_code=400, detail="As seleções precisam ser diferentes")

    stage = (request.stage or "group-stage").strip().lower()
    if not stage:
        stage = "group-stage"

    external_id = request.external_id.strip() if request.external_id else None
    if external_id and db.query(models.WorldCupGame).filter(models.WorldCupGame.external_id == external_id).first():
        raise HTTPException(status_code=409, detail="Esse jogo externo já foi cadastrado")

    game = models.WorldCupGame(
        external_id=external_id,
        match_number=request.match_number,
        home_team=home_team,
        away_team=away_team,
        group_label=request.group_label.strip() if request.group_label else None,
        stage=stage,
        venue=request.venue.strip() if request.venue else None,
        kickoff_at=to_utc_naive(request.kickoff_at),
        status="scheduled",
        source=request.source.strip() if request.source else "manual",
        created_at=datetime.utcnow(),
    )
    db.add(game)
    db.commit()
    db.refresh(game)
    return world_cup_game_response(game, user)


@app.post("/api/world-cup/sync/openfootball")
def sync_world_cup_openfootball(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode importar jogos da Copa")

    imported, updated = apply_world_cup_sync(db)
    games = db.query(models.WorldCupGame).order_by(models.WorldCupGame.kickoff_at.asc()).all()
    return {
        "imported": imported,
        "updated": updated,
        "games": [world_cup_game_response(game, user) for game in games],
        "leaderboard": world_cup_leaderboard_response(db),
    }


@app.get("/api/world-cup/players")
def list_world_cup_players(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return {
        "players": world_cup_players_grouped(db),
        "last_sync": get_app_setting(db, "world_cup_last_squad_sync"),
    }


@app.post("/api/world-cup/sync/squads")
def sync_world_cup_squads(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode importar os elencos")

    imported, updated = apply_world_cup_squads_sync(db)
    return {
        "imported": imported,
        "updated": updated,
        "players": world_cup_players_grouped(db),
    }


@app.post("/api/world-cup/email/test")
def world_cup_email_test(
    game_id: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    """Manda o e-mail de palpites de UM jogo SÓ pro próprio admin (teste/preview),
    sem marcar como enviado e sem mandar pra ninguém mais."""
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode testar o e-mail")
    if not (SMTP_USER and SMTP_PASSWORD):
        raise HTTPException(status_code=400, detail="SMTP não configurado: defina MAIL_USERNAME e MAIL_PASSWORD no .env")
    if not (user.email and EMAIL_PATTERN.match(user.email)):
        raise HTTPException(status_code=400, detail="Seu usuário admin não tem e-mail válido pra receber o teste")
    query = db.query(models.WorldCupGame)
    game = (
        query.filter(models.WorldCupGame.id == game_id).first()
        if game_id
        else query.filter(models.WorldCupGame.predictions.any()).order_by(models.WorldCupGame.kickoff_at.desc()).first()
    )
    if not game:
        raise HTTPException(status_code=404, detail="Nenhum jogo com palpites pra testar")
    preds = sorted(game.predictions, key=lambda p: ((p.user.name if p.user else "") or "").lower())
    ok, err = send_email(
        [user.email],
        f"[TESTE] Apostas trancadas — {game.home_team} x {game.away_team}",
        world_cup_bet_email_html(game, preds),
    )
    if not ok:
        raise HTTPException(status_code=502, detail=f"Falha ao enviar: {err}")
    return {"sent_to": user.email, "game": f"{game.home_team} x {game.away_team}", "palpites": len(preds)}


@app.get("/api/world-cup/sync/status")
def world_cup_sync_status(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    def read_status(key: str) -> dict[str, Any] | None:
        raw = get_app_setting(db, key)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None

    def read_json(key: str, fallback):
        raw = get_app_setting(db, key)
        if not raw:
            return fallback
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return fallback

    finished_query = db.query(models.WorldCupGame).filter(models.WorldCupGame.status == "finished")
    live_now = world_cup_has_live_window(db)

    # Jogos de HOJE (dia UTC) com horário, status e placar — pro topo do painel
    now = datetime.utcnow()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_rows = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at >= day_start)
        .filter(models.WorldCupGame.kickoff_at < day_start + timedelta(days=1))
        .order_by(models.WorldCupGame.kickoff_at.asc())
        .all()
    )
    today_games = [
        {
            "match_number": g.match_number,
            "home_team": g.home_team,
            "away_team": g.away_team,
            "kickoff_at": iso_utc(g.kickoff_at),
            "status": g.status,
            "score": f"{g.home_score}-{g.away_score}" if g.home_score is not None else None,
            "scorers": g.scorers,
            "scorers_complete": world_cup_scorers_complete(g),
            "scorers_confirmations": g.scorers_confirmations or 0,
            "end_source": g.end_source,
            "halftime": bool(g.halftime),
        }
        for g in today_rows
    ]

    # Requisições feitas HOJE em cada fonte (UTC), com seus limites reais
    requests_today = {
        "football_data": {"calls": daily_counter(db, "football_data"), "limit_per_min": 10, "daily_cap": None,
                          "label": "Placar + status ao vivo"},
        "api_football": {"calls": daily_counter(db, "api_football"),
                         "daily_cap": API_FOOTBALL_DAILY_BUDGET * max(1, len(API_FOOTBALL_KEYS)),
                         "remaining": api_football_total_remaining(db) if API_FOOTBALL_KEYS else None,
                         "limit_per_min": API_FOOTBALL_MINUTE_LIMIT, "label": "Nome dos goleadores"},
        "thesportsdb": {"calls": daily_counter(db, "thesportsdb"), "limit_per_min": 30, "daily_cap": None,
                        "label": "2ª confirmação de goleadores"},
        "ai_reconcile": {"calls": daily_counter(db, "ai_reconcile"), "daily_cap": None,
                         "label": "IA: confirma goleadores (~2/jogo)"},
        "ai_insight": {"calls": daily_counter(db, "ai_insight"), "daily_cap": None,
                       "label": "IA: resenha do card de palpite"},
    }

    # Contagem regressiva: próxima atualização do painel ao vivo e dos artilheiros
    last_sync_at = get_app_setting(db, "world_cup_last_sync")
    last_live_poll_at = get_app_setting(db, "api_football_last_live_at")
    last_scorer_update = get_app_setting(db, "world_cup_last_scorer_update")
    live_source_now = (read_status("world_cup_sync_status") or {}).get("live_source") or {}
    cadence = {
        "live_now": live_now,
        "loop_seconds": WORLD_CUP_LIVE_INTERVAL if live_now else WORLD_CUP_IDLE_INTERVAL,
        "last_sync_at": last_sync_at,
        "last_live_poll_at": last_live_poll_at,
        "live_poll_gap_seconds": live_source_now.get("live_gap_seconds") or API_FOOTBALL_SAFETY_GAP,
        "live_retry_max": API_FOOTBALL_LIVE_RETRY_MAX,
        "tsd_live_retry_max": THESPORTSDB_LIVE_RETRY_MAX,
        "goal_pending": bool(live_source_now.get("goal_pending")),
        "last_scorer_update_at": last_scorer_update,
    }

    return {
        "last_sync": get_app_setting(db, "world_cup_last_sync"),
        "last_squad_sync": get_app_setting(db, "world_cup_last_squad_sync"),
        "games_sync": read_status("world_cup_sync_status"),
        "squad_sync": read_status("world_cup_squad_sync_status"),
        "runs": read_json("world_cup_sync_runs", []),
        "game_events": read_json("wc_game_events", []),
        "today_games": today_games,
        "requests_today": requests_today,
        "cadence": cadence,
        "live_now": live_now,
        # Cadência atual do loop e próxima janela
        "interval_seconds": WORLD_CUP_LIVE_INTERVAL if live_now else WORLD_CUP_IDLE_INTERVAL,
        "live_interval_seconds": WORLD_CUP_LIVE_INTERVAL,
        "idle_interval_seconds": WORLD_CUP_IDLE_INTERVAL,
        "sync_interval_seconds": WORLD_CUP_LIVE_INTERVAL if live_now else WORLD_CUP_IDLE_INTERVAL,
        "sources": {
            "openfootball_url": OPENFOOTBALL_2026_CUP_URL,
            "football_data_configured": bool(FOOTBALL_DATA_API_KEY),
            "api_football_configured": bool(API_FOOTBALL_KEYS),
            "api_football_keys": len(API_FOOTBALL_KEYS),
            "api_football_active_keys": api_football_active_keys(db),
            "api_football_suspended": len(API_FOOTBALL_KEYS) - api_football_active_keys(db),
            "api_football_daily_remaining": api_football_total_remaining(db) if API_FOOTBALL_KEYS else None,
            "api_football_daily_limit": API_FOOTBALL_DAILY_BUDGET * max(1, len(API_FOOTBALL_KEYS)),
            "score_source": "football-data.org (placar+status ao vivo)",
            "scorer_source": "API-Football (2x/jogo) + TheSportsDB (grátis) + openfootball",
            "ai_configured": bool(OPENAI_API_KEY),
            "ai_calls_today": openai_calls_today(db),
            "thesportsdb_configured": True,
            "squads_source": "Wikipedia (elencos oficiais)",
        },
        "totals": {
            "games": db.query(models.WorldCupGame).count(),
            "live_games": db.query(models.WorldCupGame).filter(models.WorldCupGame.status == "live").count(),
            "finished_games": finished_query.count(),
            "finished_without_scorers": finished_query.filter(
                or_(models.WorldCupGame.scorers.is_(None), models.WorldCupGame.scorers == "")
            ).count(),
            "players": db.query(models.WorldCupPlayer).count(),
            "teams_with_squads": db.query(models.WorldCupPlayer.team).distinct().count(),
        },
        # Saúde por jogo (ao vivo + encerrados): visível no painel público de transparência
        "games_health": [
            {
                "match_number": g.match_number,
                "matchup": f"{g.home_team} x {g.away_team}",
                "status": g.status,
                "score": f"{g.home_score}-{g.away_score}" if g.home_score is not None else None,
                "goals": (g.home_score or 0) + (g.away_score or 0),
                "scorers": g.scorers,
                "scorers_count": len(game_scorer_names(g)),
                "scorers_complete": world_cup_scorers_complete(g),
                "scorers_final": bool(g.scorers_final),
                "scorers_confirmed": bool(g.scorers_confirmed),
                "scorers_confirmations": g.scorers_confirmations or 0,
                "confirmation_sources": g.confirmation_sources,
                "end_source": g.end_source,
                "halftime": bool(g.halftime),
                "reconfirmed": bool(g.reconfirmed),
                "polls": {
                    "gratuito": game_poll_count(db, g.id, "gratis"),
                    "api_football": game_poll_count(db, g.id, "af"),
                    "thesportsdb": game_poll_count(db, g.id, "tsd"),
                    "ia": game_poll_count(db, g.id, "ia"),
                },
                "goal_flow": (
                    lambda p: {
                        "score": p.get("score"),
                        "stage": p.get("stage"),
                    }
                )(get_goal_pipeline(db, g))
                if g.status == "live"
                else None,
                "has_fixture_id": g.api_fixture_id is not None,
                "predictions": len(g.predictions),
            }
            for g in db.query(models.WorldCupGame)
            .filter(models.WorldCupGame.status.in_(("live", "finished")))
            .order_by(models.WorldCupGame.kickoff_at.desc())
            .all()
        ],
    }


@app.post("/api/world-cup/games/{game_id}/prediction")
def submit_world_cup_prediction(
    game_id: int,
    request: WorldCupPredictionRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    game = db.query(models.WorldCupGame).filter(models.WorldCupGame.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo do bolão não encontrado")
    if not is_bettable_world_cup_game(game):
        raise HTTPException(status_code=400, detail="Este jogo ainda não tem seleções definidas para palpite")
    if world_cup_game_lock_passed(game):
        raise HTTPException(status_code=400, detail="Palpites fecham 1 hora antes do jogo e este já está fechado")

    prediction = (
        db.query(models.WorldCupPrediction)
        .filter_by(user_id=user.id, game_id=game_id)
        .first()
    )
    if not prediction:
        prediction = models.WorldCupPrediction(user_id=user.id, game_id=game_id, created_at=datetime.utcnow())
        db.add(prediction)

    scorer_guess = re.sub(r"\s+", " ", request.scorer_guess or "").strip()[:80]
    prediction.home_score = clamp_prediction_score(request.home_score)
    prediction.away_score = clamp_prediction_score(request.away_score)
    prediction.scorer_guess = scorer_guess or None
    prediction.scorer_hit = False
    prediction.points = 0
    prediction.status = "pending"
    prediction.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(game)
    return world_cup_game_response(game, user)


@app.post("/api/world-cup/sanitize-logs/all")
def sanitize_all_world_cup_game_logs(
    before_match_number: int | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode sanitizar logs do jogo")

    results = sanitize_all_finished_timelines(db, before_match_number=before_match_number)
    db.commit()
    return {"ok": True, "count": len(results), "games": results}


@app.post("/api/world-cup/games/{game_id}/sanitize-logs")
def sanitize_world_cup_game_logs(
    game_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode sanitizar logs do jogo")

    game = db.query(models.WorldCupGame).filter(models.WorldCupGame.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo do bolão não encontrado")

    events = rebuild_clean_game_timeline(db, game)
    db.commit()
    return {
        "ok": True,
        "match_number": game.match_number,
        "matchup": f"{game.home_team} x {game.away_team}",
        "events": len(events),
        "polls": {
            "gratuito": game_poll_count(db, game.id, "gratis"),
            "api_football": game_poll_count(db, game.id, "af"),
            "thesportsdb": game_poll_count(db, game.id, "tsd"),
            "ia": game_poll_count(db, game.id, "ia"),
        },
    }


@app.post("/api/world-cup/games/{game_id}/result")
def set_world_cup_game_result(
    game_id: int,
    request: WorldCupGameResultRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode lançar resultados do bolão")

    game = db.query(models.WorldCupGame).filter(models.WorldCupGame.id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Jogo do bolão não encontrado")

    result_status = (request.status or "finished").strip().lower()
    if result_status not in WORLD_CUP_GAME_STATUSES:
        raise HTTPException(status_code=400, detail="Status do jogo inválido")

    game.home_score = clamp_prediction_score(request.home_score)
    game.away_score = clamp_prediction_score(request.away_score)
    game.status = result_status
    if request.scorers is not None:
        game.scorers = re.sub(r"\s+", " ", request.scorers).strip()[:500] or None
    db.flush()
    score_world_cup_game(game)
    db.commit()
    db.refresh(game)
    return {
        "game": world_cup_game_response(game, user),
        "leaderboard": world_cup_leaderboard_response(db),
    }


@app.post("/api/world-cup/champion-pick")
def submit_world_cup_champion_pick(
    request: WorldCupChampionPickRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if world_cup_champion_locked(db):
        raise HTTPException(status_code=400, detail="Os palpites de campeão já estão fechados")

    team = re.sub(r"\s+", " ", request.team or "").strip()[:80]
    if not team:
        raise HTTPException(status_code=400, detail="Informe a seleção campeã")

    pick = db.query(models.WorldCupChampionPick).filter_by(user_id=user.id).first()
    if pick:
        raise HTTPException(status_code=400, detail="Palpite de campeão já registrado e não pode ser alterado")

    pick = models.WorldCupChampionPick(user_id=user.id, created_at=datetime.utcnow())
    db.add(pick)
    pick.team = team
    pick.points = 0
    pick.status = "pending"
    pick.updated_at = datetime.utcnow()
    db.commit()
    return world_cup_champion_response(db, user)


@app.post("/api/world-cup/champion")
def announce_world_cup_champion(
    request: WorldCupChampionAnnounceRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode definir o campeão da Copa")

    team = re.sub(r"\s+", " ", request.team or "").strip()[:80]
    if not team:
        raise HTTPException(status_code=400, detail="Informe a seleção campeã")

    set_app_setting(db, "world_cup_champion", team)
    picks = db.query(models.WorldCupChampionPick).all()
    for pick in picks:
        correct = normalize_scorer_name(pick.team) == normalize_scorer_name(team)
        pick.points = WORLD_CUP_POINTS_CHAMPION if correct else 0
        pick.status = "scored"
        pick.updated_at = datetime.utcnow()
    db.commit()
    return {
        "champion": world_cup_champion_response(db, user),
        "leaderboard": world_cup_leaderboard_response(db),
    }


@app.get("/api/world-cup/leaderboard")
def world_cup_leaderboard(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    return {"leaderboard": world_cup_leaderboard_response(db)}


@app.get("/api/feed")
def feed(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    posts = (
        db.query(models.Post)
        .options(
            joinedload(models.Post.user)
            .subqueryload(models.User.posts)
            .subqueryload(models.Post.likes),
            joinedload(models.Post.user).subqueryload(models.User.rsvps),
            joinedload(models.Post.user).subqueryload(models.User.comments),
            subqueryload(models.Post.likes),
            subqueryload(models.Post.comments).joinedload(models.Comment.user),
            joinedload(models.Post.match),
        )
        .order_by(models.Post.created_at.desc())
        .all()
    )
    return {"posts": [post_response(post, user) for post in posts]}


@app.post("/api/posts")
def create_post(
    request: PostCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not request.description.strip():
        raise HTTPException(status_code=400, detail="Escreva uma legenda para o post")

    if request.match_id:
        match = db.query(models.Match).filter(models.Match.id == request.match_id).first()
        if not match:
            raise HTTPException(status_code=404, detail="Evento não encontrado")

    image_url = validate_url(request.image_url)
    claimed_goals = max(0, min(20, request.goals_scored or 0))
    if claimed_goals > 0 and not request.match_id:
        raise HTTPException(status_code=400, detail="Selecione o evento para solicitar validação dos gols")

    goal_status = "none"
    reviewed_by_id = None
    reviewed_at = None
    if claimed_goals > 0:
        goal_status = "approved" if is_admin_user(user) else "pending"
        if goal_status == "approved":
            reviewed_by_id = user.id
            reviewed_at = datetime.utcnow()

    post = models.Post(
        user_id=user.id,
        match_id=request.match_id,
        title=request.title,
        description=request.description,
        image_url=image_url,
        goals_scored=claimed_goals,
        goal_status=goal_status,
        goal_reviewed_by_id=reviewed_by_id,
        goal_reviewed_at=reviewed_at,
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return post_response(post, user)


@app.post("/api/admin/posts/{post_id}/goals")
def review_post_goals(
    post_id: int,
    request: GoalReviewRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode aprovar gols")

    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")
    if (post.goals_scored or 0) <= 0:
        raise HTTPException(status_code=400, detail="Esse post não possui solicitação de gol")

    review_status = request.status.strip().lower()
    if review_status not in ("approved", "rejected"):
        raise HTTPException(status_code=400, detail="Status de gol inválido")

    post.goal_status = review_status
    post.goal_reviewed_by_id = user.id
    post.goal_reviewed_at = datetime.utcnow()
    db.commit()
    db.refresh(post)
    return post_response(post, user)


@app.post("/api/posts/{post_id}/like")
def toggle_like(
    post_id: int,
    request: ReactionRequest | None = None,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    reaction_type = (request.reaction_type if request else "torcida").strip().lower()
    if reaction_type not in SUPPORTED_REACTIONS:
        raise HTTPException(status_code=400, detail="Reação inválida")

    like = db.query(models.Like).filter_by(post_id=post_id, user_id=user.id).first()
    if like and (like.reaction_type or "torcida") == reaction_type:
        db.delete(like)
        liked = False
    elif like:
        like.reaction_type = reaction_type
        liked = True
    else:
        db.add(models.Like(post_id=post_id, user_id=user.id, reaction_type=reaction_type))
        liked = True

    db.commit()
    db.refresh(post)
    return {"liked": liked, "post": post_response(post, user)}


@app.post("/api/posts/{post_id}/comments")
def add_comment(
    post_id: int,
    request: CommentCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    post = db.query(models.Post).filter(models.Post.id == post_id).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post não encontrado")

    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Comentário vazio")

    if request.parent_id:
        parent = (
            db.query(models.Comment)
            .filter_by(id=request.parent_id, post_id=post_id)
            .first()
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Comentário original não encontrado")

    media_type = request.media_type.strip().lower() if request.media_type else None
    media_url = validate_url(request.media_url.strip() if request.media_url else None)
    if media_type and media_type not in SUPPORTED_MEDIA_TYPES:
        raise HTTPException(status_code=400, detail="Tipo de mídia inválido")
    if media_type and not media_url:
        raise HTTPException(status_code=400, detail="Informe a URL da mídia")

    comment = models.Comment(
        post_id=post_id,
        user_id=user.id,
        parent_id=request.parent_id,
        text=request.text.strip(),
        media_url=media_url,
        media_type=media_type,
    )
    db.add(comment)
    db.commit()
    db.refresh(post)
    return post_response(post, user)


@app.get("/api/events")
def list_events(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    matches = (
        db.query(models.Match)
        .options(
            subqueryload(models.Match.rsvps)
            .joinedload(models.MatchRSVP.user)
            .subqueryload(models.User.posts)
            .subqueryload(models.Post.likes),
            subqueryload(models.Match.rsvps)
            .joinedload(models.MatchRSVP.user)
            .subqueryload(models.User.rsvps),
            subqueryload(models.Match.rsvps)
            .joinedload(models.MatchRSVP.user)
            .subqueryload(models.User.comments),
        )
        .order_by(models.Match.date.asc())
        .all()
    )
    return {"events": [match_response(match, user) for match in matches]}


@app.post("/api/events")
def create_event(
    request: EventCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode cadastrar eventos")

    title = request.title.strip()
    location = request.location.strip()
    description = request.description.strip()
    event_type = (request.event_type or "pelada").strip().lower()
    cover_url = validate_image_url(request.cover_url.strip() if request.cover_url else None)

    if not title:
        raise HTTPException(status_code=400, detail="Informe o nome do evento")
    if not location:
        raise HTTPException(status_code=400, detail="Informe o local do evento")
    if not description:
        raise HTTPException(status_code=400, detail="Informe a descrição do evento")

    match = models.Match(
        title=title,
        event_type=event_type or "pelada",
        location=location,
        date=request.date,
        description=description,
        max_players=max(2, min(request.max_players or 20, 200)),
        status="scheduled",
        cover_url=cover_url,
        created_at=datetime.utcnow(),
    )
    db.add(match)
    db.commit()
    db.refresh(match)
    return match_response(match, user)


@app.put("/api/events/{match_id}")
def update_event(
    match_id: int,
    request: EventCreateRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode editar eventos")

    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    title = request.title.strip()
    location = request.location.strip()
    description = request.description.strip()
    event_type = (request.event_type or "pelada").strip().lower()
    cover_url = validate_image_url(request.cover_url.strip() if request.cover_url else None)

    if not title:
        raise HTTPException(status_code=400, detail="Informe o nome do evento")
    if not location:
        raise HTTPException(status_code=400, detail="Informe o local do evento")
    if not description:
        raise HTTPException(status_code=400, detail="Informe a descrição do evento")

    match.title = title
    match.event_type = event_type or "pelada"
    match.location = location
    match.date = request.date
    match.description = description
    match.max_players = max(2, min(request.max_players or 20, 200))
    match.cover_url = cover_url

    db.commit()
    db.refresh(match)
    return match_response(match, user)


@app.delete("/api/events/{match_id}")
def delete_event(
    match_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode excluir eventos")

    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    db.query(models.MatchRSVP).filter(models.MatchRSVP.match_id == match_id).delete(synchronize_session=False)
    db.query(models.Post).filter(models.Post.match_id == match_id).update(
        {models.Post.match_id: None},
        synchronize_session=False,
    )
    db.delete(match)
    db.commit()
    return {"ok": True}


@app.get("/api/events/{match_id}")
def get_event(
    match_id: int,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    return match_response(match, user)


@app.get("/api/matches/next")
def get_next_match(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    match = db.query(models.Match).order_by(models.Match.date.asc()).first()
    if not match:
        raise HTTPException(status_code=404, detail="Nenhum evento cadastrado")

    return match_response(match, user)


@app.post("/api/events/{match_id}/rsvp")
@app.post("/api/matches/{match_id}/rsvp")
def rsvp_match(
    match_id: int,
    request: RSVPRequest,
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if request.status not in ["going", "not_going"]:
        raise HTTPException(status_code=400, detail="Status inválido")

    match = db.query(models.Match).filter(models.Match.id == match_id).first()
    if not match:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    rsvp = db.query(models.MatchRSVP).filter_by(user_id=user.id, match_id=match_id).first()
    if not rsvp:
        rsvp = models.MatchRSVP(user_id=user.id, match_id=match_id, status=request.status)
        db.add(rsvp)
    else:
        rsvp.status = request.status

    db.commit()
    db.refresh(match)
    return match_response(match, user)
