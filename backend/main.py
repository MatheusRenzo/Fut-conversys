import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import inspect, or_, text
from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine, get_db
import models

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "redacted@example.com")
VERIFIED_DOMAIN = "conversys.global"
PASSWORD_ITERATIONS = 260000
TOKEN_TTL_SECONDS = 60 * 60 * 8
AUTH_SECRET = os.getenv("AUTH_SECRET") or os.getenv("SECRET_KEY") or "fut-conversys-dev-secret"
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
USERNAME_PATTERN = re.compile(r"[^a-z0-9._-]+")


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


def microsoft_authorize_url() -> str:
    config = microsoft_env()
    if not microsoft_is_configured():
        raise HTTPException(status_code=500, detail="Microsoft Auth não configurado")

    query = urllib.parse.urlencode(
        {
            "client_id": config["client_id"],
            "response_type": "code",
            "redirect_uri": config["redirect_uri"],
            "response_mode": "query",
            "scope": "openid profile email User.Read",
            "state": secrets.token_urlsafe(24),
            "prompt": "select_account",
        }
    )
    return f"https://login.microsoftonline.com/{config['tenant_id']}/oauth2/v2.0/authorize?{query}"


def request_json(url: str, data: dict[str, str] | None = None, token: str | None = None) -> dict[str, Any]:
    encoded_data = urllib.parse.urlencode(data).encode("utf-8") if data else None
    request = urllib.request.Request(url, data=encoded_data)
    if data:
        request.add_header("Content-Type", "application/x-www-form-urlencoded")
    if token:
        request.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.loads(response.read().decode("utf-8"))
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
            photo = response.read()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_origin_regex=r"http://(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+|192\.168\.\d+\.\d+):\d+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    username: str | None = None


class MicrosoftCallbackRequest(BaseModel):
    code: str
    redirect_uri: str | None = None


class PostCreateRequest(BaseModel):
    title: str | None = None
    description: str
    image_url: str | None = None
    match_id: int | None = None
    goals_scored: int | None = None


class CommentCreateRequest(BaseModel):
    text: str
    parent_id: int | None = None
    media_url: str | None = None
    media_type: str | None = None


class ReactionRequest(BaseModel):
    reaction_type: str = "torcida"


class GoalReviewRequest(BaseModel):
    status: str


class VerifiedFeatureRequest(BaseModel):
    verified_enabled: bool


class RSVPRequest(BaseModel):
    status: str


class EventCreateRequest(BaseModel):
    title: str
    event_type: str = "pelada"
    location: str
    date: datetime
    description: str
    max_players: int = 20
    cover_url: str | None = None


class ProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    title: str | None = None
    bio: str | None = None
    position: str | None = None
    favorite_team: str | None = None
    favorite_player: str | None = None
    avatar_url: str | None = None
    banner_url: str | None = None
    banner_position_x: int | None = None
    banner_position_y: int | None = None
    profile_frame: str | None = None
    cosmetic_tier: str | None = None
    animated_banner: bool | None = None
    profile_effect: str | None = None
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
        "avatar_url": user.avatar_url,
        "banner_url": user.banner_url,
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
        user = models.User(username=username, password_hash=hash_password("admin123"))
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
def microsoft_start():
    return RedirectResponse(microsoft_authorize_url())


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
            "redirect_uri": request.redirect_uri or config["redirect_uri"],
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
        setattr(user, field, value)

    if not has_verified_features(user):
        clear_verified_features(user)
    db.commit()
    db.refresh(user)
    return {
        **user_summary(user),
        "stats": player_stats(user),
    }


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
def get_user_profile(user_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")

    return {
        **user_summary(user),
        "stats": player_stats(user),
        "posts": [
            post_response(post)
            for post in sorted(user.posts, key=lambda item: item.created_at, reverse=True)
        ],
    }


@app.get("/api/leaderboard")
def leaderboard(db: Session = Depends(get_db)):
    users = db.query(models.User).all()
    return {
        "top_scorers": [
            {**user_summary(user), "score": approved_goals_for_user(user)}
            for user in sorted(users, key=approved_goals_for_user, reverse=True)[:5]
        ],
        "top_barbecue": [
            {**user_summary(user), "score": user.barbecue_score or 0}
            for user in sorted(users, key=lambda item: item.barbecue_score or 0, reverse=True)[:5]
        ],
    }


@app.get("/api/feed")
def feed(
    db: Session = Depends(get_db),
    user: models.User = Depends(get_current_user),
):
    posts = db.query(models.Post).order_by(models.Post.created_at.desc()).all()
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
        image_url=request.image_url,
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
    media_url = request.media_url.strip() if request.media_url else None
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
    matches = db.query(models.Match).order_by(models.Match.date.asc()).all()
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
    cover_url = request.cover_url.strip() if request.cover_url else None

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
