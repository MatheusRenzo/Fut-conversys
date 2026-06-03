from sqlalchemy import Boolean, Column, Integer, String, ForeignKey, DateTime, Text, UniqueConstraint
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

    rsvps = relationship("MatchRSVP", back_populates="user")
    posts = relationship("Post", back_populates="user")
    comments = relationship("Comment", back_populates="user")
    likes = relationship("Like", back_populates="user")
    world_cup_predictions = relationship("WorldCupPrediction", back_populates="user")

class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    event_type = Column(String, default="pelada")
    location = Column(String)
    date = Column(DateTime)
    description = Column(Text)
    max_players = Column(Integer, default=20)
    status = Column(String, default="scheduled")
    cover_url = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    rsvps = relationship("MatchRSVP", back_populates="match")
    posts = relationship("Post", back_populates="match")

class MatchRSVP(Base):
    __tablename__ = "match_rsvps"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    match_id = Column(Integer, ForeignKey("matches.id"))
    status = Column(String) # 'going', 'not_going'
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="rsvps")
    match = relationship("Match", back_populates="rsvps")

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    image_url = Column(String, nullable=True)
    title = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    goals_scored = Column(Integer, default=0)
    goal_status = Column(String, default="none") # 'none', 'pending', 'approved', 'rejected'
    goal_reviewed_by_id = Column(Integer, nullable=True)
    goal_reviewed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="posts")
    match = relationship("Match", back_populates="posts")
    comments = relationship("Comment", back_populates="post")
    likes = relationship("Like", back_populates="post")

class Comment(Base):
    __tablename__ = "comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    parent_id = Column(Integer, ForeignKey("comments.id"), nullable=True)
    text = Column(Text)
    media_url = Column(String, nullable=True)
    media_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="comments")
    user = relationship("User", back_populates="comments")

class Like(Base):
    __tablename__ = "likes"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("posts.id"))
    user_id = Column(Integer, ForeignKey("users.id"))
    reaction_type = Column(String, default="torcida")
    created_at = Column(DateTime, default=datetime.utcnow)

    post = relationship("Post", back_populates="likes")
    user = relationship("User", back_populates="likes")


class WorldCupGame(Base):
    __tablename__ = "world_cup_games"

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
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    predictions = relationship("WorldCupPrediction", back_populates="game")


class WorldCupPrediction(Base):
    __tablename__ = "world_cup_predictions"
    __table_args__ = (UniqueConstraint("user_id", "game_id", name="uq_world_cup_prediction_user_game"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    game_id = Column(Integer, ForeignKey("world_cup_games.id"))
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    points = Column(Integer, default=0)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="world_cup_predictions")
    game = relationship("WorldCupGame", back_populates="predictions")
