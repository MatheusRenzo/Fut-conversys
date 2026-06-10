"""Dados de demonstração para ranking do bolão e artilharia das peladas.

Uso:
  python seed_demo_rankings.py          # popula
  python seed_demo_rankings.py --clear  # remove só o que este script criou

Marcador: app_settings.demo_rankings_seed = "1"
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime

from database import SessionLocal
from main import hash_password, score_world_cup_game
from models import Post, User, WorldCupChampionPick, WorldCupGame, WorldCupPrediction
from main import get_app_setting, set_app_setting

DEMO_FLAG = "demo_rankings_seed"
DEMO_EMAILS = (
    "redacted@example.com",
    "redacted@example.com",
    "redacted@example.com",
)

FINISHED_GAMES = (
    (1, 2, 1, "Lozano, Zwane"),
    (2, 1, 2, "Son Heung-min, Patrik Schick"),
    (7, 1, 1, "Jonathan David, Dzeko"),
    (13, 3, 0, "Vini Jr, Rodrygo, Rafinha"),
    (19, 2, 1, "Pulisic, Balde"),
)

PREDICTIONS = (
    # game_id, email, home, away, scorer_guess
    (1, "redacted@example.com", 2, 1, "Lozano"),
    (1, "redacted@example.com", 1, 1, "Lozano"),
    (1, "redacted@example.com", 2, 0, "Lozano"),
    (1, "redacted@example.com", 0, 1, "Zwane"),
    (1, "redacted@example.com", 1, 2, None),
    (2, "redacted@example.com", 1, 2, "Patrik Schick"),
    (2, "redacted@example.com", 0, 2, "Patrik Schick"),
    (2, "redacted@example.com", 1, 2, "Son Heung-min"),
    (2, "redacted@example.com", 2, 2, None),
    (2, "redacted@example.com", 1, 2, "Patrik Schick"),
    (7, "redacted@example.com", 1, 1, "Jonathan David"),
    (7, "redacted@example.com", 0, 0, None),
    (7, "redacted@example.com", 2, 1, "Dzeko"),
    (7, "redacted@example.com", 1, 1, "Jonathan David"),
    (7, "redacted@example.com", 1, 1, "Jonathan David"),
    (13, "redacted@example.com", 3, 0, "Vini Jr"),
    (13, "redacted@example.com", 2, 0, "Rodrygo"),
    (13, "redacted@example.com", 3, 0, "Vini Jr"),
    (13, "redacted@example.com", 2, 1, None),
    (13, "redacted@example.com", 3, 1, "Vini Jr"),
    (19, "redacted@example.com", 2, 1, "Pulisic"),
    (19, "redacted@example.com", 1, 1, "Balde"),
    (19, "redacted@example.com", 2, 0, "Pulisic"),
    (19, "redacted@example.com", 3, 0, None),
    (19, "redacted@example.com", 2, 1, "Pulisic"),
)

CHAMPION_PICKS = (
    ("redacted@example.com", "Brazil"),
    ("redacted@example.com", "Argentina"),
    ("redacted@example.com", "France"),
    ("redacted@example.com", "Spain"),
    ("redacted@example.com", "Brazil"),
)

PElADA_GOALS = (
    ("redacted@example.com", 5),
    ("redacted@example.com", 3),
    ("redacted@example.com", 7),
    ("redacted@example.com", 2),
    ("redacted@example.com", 4),
)


def ensure_demo_users(db) -> dict[str, User]:
    users: dict[str, User] = {}
    seed = [
        ("demo.ana", "Ana Demo", "redacted@example.com"),
        ("demo.bruno", "Bruno Demo", "redacted@example.com"),
        ("demo.carla", "Carla Demo", "redacted@example.com"),
    ]
    password_hash = hash_password("demo123456")
    for username, name, email in seed:
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                username=username,
                email=email,
                password_hash=password_hash,
                name=name,
                position="Atacante",
                verified_domain=True,
                verified_enabled=False,
                provider="local",
                created_at=datetime.utcnow(),
            )
            db.add(user)
            db.flush()
        users[email] = user
    for user in db.query(User).all():
        if user.email:
            users[user.email] = user
    return users


def seed(db) -> None:
    if get_app_setting(db, DEMO_FLAG) == "1":
        print("Demo já aplicado. Use --clear antes de rodar de novo.")
        return

    users = ensure_demo_users(db)

    for game_id, home_score, away_score, scorers in FINISHED_GAMES:
        game = db.query(WorldCupGame).filter(WorldCupGame.id == game_id).first()
        if not game:
            continue
        game.home_score = home_score
        game.away_score = away_score
        game.scorers = scorers
        game.status = "finished"

    db.flush()

    for game_id, email, home, away, scorer in PREDICTIONS:
        user = users.get(email)
        if not user:
            continue
        existing = (
            db.query(WorldCupPrediction)
            .filter_by(user_id=user.id, game_id=game_id)
            .first()
        )
        if existing:
            prediction = existing
        else:
            prediction = WorldCupPrediction(
                user_id=user.id,
                game_id=game_id,
                created_at=datetime.utcnow(),
            )
            db.add(prediction)
        prediction.home_score = home
        prediction.away_score = away
        prediction.scorer_guess = scorer
        prediction.scorer_hit = False
        prediction.points = 0
        prediction.status = "pending"
        prediction.updated_at = datetime.utcnow()

    db.flush()

    for game_id, *_ in FINISHED_GAMES:
        game = db.query(WorldCupGame).filter(WorldCupGame.id == game_id).first()
        if game:
            score_world_cup_game(game)

    for email, team in CHAMPION_PICKS:
        user = users.get(email)
        if not user:
            continue
        pick = db.query(WorldCupChampionPick).filter_by(user_id=user.id).first()
        if not pick:
            pick = WorldCupChampionPick(user_id=user.id, created_at=datetime.utcnow())
            db.add(pick)
        pick.team = team
        pick.points = 0
        pick.status = "pending"
        pick.updated_at = datetime.utcnow()

    for email, goals in PElADA_GOALS:
        user = users.get(email)
        if not user:
            continue
        db.add(
            Post(
                user_id=user.id,
                title="[DEMO] Gols da pelada",
                description="Post de demonstração para ranking de artilharia — pode apagar depois.",
                goals_scored=goals,
                goal_status="approved",
                goal_reviewed_at=datetime.utcnow(),
                created_at=datetime.utcnow(),
            )
        )

    set_app_setting(db, DEMO_FLAG, "1")
    db.commit()
    print("Demo aplicado: bolão (5 jogos finalizados) + artilharia das peladas.")


def clear(db) -> None:
    if get_app_setting(db, DEMO_FLAG) != "1":
        print("Nenhum demo marcado no banco.")
        return

    demo_users = db.query(User).filter(User.email.in_(DEMO_EMAILS)).all()
    demo_user_ids = [user.id for user in demo_users]

    for game_id, *_ in FINISHED_GAMES:
        game = db.query(WorldCupGame).filter(WorldCupGame.id == game_id).first()
        if game:
            game.home_score = None
            game.away_score = None
            game.scorers = None
            game.status = "scheduled"

    if demo_user_ids:
        db.query(WorldCupPrediction).filter(WorldCupPrediction.user_id.in_(demo_user_ids)).delete(
            synchronize_session=False
        )
        db.query(WorldCupChampionPick).filter(WorldCupChampionPick.user_id.in_(demo_user_ids)).delete(
            synchronize_session=False
        )
        for user in demo_users:
            db.delete(user)

    db.query(Post).filter(Post.title == "[DEMO] Gols da pelada").delete(synchronize_session=False)

    for game_id, *_ in FINISHED_GAMES:
        game = db.query(WorldCupGame).filter(WorldCupGame.id == game_id).first()
        if game:
            db.query(WorldCupPrediction).filter(WorldCupPrediction.game_id == game.id).delete(
                synchronize_session=False
            )

    set_app_setting(db, DEMO_FLAG, "0")
    db.commit()
    print("Demo removido.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clear", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        if args.clear:
            clear(db)
        else:
            seed(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
