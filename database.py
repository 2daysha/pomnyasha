import os
import json
from typing import Optional, Generator

from dotenv import load_dotenv
from sqlalchemy import (
    create_engine, Integer, String, DateTime, Text, ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import (
    declarative_base, sessionmaker, relationship, Session, Mapped, mapped_column
)
from sqlalchemy.sql import func
from sqlalchemy import text
from google.oauth2.credentials import Credentials

load_dotenv()

Base = declarative_base()

# ---------- Модели ----------

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[Optional[object]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    tokens: Mapped[list["OAuthToken"]] = relationship("OAuthToken", back_populates="user", cascade="all, delete-orphan")
    events: Mapped[list["Event"]]      = relationship("Event",      back_populates="user", cascade="all, delete-orphan")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    token_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[Optional[object]] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="tokens")

    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    start_time: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time:   Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)

    source: Mapped[str] = mapped_column(String(50), default="local", nullable=False)  # local|google

    # новые поля для внешних ID
    external_id_google: Mapped[Optional[str]] = mapped_column(String(255))
    external_id_yandex: Mapped[Optional[str]] = mapped_column(String(255))

    synced_at: Mapped[Optional[object]] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="events")


# ---------- Подключение к БД ----------

DATABASE_URL: str | None = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///app.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal: sessionmaker[Session] = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db() -> Generator[Session, None, None]:
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def create_tables() -> None:
    Base.metadata.create_all(bind=engine)

# ---- Авто-«миграция» схемы для SQLite (добавим недостающие колонки) ----
def ensure_schema() -> None:
    if not DATABASE_URL.startswith("sqlite"):
        return
    with engine.begin() as conn:
        cols = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info('events')")}
        if "external_id_google" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN external_id_google VARCHAR(255)")
        if "external_id_yandex" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN external_id_yandex VARCHAR(255)")
        if "synced_at" not in cols:
            conn.exec_driver_sql("ALTER TABLE events ADD COLUMN synced_at TIMESTAMP")

# ---------- Google OAuth токены ----------

def get_user_creds(user_id: int | None) -> Optional[Credentials]:
    if not user_id:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT token_json FROM oauth_tokens WHERE user_id = :u AND provider = 'google'"),
            {"u": user_id},
        ).fetchone()
    if not row:
        return None
    creds_dict = json.loads(row[0])
    return Credentials.from_authorized_user_info(creds_dict)

def save_user_creds(user_id: int, creds: Credentials) -> None:
    token_json = creds.to_json()
    with engine.begin() as conn:
        existing = conn.execute(
            text("SELECT id FROM oauth_tokens WHERE user_id = :u AND provider = 'google'"),
            {"u": user_id},
        ).fetchone()
        if existing:
            conn.execute(
                text("UPDATE oauth_tokens SET token_json = :t WHERE user_id = :u AND provider = 'google'"),
                {"t": token_json, "u": user_id},
            )
        else:
            conn.execute(
                text("INSERT INTO oauth_tokens (user_id, provider, token_json) VALUES (:u, 'google', :t)"),
                {"u": user_id, "t": token_json},
            )