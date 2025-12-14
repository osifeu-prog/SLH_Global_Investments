# Paste this block at the END of app/models.py (after Base is defined and after your existing models)

from sqlalchemy import Column, Integer, BigInteger, String, Numeric, DateTime, Text, Index
from sqlalchemy.sql import func

class InternalTransfer(Base):
    __tablename__ = "internal_transfers"

    id = Column(Integer, primary_key=True)
    from_telegram_id = Column(BigInteger, index=True, nullable=False)
    to_telegram_id = Column(BigInteger, index=True, nullable=False)
    amount = Column(Numeric(24, 8), nullable=False)
    currency = Column(String(16), nullable=False, default="SLHA")
    reason = Column(String(32), nullable=False, default="transfer")
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_internal_transfers_from", "from_telegram_id"),
        Index("ix_internal_transfers_to", "to_telegram_id"),
    )


class RedemptionRequest(Base):
    __tablename__ = "redemption_requests"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)
    amount_slha = Column(Numeric(24, 8), nullable=False)
    cohort = Column(String(32), nullable=False, default="standard")
    policy = Column(String(32), nullable=False, default="regular")    # regular / early
    status = Column(String(32), nullable=False, default="pending")    # pending / approved / rejected / paid
    payout_address = Column(String(128), nullable=True)               # future SLH on-chain address (optional)
    note = Column(Text, nullable=True)
    meta = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    __table_args__ = (
        Index("ix_redemption_requests_tid", "telegram_id"),
        Index("ix_redemption_requests_status", "status"),
    )
