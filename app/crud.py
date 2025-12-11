from __future__ import annotations

from decimal import Decimal
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app import models


def _dec(x) -> Decimal:
    return Decimal(str(x))


# ===== Users & Wallets =====

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
            role="visitor",
            balance_slh=_dec("0"),
            slha_balance=_dec("0"),
        )
        db.add(user)
        db.commit()
        db.refresh(user)

        # create basic wallet
        w = models.Wallet(
            telegram_id=telegram_id,
            wallet_type="basic",
            is_active=True,
            balance_slh=_dec("0"),
            balance_slha=_dec("0"),
        )
        db.add(w)
        db.commit()
    else:
        # update username if changed
        if username and user.username != username:
            user.username = username
            db.add(user)
            db.commit()

        # ensure basic wallet exists
        w = (
            db.query(models.Wallet)
            .filter(
                and_(
                    models.Wallet.telegram_id == telegram_id,
                    models.Wallet.wallet_type == "basic",
                )
            )
            .first()
        )
        if not w:
            w = models.Wallet(
                telegram_id=telegram_id,
                wallet_type="basic",
                is_active=True,
                balance_slh=_dec("0"),
                balance_slha=_dec("0"),
            )
            db.add(w)
            db.commit()

    return user


def set_bnb_address(db: Session, user: models.User, address: str):
    user.bnb_address = address
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_wallet(db: Session, telegram_id: int, wallet_type: str) -> models.Wallet | None:
    return (
        db.query(models.Wallet)
        .filter(
            and_(
                models.Wallet.telegram_id == telegram_id,
                models.Wallet.wallet_type == wallet_type,
            )
        )
        .first()
    )


def ensure_investor_wallet(db: Session, telegram_id: int) -> models.Wallet:
    w = get_wallet(db, telegram_id, "investor")
    if not w:
        w = models.Wallet(
            telegram_id=telegram_id,
            wallet_type="investor",
            is_active=False,  # activated only after approve
            balance_slh=_dec("0"),
            balance_slha=_dec("0"),
        )
        db.add(w)
        db.commit()
        db.refresh(w)
    return w


# ===== Investor onboarding =====

def start_invest_onboarding(
    db: Session,
    telegram_id: int,
    referrer_tid: int | None,
    risk_ack: bool,
) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="candidate",
            risk_ack=bool(risk_ack),
            referrer_tid=referrer_tid,
        )
        db.add(prof)

    # bump user role -> candidate (if not investor already)
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )
    if user and user.role != "investor":
        user.role = "candidate"
        db.add(user)

    # ensure investor wallet exists (inactive)
    ensure_investor_wallet(db, telegram_id)

    db.commit()
    db.refresh(prof)
    return prof


def approve_investor(
    db: Session,
    admin_tid: int,
    telegram_id: int,
) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        # create profile if missing
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="investor",
            risk_ack=False,
            approved_at=datetime.now(timezone.utc),
        )
        db.add(prof)
    else:
        prof.status = "investor"
        prof.approved_at = datetime.now(timezone.utc)
        db.add(prof)

    # activate investor wallet
    w = ensure_investor_wallet(db, telegram_id)
    w.is_active = True
    db.add(w)

    # set user role
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == telegram_id)
        .first()
    )
    if user:
        user.role = "investor"
        db.add(user)

    # ledger event
    tx = models.Transaction(
        from_user=admin_tid,
        to_user=telegram_id,
        amount_slh=_dec("0"),
        tx_type="admin_approve_investor",
        meta=None,
    )
    db.add(tx)

    db.commit()
    db.refresh(prof)
    return prof


def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof or prof.status != "investor":
        return False
    w = get_wallet(db, telegram_id, "investor")
    return bool(w and w.is_active)


# ===== Referrals =====

