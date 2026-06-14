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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_CHAT_URL = os.getenv("OPENAI_CHAT_URL", "https://api.openai.com/v1/chat/completions")
API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "").strip()
API_FOOTBALL_LIVE_URL = os.getenv("API_FOOTBALL_LIVE_URL", "https://v3.football.api-sports.io/fixtures?live=all")
API_FOOTBALL_FIXTURE_URL = os.getenv("API_FOOTBALL_FIXTURE_URL", "https://v3.football.api-sports.io/fixtures")
API_FOOTBALL_LEAGUE_ID = int(os.getenv("API_FOOTBALL_LEAGUE_ID", "1"))
API_FOOTBALL_DAILY_BUDGET = int(os.getenv("API_FOOTBALL_DAILY_BUDGET", "100"))
# Reserva: para de chamar a API quando restam só N requisições do dia
API_FOOTBALL_DAILY_RESERVE = int(os.getenv("API_FOOTBALL_DAILY_RESERVE", "4"))
# Intervalo do loop: rápido quando há jogo ao vivo, lento quando não há
WORLD_CUP_LIVE_INTERVAL = max(45, int(os.getenv("WORLD_CUP_LIVE_INTERVAL_SECONDS", "75")))
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

    churrasco = min(99, 42 + barbecue * 4 + reaction_totals["churras"] * 8 + reaction_totals["bebedeira"] * 2 + matches)
    bebedeira = min(99, 38 + barbecue * 3 + reaction_totals["bebedeira"] * 9 + reaction_totals["churras"] * 4 + comments_received * 2)
    golaco = min(99, 42 + post_goals * 9 + reaction_totals["golaco"] * 8)
    resenha = min(99, 44 + len(user.posts) * 4 + comments_received * 4 + comments_made + reaction_totals["resenha"] * 7)
    midia = min(99, 40 + media_posts * 12 + media_comments * 5 + reaction_totals["midia"] * 9 + reactions_received * 2)
    torcida = min(99, 42 + reaction_totals["torcida"] * 8 + reactions_received * 2 + matches)
    overall = round((churrasco + bebedeira + golaco + resenha + midia + torcida) / 6)
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
    return changed


