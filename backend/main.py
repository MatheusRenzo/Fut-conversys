import base64
import fcntl
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time as time_module
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
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
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "redacted@example.com")
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
API_FOOTBALL_DAILY_RESERVE = int(os.getenv("API_FOOTBALL_DAILY_RESERVE", "2"))
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
# ~4 chamadas (busca dia ±1 + timeline), então 6 jogos/ciclo = ~24 < 30. Seguro.
THESPORTSDB_CYCLE_LIMIT = max(1, int(os.getenv("THESPORTSDB_CYCLE_LIMIT", "6")))
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
# Intervalo do loop: rápido quando há jogo ao vivo, lento quando não há. 30s deixa
# o PLACAR/GOL bem ao vivo (football-data 10/min aguenta de sobra: ~2/min) e faz o
# gatilho de goleador disparar logo após o gol; a cota paga é protegida à parte.
WORLD_CUP_LIVE_INTERVAL = max(25, int(os.getenv("WORLD_CUP_LIVE_INTERVAL_SECONDS", "30")))
WORLD_CUP_IDLE_INTERVAL = max(120, int(os.getenv("WORLD_CUP_SYNC_INTERVAL_SECONDS", "600")))
# Schedule (openfootball/football-data) revalida no máximo a cada N segundos
WORLD_CUP_SCHEDULE_MIN_GAP = max(120, int(os.getenv("WORLD_CUP_SCHEDULE_MIN_GAP", "300")))
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
            "end_source": "VARCHAR",
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


def user_summary(user: models.User) -> dict[str, Any]:
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
        "player_rating": player_traits(user)["overall"],
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


def world_cup_prediction_points(
    prediction_home: int,
    prediction_away: int,
    game_home: int | None,
    game_away: int | None,
) -> int:
    if game_home is None or game_away is None:
        return 0
    if prediction_home == game_home and prediction_away == game_away:
        return WORLD_CUP_POINTS_EXACT
    if game_outcome(prediction_home, prediction_away) == game_outcome(game_home, game_away):
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
        "home_score": game.home_score,
        "away_score": game.away_score,
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


