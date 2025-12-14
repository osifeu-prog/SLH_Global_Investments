# app/database.py
from __future__ import annotations

import logging
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

DATABASE_URL = (settings.DATABASE_URL or "").strip()
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is missing")

# Railway/Postgres: pool_pre_ping חשוב לניתוקים
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, future=True)


def init_db() -> None:
    """
    יוצר טבלאות (אם אין Alembic עדיין).
    אם בהמשך תעבור ל-Alembic מלא, אפשר להשאיר זאת רק לדב/לוקאל.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("DB initialized")


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
