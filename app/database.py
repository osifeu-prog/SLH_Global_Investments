# app/database.py
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.DATABASE_URL,
    future=True,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True,
)

# IMPORTANT: Base יחיד – של המודלים
from app.models import Base  # noqa: E402


def _ensure_schema():
    """
    Soft-migration: מוסיף defaults/עמודות חסרות בצורה בטוחה.
    המטרה: לא לקרוס על NOT NULL, וליישר קו עם הסכימה בפועל.
    """
    statements: list[str] = [
        # --------------------
        # investor_profiles
        # --------------------
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS risk_ack boolean NOT NULL DEFAULT false;",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS referrer_tid BIGINT;",
        "ALTER TABLE investor_profiles ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;",
        # לא נוגעים ב-default של status אם כבר קיים אצלך בלי default
        # אבל נדאג שלרשומות חדשות לא יהיה NULL (הקוד מטפל בזה)

        # --------------------
        # wallets – קריטי למניעת הקריסה
        # --------------------
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS wallet_type VARCHAR(16) NOT NULL DEFAULT 'base';",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS balance_slh NUMERIC(24,6) NOT NULL DEFAULT 0;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS balance_slha NUMERIC(24,8) NOT NULL DEFAULT 0;",

        # יישור עמודות שקיימות אצלך
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS kind VARCHAR(50) NOT NULL DEFAULT 'base';",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS deposits_enabled BOOLEAN NOT NULL DEFAULT TRUE;",
        "ALTER TABLE wallets ADD COLUMN IF NOT EXISTS withdrawals_enabled BOOLEAN NOT NULL DEFAULT FALSE;",

        # ברמת DB: להפוך את זה לחסין גם אם קוד ישן מנסה להכניס בלי שדות
        "ALTER TABLE wallets ALTER COLUMN wallet_type SET DEFAULT 'base';",
        "ALTER TABLE wallets ALTER COLUMN is_active SET DEFAULT TRUE;",
        "ALTER TABLE wallets ALTER COLUMN balance_slh SET DEFAULT 0;",
        "ALTER TABLE wallets ALTER COLUMN balance_slha SET DEFAULT 0;",

        # תיקון נתונים קיימים אם יש NULL-ים (בדרך כלל אצלך UPDATE 0 אבל זה בטוח)
        "UPDATE wallets SET wallet_type = COALESCE(wallet_type, kind, 'base') WHERE wallet_type IS NULL;",
        "UPDATE wallets SET is_active = COALESCE(is_active, TRUE) WHERE is_active IS NULL;",
        "UPDATE wallets SET balance_slh = COALESCE(balance_slh, 0) WHERE balance_slh IS NULL;",
        "UPDATE wallets SET balance_slha = COALESCE(balance_slha, 0) WHERE balance_slha IS NULL;",

        # --------------------
        # users – אופציונלי/בטוח
        # --------------------
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS slha_balance NUMERIC(24, 8) NOT NULL DEFAULT 0;",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();",

        # --------------------
        # referrals – אם חסר
        # --------------------
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referrer_tid BIGINT;",
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS referred_tid BIGINT;",
        "ALTER TABLE referrals ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ DEFAULT NOW();",
    ]

    with engine.begin() as conn:
        for sql in statements:
            conn.execute(text(sql))


def init_db():
    """
    1) create_all: יוצר טבלאות שחסרות לפי models.Base
    2) soft-migration: מיישר defaults/עמודות כדי שלא יהיו קריסות NOT NULL
    """
    from app import models  # noqa: F401  (רק כדי לטעון את כל המודלים)

    Base.metadata.create_all(bind=engine)
    _ensure_schema()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