def fetch_football_data_results() -> list[dict[str, Any]]:
    # Fonte secundária: resultados oficiais da football-data.org (precisa de chave gratuita)
    request = urllib.request.Request(
        FOOTBALL_DATA_MATCHES_URL,
        headers={"X-Auth-Token": FOOTBALL_DATA_API_KEY, "User-Agent": "ConversysFut/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(read_capped(response).decode("utf-8"))
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
        results = fetch_football_data_results()
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
        finished_remote = item["status"] in ("FINISHED", "AWARDED") and item["home_score"] is not None and item["away_score"] is not None
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
            game.home_score = official_h
            game.away_score = official_a
            game.status = "finished"
            # placar mudou → goleadores precisam ser refinalizados pela fonte definitiva
            if scores_differ:
                game.scorers_final = False
            status["filled"] += 1
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
    if not API_FOOTBALL_KEY:
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
        rem = status.get("daily_remaining")
        if rem is not None and rem <= API_FOOTBALL_DAILY_RESERVE:
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


def api_football_get(url: str, db: Session, status: dict[str, Any]) -> dict[str, Any] | None:
    """GET na API-Football lendo a folga real de requisições dos headers.

    Atualiza o orçamento do dia pelos headers (fonte da verdade) e respeita o
    limite diário. Devolve o payload ou None (com erro em status)."""
    request = urllib.request.Request(
        url, headers={"x-apisports-key": API_FOOTBALL_KEY, "User-Agent": "ConversysFut/1.0"}
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(read_capped(response).decode("utf-8"))
            day_remaining = response.headers.get("x-ratelimit-requests-remaining")
            day_limit = response.headers.get("x-ratelimit-requests-limit")
    except Exception as exc:
        status["error"] = str(exc)[:300]
        return None
    if day_remaining is not None:
        try:
            status["daily_remaining"] = int(day_remaining)
            status["daily_limit"] = int(day_limit) if day_limit else status.get("daily_limit")
            set_app_setting(db, "api_football_daily_remaining", day_remaining)
        except ValueError:
            pass
    status["calls_made"] = status.get("calls_made", 0) + 1
    if payload.get("errors"):
        status["error"] = json.dumps(payload["errors"], ensure_ascii=False)[:300]
        return None
    return payload


def apply_api_football_live(db: Session) -> dict[str, Any]:
    """Sistema definitivo de captura ao vivo via API-Football (plano grátis).

    1) `live=all` (1 chamada) pega todos os jogos da Copa em andamento: placar
       parcial, goleadores progressivos e o fixture_id de cada um.
    2) Quando um jogo encerra, busca `fixtures?id=<id>` (1 chamada) para fixar
       os goleadores definitivos com nome completo — fecha o buraco de gols de
       última hora que o feed ao vivo perdia.
    Tudo respeitando o limite diário (lido dos headers) e um intervalo mínimo
    entre chamadas, com os goleadores sempre UNIDOS (nunca sobrescritos)."""
    status: dict[str, Any] = {
        "configured": bool(API_FOOTBALL_KEY),
        "ok": False,
        "live_games": 0,
        "scorers_updated": 0,
        "finalized": 0,
        "calls_made": 0,
        "daily_remaining": None,
        "daily_limit": API_FOOTBALL_DAILY_BUDGET,
        "skipped": None,
        "error": None,
    }
    if not API_FOOTBALL_KEY:
        return status

    cached_remaining = get_app_setting(db, "api_football_daily_remaining")
    if cached_remaining is not None:
        try:
            status["daily_remaining"] = int(cached_remaining)
        except ValueError:
            pass

    now = datetime.utcnow()
    live_window = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.kickoff_at.isnot(None))
        .filter(models.WorldCupGame.kickoff_at <= now)
        .filter(models.WorldCupGame.kickoff_at >= now - timedelta(hours=3, minutes=30))
        .filter(models.WorldCupGame.status.in_(("scheduled", "live")))
        .all()
    )
    # Jogos encerrados sem goleadores definitivos (com ou sem id ainda)
    incomplete_finished = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "finished")
        .filter(or_(models.WorldCupGame.scorers_final.is_(False), models.WorldCupGame.scorers_final.is_(None)))
        .all()
    )
    # Jogos presos em "live" mas que provavelmente já acabaram (kickoff > 2h30):
    # se as outras fontes atrasarem, a API-Football fecha pelo fixture id
    stuck_live = (
        db.query(models.WorldCupGame)
        .filter(models.WorldCupGame.status == "live")
        .filter(models.WorldCupGame.api_fixture_id.isnot(None))
        .filter(models.WorldCupGame.kickoff_at <= now - timedelta(hours=2, minutes=30))
        .all()
    )
    if not live_window and not incomplete_finished and not stuck_live:
        status["ok"] = True
        status["skipped"] = "sem jogos em andamento"
        return status

    remaining_guard = status["daily_remaining"]
    if remaining_guard is not None and remaining_guard <= API_FOOTBALL_DAILY_RESERVE:
        status["skipped"] = "folga diária de requisições no limite de reserva"
        return status

    # Descobre fixture_id dos encerrados que ainda não têm (cold-start)
    discover_api_fixture_ids(db, status)
    db.flush()
    # Agora (re)coleta os pendentes que têm id (encerrados + presos em live)
    pending_final = [g for g in incomplete_finished if g.api_fixture_id]
    pending_ids = {g.id for g in pending_final}
    pending_final += [g for g in stuck_live if g.id not in pending_ids]
    status["ok"] = True

    if live_window:
        payload = api_football_get(API_FOOTBALL_LIVE_URL, db, status)
        if payload is None:
            return status
        status["ok"] = True
        by_teams: dict[tuple[str, str], dict[str, Any]] = {}
        for item in payload.get("response", []):
            if ((item.get("league") or {}).get("id")) != API_FOOTBALL_LEAGUE_ID:
                continue
            teams = item.get("teams") or {}
            home = normalize_world_cup_team(((teams.get("home") or {}).get("name")) or "")
            away = normalize_world_cup_team(((teams.get("away") or {}).get("name")) or "")
            if home and away:
                by_teams[(normalize_scorer_name(home), normalize_scorer_name(away))] = item
        status["live_games"] = len(by_teams)

        for game in live_window:
            item = by_teams.get(
                (
                    normalize_scorer_name(normalize_world_cup_team(game.home_team)),
                    normalize_scorer_name(normalize_world_cup_team(game.away_team)),
                )
            )
            if not item:
                continue
            fixture_id = ((item.get("fixture") or {}).get("id"))
            if fixture_id and not game.api_fixture_id:
                game.api_fixture_id = int(fixture_id)
            goals = item.get("goals") or {}
            if goals.get("home") is not None and goals.get("away") is not None:
                game.home_score = int(goals["home"])
                game.away_score = int(goals["away"])
            if (game.status or "scheduled") == "scheduled":
                game.status = "live"
            merged, changed = merge_scorers(game.scorers, extract_api_football_scorers(item))
            if changed:
                game.scorers = merged
                status["scorers_updated"] += 1

    # Fixa goleadores definitivos dos jogos encerrados (1 chamada cada, com folga)
    for game in pending_final:
        rem = status["daily_remaining"]
        if rem is not None and rem <= API_FOOTBALL_DAILY_RESERVE:
            status["skipped"] = "folga diária insuficiente para finalizar goleadores"
            break
        payload = api_football_get(
            f"{API_FOOTBALL_FIXTURE_URL}?id={game.api_fixture_id}", db, status
        )
        if payload is None:
            break
        fixtures = payload.get("response") or []
        if not fixtures:
            game.scorers_final = True  # não há o que buscar
            continue
        fixture = fixtures[0]
        short = (((fixture.get("fixture") or {}).get("status") or {}).get("short")) or ""
        if short not in ("FT", "AET", "PEN", "AWD", "WO"):
            continue  # ainda não é definitivo
        # Jogo acabou de verdade: aplica placar final oficial e fecha o status
        # (resolve o jogo preso em "live" com placar parcial congelado)
        goals = fixture.get("goals") or {}
        if goals.get("home") is not None and goals.get("away") is not None:
            game.home_score = int(goals["home"])
            game.away_score = int(goals["away"])
        game.status = "finished"
        merged, changed = merge_scorers(game.scorers, extract_api_football_scorers(fixture))
        if changed:
            game.scorers = merged
            status["scorers_updated"] += 1
        status["finalized"] += 1
        # Só considera "fechado" quando os goleadores batem com o total de gols —
        # senão segue tentando no próximo ciclo (auto-heal de dado incompleto)
        if world_cup_scorers_complete(game):
            game.scorers_final = True

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
    for item in fetch_openfootball_world_cup_games():
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
    set_app_setting(db, "world_cup_last_sync", datetime.now(timezone.utc).isoformat())
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
            "live_games": live.get("live_games", 0),
            "scorers_updated": live.get("scorers_updated", 0),
            "finalized": live.get("finalized", 0),
            "api_calls": live.get("calls_made", 0),
            "api_remaining": live.get("daily_remaining"),
            "filled": secondary.get("filled", 0),
            "conflicts": len(secondary.get("conflicts", []) or []),
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


