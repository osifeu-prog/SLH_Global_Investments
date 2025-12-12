# app/crud.py
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app import models


# ---------------- Users ----------------

def get_or_create_user(db: Session, telegram_id: int, username: str | None = None) -> models.User:
    user = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if user:
        if username is not None and hasattr(user, "username") and user.username != username:
            user.username = username
            db.add(user)
            db.commit()
        return user

    kwargs = {"telegram_id": telegram_id}
    if hasattr(models.User, "username"):
        kwargs["username"] = username
    if hasattr(models.User, "role"):
        kwargs["role"] = "user"
    if hasattr(models.User, "investor_status"):
        kwargs["investor_status"] = "none"
    if hasattr(models.User, "balance_slh"):
        kwargs["balance_slh"] = Decimal("0")
    if hasattr(models.User, "slha_balance"):
        kwargs["slha_balance"] = Decimal("0")

    user = models.User(**kwargs)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def set_bnb_address(db: Session, user: models.User, addr: str) -> models.User:
    if hasattr(user, "bnb_address"):
        user.bnb_address = addr
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------- Wallets ----------------

def get_wallet(db: Session, telegram_id: int, kind: str) -> models.Wallet | None:
    return (
        db.query(models.Wallet)
        .filter(models.Wallet.telegram_id == telegram_id, models.Wallet.kind == kind)
        .first()
    )


def get_or_create_wallet(
    db: Session,
    telegram_id: int,
    kind: str,
    deposits_enabled: bool = True,
    withdrawals_enabled: bool = False,
) -> models.Wallet:
    w = get_wallet(db, telegram_id, kind)
    if w:
        if hasattr(w, "deposits_enabled"):
            w.deposits_enabled = deposits_enabled
        if hasattr(w, "withdrawals_enabled"):
            w.withdrawals_enabled = withdrawals_enabled
        if hasattr(w, "is_active"):
            w.is_active = True
        db.add(w)
        db.commit()
        db.refresh(w)
        return w

    kwargs = {"telegram_id": telegram_id, "kind": kind}
    if hasattr(models.Wallet, "deposits_enabled"):
        kwargs["deposits_enabled"] = deposits_enabled
    if hasattr(models.Wallet, "withdrawals_enabled"):
        kwargs["withdrawals_enabled"] = withdrawals_enabled
    if hasattr(models.Wallet, "is_active"):
        kwargs["is_active"] = True
    if hasattr(models.Wallet, "balance_slh"):
        kwargs["balance_slh"] = Decimal("0")

    w = models.Wallet(**kwargs)
    db.add(w)
    db.commit()
    db.refresh(w)
    return w


# ---------------- Investors ----------------

def is_investor_active(db: Session, telegram_id: int) -> bool:
    # Prefer InvestorProfile if exists
    try:
        prof = (
            db.query(models.InvestorProfile)
            .filter(models.InvestorProfile.telegram_id == telegram_id)
            .first()
        )
        if prof and getattr(prof, "status", None):
            return str(prof.status).lower() in ("active", "approved")
    except Exception:
        pass

    # Fallback: user role/status
    u = db.query(models.User).filter(models.User.telegram_id == telegram_id).first()
    if not u:
        return False
    role = str(getattr(u, "role", "") or "").lower()
    inv_status = str(getattr(u, "investor_status", "") or "").lower()
    return role == "investor" or inv_status in ("approved", "active")


def start_invest_onboarding(
    db: Session,
    telegram_id: int,
    note: str | None = None,
    risk_ack: bool = True,   # ✅ תמיד נזין True כדי לא ליפול על NOT NULL
) -> models.InvestorProfile:
    prof = (
        db.query(models.InvestorProfile)
        .filter(models.InvestorProfile.telegram_id == telegram_id)
        .first()
    )

    if prof:
        if hasattr(prof, "status"):
            prof.status = "candidate"
        if hasattr(prof, "note"):
            prof.note = note
        # ✅ קריטי: risk_ack לא יכול להיות NULL
        if hasattr(prof, "risk_ack"):
            prof.risk_ack = bool(risk_ack)

        db.add(prof)
        db.commit()
        db.refresh(prof)

        # ensure investor wallet exists
        get_or_create_wallet(
            db,
            telegram_id=telegram_id,
            kind="investor",
            deposits_enabled=True,
            withdrawals_enabled=False,
        )
        return prof

    fields = {"telegram_id": telegram_id}

    if hasattr(models.InvestorProfile, "status"):
        fields["status"] = "candidate"
    if hasattr(models.InvestorProfile, "note"):
        fields["note"] = note

    # ✅ קריטי: אם השדה קיים - תמיד להכניס ערך (True/False), לא להשאיר NULL
    if hasattr(models.InvestorProfile, "risk_ack"):
        fields["risk_ack"] = bool(risk_ack)

    if hasattr(models.InvestorProfile, "created_at"):
        fields["created_at"] = datetime.utcnow()

    prof = models.InvestorProfile(**fields)
    db.add(prof)
    db.commit()
    db.refresh(prof)

    # ensure investor wallet exists (deposits only)
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
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on approve", risk_ack=True)

    if hasattr(prof, "status"):
        prof.status = "active"
    if hasattr(prof, "risk_ack"):
        prof.risk_ack = True

    # also mark user if fields exist
    u = get_or_create_user(db, telegram_id, None)
    if hasattr(u, "role"):
        u.role = "investor"
    if hasattr(u, "investor_status"):
        u.investor_status = "approved"

    # investor wallet: deposits yes, withdrawals still no
    w = get_or_create_wallet(
        db,
        telegram_id,
        "investor",
        deposits_enabled=True,
        withdrawals_enabled=False,
    )

    db.add(prof)
    db.add(u)
    db.add(w)
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
        prof = start_invest_onboarding(db, telegram_id, note="Auto-created on reject", risk_ack=True)

    if hasattr(prof, "status"):
        prof.status = "rejected"
    if hasattr(prof, "risk_ack"):
        prof.risk_ack = True

    db.add(prof)
    db.commit()
    db.refresh(prof)
    return prof


# ---------------- Referrals ----------------

def count_referrals(db: Session, telegram_id: int) -> int:
    # If you have a Referral model/table, use it. Otherwise return 0 safely.
    if hasattr(models, "Referral"):
        return db.query(models.Referral).filter(models.Referral.referrer_tid == telegram_id).count()
    if hasattr(models, "ReferralEvent"):
        return db.query(models.ReferralEvent).filter(models.ReferralEvent.referrer_tid == telegram_id).count()
    return 0
