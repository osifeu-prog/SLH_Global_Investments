# app/models.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Integer,
    Numeric,
    String,
    Text,
    Index,
    func,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(64), nullable=True)

    # internal balances (user-level)
    balance_slh = Column(Numeric(24, 6), nullable=False, default=Decimal("0"))
    slha_balance = Column(Numeric(24, 8), nullable=False, default=Decimal("0"))

    # optional onchain address
    bnb_address = Column(String(128), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, nullable=False, index=True)

    # IMPORTANT: DB says varchar(16) NOT NULL
    wallet_type = Column(String(16), nullable=False)

    # IMPORTANT: DB says NOT NULL (no default in your table output)
    is_active = Column(Boolean, nullable=False, default=True)

    # IMPORTANT: DB says NOT NULL, numeric(24,6)
    balance_slh = Column(Numeric(24, 6), nullable=False, default=Decimal("0"))

    # IMPORTANT: DB says NOT NULL, numeric(24,8)
    balance_slha = Column(Numeric(24, 8), nullable=False, default=Decimal("0"))

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    # other columns you have
    kind = Column(String(50), nullable=False, server_default="base")
    deposits_enabled = Column(Boolean, nullable=False, server_default="true")
    withdrawals_enabled = Column(Boolean, nullable=False, server_default="false")


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    telegram_id = Column(BigInteger, primary_key=True, index=True)

    status = Column(String(32), nullable=False)  # no DB default
    risk_ack = Column(Boolean, nullable=False, server_default="false")

    referrer_tid = Column(BigInteger, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)
    note = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_investor_profiles_status", "status"),
        Index("ix_investor_profiles_telegram_id", "telegram_id"),
    )


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True)
    referrer_tid = Column(BigInteger, nullable=False, index=True)
    referred_tid = Column(BigInteger, nullable=False, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_referrals_referrer_referred", "referrer_tid", "referred_tid", unique=True),
    )
