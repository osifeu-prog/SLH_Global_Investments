from decimal import Decimal
from sqlalchemy.orm import Session

from app import models


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


# ---------- Wallet gating (Layer-0 / Investor) ----------

def get_or_create_wallet(
    db: Session,
    telegram_id: int,
    kind: str,
    deposits_enabled: bool = True,
    withdrawals_enabled: bool = False,
) -> models.Wallet:
    w = (
        db.query(models.Wallet)
        .filter(
            models.Wallet.telegram_id == telegram_id,
            models.Wallet.kind == kind,
        )
        .first()
    )
    if not w:
        w = models.Wallet(
            telegram_id=telegram_id,
            kind=kind,
            deposits_enabled=deposits_enabled,
            withdrawals_enabled=withdrawals_enabled,
        )
        db.add(w)
        db.commit()
        db.refresh(w)
    return w


def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        return False
    return (prof.status or "").lower() == "active"


def start_invest_onboarding(
    db: Session,
    telegram_id: int,
    note: str | None = None,
) -> models.InvestorProfile:
    """
    יוצר/מעדכן פרופיל משקיע ל-pending ומכין investor wallet:
    - deposits_enabled=True
    - withdrawals_enabled=False
    """
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="pending",
            note=note,
        )
        db.add(prof)
    else:
        prof.status = "pending"
        if note:
            prof.note = note

    db.commit()
    db.refresh(prof)

    # investor wallet exists (deposit-only until admin approves)
    get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )
    return prof


# ---------- Referrals ----------

def register_referral(db: Session, referrer_tid: int, referred_tid: int) -> bool:
    if referrer_tid == referred_tid:
        return False
    exists = (
        db.query(models.Referral)
        .filter(
            models.Referral.referrer_tid == referrer_tid,
            models.Referral.referred_tid == referred_tid,
        )
        .first()
    )
    if exists:
        return False

    r = models.Referral(referrer_tid=referrer_tid, referred_tid=referred_tid)
    db.add(r)
    db.commit()
    return True


def count_referrals(db: Session, referrer_tid: int) -> int:
    return (
        db.query(models.Referral)
        .filter(models.Referral.referrer_tid == referrer_tid)
        .count()
    )