def world_cup_leaderboard_response(db: Session) -> list[dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    predictions = (
        db.query(models.WorldCupPrediction)
        .options(
            joinedload(models.WorldCupPrediction.user)
            .subqueryload(models.User.posts)
            .subqueryload(models.Post.likes),
            joinedload(models.WorldCupPrediction.user)
            .subqueryload(models.User.rsvps),
            joinedload(models.WorldCupPrediction.user)
            .subqueryload(models.User.comments),
            joinedload(models.WorldCupPrediction.game),
        )
        .all()
    )
    def empty_row(user: models.User) -> dict[str, Any]:
        return {
            "user": user_summary(user),
            "points": 0,
            "predictions": 0,
            "scored_predictions": 0,
            "exact_scores": 0,
            "outcome_hits": 0,
            "scorer_hits": 0,
            "champion_team": None,
            "champion_points": 0,
        }

    for prediction in predictions:
        if prediction.user_id not in rows:
            rows[prediction.user_id] = empty_row(prediction.user)

        row = rows[prediction.user_id]
        row["points"] += prediction.points or 0
        row["predictions"] += 1
        if prediction.status == "scored":
            row["scored_predictions"] += 1
            game = prediction.game
            if game and game.home_score is not None and game.away_score is not None:
                if prediction.home_score == game.home_score and prediction.away_score == game.away_score:
                    row["exact_scores"] += 1
                if game_outcome(prediction.home_score or 0, prediction.away_score or 0) == game_outcome(
                    game.home_score, game.away_score
                ):
                    row["outcome_hits"] += 1
            if prediction.scorer_hit:
                row["scorer_hits"] += 1

    champion_picks = (
        db.query(models.WorldCupChampionPick)
        .options(joinedload(models.WorldCupChampionPick.user))
        .all()
    )
    # Palpite de campeã é público no ranking (é único e não pode ser trocado)
    for pick in champion_picks:
        if pick.user_id not in rows:
            rows[pick.user_id] = empty_row(pick.user)
        row = rows[pick.user_id]
        row["champion_team"] = pick.team
        row["champion_points"] = pick.points or 0
        row["points"] += pick.points or 0

    # Só entra no ranking quem palpitou em jogos ou já pontuou; palpite de campeão sozinho não lista
    leaderboard = sorted(
        (row for row in rows.values() if row["predictions"] > 0 or row["points"] > 0),
        key=lambda item: (item["points"], item["exact_scores"], item["outcome_hits"], item["scorer_hits"], item["predictions"]),
        reverse=True,
    )
    for index, row in enumerate(leaderboard, start=1):
        row["rank"] = index

    # Movimentação determinística: compara o ranking ATUAL com o ranking SEM o
    # último jogo encerrado. Verde = subiu por causa do último resultado.
    last_game = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .order_by(models.WorldCupGame.kickoff_at.desc())
        .first()
    )
    last_game_points: dict[int, int] = {}
    if last_game:
        for pred in last_game.predictions:
            last_game_points[pred.user_id] = last_game_points.get(pred.user_id, 0) + (pred.points or 0)
    before = sorted(
        leaderboard,
        key=lambda item: (
            item["points"] - last_game_points.get(item["user"]["id"], 0),
            item["exact_scores"],
            item["outcome_hits"],
            item["scorer_hits"],
            item["predictions"],
        ),
        reverse=True,
    )
    before_rank = {row["user"]["id"]: i for i, row in enumerate(before, start=1)}
    for row in leaderboard:
        row["movement"] = before_rank.get(row["user"]["id"], row["rank"]) - row["rank"]

    return leaderboard[:30]


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
    cleaned = re.sub(r"\ba\.e\.t\.?", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpen\.?\s+\d{1,2}-\d{1,2}", " ", cleaned, flags=re.IGNORECASE)
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
    row = db.query(models.AppSetting).filter(models.AppSetting.key == key).first()
    if not row:
        row = models.AppSetting(key=key)
        db.add(row)
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


def log_game_event(db: Session, game: models.WorldCupGame, action: str) -> None:
    """Registra um evento do jogo (gol, encerramento, confirmação) num log rolante
    pro painel: 'o que fez, em qual jogo, quando'."""
    raw = get_app_setting(db, "wc_game_events")
    try:
        events = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        events = []
    events.insert(0, {
        "at": datetime.now(timezone.utc).isoformat(),
        "match_number": game.match_number,
        "game": f"{game.home_team} x {game.away_team}",
        "action": action,
    })
    set_app_setting(db, "wc_game_events", json.dumps(events[:80], ensure_ascii=False))


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
        log_game_event(db, game, "🟢 começou — palpites fechados, sistema ao vivo")
    return changed


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
            game.end_source = "football-data"  # confirmação oficial de FIM
            # placar mudou → goleadores precisam ser refinalizados pela fonte definitiva
            if scores_differ:
                game.scorers_final = False
            status["filled"] += 1
            if not was_finished:
                log_game_event(db, game, f"🏁 encerrado {official_h}-{official_a} (football-data, oficial)")
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


def api_football_key_remaining(db: Session, index: int) -> int | None:
    """Cota restante HOJE (UTC) de uma chave; None se desconhecida (assume cheia)."""
    raw = get_app_setting(db, f"api_football_remaining_{index}")
    if raw and ":" in raw:
        day_part, _, val = raw.partition(":")
        if day_part == f"{datetime.utcnow():%Y%m%d}" and val.lstrip("-").isdigit():
            return int(val)
    return None


def fetch_thesportsdb_scorers(game: models.WorldCupGame, db: Session | None = None) -> list[str] | None:
    """Goleadores do jogo pela 2ª fonte (TheSportsDB, grátis) para CONFIRMAR.

    Casa o jogo pela data + times (ou pelo idAPIfootball) e lê a timeline de
    gols. Devolve a lista de nomes ou None se não achou."""
    if not game.kickoff_at:
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
            if db is not None:
                bump_daily_counter(db, "thesportsdb")
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
        if db is not None:
            bump_daily_counter(db, "thesportsdb")
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
        effective = API_FOOTBALL_DAILY_BUDGET if rem is None else rem
        if effective <= API_FOOTBALL_DAILY_RESERVE:
            continue
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
    """Captura de goleadores ENXUTA: a fonte limitada (API-Football) é usada só
    DUAS vezes por jogo — uma no meio (≈intervalo) e uma quando ele encerra
    oficialmente (definitiva). O placar/status ao vivo vem da football-data
    (ilimitada) a cada ciclo, então não gastamos cota com isso.

    No fim, confirmamos os goleadores na 2ª fonte grátis (TheSportsDB): se as
    duas baterem, marca confirmado; se divergirem, registra pro admin.
    A cota do dia é dividida entre os jogos do dia, com o FIM sempre garantido."""
    status: dict[str, Any] = {
        "configured": bool(API_FOOTBALL_KEYS),
        "ok": False,
        "live_games": 0,
        "mid_checks": 0,
        "finalized": 0,
        "confirmed": 0,
        "conflicts": [],
        "scorers_updated": 0,
        "calls_made": 0,
        "daily_remaining": None,
        "daily_limit": API_FOOTBALL_DAILY_BUDGET,
        "games_today": 0,
        "per_game_cap": 0,
        "live_gap_seconds": 0,
        "ai_reconciles": 0,
        "tsd_calls": 0,
        "goal_pending": False,
        "skipped": None,
        "error": None,
    }
    if not API_FOOTBALL_KEYS:
        return status
    status["daily_remaining"] = api_football_total_remaining(db)
    now = datetime.utcnow()

    # Jogos de HOJE (UTC) — pra dividir a cota igualmente entre eles
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    games_today = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at >= day_start)
        .filter(models.WorldCupGame.kickoff_at < day_start + timedelta(days=1))
        .count()
    )
    status["games_today"] = games_today
    status["reserve"] = API_FOOTBALL_DAILY_RESERVE
    # Quantos jogos do dia ainda NÃO estão finalizados (a cota flui pros que faltam)
    active_today = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at >= day_start)
        .filter(models.WorldCupGame.kickoff_at < day_start + timedelta(days=1))
        .filter(models.WorldCupGame.status != "finished")
        .count()
    )
    # RESERVA DINÂMICA: garante 1 chamada de FIM por jogo ainda ativo do dia (a
    # finalização é a que não pode faltar) + folga de descoberta. O resto é live.
    remaining = status["daily_remaining"] or 0
    finalize_reserve = min(remaining, max(API_FOOTBALL_DAILY_RESERVE, active_today + 2))
    usable = max(0, remaining - finalize_reserve)
    status["reserve"] = finalize_reserve
    # USA O MÁXIMO: divide a cota de live entre os jogos que faltam.
    per_game_cap = usable // max(1, active_today) if active_today else usable
    status["per_game_cap"] = per_game_cap
    status["active_today"] = active_today
    # Cadência do live=all: 1 chamada cobre TODOS os jogos rolando. Espalha a cota
    # de live numa janela de ~2h, com piso pra não torrar a cota (placar é grátis).
    live_calls = max(1, usable)
    live_gap = min(1800, max(API_FOOTBALL_LIVE_GAP_FLOOR, int(7200 / live_calls)))
    status["live_gap_seconds"] = live_gap

    def call(url: str) -> dict[str, Any] | None:
        if api_football_pick_key(db) is None:
            status["skipped"] = "cota no limite de reserva"
            return None
        return api_football_get(url, db, status)

    # ── FIM (prioridade): jogo encerrou → goleadores definitivos + confirmação ──
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
    if incomplete_finished or stuck_live:
        discover_api_fixture_ids(db, status)
        db.flush()
    pending = [g for g in incomplete_finished if g.api_fixture_id]
    seen = {g.id for g in pending}
    pending += [g for g in stuck_live if g.id not in seen and g.api_fixture_id]

    for game in pending:
        payload = call(f"{API_FOOTBALL_FIXTURE_URL}?id={game.api_fixture_id}")
        if payload is None:
            break
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
        game.status = "finished"
        game.end_source = "api-football"  # 1ª confirmação oficial de FIM
        squad = world_cup_game_squad(db, game)
        # Fonte 1 (paga, definitiva): goleadores do fixture oficial
        api_names = extract_api_football_scorers(fixture)
        # Fonte 2 (grátis, 30/min → teto por ciclo): TheSportsDB
        tsd_names = []
        if status["tsd_calls"] < THESPORTSDB_CYCLE_LIMIT:
            status["tsd_calls"] += 1
            tsd_names = fetch_thesportsdb_scorers(game, db) or []
        # Fonte 3 (backup): o que o openfootball/feed já tinha
        of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
        # A IA SEMPRE entra: recebe as 3 fontes + o ELENCO real e devolve o conjunto
        # definitivo (cacheado por assinatura — só re-chama quando as fontes mudam).
        reconciled = ai_reconcile_scorers(
            db, game,
            {"API-Football": api_names, "TheSportsDB": tsd_names, "openfootball": of_names},
            status, squad=squad,
        )
        base = reconciled if reconciled else merge_scorers(game.scorers, api_names + tsd_names)[0].split(", ")
        base = [n for n in (s.strip() for s in base) if n]
        # Encaixa no nome EXATO do elenco salvo (à prova de bala pro casamento com o
        # palpite, que vem do dropdown do elenco). 'unmatched' = revisar.
        official, unmatched = snap_scorers_to_squad(base, squad)
        new_scorers = ", ".join(official)[:500]
        if new_scorers != (game.scorers or ""):
            game.scorers = new_scorers
            status["scorers_updated"] += 1
        status["finalized"] += 1
        # CONTAGEM DE CONFIRMAÇÕES: só fontes INDEPENDENTES de verdade (a paga e a
        # grátis). openfootball não conta aqui pra não inflar (pode espelhar o que a
        # própria API já gravou). 2 = paga e grátis bateram.
        confirms = sum(1 for src in (api_names, tsd_names) if scorer_sets_agree(src, official))
        game.scorers_confirmations = confirms
        # 2+ fontes concordando, OU dado completo já reconciliado pela IA → confirmado
        if confirms >= 2 or (reconciled and world_cup_scorers_complete(game)):
            game.scorers_confirmed = True
            status["confirmed"] += 1
        if unmatched:
            status["conflicts"].append(
                {"game": f"{game.home_team} x {game.away_team}", "fora_do_elenco": unmatched,
                 "api": api_names, "tsd": tsd_names}
            )
        if world_cup_scorers_complete(game):
            game.scorers_final = True
        conf_txt = f" · ✓✓ {confirms} fonte(s)" if game.scorers_confirmed else ""
        gol_txt = f" · goleadores: {game.scorers}" if game.scorers else " · sem goleador ainda"
        log_game_event(db, game, f"🏁 encerrado {game.home_score}-{game.away_score} (API-Football){conf_txt}{gol_txt}")

    # ── REDE DE SEGURANÇA DE FIM: jogo "ao vivo" há tempo demais e nenhuma fonte
    # confirmou o fim → encerra sozinho (nenhum jogo fica aberto por horas). Mantém
    # o melhor placar e segue tentando confirmar goleadores nos próximos ciclos. ──
    for game in stuck_live:
        if game.status == "live" and game.kickoff_at and game.kickoff_at <= now - WORLD_CUP_FORCE_FINISH_AFTER:
            game.status = "finished"
            if not game.end_source:
                game.end_source = "auto:tempo"
                log_game_event(db, game, f"⏱ encerrado por tempo {game.home_score}-{game.away_score} (sem confirmação de fonte)")
            status["finalized"] += 1

    # ── AO VIVO: live=all na cadência do orçamento (usa a cota do jogo ao máximo) ──
    # 1 chamada cobre TODOS os jogos rolando. Espaçada pela cota/dia ÷ jogos.
    live_now_games = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "live")
        .filter(models.WorldCupGame.kickoff_at <= now - timedelta(minutes=2))
        .all()
    )
    # GATILHO POR GOL: um jogo ao vivo tem GOL NOVO sem goleador capturado se o
    # placar (que a football-data já trouxe de graça) mudou desde a última busca
    # paga e os goleadores ainda não cobrem os gols. Só isso dispara a cota.
    def has_new_goal(g: models.WorldCupGame) -> bool:
        if world_cup_scorers_complete(g):
            return False
        last_polled = get_app_setting(db, f"wc_live_polled_{g.id}")
        current = f"{g.home_score or 0}-{g.away_score or 0}"
        return last_polled != current  # placar mudou desde a última chamada paga

    goal_pending = any(has_new_goal(g) for g in live_now_games)
    status["goal_pending"] = goal_pending
    # Reação rápida (60s) quando falta o nome de um gol; senão só um poll de
    # segurança espaçado (600s) — na maior parte do tempo nem gasta cota.
    effective_gap = API_FOOTBALL_GOAL_GAP if goal_pending else max(live_gap, API_FOOTBALL_SAFETY_GAP)
    status["live_gap_seconds"] = effective_gap
    last_live_raw = get_app_setting(db, "api_football_last_live_at")
    gap_ok = True
    if last_live_raw:
        try:
            t = datetime.fromisoformat(last_live_raw)
            if t.tzinfo:
                t = t.astimezone(timezone.utc).replace(tzinfo=None)
            gap_ok = (now - t).total_seconds() >= effective_gap
        except ValueError:
            gap_ok = True
    # O live só roda se ainda houver cota ACIMA da reserva de fim — assim o
    # finalize (que roda primeiro, com prioridade) sempre tem call garantida.
    live_budget_ok = api_football_total_remaining(db) > finalize_reserve
    if live_now_games and gap_ok and live_budget_ok and api_football_pick_key(db) is not None:
        payload = call(API_FOOTBALL_LIVE_URL)
        if payload:
            # só conta o gap a partir de uma chamada bem-sucedida (se foi
            # estrangulada por minuto/cota, tenta de novo no próximo ciclo)
            set_app_setting(db, "api_football_last_live_at", datetime.now(timezone.utc).isoformat())
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
            for game in live_now_games:
                item = by_teams.get((
                    normalize_scorer_name(normalize_world_cup_team(game.home_team)),
                    normalize_scorer_name(normalize_world_cup_team(game.away_team)),
                ))
                if not item:
                    continue
                fid = ((item.get("fixture") or {}).get("id"))
                if fid and not game.api_fixture_id:
                    game.api_fixture_id = int(fid)
                goals = item.get("goals") or {}
                if goals.get("home") is not None and goals.get("away") is not None:
                    game.home_score = int(goals["home"])
                    game.away_score = int(goals["away"])
                live_scorers = extract_api_football_scorers(item)
                if live_scorers:
                    # já normaliza o nome ao vivo pro nome oficial do elenco
                    squad = world_cup_game_squad(db, game)
                    union = merge_scorers(game.scorers, live_scorers)[0].split(", ")
                    official, _ = snap_scorers_to_squad([n for n in (s.strip() for s in union) if n], squad)
                    new_s = ", ".join(official)[:500]
                    if new_s != (game.scorers or ""):
                        game.scorers = new_s
                        status["scorers_updated"] += 1
                        log_game_event(
                            db, game,
                            f"⚽ AO VIVO {game.home_score}-{game.away_score} · goleadores: {new_s}",
                        )
                # marca que JÁ buscamos o nome neste placar — não re-dispara cota no
                # mesmo gol (ex.: gol contra que nunca terá goleador nomeado)
                set_app_setting(db, f"wc_live_polled_{game.id}", f"{game.home_score or 0}-{game.away_score or 0}")
                status["mid_checks"] += 1

    # ── Confirmação GRÁTIS (TheSportsDB) pra encerrados ainda não confirmados ──
    # Cobre jogos antigos sem fixture_id da API paga (fora da janela do plano).
    # Não gasta cota da API-Football; limitado a poucos por ciclo (30/min do free).
    to_confirm = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(or_(models.WorldCupGame.scorers_confirmed.is_(False), models.WorldCupGame.scorers_confirmed.is_(None)))
        .order_by(models.WorldCupGame.kickoff_at.desc())
        .limit(THESPORTSDB_CYCLE_LIMIT)
        .all()
    )
    for game in to_confirm:
        if status["tsd_calls"] >= THESPORTSDB_CYCLE_LIMIT:
            break  # teto por ciclo (30/min) — segue no próximo
        status["tsd_calls"] += 1
        tsd_names = fetch_thesportsdb_scorers(game, db)
        if tsd_names is None:
            continue
        squad = world_cup_game_squad(db, game)
        of_names = [n.strip() for n in re.split(r"[,;\n]", game.scorers or "") if n.strip()]
        # IA com elenco: monta o conjunto definitivo a partir da 2ª fonte + backup
        reconciled = ai_reconcile_scorers(
            db, game, {"TheSportsDB": tsd_names, "openfootball": of_names}, status, squad=squad
        )
        base = reconciled if reconciled else merge_scorers(game.scorers, tsd_names)[0].split(", ")
        base = [n for n in (s.strip() for s in base) if n]
        official, _ = snap_scorers_to_squad(base, squad)
        new_scorers = ", ".join(official)[:500]
        if new_scorers != (game.scorers or ""):
            game.scorers = new_scorers
            status["scorers_updated"] += 1
        # aqui não há fonte paga; TheSportsDB é a única confirmação independente
        confirms = 1 if scorer_sets_agree(tsd_names, official) else 0
        game.scorers_confirmations = max(game.scorers_confirmations or 0, confirms)
        if confirms >= 1 and world_cup_scorers_complete(game):
            game.scorers_confirmed = True
            status["confirmed"] += 1
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
            game.home_score = home_score
            game.away_score = away_score
            game.status = "finished"
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
            f"{game.home_team} x {game.away_team}" for game in finished_games if not game.scorers
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
) -> list[str] | None:
    """IA reconcilia os goleadores das VÁRIAS fontes num conjunto definitivo.

    As APIs trazem nomes/quantidades diferentes; o GPT decide a lista correta
    (1 nome por gol, nomes completos, sem gol contra). Recebe também o ELENCO real
    dos dois times — já conhecemos todos os jogadores — então mapeia cada gol pro
    nome oficial e nunca inventa. Cacheado por assinatura (gasta pouquíssimo).
    Devolve a lista reconciliada ou None."""
    if not OPENAI_API_KEY:
        return None
    total = (game.home_score or 0) + (game.away_score or 0)
    if total == 0:
        return []
    # assinatura inclui o elenco — se nada mudou, não chama de novo
    sig = json.dumps(
        {"src": {k: sorted(v) for k, v in sources.items()}, "squad": sorted(squad or [])},
        ensure_ascii=False,
    )
    cache_key = f"ai_scorers_{game.id}"
    cached_raw = get_app_setting(db, cache_key)
    if cached_raw:
        try:
            cached = json.loads(cached_raw)
            if cached.get("sig") == sig and isinstance(cached.get("names"), list):
                return cached["names"]
        except json.JSONDecodeError:
            pass
    fontes_txt = "; ".join(f"{name}: {', '.join(lst) if lst else '(vazio)'}" for name, lst in sources.items())
    # O elenco pode ser grande; manda um recorte enxuto pra não estourar tokens.
    squad_txt = ", ".join((squad or [])[:60])
    text = openai_chat(
        system=(
            "Você reconcilia dados de futebol de fontes diferentes. Recebe listas de goleadores "
            "de várias APIs (que podem divergir, abreviar nomes ou estar incompletas), o total de gols "
            "e o ELENCO oficial dos dois times. "
            "Devolva APENAS um array JSON com os nomes dos goleadores, 1 entrada por gol de jogador "
            "(ignore gols contra). REGRA: todo nome devolvido DEVE ser de um jogador do elenco fornecido — "
            "use exatamente a grafia do elenco (resolva abreviações/acentos pra esse nome oficial). "
            "Se uma fonte citar alguém fora do elenco, escolha o jogador do elenco mais provável. "
            "Não invente. Responda só o JSON, ex: [\"Nome Oficial A\",\"Nome Oficial B\"]."
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
        return None
    status["ai_reconciles"] = status.get("ai_reconciles", 0) + 1
    try:
        start, end = text.find("["), text.rfind("]")
        names = json.loads(text[start : end + 1]) if start >= 0 and end > start else None
    except json.JSONDecodeError:
        names = None
    if not isinstance(names, list):
        return None
    names = [re.sub(r"\s+", " ", str(n)).strip() for n in names if str(n).strip()]
    set_app_setting(db, cache_key, json.dumps({"sig": sig, "names": names}, ensure_ascii=False))
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
    partes = [
        f"{home} x {away}",
        f"{total} palpites cravados",
        f"{home_w} apostam no {home}, {away_w} no {away}, {draws} no empate",
        f"placar mais cravado: {top_score[0]} ({top_score[1]}x)",
    ]
    if top_scorer:
        partes.append(f"artilheiro favorito: {top_scorer[0]} ({top_scorer[1]} palpites)")
    text = openai_chat(
        system=(
            "Você é um narrador esportivo brasileiro animado de um bolão de Copa. "
            "Escreva UMA frase curtíssima e empolgante (pt-BR, no MÁXIMO 110 caracteres) sobre a "
            "tendência dos palpites pro próximo jogo. Direto e com energia. "
            "Não revele nomes de quem palpitou. Não invente números. Sem hashtags."
        ),
        user="Tendência dos palpites: " + "; ".join(partes) + ".",
        max_tokens=70,
        db=db,
        temperature=0.7,
    )
    if not text:
        return base
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
    # Palpite de campeão fica aberto até 1h antes da estreia do Brasil;
    # se o Brasil não estiver na tabela, vale até o fim da fase de grupos
    brazil_game = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(
            or_(
                models.WorldCupGame.home_team.in_(("Brazil", "Brasil")),
                models.WorldCupGame.away_team.in_(("Brazil", "Brasil")),
            )
        )
        .order_by(models.WorldCupGame.kickoff_at.asc())
        .first()
    )
    if brazil_game:
        return brazil_game.kickoff_at - WORLD_CUP_BET_CUTOFF
    last_group_game = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(models.WorldCupGame.stage == "group-stage")
        .order_by(models.WorldCupGame.kickoff_at.desc())
        .first()
    )
    return last_group_game.kickoff_at if last_group_game else None


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


@app.get("/api/world-cup/sync/status")
def world_cup_sync_status(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Apenas o admin pode ver o status de sincronização")

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
        "openai": {"calls": openai_calls_today(db), "daily_cap": None, "label": "Reconciliação por IA"},
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
        # Saúde por jogo (ao vivo + encerrados): o admin vê o que está rolando,
        # se encerrou, e se os goleadores já foram capturados por completo
        "games_health": [
            {
                "match_number": g.match_number,
                "matchup": f"{g.home_team} x {g.away_team}",
                "status": g.status,
                "score": f"{g.home_score}-{g.away_score}" if g.home_score is not None else None,
                "goals": (g.home_score or 0) + (g.away_score or 0),
                "scorers_count": len(game_scorer_names(g)),
                "scorers_complete": world_cup_scorers_complete(g),
                "scorers_final": bool(g.scorers_final),
                "scorers_confirmed": bool(g.scorers_confirmed),
                "scorers_confirmations": g.scorers_confirmations or 0,
                "end_source": g.end_source,
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
