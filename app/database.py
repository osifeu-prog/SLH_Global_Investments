# app/database.py
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Base  # Base מיובא מ-models (כמו שביקשת)

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


def _ensure_schema():
    """
    Soft-migration: מוסיף עמודות וטבלאות בצורה בטוחה ומהירה.
    מאפשר להתקדם בלי Alembic בשלב הזה.
    """
    statements: list[str] = [
        # --- users ---
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS slha_balance NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS role VARCHAR(64) NOT NULL DEFAULT 'user';",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS investor_status VARCHAR(64) NOT NULL DEFAULT 'none';",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- investor_profiles ---
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'pending';",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS risk_ack BOOLEAN NOT NULL DEFAULT false;",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS referrer_tid BIGINT;",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS note TEXT;",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS investor_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- wallets ---
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS wallet_type VARCHAR(16) NOT NULL DEFAULT 'base';",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS balance_slh NUMERIC(24, 6) NOT NULL DEFAULT 0;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS balance_slha NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS kind VARCHAR(50) NOT NULL DEFAULT 'base';",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS deposits_enabled BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS withdrawals_enabled BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE IF EXISTS wallets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --- referrals ---
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS referrer_tid BIGINT;",
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS referred_tid BIGINT;",
        "ALTER TABLE IF EXISTS referrals ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",

        # --- ledger_entries (חדש) ---
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
    1) create_all: יוצר טבלאות שחסרות (לפי models)
    2) soft-migration: מוסיף עמודות שחסרות בטבלאות קיימות
    """
    # חשוב: import models כדי לרשום metadata
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
