# app/crud.py
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Iterable

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models


def _utcnow():
    return datetime.now(timezone.utc)


def _dec(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


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
        balance_slh=Decimal("0"),
        slha_balance=Decimal("0"),
        role="user",
        investor_status="none",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_bnb_address(db: Session, user: models.User, addr: str) -> None:
    user.bnb_address = addr
    db.add(user)
    db.commit()
    db.refresh(user)


# ---------- Wallets ----------

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
    kind: str,
    deposits_enabled: bool,
    withdrawals_enabled: bool,
) -> models.Wallet:
    w = get_wallet(db, telegram_id, wallet_type)
    if w:
        w.wallet_type = wallet_type or w.wallet_type or "base"
        w.is_active = True if w.is_active is None else w.is_active
        w.balance_slh = Decimal("0") if w.balance_slh is None else w.balance_slh
        w.balance_slha = Decimal("0") if w.balance_slha is None else w.balance_slha

        w.kind = kind
        w.deposits_enabled = deposits_enabled
        w.withdrawals_enabled = withdrawals_enabled

        db.add(w)
        db.commit()
        db.refresh(w)
        return w

    w = models.Wallet(
        telegram_id=telegram_id,
        wallet_type=wallet_type,
        is_active=True,
        balance_slh=Decimal("0"),
        balance_slha=Decimal("0"),
        kind=kind,
        deposits_enabled=deposits_enabled,
        withdrawals_enabled=withdrawals_enabled,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ---------- Referrals ----------

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

    row = models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid)
    db.add(row)
    db.commit()
    return True


# ---------- Investor Profiles ----------

def get_investor_profile(db: Session, telegram_id: int) -> Optional[models.InvestorProfile]:
    return db.query(models.InvestorProfile).filter(models.InvestorProfile.telegram_id == telegram_id).first()


def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = get_investor_profile(db, telegram_id)
    if not prof:
        return False
    return str(prof.status or "").lower() in ("active", "approved")


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


# ---------- Ledger (critical) ----------

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
    # balance = sum(in) - sum(out)
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


# ---- Stage 2: Transfers + Redemption ----

from typing import List

def transfer_slha(db: Session, *, from_tid: int, to_tid: int, amount: Decimal, reason: str = "transfer", meta: Optional[dict] = None) -> models.InternalTransfer:
    if from_tid == to_tid:
        raise ValueError("cannot transfer to self")
    amt = Decimal(str(amount))
    if amt <= 0:
        raise ValueError("amount must be > 0")

    bal = ledger.get_balance(db, telegram_id=from_tid, wallet_type="investor", currency="SLHA")
    if bal < amt:
        raise ValueError("insufficient SLHA")

    ledger.create_entry(db, telegram_id=from_tid, wallet_type="investor", direction="out", amount=amt, currency="SLHA", reason="transfer_out", meta={"to": to_tid, **(meta or {})})
    ledger.create_entry(db, telegram_id=to_tid, wallet_type="investor", direction="in", amount=amt, currency="SLHA", reason="transfer_in", meta={"from": from_tid, **(meta or {})})

    row = models.InternalTransfer(
        from_telegram_id=from_tid,
        to_telegram_id=to_tid,
        amount=amt,
        currency="SLHA",
        reason=reason,
        meta=(None if meta is None else str(meta)),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def create_redemption_request(db: Session, *, telegram_id: int, amount_slha: Decimal, cohort: str, policy: str = "regular", payout_address: Optional[str] = None, note: Optional[str] = None) -> models.RedemptionRequest:
    amt = Decimal(str(amount_slha))
    if amt <= 0:
        raise ValueError("amount must be > 0")

    bal = ledger.get_balance(db, telegram_id=telegram_id, wallet_type="investor", currency="SLHA")
    if bal < amt:
        raise ValueError("insufficient SLHA")

    ledger.create_entry(db, telegram_id=telegram_id, wallet_type="investor", direction="out", amount=amt, currency="SLHA", reason="redeem_lock", meta={"policy": policy})

    row = models.RedemptionRequest(
        telegram_id=telegram_id,
        amount_slha=amt,
        cohort=(cohort or "standard"),
        policy=(policy or "regular"),
        status="pending",
        payout_address=payout_address,
        note=note,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_redemption_requests(db: Session, *, status: Optional[str] = None, limit: int = 20) -> List[models.RedemptionRequest]:
    q = db.query(models.RedemptionRequest).order_by(models.RedemptionRequest.id.desc())
    if status:
        q = q.filter(models.RedemptionRequest.status == status)
    return q.limit(limit).all()


def set_redemption_status(db: Session, *, req_id: int, status: str, note: Optional[str] = None) -> Optional[models.RedemptionRequest]:
    row = db.query(models.RedemptionRequest).filter(models.RedemptionRequest.id == req_id).first()
    if not row:
        return None
    row.status = status
    if note:
        row.note = note
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
