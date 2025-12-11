from __future__ import annotations

from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import and_
from sqlalchemy.sql import func

from app import models


# ---------- Users ----------

def get_or_create_user(db: Session, telegram_id: int, username: str | None):
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )
    if not user:
        user = models.User(
            telegram_id=telegram_id,
            username=username,
            balance_slh=Decimal("0"),
            slha_balance=Decimal("0"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        if username and user.username != username:
            user.username = username
            db.add(user)
            db.commit()
            db.refresh(user)
    return user


def set_bnb_address(db: Session, user: models.User, address: str):
    user.bnb_address = address
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------- Investor onboarding ----------

def _get_or_create_investor_profile(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        prof = models.InvestorProfile(telegram_id=telegram_id, status="none")
        db.add(prof)
        db.commit()
        db.refresh(prof)
    return prof


def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    return bool(prof and (prof.status or "").lower() == "approved")


def request_investor(db: Session, telegram_id: int, note: str | None = None) -> models.InvestorProfile:
    prof = _get_or_create_investor_profile(db, telegram_id)
    if (prof.status or "none").lower() == "approved":
        return prof
    prof.status = "pending"
    prof.note = note
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def approve_investor(db: Session, telegram_id: int, note: str | None = None) -> models.InvestorProfile:
    prof = _get_or_create_investor_profile(db, telegram_id)
    prof.status = "approved"
    if note:
        prof.note = note
    db.add(prof)
    db.commit()
    db.refresh(prof)
    # ensure investor wallet exists
    create_wallet(db, telegram_id=telegram_id, kind="investor")
    return prof


def reject_investor(db: Session, telegram_id: int, note: str | None = None) -> models.InvestorProfile:
    prof = _get_or_create_investor_profile(db, telegram_id)
    prof.status = "rejected"
    if note:
        prof.note = note
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


def list_investor_candidates(db: Session, limit: int = 50) -> list[models.InvestorProfile]:
    return (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.status == "pending")
        .order_by(models.InvestorProfile.created_at.desc())
        .limit(limit)
        .all()
    )


# ---------- Wallets (Layer-0) ----------

def get_wallet(db: Session, telegram_id: int, kind: str = "user") -> models.Wallet | None:
    return (
        db.query(models.Wallet)
        .filter(and_(models.Wallet.telegram_id == telegram_id, models.Wallet.kind == kind))
        .first()
    )


def create_wallet(db: Session, telegram_id: int, kind: str = "user") -> models.Wallet:
    w = get_wallet(db, telegram_id, kind)
    if w:
        return w
    w = models.Wallet(telegram_id=telegram_id, kind=kind, deposits_enabled=True, withdrawals_enabled=False)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ---------- Ledger / transactions ----------

def change_balance(
    db: Session,
    user: models.User,
    delta_slh: float | Decimal,
    tx_type: str,
    from_user: int | None,
    to_user: int | None,
) -> models.Transaction:
    amount = Decimal(str(delta_slh))
    current = user.balance_slh or Decimal("0")
    user.balance_slh = current + amount

    tx = models.Transaction(
        from_user=from_user,
        to_user=to_user,
        amount_slh=amount,
        tx_type=tx_type,
    )

    db.add(user)
    db.add(tx)
    db.commit()
    db.refresh(user)
    db.refresh(tx)
    return tx


def internal_transfer(
    db: Session,
    sender: models.User,
    receiver: models.User,
    amount_slh: float | Decimal,
) -> models.Transaction:
    amount = Decimal(str(amount_slh))

    sender_balance = sender.balance_slh or Decimal("0")
    if sender_balance < amount:
        raise ValueError("Insufficient balance for this transfer.")

    sender.balance_slh = sender_balance - amount
    receiver_balance = receiver.balance_slh or Decimal("0")
    receiver.balance_slh = receiver_balance + amount

    tx = models.Transaction(
        from_user=sender.telegram_id,
        to_user=receiver.telegram_id,
        amount_slh=amount,
        tx_type="internal_transfer",
    )

    db.add(sender)
    db.add(receiver)
    db.add(tx)
    db.commit()
    db.refresh(sender)
    db.refresh(receiver)
    db.refresh(tx)
    return tx


def change_slha(
    db: Session,
    user: models.User,
    delta_slha: float | Decimal,
    reason: str,
) -> None:
    amount = Decimal(str(delta_slha))
    current = user.slha_balance or Decimal("0")
    user.slha_balance = current + amount

    # log note
    note = models.Transaction(
        from_user=None,
        to_user=user.telegram_id,
        amount_slh=Decimal("0"),
        tx_type=f"slha_{reason}",
    )
    db.add(user)
    db.add(note)
    db.commit()
    db.refresh(user)


# ---------- Referrals ----------

def register_referral(db: Session, referrer_tid: int, referred_tid: int) -> bool:
    """Create referral edge once per referred user."""
    if referrer_tid == referred_tid:
        return False

    existing = (
        db.query(models.Referral)
        .filter(models.Referral.referred_tid == referred_tid)
        .first()
    )
    if existing:
        return False

    edge = models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid)
    db.add(edge)
    db.commit()
    return True


def count_referrals(db: Session, referrer_tid: int) -> int:
    return (
        db.query(models.Referral)
        .filter(models.Referral.referrer_tid == referrer_tid)
        .count()
    )


# ---------- Deposits ----------

def create_deposit(
    db: Session,
    telegram_id: int,
    network: str,
    asset: str,
    tx_hash: str,
    from_address: str | None,
    to_address: str | None,
    amount: Decimal | None,
    status: str = "verified",
) -> models.Deposit:
    dep = models.Deposit(
        telegram_id=telegram_id,
        network=network,
        asset=asset,
        tx_hash=tx_hash,
        from_address=from_address,
        to_address=to_address,
        amount=amount,
        status=status,
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)
    return dep


def get_deposit_by_hash(db: Session, tx_hash: str) -> models.Deposit | None:
    return db.query(models.Deposit).filter(models.Deposit.tx_hash == tx_hash).first()


def list_deposits(db: Session, telegram_id: int, limit: int = 10) -> list[models.Deposit]:
    return (
        db.query(models.Deposit)
        .filter(models.Deposit.telegram_id == telegram_id)
        .order_by(models.Deposit.created_at.desc())
        .limit(limit)
        .all()
    )


def get_deposit(db: Session, deposit_id: int) -> models.Deposit | None:
    return db.query(models.Deposit).filter(models.Deposit.id == deposit_id).first()


def confirm_deposit(
    db: Session,
    deposit: models.Deposit,
    admin_tid: int,
    credit_slh: Decimal,
) -> models.Transaction:
    deposit.status = "confirmed"
    deposit.confirmed_slh = credit_slh
    deposit.confirmed_by = admin_tid
    deposit.confirmed_at = func.now()
    db.add(deposit)

    user = get_or_create_user(db, telegram_id=deposit.telegram_id, username=None)

    tx = change_balance(
        db,
        user=user,
        delta_slh=credit_slh,
        tx_type="deposit_credit",
        from_user=None,
        to_user=user.telegram_id,
    )
    db.commit()
    db.refresh(deposit)
    return tx
