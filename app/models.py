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
)
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True, autoincrement=False)
    username = Column(String(255), index=True, nullable=True)
    bnb_address = Column(String(255), nullable=True)

    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)
    slha_balance = Column(Numeric(24, 8), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    from_user = Column(BigInteger, nullable=True)
    to_user = Column(BigInteger, nullable=True)

    amount_slh = Column(Numeric(24, 6), nullable=False)
    tx_type = Column(String(50), nullable=False)


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    # ב-DB אצלך מוגדר SEQ כברירת מחדל, אבל אנחנו עדיין מכניסים את ה-Telegram ID בפועל.
    telegram_id = Column(BigInteger, primary_key=True, index=True, autoincrement=False)

    # ב-DB: NOT NULL בלי DEFAULT => חובה לספק תמיד בקוד
    status = Column(String(32), nullable=False)

    # ב-DB: NOT NULL DEFAULT false
    risk_ack = Column(Boolean, nullable=False, default=False)

    # אופציונלי
    referrer_tid = Column(BigInteger, nullable=True)
    approved_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    note = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)

    # ב-DB: NOT NULL בלי DEFAULT => חובה בקוד
    wallet_type = Column(String(16), nullable=False)

    # ב-DB: NOT NULL בלי DEFAULT => חובה בקוד
    is_active = Column(Boolean, nullable=False)

    # ב-DB: NOT NULL בלי DEFAULT => חובה בקוד
    balance_slh = Column(Numeric(24, 6), nullable=False)
    balance_slha = Column(Numeric(24, 8), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # אצלך קיימים גם אלה:
    kind = Column(String(50), nullable=False, default="base")
    deposits_enabled = Column(Boolean, nullable=False, default=True)
    withdrawals_enabled = Column(Boolean, nullable=False, default=False)


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    referrer_tid = Column(BigInteger, index=True, nullable=False)
    referred_tid = Column(BigInteger, index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
