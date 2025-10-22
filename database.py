from sqlalchemy import (
    create_engine,
    Integer,
    String,
    DateTime,
    Text,
    ForeignKey,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import (
    declarative_base,
    sessionmaker,
    relationship,
    Session,
    Mapped,
    mapped_column,
)
from sqlalchemy.sql import func
from typing import Optional, Generator
import os
import json
from dotenv import load_dotenv
from google.oauth2.credentials import Credentials


load_dotenv()

Base = declarative_base()



class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(100))
    last_name: Mapped[Optional[str]] = mapped_column(String(100))
    created_at: Mapped[Optional[object]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tasks: Mapped[list["Task"]] = relationship(
        "Task", back_populates="user", cascade="all, delete-orphan"
    )
    tokens: Mapped[list["OAuthToken"]] = relationship(
        "OAuthToken", back_populates="user", cascade="all, delete-orphan"
    )
    events: Mapped[list["Event"]] = relationship(
        "Event", back_populates="user", cascade="all, delete-orphan"
    )


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    task_type: Mapped[Optional[str]] = mapped_column(String(50))
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    deadline: Mapped[Optional[object]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Optional[object]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="tasks")


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    token_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[Optional[object]] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="tokens")

   
    __table_args__ = (
        UniqueConstraint("user_id", "provider", name="uq_user_provider"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    start_time: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(
        String(50), default="local", nullable=False
    )  # local | google | yandex
    external_id: Mapped[Optional[str]] = mapped_column(String(255))
    synced_at: Mapped[Optional[object]] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship("User", back_populates="events")




DATABASE_URL: str | None = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///app.db"

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)

SessionLocal: sessionmaker[Session] = sessionmaker(
    autocommit=False, autoflush=False, bind=engine
)


def get_db() -> Generator[Session, None, None]:
    """Создаёт и закрывает сессию SQLAlchemy"""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables() -> None:
    """Создаёт все таблицы"""
    Base.metadata.create_all(bind=engine)


def drop_tables() -> None:
    """Удаляет все таблицы"""
    Base.metadata.drop_all(bind=engine)


def recreate_tables() -> None:
    """Полностью пересоздаёт все таблицы"""
    drop_tables()
    create_tables()


def get_user_creds(user_id: int | None) -> Optional[Credentials]:
    """Возвращает Google Credentials для пользователя"""
    if not user_id:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT token_json FROM oauth_tokens WHERE user_id = :u AND provider = 'google'"
            ),
            {"u": user_id},
        ).fetchone()
    if not row:
        return None
    try:
        creds_dict = json.loads(row[0])
        return Credentials.from_authorized_user_info(creds_dict)
    except Exception:
        return None


def save_user_creds(user_id: int, creds: Credentials) -> None:
    """Обновляет или сохраняет токен Google"""
    token_json = creds.to_json()
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO oauth_tokens (user_id, provider, token_json)
                VALUES (:u, 'google', :t)
                ON CONFLICT(user_id, provider)
                DO UPDATE SET token_json = :t
            """),
            {"u": user_id, "t": token_json},
        )



def get_user_creds_yandex(user_id: int | None) -> Optional[str]:
    """Возвращает access_token Яндекс пользователя"""
    if not user_id:
        return None
    with engine.begin() as conn:
        row = conn.execute(
            text(
                "SELECT token_json FROM oauth_tokens WHERE user_id = :u AND provider = 'yandex'"
            ),
            {"u": user_id},
        ).fetchone()
    if not row:
        return None
    try:
        token_data = json.loads(row[0])
        return token_data.get("access_token")
    except Exception:
        return None


def save_user_creds_yandex(user_id: int, token_json: str) -> None:
    """Сохраняет токен Яндекс"""
    with engine.begin() as conn:
        conn.execute(
            text("""
                INSERT INTO oauth_tokens (user_id, provider, token_json)
                VALUES (:u, 'yandex', :t)
                ON CONFLICT(user_id, provider)
                DO UPDATE SET token_json = :t
            """),
            {"u": user_id, "t": token_json},
        )