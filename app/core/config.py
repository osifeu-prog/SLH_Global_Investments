# app/core/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BOT_TOKEN: str | None = None
    DATABASE_URL: str

    WEBHOOK_URL: str | None = None
    ADMIN_USER_ID: str | None = None

    # Rewards
    SLHA_REWARD_REFERRAL: str | None = None

    # Deposit anchors (TON)
    TON_TREASURY_ADDRESS: str | None = None
    USDT_TON_TREASURY_ADDRESS: str | None = None

    DEFAULT_DEPOSIT_ASSET: str = "USDT_TON"  # USDT_TON / TON
    DEFAULT_APR: str = "0.18"  # used for display/plan, not a promise

    DEFAULT_LANGUAGE: str = "he"


settings = Settings()
