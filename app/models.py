# app/models.py
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Numeric,
    DateTime,
    Integer,
    Boolean,
    Text,
    UniqueConstraint,
    Index,
)
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(255), index=True, nullable=True)
    bnb_address = Column(String(255), nullable=True)

    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)
    slha_balance = Column(Numeric(24, 8), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Wallet(Base):
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)

    # base / investor (או כל סוג אחר בהמשך)
    kind = Column(String(50), nullable=False, default="base")

    deposits_enabled = Column(Boolean, nullable=False, default=True)
    withdrawals_enabled = Column(Boolean, nullable=False, default=False)

    # יתרה פנימית (לדוגמה: SLH קרדיט פנימי)
    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("telegram_id", "kind", name="uq_wallet_user_kind"),
        Index("ix_wallet_user_kind", "telegram_id", "kind"),
    )


class InvestorProfile(Base):
    __tablename__ = "investor_profiles"

    telegram_id = Column(BigInteger, primary_key=True, index=True)

    # pending / candidate / active / rejected
    status = Column(String(50), nullable=False, default="pending")

    # חובה כדי שלא יקרוס על NOT NULL אם קיים ב-DB
    risk_ack = Column(Boolean, nullable=False, default=False)

    note = Column(Text, nullable=True)

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

    __table_args__ = (
        Index("ix_tx_from_user", "from_user"),
        Index("ix_tx_to_user", "to_user"),
        Index("ix_tx_created_at", "created_at"),
    )


class Referral(Base):
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    referrer_tid = Column(BigInteger, index=True, nullable=False)
    referred_tid = Column(BigInteger, index=True, nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint("referred_tid", name="uq_ref_referred_once"),
        Index("ix_ref_referrer", "referrer_tid"),
    )
