from __future__ import annotations

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

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

Base = declarative_base()


def _safe_exec(sql: str) -> None:
    """Execute a migration statement safely (ignore errors)."""
    try:
        with engine.begin() as conn:
            conn.execute(text(sql))
    except Exception as e:
        logger.info("migration skipped: %s | %s", sql.splitlines()[0][:120], e)


def init_db():
    """Ensure required tables/columns exist.

    We keep this extremely defensive:
    - create_all for missing tables
    - best-effort ALTER TABLE ADD COLUMN for new fields (won't drop anything)
    """
    from app import models  # noqa: F401

    # Create missing tables
    Base.metadata.create_all(bind=engine)

    # Best-effort additive migrations for existing deployments
    _safe_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS slha_balance NUMERIC(24,12) NOT NULL DEFAULT 0;")
    _safe_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(32) NOT NULL DEFAULT 'user';")
    _safe_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS investor_status VARCHAR(32) NOT NULL DEFAULT 'none';")
    _safe_exec("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();")

    # Deposits / referrals tables may not exist on older DBs
    _safe_exec("""
    CREATE TABLE IF NOT EXISTS referrals (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        referrer_tid BIGINT NOT NULL,
        referred_tid BIGINT NOT NULL
    );
    """)
    _safe_exec("CREATE UNIQUE INDEX IF NOT EXISTS uq_referrals_referred_tid ON referrals (referred_tid);")

    _safe_exec("""
    CREATE TABLE IF NOT EXISTS deposits (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        telegram_id BIGINT NOT NULL,
        network VARCHAR(16) NOT NULL DEFAULT 'bsc',
        asset VARCHAR(16) NOT NULL DEFAULT 'BNB',
        tx_hash VARCHAR(128) NOT NULL,
        from_address VARCHAR(255),
        to_address VARCHAR(255),
        amount NUMERIC(36,18),
        status VARCHAR(32) NOT NULL DEFAULT 'pending',
        admin_note VARCHAR(255),
        confirmed_slh NUMERIC(24,6),
        confirmed_by BIGINT,
        confirmed_at TIMESTAMPTZ
    );
    """)
    _safe_exec("CREATE UNIQUE INDEX IF NOT EXISTS uq_deposits_tx_hash ON deposits (tx_hash);")
    _safe_exec("CREATE INDEX IF NOT EXISTS ix_deposits_telegram_id ON deposits (telegram_id);")
    _safe_exec("""
    CREATE TABLE IF NOT EXISTS investor_profiles (
        telegram_id BIGINT PRIMARY KEY,
        status VARCHAR(32) NOT NULL DEFAULT 'none',
        note VARCHAR(255),
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ
    );
    """)
    _safe_exec("CREATE INDEX IF NOT EXISTS ix_investor_profiles_status ON investor_profiles (status);")

    _safe_exec("""
    CREATE TABLE IF NOT EXISTS wallets (
        id SERIAL PRIMARY KEY,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        telegram_id BIGINT NOT NULL,
        kind VARCHAR(16) NOT NULL DEFAULT 'user',
        deposits_enabled BOOLEAN NOT NULL DEFAULT TRUE,
        withdrawals_enabled BOOLEAN NOT NULL DEFAULT FALSE
    );
    """)
    _safe_exec("CREATE UNIQUE INDEX IF NOT EXISTS uq_wallets_telegram_kind ON wallets (telegram_id, kind);")



def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
