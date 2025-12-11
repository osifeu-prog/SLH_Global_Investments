from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

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

Base = declarative_base()


def _ensure_schema():
    """
    Soft-migration: מוסיף עמודות חסרות בלי לשבור DB קיים.
    זה קריטי כשעובדים בלי Alembic ועדיין רוצים להתקדם מהר.
    """
    statements: list[str] = [
        # --- users ---
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS slha_balance NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- investor_profiles ---
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS note TEXT;",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- wallets (internal wallets) ---
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- deposits ---
        "ALTER TABLE IF EXISTS deposits ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS deposits ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS deposits ADD COLUMN IF NOT EXISTS note TEXT;",

        # --- referrals ---
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
    ]

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def init_db():
    """
    1) create_all כדי ליצור טבלאות חסרות.
    2) soft-migration כדי להוסיף עמודות חסרות בטבלאות קיימות.
    """
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

    # חשוב: אחרי create_all
    _ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
