# Append these functions to the END of app/crud.py

from decimal import Decimal
from typing import Optional, List
from sqlalchemy.orm import Session

from app import models, ledger


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def transfer_slha(db: Session, *, from_tid: int, to_tid: int, amount: Decimal, reason: str = "transfer", meta: Optional[dict] = None) -> models.InternalTransfer:
    if from_tid == to_tid:
        raise ValueError("cannot transfer to self")
    amt = _d(amount)
    if amt <= 0:
        raise ValueError("amount must be > 0")

    bal = ledger.get_balance(db, telegram_id=from_tid, wallet_type="investor", currency="SLHA")
    if bal < amt:
        raise ValueError("insufficient SLHA")

    # Audit via ledger (source of truth)
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
    amt = _d(amount_slha)
    if amt <= 0:
        raise ValueError("amount must be > 0")

    bal = ledger.get_balance(db, telegram_id=telegram_id, wallet_type="investor", currency="SLHA")
    if bal < amt:
        raise ValueError("insufficient SLHA")

    # Lock points (so they can't be transferred while pending)
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
