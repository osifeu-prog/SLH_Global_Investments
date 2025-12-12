# app/crud.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy.orm import Session

from app import models


# ========= Users =========

def get_or_create_user(
    db: Session,
    telegram_id: int,
    username: Optional[str] = None,
) -> models.User:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        if username is not None and user.username != username:
            user.username = username
            db.add(user)
            db.commit()
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


# ========= Wallets =========

def get_or_create_wallet(
    db: Session,
    telegram_id: int,
    kind: str,
    deposits_enabled: bool = True,
    withdrawals_enabled: bool = False,
) -> models.Wallet:
    wallet = (
        db.query(models.Wallet)
        .filter(
            models.Wallet.telegram_id == telegram_id,
            models.Wallet.kind == kind,
        )
        .first()
    )
    if wallet:
        wallet.deposits_enabled = deposits_enabled
        wallet.withdrawals_enabled = withdrawals_enabled
        db.add(wallet)
        db.commit()
        return wallet

    wallet = models.Wallet(
        telegram_id=telegram_id,
        kind=kind,
        deposits_enabled=deposits_enabled,
        withdrawals_enabled=withdrawals_enabled,
        balance_slh=Decimal("0"),
    )
    db.add(wallet)
    db.commit()
    db.refresh(wallet)
    return wallet


# ========= Investor status =========

def is_investor_active(db: Session, telegram_id: int) -> bool:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        return False
    return str(prof.status).lower() == "active"


def start_invest_onboarding(
    db: Session,
    telegram_id: int,
    note: Optional[str] = None,
    risk_ack: bool = False,
) -> models.InvestorProfile:
    """
    פותח בקשת השקעה בצורה בטוחה:
    - תמיד מספק risk_ack (חובה ב-DB)
    - יוצר/מעדכן InvestorProfile
    - יוצר ארנק investor (הפקדות בלבד)
    """
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )

    if prof:
        prof.status = "candidate"
        prof.risk_ack = bool(risk_ack)
        if note:
            prof.note = note
        db.add(prof)
        db.commit()
        db.refresh(prof)
    else:
        prof = models.InvestorProfile(
            telegram_id=telegram_id,
            status="candidate",
            risk_ack=bool(risk_ack),
            note=note,
            created_at=datetime.utcnow(),
        )
        db.add(prof)
        db.commit()
        db.refresh(prof)

    # ודא ארנק משקיע
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
        prof = start_invest_onboarding(
            db,
            telegram_id=telegram_id,
            note="Auto-created on approve",
            risk_ack=True,
        )

    prof.status = "active"
    db.add(prof)

    # ארנק משקיע נשאר הפקדות בלבד (משיכות לפי מדיניות עתידית)
    get_or_create_wallet(
        db,
        telegram_id=telegram_id,
        kind="investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )

    db.commit()
    db.refresh(prof)
    return prof


def reject_investor(db: Session, telegram_id: int) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )
    if not prof:
        prof = start_invest_onboarding(
            db,
            telegram_id=telegram_id,
            note="Auto-created on reject",
            risk_ack=False,
        )

    prof.status = "rejected"
    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# ========= Referrals =========

def count_referrals(db: Session, telegram_id: int) -> int:
    return (
        db.query(models.Referral)
        .filter(models.Referral.referrer_tid == telegram_id)
        .count()
    )


def add_referral(
    db: Session,
    referrer_tid: int,
    referred_tid: int,
) -> bool:
    """
    מחזיר True אם נוצר רפרל חדש, False אם כבר קיים
    """
    if referrer_tid == referred_tid:
        return False

    exists = (
        db.query(models.Referral)
        .filter(models.Referral.referred_tid == referred_tid)
        .first()
    )
    if exists:
        return False

    ref = models.Referral(
        referrer_tid=referrer_tid,
        referred_tid=referred_tid,
    )
    db.add(ref)
    db.commit()
    return True


# ========= Transactions (בסיס) =========

def add_transaction(
    db: Session,
    from_user: Optional[int],
    to_user: Optional[int],
    amount_slh: Decimal,
    tx_type: str,
) -> models.Transaction:
    tx = models.Transaction(
        from_user=from_user,
        to_user=to_user,
        amount_slh=amount_slh,
        tx_type=tx_type,
    )
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return tx
