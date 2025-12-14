# app/crud.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app import models


def _utcnow():
    return datetime.now(timezone.utc)


# =========================
# Users
# =========================

def get_or_create_user(db: Session, telegram_id: int, username: str | None = None) -> models.User:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        if username is not None and getattr(user, "username", None) != username:
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


def set_bnb_address(db: Session, user: models.User, addr: str) -> models.User:
    user.bnb_address = addr
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# =========================
# Wallets (IMPORTANT: align with DB NOT NULL)
# DB columns:
# - wallet_type (NOT NULL, no default)
# - is_active (NOT NULL, no default)
# - balance_slh (NOT NULL, no default)
# - balance_slha (NOT NULL, no default)
# plus kind/deposits_enabled/withdrawals_enabled
# =========================

def get_wallet(db: Session, telegram_id: int, wallet_type: str) -> models.Wallet | None:
    return (
        db.query(models.Wallet)
        .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.wallet_type == wallet_type)
        .first()
    )


def get_or_create_wallet(
    db: Session,
    telegram_id: int,
    kind: str,
    deposits_enabled: bool = True,
    withdrawals_enabled: bool = False,
    is_active: bool = True,
) -> models.Wallet:
    """
    kind: 'base' / 'investor' (and more in future)
    We map wallet_type = kind to satisfy DB wallet_type NOT NULL.
    """
    wallet_type = kind  # ✅ crucial: match DB column that is NOT NULL

    w = get_wallet(db, telegram_id, wallet_type)
    if w:
        # keep consistent
        w.kind = kind
        w.deposits_enabled = bool(deposits_enabled)
        w.withdrawals_enabled = bool(withdrawals_enabled)
        w.is_active = bool(w.is_active) if w.is_active is not None else bool(is_active)

        # NOT NULL guards
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
        wallet_type=wallet_type,      # ✅ NOT NULL
        is_active=bool(is_active),    # ✅ NOT NULL
        balance_slh=Decimal("0"),     # ✅ NOT NULL
        balance_slha=Decimal("0"),    # ✅ NOT NULL
        kind=kind,
        deposits_enabled=bool(deposits_enabled),
        withdrawals_enabled=bool(withdrawals_enabled),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# =========================
# Investor profiles (align with DB)
# DB columns:
# - status (NOT NULL, NO DEFAULT) => ALWAYS set it in code
# - risk_ack (NOT NULL DEFAULT false) => still safe to set in code
# - referrer_tid nullable
# - approved_at nullable
# =========================

def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        return False
    return str(prof.status).lower() in ("active", "approved")


def start_invest_onboarding(
    db: Session,
    telegram_id: int,
    note: str | None = None,
    *,
    referrer_tid: int | None = None,
    risk_ack: bool | None = False,
) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )

    if prof:
        prof.status = "candidate"  # ✅ must be NOT NULL
        # keep risk_ack safe (NOT NULL)
        prof.risk_ack = bool(prof.risk_ack) if prof.risk_ack is not None else bool(risk_ack)
        if referrer_tid is not None:
            prof.referrer_tid = referrer_tid
        if note is not None:
            prof.note = note

        db.add(prof)
        db.commit()
        db.refresh(prof)
    else:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="candidate",           # ✅ REQUIRED (no default)
            risk_ack=bool(risk_ack),      # ✅ NOT NULL
            referrer_tid=referrer_tid,
            note=note,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
        db.add(prof)
        db.commit()
        db.refresh(prof)

    # Ensure investor wallet exists (deposits only by default)
    get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )
    return prof


def approve_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on approve")

    prof.status = "active"          # ✅ REQUIRED
    prof.risk_ack = bool(prof.risk_ack) if prof.risk_ack is not None else False
    prof.approved_at = _utcnow()

    db.add(prof)
    db.commit()
    db.refresh(prof)

    # Ensure investor wallet exists
    get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )
    return prof


def reject_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on reject")

    prof.status = "rejected"        # ✅ REQUIRED
    prof.risk_ack = bool(prof.risk_ack) if prof.risk_ack is not None else False

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# =========================
# Referrals
# =========================

def count_referrals(db: Session, telegram_id: int) -> int:
    return db.query(models.Referral).filter(models.Referral.referrer_tid == telegram_id).count()


def apply_referral(db: Session, referrer_tid: int, referred_tid: int) -> bool:
    """Create a referral relation only once. Returns True if created."""
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
    db.commit()
    return True
