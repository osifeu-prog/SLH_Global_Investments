
# ADDITIONS FOR STAGE 2 (keep existing content above)

from sqlalchemy import Column, Integer, BigInteger, String, Numeric, DateTime, Text
from sqlalchemy.sql import func

class InternalTransfer(Base):
    __tablename__ = "internal_transfers"

    id = Column(Integer, primary_key=True)
    from_telegram_id = Column(BigInteger, nullable=False)
    to_telegram_id = Column(BigInteger, nullable=False)
    amount = Column(Numeric(24,8), nullable=False)
    currency = Column(String(16), default="SLHA")
    reason = Column(String(32), default="transfer")
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class RedemptionRequest(Base):
    __tablename__ = "redemption_requests"

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, nullable=False)
    amount_slha = Column(Numeric(24,8), nullable=False)
    cohort = Column(String(32), default="standard")
    policy = Column(String(32), default="regular")  # regular / early
    status = Column(String(32), default="pending") # pending/approved/rejected/paid
    note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
