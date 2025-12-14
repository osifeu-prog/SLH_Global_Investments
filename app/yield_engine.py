# app/yield_engine.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_DOWN
from typing import Optional, Dict, Any, List

from sqlalchemy.orm import Session

from app import models
from app import crud
from app import ledger


def _d(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _quantize_money(x: Decimal) -> Decimal:
    # 8 decimals for stablecoins/jettons accounting in ledger
    return x.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)


@dataclass(frozen=True)
class AccrualResult:
    processed: int
    credited: int
    skipped: int
    total_interest: Decimal


def run_daily_interest_accrual(
    db: Session,
    *,
    apr: Decimal,
    currency: str,
    wallet_type: str = "investor",
    accrual_day: Optional[date] = None,
) -> AccrualResult:
    """
    ריבית יומית עם ריבית-דריבית:
    - מחשבים יתרה נוכחית מה-ledger
    - interest = balance * (apr/365)
    - כותבים ledger IN reason='interest'
    - idempotent ליום לפי meta.accrual_date
    """
    if accrual_day is None:
        accrual_day = date.today()

    apr = _d(apr)
    if apr < 0:
        raise ValueError("APR must be >= 0")

    currency = currency.upper().strip()
    daily_rate = apr / Decimal("365")

    # רק משקיעים פעילים
    actives = (
        db.query(models.InvestorProfile.telegram_id)
        .filter(models.InvestorProfile.status.in_(["active", "approved"]))
        .all()
    )
    tids = [x[0] for x in actives]

    processed = 0
    credited = 0
    skipped = 0
    total_interest = Decimal("0")

    for tid in tids:
        processed += 1

        # מניעת כפילות לאותו יום
        if ledger.has_interest_for_day(
            db,
            telegram_id=tid,
            wallet_type=wallet_type,
            currency=currency,
            day=accrual_day,
        ):
            skipped += 1
            continue

        bal = ledger.get_balance(db, telegram_id=tid, wallet_type=wallet_type, currency=currency)
        if bal <= 0:
            skipped += 1
            continue

        interest = _quantize_money(bal * daily_rate)
        if interest <= 0:
            skipped += 1
            continue

        ledger.create_entry(
            db,
            telegram_id=tid,
            wallet_type=wallet_type,
            direction="in",
            amount=interest,
            currency=currency,
            reason="interest",
            meta={"accrual_date": accrual_day.isoformat(), "apr": str(apr)},
        )
        credited += 1
        total_interest += interest

    return AccrualResult(
        processed=processed,
        credited=credited,
        skipped=skipped,
        total_interest=_quantize_money(total_interest),
    )
