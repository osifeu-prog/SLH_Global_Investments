# app/core/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Core ---
    BOT_TOKEN: str | None = None
    DATABASE_URL: str
    SECRET_KEY: str | None = None

    WEBHOOK_URL: str | None = None
    ADMIN_USER_ID: str | None = None

    # --- Blockchain (BSC) ---
    BSC_RPC_URL: str | None = None
    BSC_SCAN_BASE: str | None = None

    SLH_TOKEN_ADDRESS: str | None = None
    SLH_TOKEN_DECIMALS: str | None = None
    SLH_PRICE_NIS: str | None = None

    COMMUNITY_WALLET_ADDRESS: str | None = None
    COMMUNITY_WALLET_PRIVATE_KEY: str | None = None

    # --- TON anchors ---
    TON_COMMUNITY_WALLET_ADDRESS: str | None = None
    TON_TREASURY_ADDRESS: str | None = None
    USDT_TON_TREASURY_ADDRESS: str | None = None

    DEFAULT_DEPOSIT_ASSET: str = "USDT_TON"  # USDT_TON / TON
    DEFAULT_APR: str = "0.18"                # display only (not a promise)

    # --- Rewards / referrals ---
    SLHA_REWARD_DEPOSIT_PER_ILS: str | None = None
    SLHA_REWARD_REFERRAL: str | None = None

    # --- Logging channels (optional) ---
    MAIN_COMMUNITY_CHAT_ID: str | None = None
    LOG_NEW_USERS_CHAT_ID: str | None = None
    LOG_TRANSACTIONS_CHAT_ID: str | None = None
    LOG_ERRORS_CHAT_ID: str | None = None
    REFERRAL_LOGS_CHAT_ID: str | None = None

    # --- i18n ---
    DEFAULT_LANGUAGE: str = "he"
    SUPPORTED_LANGUAGES: str | None = None

    # --- External AI (optional, future use) ---
    OPENAI_API_KEY: str | None = None
    OPENAI_MODEL: str | None = None

    # --- Public docs / UI ---
    DOCS_URL: str | None = None
    PUBLIC_BASE_URL: str | None = None


settings = Settings()