def openai_chat(system: str, user: str, max_tokens: int = 140) -> str | None:
    # Chamada enxuta à OpenAI (modelo leve) via REST; sem dependência extra.
    if not OPENAI_API_KEY:
        return None
    body = json.dumps(
        {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
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
    return {
        "last_sync": get_app_setting(db, "world_cup_last_sync"),
        "last_squad_sync": get_app_setting(db, "world_cup_last_squad_sync"),
        "games_sync": read_status("world_cup_sync_status"),
        "squad_sync": read_status("world_cup_squad_sync_status"),
        "runs": read_json("world_cup_sync_runs", []),
        "live_now": live_now,
        # Cadência atual do loop e próxima janela
        "interval_seconds": WORLD_CUP_LIVE_INTERVAL if live_now else WORLD_CUP_IDLE_INTERVAL,
        "live_interval_seconds": WORLD_CUP_LIVE_INTERVAL,
        "idle_interval_seconds": WORLD_CUP_IDLE_INTERVAL,
        "sync_interval_seconds": WORLD_CUP_LIVE_INTERVAL if live_now else WORLD_CUP_IDLE_INTERVAL,
        "sources": {
            "openfootball_url": OPENFOOTBALL_2026_CUP_URL,
            "football_data_configured": bool(FOOTBALL_DATA_API_KEY),
            "api_football_configured": bool(API_FOOTBALL_KEY),
            "api_football_daily_remaining": (
                int(get_app_setting(db, "api_football_daily_remaining"))
                if (get_app_setting(db, "api_football_daily_remaining") or "").lstrip("-").isdigit()
                else None
            ),
            "api_football_daily_limit": API_FOOTBALL_DAILY_BUDGET,
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
