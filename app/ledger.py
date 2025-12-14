# app/ledger.py
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy import func, case, desc
from sqlalchemy.orm import Session

from app import models


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_decimal(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _canonical_json(meta: Dict[str, Any]) -> str:
    # Deterministic JSON so substring marker queries are stable.
    return json.dumps(meta, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def create_entry(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: str,
    direction: str,
    amount: Decimal,
    currency: str,
    reason: str,
    meta: Optional[Dict[str, Any]] = None,
) -> models.LedgerEntry:
    direction = direction.lower().strip()
    if direction not in ("in", "out"):
        raise ValueError("direction must be 'in' or 'out'")

    amt = _to_decimal(amount)
    if amt <= 0:
        raise ValueError("amount must be > 0")

    row = models.LedgerEntry(
        telegram_id=telegram_id,
        wallet_type=wallet_type,
        direction=direction,
        amount=amt,
        currency=currency.upper().strip(),
        reason=reason.strip(),
        meta=(_canonical_json(meta) if meta else None),
        created_at=_utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_balance(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: str,
    currency: str,
) -> Decimal:
    currency = currency.upper().strip()

    signed_amount = case(
        (models.LedgerEntry.direction == "in", models.LedgerEntry.amount),
        else_=-models.LedgerEntry.amount,
    )

    total = (
        db.query(func.coalesce(func.sum(signed_amount), 0))
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
            models.LedgerEntry.currency == currency,
        )
        .scalar()
    )
    return _to_decimal(total)


def get_statement(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: str,
    currency: Optional[str] = None,
    limit: int = 10,
) -> List[models.LedgerEntry]:
    q = (
        db.query(models.LedgerEntry)
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
        )
        .order_by(desc(models.LedgerEntry.id))
        .limit(limit)
    )
    if currency:
        q = q.filter(models.LedgerEntry.currency == currency.upper().strip())
    return q.all()


def has_interest_for_day(
    db: Session,
    *,
    telegram_id: int,
    wallet_type: str,
    currency: str,
    day: date,
) -> bool:
    marker = f'"accrual_date":"{day.isoformat()}"'
    row = (
        db.query(models.LedgerEntry.id)
        .filter(
            models.LedgerEntry.telegram_id == telegram_id,
            models.LedgerEntry.wallet_type == wallet_type,
            models.LedgerEntry.currency == currency.upper().strip(),
            models.LedgerEntry.reason == "interest",
            models.LedgerEntry.meta.isnot(None),
            models.LedgerEntry.meta.contains(marker),
        )
        .first()
    )
    return bool(row)
