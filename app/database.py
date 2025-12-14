# app/database.py
from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from typing import Generator, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

# ---------- DB URL ----------
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
if not DATABASE_URL:
    # לא נזרוק כאן חריגה כדי לא להפיל import של מודולים אחרים (כמו הבוט),
    # את הבדיקה נבצע ב-init_db/selftest/ready.
    logger.warning("DATABASE_URL is empty. DB will fail to init until set.")

# ---------- Engine ----------
def _make_engine(url: str) -> Engine:
    # Railway Postgres דורש לרוב SSL. אם DATABASE_URL כבר מכיל sslmode – לא נוגעים.
    connect_args = {}
    if url.startswith("postgresql"):
        if "sslmode=" not in url:
            # ברירת מחדל בטוחה ל-Hosted Postgres
            url = url + ("&" if "?" in url else "?") + "sslmode=require"

        # psycopg2 תומך ב-sslmode דרך ה-URL, אז connect_args ריק מספיק לרוב.
        # אם תרצה בעתיד לנהל certים – זה המקום.
        connect_args = {}

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=int(os.getenv("DB_POOL_SIZE", "5")),
        max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "10")),
        pool_timeout=int(os.getenv("DB_POOL_TIMEOUT", "30")),
        connect_args=connect_args,
    )


engine: Optional[Engine] = None
if DATABASE_URL:
    engine = _make_engine(DATABASE_URL)

# SessionLocal חייב להיות מוגדר תמיד כדי שלא יקרוס import של הבוט.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)  # type: ignore[arg-type]


# ---------- Helpers ----------
def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def db_session() -> Generator[Session, None, None]:
    """
    Context manager נוח לשימוש פנימי (בוט/קרון/משימות).
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def select1(db: Optional[Session] = None) -> dict:
    """
    בדיקת DB קלה. מחזיר זמן ביצוע במילישניות.
    """
    start = time.time()
    own = False
    if db is None:
        db = SessionLocal()
        own = True
    try:
        db.execute(text("SELECT 1"))
        ms = int((time.time() - start) * 1000)
        return {"ok": True, "ms": ms}
    finally:
        if own:
            db.close()


# ---------- Init Schema ----------
def init_db() -> None:
    """
    יוצר טבלאות לפי SQLAlchemy metadata.
    חשוב: אנחנו מייבאים models רק כאן כדי לא להפיל import של app.database
    במקרה שיש בעיה נקודתית במודלים.
    """
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set")

    global engine
    if engine is None:
        engine = _make_engine(DATABASE_URL)
        SessionLocal.configure(bind=engine)

    # יבוא מאוחר כדי למנוע קריסות import (הבעיה שהייתה לך עם SessionLocal)
    from app.models import Base  # noqa: WPS433

    Base.metadata.create_all(bind=engine)
    logger.info("DB initialized")
