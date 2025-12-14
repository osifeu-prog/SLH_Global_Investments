# app/models.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Numeric,
    Text,
)
from sqlalchemy.orm import declarative_base

Base = declarative_base()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)
    username = Column(String(128), nullable=True)

    bnb_address = Column(String(128), nullable=True)

    # SLH פנימי (אם תרצה בהמשך)
    balance_slh = Column(Numeric(36, 18), nullable=False, default=Decimal("0"))

    # SLHA נקודות
    slha_balance = Column(Numeric(36, 18), nullable=False, default=Decimal("0"))

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, index=True, nullable=False)

    wallet_type = Column(String(32), index=True, nullable=False)  # base / investor וכו'
    kind = Column(String(32), nullable=False, default="base")

    deposits_enabled = Column(Boolean, nullable=False, default=True)
    withdrawals_enabled = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, index=True, nullable=False)

    status = Column(String(32), index=True, nullable=False, default="candidate")  # candidate/active/rejected
    risk_ack = Column(Boolean, nullable=True, default=False)

    referrer_tid = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True)
    referrer_tid = Column(Integer, index=True, nullable=False)
    referred_tid = Column(Integer, index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id = Column(Integer, primary_key=True)

    telegram_id = Column(Integer, index=True, nullable=False)
    wallet_type = Column(String(32), index=True, nullable=False)  # investor / slha וכו'
    direction = Column(String(8), index=True, nullable=False)     # in / out

    amount = Column(Numeric(36, 18), nullable=False, default=Decimal("0"))
    currency = Column(String(32), index=True, nullable=False)     # SLHA / USDT_TON / TON וכו'

    reason = Column(String(64), index=True, nullable=False, default="manual")
    meta = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
