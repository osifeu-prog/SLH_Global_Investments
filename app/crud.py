# app/crud.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# -------- Users --------

def get_or_create_user(db: Session, telegram_id: int, username: str | None = None) -> models.User:
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
        role="user",
        investor_status="none",
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


# -------- Wallets --------

def get_wallet(db: Session, telegram_id: int, wallet_type: str) -> models.Wallet | None:
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
    w = get_wallet(db, telegram_id, wallet_type)
    if w:
        # align toggles safely
        w.kind = kind
        w.deposits_enabled = bool(deposits_enabled)
        w.withdrawals_enabled = bool(withdrawals_enabled)
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
        wallet_type=wallet_type,        # NOT NULL
        is_active=True,                 # NOT NULL
        balance_slh=Decimal("0"),       # NOT NULL
        balance_slha=Decimal("0"),      # NOT NULL
        kind=kind,
        deposits_enabled=bool(deposits_enabled),
        withdrawals_enabled=bool(withdrawals_enabled),
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# -------- Investor Profiles --------

def get_investor_profile(db: Session, telegram_id: int) -> models.InvestorProfile | None:
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
    referrer_tid: int | None = None,
    note: str | None = None,
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
        db.add(prof)
        db.commit()
        db.refresh(prof)
    else:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="candidate",
            risk_ack=False,
            referrer_tid=referrer_tid,
            note=note,
        )
        db.add(prof)
        db.commit()
        db.refresh(prof)

    # ensure investor wallet exists (deposits only)
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

    # update user flags (יש אצלך ב-DB)
    u = get_or_create_user(db, telegram_id, None)
    u.role = "investor"
    u.investor_status = "approved"

    db.add(prof)
    db.add(u)
    db.commit()
    db.refresh(prof)

    # investor wallet stays deposits only unless you change policy
    get_or_create_wallet(db, telegram_id, "investor", kind="investor", deposits_enabled=True, withdrawals_enabled=False)
    return prof


def reject_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = get_investor_profile(db, telegram_id)
    if not prof:
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on reject")

    prof.status = "rejected"
    if prof.risk_ack is None:
        prof.risk_ack = False

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# -------- Referrals --------

def count_referrals(db: Session, telegram_id: int) -> int:
    return db.query(models.Referral).filter(models.Referral.referrer_tid == telegram_id).count()


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
    db.add(models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid))
    db.commit()
    return True


# -------- Ledger (core) --------

def ledger_add(
    db: Session,
    telegram_id: int,
    *,
    wallet_type: str,
    direction: str,
    amount: Decimal,
    currency: str = "ILS",
    reason: str = "manual",
    meta: str | None = None,
) -> models.LedgerEntry:
    row = models.LedgerEntry(
        telegram_id=telegram_id,
        wallet_type=wallet_type,
        direction=direction,
        amount=Decimal(amount),
        currency=currency,
        reason=reason,
        meta=meta,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def ledger_balance(
    db: Session,
    telegram_id: int,
    *,
    wallet_type: str,
    currency: str = "ILS",
) -> Decimal:
    """
    סכימה: IN - OUT
    """
    incoming = (
        db.query(func.coalesce(func.sum(models.LedgerEntry.amount), 0))
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
            models.LedgerEntry.currency == currency,
            models.LedgerEntry.direction == "in",
        )
        .scalar()
    )
    outgoing = (
        db.query(func.coalesce(func.sum(models.LedgerEntry.amount), 0))
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
            models.LedgerEntry.currency == currency,
            models.LedgerEntry.direction == "out",
        )
        .scalar()
    )
    return Decimal(str(incoming)) - Decimal(str(outgoing))
