# app/crud.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app import ledger


def _utcnow():
    return datetime.now(timezone.utc)


def _dec(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except (InvalidOperation, TypeError):
        return Decimal("0")


# ---------- Users ----------

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
        created_at=_utcnow(),
        updated_at=_utcnow(),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_bnb_address(db: Session, user: models.User, bnb_address: str) -> models.User:
    user.bnb_address = bnb_address
    user.updated_at = _utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------- Wallets ----------

def get_or_create_wallet(
    db: Session,
    telegram_id: int,
    *,
    wallet_type: str = "base",
    kind: str = "base",
    deposits_enabled: bool = True,
    withdrawals_enabled: bool = False,
) -> models.Wallet:
    w = (
        db.query(models.Wallet)
        .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.wallet_type == wallet_type)
        .first()
    )
    if w:
        changed = False
        if w.kind != kind:
            w.kind = kind
            changed = True
        if w.deposits_enabled != deposits_enabled:
            w.deposits_enabled = deposits_enabled
            changed = True
        if w.withdrawals_enabled != withdrawals_enabled:
            w.withdrawals_enabled = withdrawals_enabled
            changed = True
        if changed:
            db.add(w)
            db.commit()
            db.refresh(w)
        return w

    w = models.Wallet(
        telegram_id=telegram_id,
        wallet_type=wallet_type,
        kind=kind,
        deposits_enabled=deposits_enabled,
        withdrawals_enabled=withdrawals_enabled,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ---------- Referrals ----------

def apply_referral(db: Session, referrer_tid: int, referred_tid: int) -> bool:
    if referrer_tid == referred_tid:
        return False

    exists = (
        db.query(models.Referral.id)
        .filter(models.Referral.referrer_tid == referrer_tid, models.Referral.referred_tid == referred_tid)
        .first()
    )
    if exists:
        return False

    row = models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid)
    db.add(row)
    db.commit()
    return True


def count_referrals(db: Session, telegram_id: int) -> int:
    return int(
        db.query(func.count(models.Referral.id))
        .filter(models.Referral.referrer_tid == telegram_id)
        .scalar()
        or 0
    )


# ---------- Investors ----------

def get_investor_profile(db: Session, telegram_id: int) -> Optional[models.InvestorProfile]:
    return db.query(models.InvestorProfile).filter(models.InvestorProfile.telegram_id == telegram_id).first()


def is_investor_active(db: Session, telegram_id: int) -> bool:
    p = get_investor_profile(db, telegram_id)
    if not p:
        return False
    return str(p.status).lower() in ("active", "approved")


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
        prof.risk_ack = False if prof.risk_ack is None else prof.risk_ack
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
            status="candidate",
            risk_ack=False,
            referrer_tid=referrer_tid,
            note=note,
            created_at=_utcnow(),
            updated_at=_utcnow(),
        )
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


def approve_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = get_investor_profile(db, telegram_id)
    if not prof:
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on approve")

    prof.status = "active"
    prof.approved_at = _utcnow()
    prof.risk_ack = False if prof.risk_ack is None else prof.risk_ack
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
    prof.risk_ack = False if prof.risk_ack is None else prof.risk_ack
    prof.updated_at = _utcnow()

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# ---------- Ledger ----------

def add_ledger_entry(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: str,
    direction: str,
    amount: Decimal,
    currency: str,
    reason: str = "manual",
    meta: Optional[str] = None,
) -> models.LedgerEntry:
    e = models.LedgerEntry(
        telegram_id=telegram_id,
        wallet_type=wallet_type,
        direction=direction,
        amount=_dec(amount),
        currency=currency,
        reason=reason,
        meta=meta,
        created_at=_utcnow(),
    )
    db.add(e)
    db.commit()
    db.refresh(e)
    return e


def get_ledger_balance(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: str,
    currency: str,
) -> Decimal:
    in_sum = (
        db.query(func.coalesce(func.sum(models.LedgerEntry.amount), 0))
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
            models.LedgerEntry.currency == currency,
            models.LedgerEntry.direction == "in",
        )
        .scalar()
    )
    out_sum = (
        db.query(func.coalesce(func.sum(models.LedgerEntry.amount), 0))
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
            models.LedgerEntry.currency == currency,
            models.LedgerEntry.direction == "out",
        )
        .scalar()
    )
    return _dec(in_sum) - _dec(out_sum)


