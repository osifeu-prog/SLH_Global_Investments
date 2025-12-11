from __future__ import annotations

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Numeric,
    DateTime,
    Integer,
    Boolean,
    UniqueConstraint,
    ForeignKey,
)
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """System user (Telegram identity).

    - telegram_id is primary key.
    - Holds generic information usable for both regular users and investors.
    """

    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(255), index=True, nullable=True)

    # Optional linked on-chain wallet (BSC address) for viewing + deposit proofs
    bnb_address = Column(String(255), nullable=True)

    # Internal ledger balances (off-chain)
    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)
    slha_balance = Column(Numeric(24, 12), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InvestorProfile(Base):
    """Investor onboarding status (separate from User to keep user table stable)."""

    __tablename__ = "investor_profiles"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    status = Column(String(32), nullable=False, default="none")  # none/pending/approved/rejected
    note = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Wallet(Base):
    """Internal wallet object (Layer-0).

    kind:
      - user: regular user internal wallet
      - investor: investor internal wallet (created only after approval)
    """

    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    telegram_id = Column(BigInteger, nullable=False, index=True)
    kind = Column(String(16), nullable=False, default="user")  # user/investor

    # deposits only for now
    deposits_enabled = Column(Boolean, nullable=False, default=True)
    withdrawals_enabled = Column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("telegram_id", "kind", name="uq_wallets_telegram_kind"),
    )


class Transaction(Base):
    """Internal off-chain ledger transactions (SLH)."""

    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    from_user = Column(BigInteger, nullable=True)
    to_user = Column(BigInteger, nullable=True)

    amount_slh = Column(Numeric(24, 6), nullable=False)
    tx_type = Column(String(50), nullable=False)


class Referral(Base):
    """Referral edges: referrer -> referred user (one-time)."""

    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    referrer_tid = Column(BigInteger, nullable=False)
    referred_tid = Column(BigInteger, nullable=False)

    __table_args__ = (
        UniqueConstraint("referred_tid", name="uq_referrals_referred_tid"),
    )


class Deposit(Base):
    """On-chain deposit proofs.

    Stored as evidence. Admin confirms and credits internal ledger.
    """

    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    telegram_id = Column(BigInteger, nullable=False, index=True)

    network = Column(String(16), nullable=False, default="bsc")  # bsc/ton (future)
    asset = Column(String(16), nullable=False, default="BNB")  # BNB/SLH/USDT (future)

    tx_hash = Column(String(128), nullable=False, unique=True, index=True)
    from_address = Column(String(255), nullable=True)
    to_address = Column(String(255), nullable=True)

    amount = Column(Numeric(36, 18), nullable=True)

    status = Column(String(32), nullable=False, default="pending")  # pending/verified/confirmed/rejected
    admin_note = Column(String(255), nullable=True)

    confirmed_slh = Column(Numeric(24, 6), nullable=True)
    confirmed_by = Column(BigInteger, nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