def register_referral(
    db: Session,
    new_user_tid: int,
    referrer_tid: int,
    reward_slha: Decimal,
) -> bool:
    if new_user_tid == referrer_tid:
        return False

    # prevent duplicates
    existing = (
        db.query(models.Referral)
        .filter(
            and_(
                models.Referral.new_user_tid == new_user_tid,
                models.Referral.referrer_tid == referrer_tid,
            )
        )
        .first()
    )
    if existing:
        return False

    r = models.Referral(
        referrer_tid=referrer_tid,
        new_user_tid=new_user_tid,
        reward_slha=reward_slha,
    )
    db.add(r)

    # credit SLHA: referrer + new user
    ref_user = (
        db.query(models.User)
        .filter(models.User.telegram_id == referrer_tid)
        .first()
    )
    new_user = (
        db.query(models.User)
        .filter(models.User.telegram_id == new_user_tid)
        .first()
    )
    if ref_user:
        ref_user.slha_balance = (ref_user.slha_balance or _dec("0")) + reward_slha
        db.add(ref_user)
    if new_user:
        new_user.slha_balance = (new_user.slha_balance or _dec("0")) + reward_slha
        db.add(new_user)

    # ledger event (amount_slh=0)
    tx = models.Transaction(
        from_user=None,
        to_user=referrer_tid,
        amount_slh=_dec("0"),
        tx_type="referral_bonus_slha",
        meta=f"new_user={new_user_tid},reward_slha={reward_slha}",
    )
    db.add(tx)

    db.commit()
    return True


def count_referrals(db: Session, referrer_tid: int) -> int:
    return (
        db.query(models.Referral)
        .filter(models.Referral.referrer_tid == referrer_tid)
        .count()
    )


# ===== Deposits (report -> approve) =====

def create_deposit(
    db: Session,
    telegram_id: int,
    network: str,
    currency: str,
    amount,
    tx_hash: str | None,
    note: str | None,
) -> models.Deposit:
    dep = models.Deposit(
        telegram_id=telegram_id,
        network=network,
        currency=currency,
        amount=_dec(amount),
        tx_hash=tx_hash,
        status="pending",
        note=note,
    )
    db.add(dep)
    db.commit()
    db.refresh(dep)

    # ledger event
    tx = models.Transaction(
        from_user=telegram_id,
        to_user=None,
        amount_slh=_dec("0"),
        tx_type="deposit_reported",
        meta=f"deposit_id={dep.id},network={network},currency={currency},amount={dep.amount}",
    )
    db.add(tx)
    db.commit()
    return dep


def list_pending_deposits(db: Session, limit: int = 50) -> list[models.Deposit]:
    return (
        db.query(models.Deposit)
        .filter(models.Deposit.status == "pending")
        .order_by(models.Deposit.created_at.asc())
        .limit(limit)
        .all()
    )


def confirm_deposit_and_credit(
    db: Session,
    admin_tid: int,
    deposit_id: int,
    credit_slh,
) -> models.Deposit:
    dep = (
        db.query(models.Deposit)
        .filter(models.Deposit.id == deposit_id)
        .first()
    )
    if not dep:
        raise ValueError("Deposit not found.")
    if dep.status != "pending":
        raise ValueError("Deposit is not pending.")

    # must be approved investor
    if not is_investor_active(db, dep.telegram_id):
        raise ValueError("Target user is not an active investor (must be approved).")

    w = ensure_investor_wallet(db, dep.telegram_id)
    if not w.is_active:
        raise ValueError("Investor wallet is not active.")

    credit = _dec(credit_slh)
    if credit <= 0:
        raise ValueError("credit_slh must be > 0")

    # confirm deposit
    dep.status = "confirmed"
    dep.confirmed_by = admin_tid
    dep.confirmed_at = datetime.now(timezone.utc)
    db.add(dep)

    # credit investor wallet
    w.balance_slh = (w.balance_slh or _dec("0")) + credit
    db.add(w)

    # also keep backward-compat balance_slh on users (optional but helpful)
    user = (
        db.query(models.User)
        .filter(models.User.telegram_id == dep.telegram_id)
        .first()
    )
    if user:
        user.balance_slh = (user.balance_slh or _dec("0")) + credit
        db.add(user)

    # ledger tx
    tx = models.Transaction(
        from_user=admin_tid,
        to_user=dep.telegram_id,
        amount_slh=credit,
        tx_type="deposit_confirmed_credit_slh",
        meta=f"deposit_id={dep.id},network={dep.network},currency={dep.currency},amount={dep.amount}",
    )
    db.add(tx)

    db.commit()
    db.refresh(dep)
    return dep