def list_ledger_entries(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: Optional[str] = None,
    limit: int = 20,
) -> list[models.LedgerEntry]:
    q = db.query(models.LedgerEntry).filter(models.LedgerEntry.telegram_id == telegram_id)
    if wallet_type:
        q = q.filter(models.LedgerEntry.wallet_type == wallet_type)
    return q.order_by(models.LedgerEntry.id.desc()).limit(int(limit)).all()


# =========================
# SLHA (internal) transfers
# =========================

def transfer_slha(
    db: Session,
    *,
    from_tid: int,
    to_tid: int,
    amount: Decimal,
    note: Optional[str] = None,
) -> dict:
    """
    העברת SLHA פנימית:
    - משנה slha_balance בטבלת users
    - רושמת גם ledger כפול (OUT ל-שולח, IN ל-מקבל) לצורך Audit
    """
    amt = _dec(amount)
    if amt <= 0:
        raise ValueError("amount must be > 0")
    if from_tid == to_tid:
        raise ValueError("cannot transfer to self")

    # סדר נעילה קבוע למניעת deadlocks
    a, b = (from_tid, to_tid) if from_tid < to_tid else (to_tid, from_tid)

    ua = db.query(models.User).filter(models.User.telegram_id == a).with_for_update().first()
    ub = db.query(models.User).filter(models.User.telegram_id == b).with_for_update().first()

    if not ua:
        ua = get_or_create_user(db, a, None)
        ua = db.query(models.User).filter(models.User.telegram_id == a).with_for_update().first()

    if not ub:
        ub = get_or_create_user(db, b, None)
        ub = db.query(models.User).filter(models.User.telegram_id == b).with_for_update().first()

    sender = ua if ua.telegram_id == from_tid else ub
    receiver = ub if sender is ua else ua

    sender_bal = _dec(sender.slha_balance)
    if sender_bal < amt:
        raise ValueError("insufficient SLHA balance")

    # עדכון יתרות
    sender.slha_balance = sender_bal - amt
    receiver.slha_balance = _dec(receiver.slha_balance) + amt
    sender.updated_at = _utcnow()
    receiver.updated_at = _utcnow()

    db.add(sender)
    db.add(receiver)
    db.commit()
    db.refresh(sender)
    db.refresh(receiver)

    # Audit ledger
    meta = {"from": from_tid, "to": to_tid}
    if note:
        meta["note"] = note

    ledger.create_entry(
        db,
        telegram_id=from_tid,
        wallet_type="slha",
        direction="out",
        amount=amt,
        currency="SLHA",
        reason="transfer",
        meta=meta,
    )
    ledger.create_entry(
        db,
        telegram_id=to_tid,
        wallet_type="slha",
        direction="in",
        amount=amt,
        currency="SLHA",
        reason="transfer",
        meta=meta,
    )

    return {
        "from_tid": from_tid,
        "to_tid": to_tid,
        "amount": str(amt),
        "from_balance": str(_dec(sender.slha_balance)),
        "to_balance": str(_dec(receiver.slha_balance)),
    }


def admin_credit_slha(db: Session, *, telegram_id: int, amount: Decimal, note: Optional[str] = None) -> dict:
    amt = _dec(amount)
    if amt <= 0:
        raise ValueError("amount must be > 0")

    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).with_for_update().first()
    if not user:
        user = get_or_create_user(db, telegram_id, None)
        user = db.query(models.User).filter(models.User.telegram_id == telegram_id).with_for_update().first()

    user.slha_balance = _dec(user.slha_balance) + amt
    user.updated_at = _utcnow()
    db.add(user)
    db.commit()
    db.refresh(user)

    meta = {"note": note} if note else None
    ledger.create_entry(
        db,
        telegram_id=telegram_id,
        wallet_type="slha",
        direction="in",
        amount=amt,
        currency="SLHA",
        reason="admin_credit",
        meta=meta,
    )

    return {"telegram_id": telegram_id, "amount": str(amt), "balance": str(_dec(user.slha_balance))}
