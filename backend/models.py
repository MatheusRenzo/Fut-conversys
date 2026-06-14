from sqlalchemy import Boolean, Column, Index, Integer, String, ForeignKey, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True, nullable=True)
    password_hash = Column(String)
    name = Column(String)
    display_name = Column(String, nullable=True)
    title = Column(String, nullable=True)
    bio = Column(Text, nullable=True)
    position = Column(String, nullable=True)
    favorite_team = Column(String, nullable=True)
    favorite_player = Column(String, nullable=True)
    avatar_url = Column(String, nullable=True)
    banner_url = Column(String, nullable=True)
    banner_position_x = Column(Integer, default=50)
    banner_position_y = Column(Integer, default=50)
    profile_frame = Column(String, default="conversys")
    cosmetic_tier = Column(String, default="starter")
    animated_banner = Column(Boolean, default=False)
    profile_effect = Column(String, default="off")
    avatar_config = Column(Text, nullable=True)
    player_rating = Column(Integer, default=78)
    verified_domain = Column(Boolean, default=False)
    verified_enabled = Column(Boolean, default=False)
    show_verified_badge = Column(Boolean, default=True)
    is_admin = Column(Boolean, default=False)
    provider = Column(String, default="local")
    provider_subject = Column(String, nullable=True)
    tenant_id = Column(String, nullable=True)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    fouls = Column(Integer, default=0)
    barbecue_score = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    rsvps = relationship("MatchRSVP", back_populates="user", lazy="select")
    posts = relationship("Post", back_populates="user", lazy="select")
    comments = relationship("Comment", back_populates="user", lazy="select")
    likes = relationship("Like", back_populates="user", lazy="select")
    world_cup_predictions = relationship("WorldCupPrediction", back_populates="user", lazy="select")


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    event_type = Column(String, default="pelada")
    location = Column(String)
    date = Column(DateTime, index=True)
    description = Column(Text)
    max_players = Column(Integer, default=20)
    status = Column(String, default="scheduled")
    cover_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    rsvps = relationship("MatchRSVP", back_populates="match", lazy="select")
    posts = relationship("Post", back_populates="match", lazy="select")


class MatchRSVP(Base):
    __tablename__ = "match_rsvps"
    __table_args__ = (
        Index("ix_match_rsvps_user_id", "user_id"),
        Index("ix_match_rsvps_match_id", "match_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="rsvps")
    match = relationship("Match", back_populates="rsvps")


class Post(Base):
    __tablename__ = "posts"
    __table_args__ = (
        Index("ix_posts_user_id", "user_id"),
        Index("ix_posts_match_id", "match_id"),
        Index("ix_posts_created_at", "created_at"),
        Index("ix_posts_goal_status", "goal_status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    image_url = Column(String, nullable=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    goals_scored = Column(Integer, default=0)
    goal_status = Column(String, default="none")
    goal_reviewed_by_id = Column(Integer, nullable=True)
    goal_reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="posts")
    match = relationship("Match", back_populates="posts")
    comments = relationship("Comment", back_populates="post", lazy="select")
    likes = relationship("Like", back_populates="post", lazy="select")


class Comment(Base):
    __tablename__ = "comments"
    __table_args__ = (
        Index("ix_comments_post_id", "post_id"),
        Index("ix_comments_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    text = Column(Text)
    media_url = Column(String, nullable=True)
    media_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")


class Like(Base):
    __tablename__ = "likes"
    __table_args__ = (
        Index("ix_likes_post_id", "post_id"),
        Index("ix_likes_user_id", "user_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    reaction_type = Column(String, default="torcida")
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="likes")
    user = relationship("User", back_populates="likes")


class WorldCupGame(Base):
    __tablename__ = "world_cup_games"
    __table_args__ = (
        Index("ix_world_cup_games_kickoff_at", "kickoff_at"),
        Index("ix_world_cup_games_status", "status"),
    )

    id = Column(Integer, primary_key=True, index=True)
    external_id = Column(String, unique=True, nullable=True)
    match_number = Column(Integer, nullable=True)
    home_team = Column(String)
    away_team = Column(String)
    group_label = Column(String, nullable=True)
    stage = Column(String, default="group-stage")
    venue = Column(String, nullable=True)
    kickoff_at = Column(DateTime)
    status = Column(String, default="scheduled")
    home_score = Column(Integer, nullable=True)
    away_score = Column(Integer, nullable=True)
    scorers = Column(Text, nullable=True)
    source = Column(String, nullable=True)
    # id do confronto na API-Football (descoberto ao vivo) — permite buscar os
    # goleadores definitivos por id quando o jogo encerra
    api_fixture_id = Column(Integer, nullable=True)
    # marca quando os goleadores já foram fixados pela fonte definitiva
    scorers_final = Column(Boolean, default=False)
    # checagem de goleadores no meio do jogo (1ª das 2 chamadas pagas por jogo)
    api_mid_checked = Column(Boolean, default=False)
    # goleadores confirmados pela 2ª fonte (TheSportsDB) batendo com a 1ª
    scorers_confirmed = Column(Boolean, default=False)
    # quantas fontes independentes corroboram o conjunto final de goleadores
    scorers_confirmations = Column(Integer, default=0)
    # nomes das fontes que corroboraram (ex.: "API-Football, TheSportsDB")
    confirmation_sources = Column(String, nullable=True)
    # quem confirmou o FIM do jogo (football-data / api-football / auto:tempo)
    end_source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    predictions = relationship("WorldCupPrediction", back_populates="game", lazy="select")


class WorldCupPrediction(Base):
    __tablename__ = "world_cup_predictions"
    __table_args__ = (
        UniqueConstraint("user_id", "game_id", name="uq_world_cup_prediction_user_game"),
        Index("ix_world_cup_predictions_user_id", "user_id"),
        Index("ix_world_cup_predictions_game_id", "game_id"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    game_id = Column(Integer, ForeignKey("world_cup_games.id"), nullable=False)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    scorer_guess = Column(String, nullable=True)
    scorer_hit = Column(Boolean, default=False)
    points = Column(Integer, default=0)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="world_cup_predictions")
    game = relationship("WorldCupGame", back_populates="predictions")


class WorldCupChampionPick(Base):
    __tablename__ = "world_cup_champion_picks"
    __table_args__ = (
        UniqueConstraint("user_id", name="uq_world_cup_champion_pick_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    team = Column(String, nullable=False)
    points = Column(Integer, default=0)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")


class WorldCupPlayer(Base):
    __tablename__ = "world_cup_players"
    __table_args__ = (
        UniqueConstraint("team", "name", name="uq_world_cup_player_team_name"),
        Index("ix_world_cup_players_team", "team"),
    )

    id = Column(Integer, primary_key=True, index=True)
    team = Column(String, nullable=False)
    name = Column(String, nullable=False)
    number = Column(Integer, nullable=True)
    position = Column(String, nullable=True)
    club = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow)
