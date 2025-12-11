import secrets
from decimal import Decimal
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # --- חובה לבוט ---
    BOT_TOKEN: str | None = None
    DATABASE_URL: str | None = None
    SECRET_KEY: str = secrets.token_urlsafe(32)

    # אדמין (לפקודות admin_credit / admin_menu וכו')
    ADMIN_USER_ID: str | None = None

    # כתובת בסיס ל־Webhook (למשל: https://tease-production.up.railway.app)
    WEBHOOK_URL: str | None = None

    # --- ארנק קהילתי / טוקן ---
    COMMUNITY_WALLET_ADDRESS: str | None = None
    COMMUNITY_WALLET_PRIVATE_KEY: str | None = None

    SLH_TOKEN_ADDRESS: str | None = None
    SLH_TOKEN_DECIMALS: int = 18

    # מחיר נומינלי ל-SLH בשקלים
    SLH_PRICE_NIS: Decimal = Decimal("444")

    # --- BSC / On-chain ---
    BSC_RPC_URL: str | None = None
    BSC_SCAN_BASE: str | None = "https://bscscan.com"

    # --- לינקים חיצוניים ---
    BUY_BNB_URL: str | None = None
    STAKING_INFO_URL: str | None = None
    DOCS_URL: str | None = None
    PUBLIC_BASE_URL: str | None = None

    # --- קבוצות / לוגים בטלגרם ---
    MAIN_COMMUNITY_CHAT_ID: str | None = None
    LOG_NEW_USERS_CHAT_ID: str | None = None
    LOG_TRANSACTIONS_CHAT_ID: str | None = None
    LOG_ERRORS_CHAT_ID: str | None = None
    REFERRAL_LOGS_CHAT_ID: str | None = None

    # --- שפות ---
    DEFAULT_LANGUAGE: str = "en"
    SUPPORTED_LANGUAGES: str | None = None  # למשל: "en,he,ru,es"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
