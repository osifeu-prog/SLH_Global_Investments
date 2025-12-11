from __future__ import annotations

from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Numeric,
    DateTime,
    Integer,
    Boolean,
    Text,
    ForeignKey,
)
from sqlalchemy.sql import func

from app.database import Base


class User(Base):
    """
    users:
    - לכל משתמש יש רשומה מיד ב-/start
    - role: visitor/candidate/investor
    """
    __tablename__ = "users"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String(255), index=True, nullable=True)

    # כתובת BSC לצפייה/קישור בלבד (לא משיכה)
    bnb_address = Column(String(255), nullable=True)

    # יתרה פנימית "ישנה" (נשאיר תאימות; בפועל Investor Wallet ינוהל בטבלת wallets)
    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)

    # נקודות פנימיות (רפררל/פעילות)
    slha_balance = Column(Numeric(24, 8), nullable=False, default=0)

    role = Column(String(32), nullable=False, default="visitor")  # visitor/candidate/investor
    lang = Column(String(8), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class InvestorProfile(Base):
    """
    investor_profiles:
    מסלול השקעה סגור:
    - candidate: התחיל אונבורדינג
    - investor: אושר ע"י אדמין
    """
    __tablename__ = "investor_profiles"

    telegram_id = Column(BigInteger, primary_key=True, index=True)
    status = Column(String(32), nullable=False, default="candidate")  # candidate/investor/rejected
    risk_ack = Column(Boolean, nullable=False, default=False)

    referrer_tid = Column(BigInteger, nullable=True)

    approved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Wallet(Base):
    """
    wallets:
    - basic: תמיד קיים (UX/תפריטים/זיהוי)
    - investor: נוצר למסלול השקעה; is_active רק אחרי approve
    """
    __tablename__ = "wallets"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)

    wallet_type = Column(String(16), nullable=False, default="basic")  # basic/investor
    is_active = Column(Boolean, nullable=False, default=True)

    balance_slh = Column(Numeric(24, 6), nullable=False, default=0)
    balance_slha = Column(Numeric(24, 8), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Deposit(Base):
    """
    deposits:
    דיווח הפקדה (pending) -> אישור אדמין (confirmed) -> זיכוי פנימי ב-wallet investor.
    """
    __tablename__ = "deposits"

    id = Column(Integer, primary_key=True, index=True)
    telegram_id = Column(BigInteger, index=True, nullable=False)

    network = Column(String(16), nullable=False, default="TON")  # TON/BNB
    currency = Column(String(16), nullable=False, default="TON")  # TON/USDT/BNB וכו'
    amount = Column(Numeric(24, 8), nullable=False, default=0)

    tx_hash = Column(String(255), nullable=True)  # אופציונלי
    status = Column(String(16), nullable=False, default="pending")  # pending/confirmed/rejected

    note = Column(Text, nullable=True)

    confirmed_by = Column(BigInteger, nullable=True)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Referral(Base):
    """
    referrals:
    רישום רפררל אמיתי: מי הפנה את מי, מתי, ומה הבונוס שנזקף.
    """
    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    referrer_tid = Column(BigInteger, index=True, nullable=False)
    new_user_tid = Column(BigInteger, index=True, nullable=False)

    reward_slha = Column(Numeric(24, 8), nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Transaction(Base):
    """
    transactions:
    ledger פנימי (SLH) + אירועים (כמו referral/deposit_confirmed).
    """
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    from_user = Column(BigInteger, nullable=True)
    to_user = Column(BigInteger, nullable=True)

    amount_slh = Column(Numeric(24, 6), nullable=False, default=0)
    tx_type = Column(String(64), nullable=False)

    meta = Column(Text, nullable=True)
