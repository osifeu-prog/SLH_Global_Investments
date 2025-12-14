# app/database.py
from __future__ import annotations

import logging
from urllib.parse import urlparse

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Base

logger = logging.getLogger(__name__)

engine = create_engine(
    settings.DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)


def _log_db_target():
    try:
        u = urlparse(settings.DATABASE_URL)
        # לא מדפיסים סיסמה
        logger.info("DB target: scheme=%s host=%s port=%s db=%s", u.scheme, u.hostname, u.port, (u.path or "").lstrip("/"))
    except Exception:
        logger.info("DB target: <parse failed>")


def _ensure_extras():
    """
    דברים "אקסטרה" שאינם תלויים במודלים (או שתרצה להבטיח גם אם מישהו מחק בטעות).
    ב-DB חדש: create_all ייצור את הטבלאות מהמודלים.
    """
    statements: list[str] = [
        # ledger_entries: אם תרצה להשאיר אותו מנוהל במודלים בלבד — אפשר למחוק את הבלוק הזה.
        """
        CREATE TABLE IF NOT EXISTS ledger_entries (
          id SERIAL PRIMARY KEY,
          telegram_id BIGINT NOT NULL,
          wallet_type VARCHAR(16) NOT NULL DEFAULT 'base',
          direction VARCHAR(16) NOT NULL,
          amount NUMERIC(24,8) NOT NULL,
          currency VARCHAR(16) NOT NULL DEFAULT 'ILS',
          reason VARCHAR(64) NOT NULL DEFAULT 'manual',
          meta TEXT,
          created_at TIMESTAMPTZ DEFAULT now()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_ledger_entries_tid ON ledger_entries(telegram_id);",
        "CREATE INDEX IF NOT EXISTS ix_ledger_entries_wallet_type ON ledger_entries(wallet_type);",
    ]

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def init_db():
    """
    DB חדש: create_all חייב ליצור את כל הטבלאות.
    אם זה נכשל — נדע בלוגים.
    """
    _log_db_target()

    # לוודא שהמודלים נטענים ומרשמים ל-metadata
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_extras()

    # sanity check: האם יש טבלאות בכלל?
    with engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
        ).scalar_one()
        logger.info("DB sanity: public tables=%s", n)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
