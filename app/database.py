# app/database.py
from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.models import Base  # keep import for ORM usage

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "")

# Railway uses postgres:// sometimes; SQLAlchemy expects postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        if not DATABASE_URL:
            raise RuntimeError("DATABASE_URL is not set")
        _engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            future=True,
        )
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=_engine, future=True)
    return _engine


def get_sessionmaker():
    if _SessionLocal is None:
        get_engine()
    return _SessionLocal


@contextmanager
def db_session() -> Generator[Session, None, None]:
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_db() -> Generator[Session, None, None]:
    with db_session() as db:
        yield db


def _ensure_schema(engine) -> None:
    """Create missing tables/indexes safely (idempotent).

    We intentionally avoid dialect-specific kwargs on SQLAlchemy Index objects
    (they caused crashes on some SQLAlchemy versions). Instead we use
    `CREATE ... IF NOT EXISTS` in raw SQL, which Postgres supports.
    """

    ddl = [
        # users
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            username VARCHAR(64),
            first_name VARCHAR(128),
            last_name VARCHAR(128),
            language VARCHAR(8),
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        # investor_profiles
        """
        CREATE TABLE IF NOT EXISTS investor_profiles (
            telegram_id BIGINT PRIMARY KEY,
            status VARCHAR(32) NOT NULL DEFAULT 'pending',
            risk_ack BOOLEAN NOT NULL DEFAULT FALSE,
            bnb_address VARCHAR(64),
            created_at TIMESTAMPTZ DEFAULT NOW(),
            updated_at TIMESTAMPTZ
        );
        """,
        # wallets
        """
        CREATE TABLE IF NOT EXISTS wallets (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            wallet_type VARCHAR(16) NOT NULL DEFAULT 'base',
            deposits_enabled BOOLEAN NOT NULL DEFAULT TRUE,
            withdrawals_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        # ledger_entries
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
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        # transactions (optional audit)
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            telegram_id BIGINT NOT NULL,
            currency VARCHAR(16) NOT NULL DEFAULT 'SLHA',
            amount NUMERIC(24,8) NOT NULL DEFAULT 0,
            tx_type VARCHAR(64) NOT NULL,
            reference VARCHAR(128),
            note TEXT
        );
        """,
        # internal_transfers (stage 2 SLHA)
        """
        CREATE TABLE IF NOT EXISTS internal_transfers (
            id SERIAL PRIMARY KEY,
            from_telegram_id BIGINT NOT NULL,
            to_telegram_id BIGINT NOT NULL,
            currency VARCHAR(16) NOT NULL DEFAULT 'SLHA',
            amount NUMERIC(24,8) NOT NULL,
            note TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW()
        );
        """,
        # indexes (IF NOT EXISTS)
        """CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id);""",
        """CREATE INDEX IF NOT EXISTS ix_investor_profiles_telegram_id ON investor_profiles (telegram_id);""",
        """CREATE INDEX IF NOT EXISTS ix_investor_profiles_status ON investor_profiles (status);""",
        """CREATE INDEX IF NOT EXISTS ix_wallets_tid ON wallets (telegram_id);""",
        """CREATE INDEX IF NOT EXISTS ix_wallets_tid_type ON wallets (telegram_id, wallet_type);""",
        """CREATE INDEX IF NOT EXISTS ix_ledger_entries_tid ON ledger_entries (telegram_id);""",
        """CREATE INDEX IF NOT EXISTS ix_ledger_entries_wallet_type ON ledger_entries (wallet_type);""",
        """CREATE INDEX IF NOT EXISTS ix_ledger_entries_currency ON ledger_entries (currency);""",
        """CREATE INDEX IF NOT EXISTS ix_internal_transfers_from ON internal_transfers (from_telegram_id);""",
        """CREATE INDEX IF NOT EXISTS ix_internal_transfers_to ON internal_transfers (to_telegram_id);""",
        """CREATE INDEX IF NOT EXISTS ix_transactions_tid ON transactions (telegram_id);""",
    ]

    with engine.begin() as conn:
        for stmt in ddl:
            conn.execute(text(stmt))


def init_db() -> None:
    engine = get_engine()

    # Create missing tables/indexes without breaking existing ones
    _ensure_schema(engine)

    # Keep ORM metadata available for queries (no-op if schema exists)
    # We DO NOT rely on create_all for indexes (it can create duplicates in some states).
    try:
        Base.metadata.create_all(bind=engine, checkfirst=True)
    except Exception as e:
        logger.warning("Base.metadata.create_all skipped/failed (non-fatal): %s", e)
