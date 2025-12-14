# app/database.py
from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = (getattr(settings, "DATABASE_URL", None) or "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

# Railway בדרך כלל נותן postgres:// ולכן ננרמל ל-postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
    future=True,
)

_initialized = False


def init_db() -> None:
    """
    יוצר טבלאות אם לא קיימות. (ללא Alembic כרגע)
    חשוב: לא מנסה ליצור Indexים עם IF NOT EXISTS (לא נתמך דרך SQLAlchemy Index kwargs).
    """
    global _initialized
    if _initialized:
        return

    # בדיקת חיבור קצרה
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
        conn.commit()

    Base.metadata.create_all(bind=engine)
    _initialized = True
    logger.info("DB initialized")


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
