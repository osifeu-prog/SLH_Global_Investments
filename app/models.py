# app/models.py
from __future__ import annotations

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Numeric,
    DateTime,
    Integer,
    Boolean,
    Text,
    Index,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(64), nullable=True)
    first_name = Column(String(128), nullable=True)
    last_name = Column(String(128), nullable=True)
    language = Column(String(8), nullable=True, default="he")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    telegram_id = Column(BigInteger, primary_key=True, index=True)

    # pending / candidate / active / blocked
    status = Column(String(32), nullable=False, default="pending")

    risk_ack = Column(Boolean, nullable=False, default=False)

    # BSC address (0x...)
    bnb_address = Column(String(64), nullable=True)

    # last seen / audit
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, autoincrement=True)

    telegram_id = Column(BigInteger, index=True, nullable=False)
    wallet_type = Column(String(16), nullable=False, default="base")  # base / investor
    deposits_enabled = Column(Boolean, nullable=False, default=True)
    withdrawals_enabled = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_wallets_tid_type", "telegram_id", "wallet_type"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Keep it flexible: internal ledger events, on-chain txs, admin actions, etc.
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    telegram_id = Column(BigInteger, index=True, nullable=False)
    currency = Column(String(16), nullable=False, default="SLHA")  # SLH / SLHA / TON / USDT_TON וכו'
    amount = Column(Numeric(24, 8), nullable=False, default=0)

    tx_type = Column(String(64), nullable=False)  # admin_credit / referral / transfer / ...
    reference = Column(String(128), nullable=True)  # external tx hash / request id / etc.
    note = Column(Text, nullable=True)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)

    telegram_id = Column(BigInteger, index=True, nullable=False)

    wallet_type = Column(String(16), nullable=False, default="base")  # base / investor
    direction = Column(String(16), nullable=False)  # in / out
    amount = Column(Numeric(24, 8), nullable=False)
    currency = Column(String(16), nullable=False, default="ILS")  # ILS / SLH / SLHA / USDT_TON וכו'
    reason = Column(String(64), nullable=False, default="manual")
    meta = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_ledger_entries_tid", "telegram_id"),
        Index("ix_ledger_entries_wallet_type", "wallet_type"),
        Index("ix_ledger_entries_currency", "currency"),
    )


class InternalTransfer(Base):
    """Audit table for SLHA (internal points) transfers between users.

    Note: this is OFF-CHAIN only. No on-chain move is performed.
    """

    __tablename__ = "internal_transfers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    from_telegram_id = Column(BigInteger, index=True, nullable=False)
    to_telegram_id = Column(BigInteger, index=True, nullable=False)

    currency = Column(String(16), nullable=False, default="SLHA")
    amount = Column(Numeric(24, 8), nullable=False)

    note = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_internal_transfers_from", "from_telegram_id"),
        Index("ix_internal_transfers_to", "to_telegram_id"),
    )
