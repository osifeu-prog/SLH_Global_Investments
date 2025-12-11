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
    Soft-migration: מוסיף עמודות וטבלאות בצורה בטוחה ומהירה.
    מאפשר להתקדם בלי Alembic בשלב הזה.
    """
    statements: list[str] = [
        # --- users ---
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS slha_balance NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- transactions ---
        "ALTER TABLE IF EXISTS transactions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",

        # --- investor_profiles ---
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS status VARCHAR(50) NOT NULL DEFAULT 'pending';",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS note TEXT;",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- wallets ---
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS kind VARCHAR(50) NOT NULL DEFAULT 'base';",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS deposits_enabled BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS withdrawals_enabled BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- referrals ---
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS referrer_tid BIGINT;",
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS referred_tid BIGINT;",
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
    ]

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def init_db():
    """
    1) create_all: יוצר טבלאות שחסרות (לפי models)
    2) soft-migration: מוסיף עמודות שחסרות בטבלאות קיימות
    """
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
