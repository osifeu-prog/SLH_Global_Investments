# app/crud.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models


def _utcnow():
    return datetime.now(timezone.utc)


# --------------------
# Users
# --------------------
def get_or_create_user(db: Session, telegram_id: int, username: Optional[str] = None) -> models.User:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        if username is not None and user.username != username:
            user.username = username
            db.add(user)
            db.commit()
            db.refresh(user)
        return user

    user = models.User(
        telegram_id=telegram_id,
        username=username,
        balance_slh=Decimal("0"),
        slha_balance=Decimal("0"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# --------------------
# Wallets
# --------------------
def get_wallet(db: Session, telegram_id: int, wallet_type: str) -> Optional[models.Wallet]:
    return (
        db.query(models.Wallet)
        .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.wallet_type == wallet_type)
        .first()
    )


def get_or_create_wallet(
    db: Session,
    telegram_id: int,
    wallet_type: str,
    *,
    kind: str = "base",
    deposits_enabled: bool = True,
    withdrawals_enabled: bool = False,
) -> models.Wallet:
    """
    CRITICAL:
    Your DB requires NOT NULL:
      wallet_type, is_active, balance_slh, balance_slha
    If any of those are missing/None -> Postgres will crash inserts.
    """
    w = get_wallet(db, telegram_id, wallet_type)
    if w:
        # keep aligned
        w.kind = kind
        w.deposits_enabled = bool(deposits_enabled)
        w.withdrawals_enabled = bool(withdrawals_enabled)

        # heal broken rows defensively
        if w.wallet_type is None:
            w.wallet_type = wallet_type
        if w.is_active is None:
            w.is_active = True
        if w.balance_slh is None:
            w.balance_slh = Decimal("0")
        if w.balance_slha is None:
            w.balance_slha = Decimal("0")

        db.add(w)
        db.commit()
        db.refresh(w)
        return w

    w = models.Wallet(
        telegram_id=telegram_id,
        wallet_type=wallet_type,          # MUST NOT NULL
        is_active=True,                   # MUST NOT NULL
        balance_slh=Decimal("0"),         # MUST NOT NULL
        balance_slha=Decimal("0"),        # MUST NOT NULL
        kind=kind,
        deposits_enabled=bool(deposits_enabled),
        withdrawals_enabled=bool(withdrawals_enabled),
    )

    db.add(w)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        # If raced, read again
        existing = get_wallet(db, telegram_id, wallet_type)
        if existing:
            return existing
        raise

    db.refresh(w)
    return w


# --------------------
# Investor Profiles
# --------------------
def get_investor_profile(db: Session, telegram_id: int) -> Optional[models.InvestorProfile]:
    return (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )


def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = get_investor_profile(db, telegram_id)
    if not prof:
        return False
    return str(prof.status).lower() in ("active", "approved")


def start_invest_onboarding(
    db: Session,
    telegram_id: int,
    *,
    referrer_tid: Optional[int] = None,
    note: Optional[str] = None,
) -> models.InvestorProfile:
    prof = get_investor_profile(db, telegram_id)

    if prof:
        prof.status = "candidate"
        if prof.risk_ack is None:
            prof.risk_ack = False
        if referrer_tid is not None:
            prof.referrer_tid = referrer_tid
        if note is not None:
            prof.note = note
        prof.updated_at = _utcnow()
        db.add(prof)
        db.commit()
        db.refresh(prof)
    else:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="candidate",   # REQUIRED
            risk_ack=False,       # REQUIRED
            referrer_tid=referrer_tid,
            note=note,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(prof)
        db.commit()
        db.refresh(prof)

    # create investor wallet (deposits only)
    get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        wallet_type="investor",
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )

    return prof


def approve_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = get_investor_profile(db, telegram_id)
    if not prof:
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on approve")

    prof.status = "active"
    prof.approved_at = _utcnow()
    if prof.risk_ack is None:
        prof.risk_ack = False
    prof.updated_at = _utcnow()

    db.add(prof)
    db.commit()
    db.refresh(prof)

    get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        wallet_type="investor",
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )
    return prof


def reject_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = get_investor_profile(db, telegram_id)
    if not prof:
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on reject")

    prof.status = "rejected"
    if prof.risk_ack is None:
        prof.risk_ack = False
    prof.updated_at = _utcnow()

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# --------------------
# Referrals
# --------------------
def apply_referral(db: Session, referrer_tid: int, referred_tid: int) -> bool:
    if referrer_tid == referred_tid:
        return False

    exists = (
        db.query(models.Referral)
        .filter(models.Referral.referrer_tid == referrer_tid, models.Referral.referred_tid == referred_tid)
        .first()
    )
    if exists:
        return False

    row = models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return False
    return True


def count_referrals(db: Session, telegram_id: int) -> int:
    return db.query(models.Referral).filter(models.Referral.referrer_tid == telegram_id).count()
