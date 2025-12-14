
# ADDITIONS FOR STAGE 2 (append to file)

from decimal import Decimal
from app import ledger, models

def transfer_slha(db, from_tid:int, to_tid:int, amount:Decimal):
    if amount <= 0:
        raise ValueError("amount must be positive")

    bal = ledger.get_balance(db, telegram_id=from_tid, wallet_type="investor", currency="SLHA")
    if bal < amount:
        raise ValueError("insufficient balance")

    ledger.create_entry(db, telegram_id=from_tid, wallet_type="investor",
                        direction="out", amount=amount, currency="SLHA",
                        reason="transfer_out", meta={"to": to_tid})

    ledger.create_entry(db, telegram_id=to_tid, wallet_type="investor",
                        direction="in", amount=amount, currency="SLHA",
                        reason="transfer_in", meta={"from": from_tid})

    row = models.InternalTransfer(
        from_telegram_id=from_tid,
        to_telegram_id=to_tid,
        amount=amount,
        currency="SLHA"
    )
    db.add(row)
    db.commit()
    return row


def create_redemption_request(db, telegram_id:int, amount:Decimal, cohort:str, policy:str):
    bal = ledger.get_balance(db, telegram_id=telegram_id, wallet_type="investor", currency="SLHA")
    if bal < amount:
        raise ValueError("insufficient balance")

    ledger.create_entry(db, telegram_id=telegram_id, wallet_type="investor",
                        direction="out", amount=amount, currency="SLHA",
                        reason="redeem_lock", meta={"policy": policy})

    row = models.RedemptionRequest(
        telegram_id=telegram_id,
        amount_slha=amount,
        cohort=cohort,
        policy=policy,
        status="pending"
    )
    db.add(row)
    db.commit()
    return row
