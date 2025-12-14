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
    username = Column(String(255), index=True, nullable=True)
    bnb_address = Column(String(255), nullable=True)

    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)
    slha_balance = Column(Numeric(24, 8), nullable=False, default=0)

    # קיימים אצלך ב-DB
    role = Column(String(64), nullable=False, default="user")
    investor_status = Column(String(64), nullable=False, default="none")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    from_user = Column(BigInteger, nullable=True)
    to_user = Column(BigInteger, nullable=True)

    amount_slh = Column(Numeric(24, 6), nullable=False)
    tx_type = Column(String(50), nullable=False)


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    telegram_id = Column(BigInteger, primary_key=True, index=True)

    # אצלך: status VARCHAR(32) NOT NULL
    status = Column(String(32), nullable=False, default="pending")

    # אצלך: risk_ack boolean NOT NULL DEFAULT false
    risk_ack = Column(Boolean, nullable=False, default=False)

    referrer_tid = Column(BigInteger, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    note = Column(Text, nullable=True)

    __table_args__ = (
        Index("ix_investor_profiles_status", "status", postgresql_if_not_exists=True),
        Index("ix_investor_profiles_telegram_id", "telegram_id", postgresql_if_not_exists=True),
    )


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)

    # אצלך: wallet_type VARCHAR(16) NOT NULL
    wallet_type = Column(String(16), nullable=False, default="base")

    # אצלך: is_active boolean NOT NULL
    is_active = Column(Boolean, nullable=False, default=True)

    # אצלך: balance_slh / balance_slha NOT NULL
    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)
    balance_slha = Column(Numeric(24, 8), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    # תואם אצלך (קיים)
    kind = Column(String(50), nullable=False, default="base")
    deposits_enabled = Column(Boolean, nullable=False, default=True)
    withdrawals_enabled = Column(Boolean, nullable=False, default=False)


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    referrer_tid = Column(BigInteger, index=True, nullable=False)
    referred_tid = Column(BigInteger, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)


class LedgerEntry(Base):
    """
    Ledger בסיסי – זה הבסיס ל"כסף אמיתי".
    במקום לשנות balance ישירות, כותבים ledger ואז מציגים סכומים לפי סכימת Entries.
    """
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)

    wallet_type = Column(String(16), nullable=False, default="base")  # base / investor
    direction = Column(String(16), nullable=False)  # in / out
    amount = Column(Numeric(24, 8), nullable=False)
    currency = Column(String(16), nullable=False, default="ILS")  # ILS / SLH / USDT וכו'
    reason = Column(String(64), nullable=False, default="manual")
    meta = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_ledger_entries_tid", "telegram_id"),
        Index("ix_ledger_entries_wallet_type", "wallet_type"),
    )
