import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

# We will try to use the DATABASE_URL from .env. If not set, we fallback to SQLite locally.
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./conversys_fut.db")

# For SQLite we need connect_args={"check_same_thread": False}. For Postgres we don't.
is_sqlite = SQLALCHEMY_DATABASE_URL.startswith("sqlite")
engine_args = {"check_same_thread": False} if is_sqlite else {}

engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args=engine_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
