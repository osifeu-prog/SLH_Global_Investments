# app/database.py
from __future__ import annotations

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models import Base  # Base מיובא מ-models

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


def _ensure_schema():
    """
    Bootstrap + soft-migration:
    1) יוצר טבלאות בסיסיות אם DB חדש וריק (CREATE TABLE IF NOT EXISTS)
    2) מוסיף עמודות/אינדקסים אם חסרים (ALTER/CREATE INDEX IF NOT EXISTS)
    """

    statements: list[str] = [
        # -------------------------
        # BOOTSTRAP TABLES (DB ריק)
        # -------------------------
        """
        CREATE TABLE IF NOT EXISTS users (
          telegram_id BIGINT PRIMARY KEY,
          username VARCHAR(255),
          bnb_address VARCHAR(255),
          balance_slh NUMERIC(24,6) NOT NULL DEFAULT 0,
          slha_balance NUMERIC(24,8) NOT NULL DEFAULT 0,
          role VARCHAR(64) NOT NULL DEFAULT 'user',
          investor_status VARCHAR(64) NOT NULL DEFAULT 'none',
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ DEFAULT now()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users(telegram_id);",
        "CREATE INDEX IF NOT EXISTS ix_users_username ON users(username);",

        """
        CREATE TABLE IF NOT EXISTS investor_profiles (
          telegram_id BIGINT PRIMARY KEY,
          status VARCHAR(32) NOT NULL DEFAULT 'candidate',
          risk_ack BOOLEAN NOT NULL DEFAULT false,
          referrer_tid BIGINT,
          approved_at TIMESTAMPTZ,
          note TEXT,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ DEFAULT now()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_investor_profiles_status ON investor_profiles(status);",
        "CREATE INDEX IF NOT EXISTS ix_investor_profiles_telegram_id ON investor_profiles(telegram_id);",

        """
        CREATE TABLE IF NOT EXISTS wallets (
          id SERIAL PRIMARY KEY,
          telegram_id BIGINT NOT NULL,
          wallet_type VARCHAR(16) NOT NULL DEFAULT 'base',
          is_active BOOLEAN NOT NULL DEFAULT true,
          balance_slh NUMERIC(24,6) NOT NULL DEFAULT 0,
          balance_slha NUMERIC(24,8) NOT NULL DEFAULT 0,
          kind VARCHAR(50) NOT NULL DEFAULT 'base',
          deposits_enabled BOOLEAN NOT NULL DEFAULT true,
          withdrawals_enabled BOOLEAN NOT NULL DEFAULT false,
          created_at TIMESTAMPTZ DEFAULT now(),
          updated_at TIMESTAMPTZ DEFAULT now()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_wallets_id ON wallets(id);",
        "CREATE INDEX IF NOT EXISTS ix_wallets_telegram_id ON wallets(telegram_id);",
        "CREATE INDEX IF NOT EXISTS ix_wallets_wallet_type ON wallets(wallet_type);",

        """
        CREATE TABLE IF NOT EXISTS referrals (
          id SERIAL PRIMARY KEY,
          referrer_tid BIGINT NOT NULL,
          referred_tid BIGINT NOT NULL,
          created_at TIMESTAMPTZ DEFAULT now()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_referrals_referrer_tid ON referrals(referrer_tid);",
        "CREATE INDEX IF NOT EXISTS ix_referrals_referred_tid ON referrals(referred_tid);",

        """
        CREATE TABLE IF NOT EXISTS transactions (
          id SERIAL PRIMARY KEY,
          created_at TIMESTAMPTZ DEFAULT now(),
          from_user BIGINT,
          to_user BIGINT,
          amount_slh NUMERIC(24,6) NOT NULL,
          tx_type VARCHAR(50) NOT NULL
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_transactions_id ON transactions(id);",

        """
        CREATE TABLE IF NOT EXISTS ledger_entries (
          id SERIAL PRIMARY KEY,
          telegram_id BIGINT NOT NULL,
          wallet_type VARCHAR(16) NOT NULL DEFAULT 'base',
          direction VARCHAR(16) NOT NULL, -- in/out
          amount NUMERIC(24,8) NOT NULL,
          currency VARCHAR(16) NOT NULL DEFAULT 'ILS',
          reason VARCHAR(64) NOT NULL DEFAULT 'manual',
          meta TEXT,
          created_at TIMESTAMPTZ DEFAULT now()
        );
        """,
        "CREATE INDEX IF NOT EXISTS ix_ledger_entries_tid ON ledger_entries(telegram_id);",
        "CREATE INDEX IF NOT EXISTS ix_ledger_entries_wallet_type ON ledger_entries(wallet_type);",

        # -------------------------
        # SOFT-MIGRATIONS (עמודות)
        # -------------------------
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS slha_balance NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(64) NOT NULL DEFAULT 'user';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS investor_status VARCHAR(64) NOT NULL DEFAULT 'none';",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'candidate';",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS risk_ack BOOLEAN NOT NULL DEFAULT false;",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS referrer_tid BIGINT;",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS note TEXT;",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS wallet_type VARCHAR(16) NOT NULL DEFAULT 'base';",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS balance_slh NUMERIC(24, 6) NOT NULL DEFAULT 0;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS balance_slha NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS kind VARCHAR(50) NOT NULL DEFAULT 'base';",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS deposits_enabled BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS withdrawals_enabled BOOLEAN NOT NULL DEFAULT FALSE;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",
    ]

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def init_db():
    """
    Bootstrap schema in a safe, idempotent way.

    ⚠️ We avoid `Base.metadata.create_all()` in production because it may attempt
    to (re)create indexes and fail with "already exists" across redeploys.
    All schema bootstrapping is handled in `_ensure_schema()` using IF NOT EXISTS.
    """
    # Ensure models are importable (register Base mappings)
    try:
        import app.models  # noqa: F401
    except Exception:
        logger.exception("Import app.models failed")

    _ensure_schema()


def get_db():
():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
