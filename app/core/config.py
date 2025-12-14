# app/core/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BOT_TOKEN: str | None = None
    DATABASE_URL: str

    WEBHOOK_URL: str | None = None
    ADMIN_USER_ID: str | None = None

    SLHA_REWARD_REFERRAL: str | None = None
    DEFAULT_LANGUAGE: str | None = "he"

    # Deposits / treasury
    TON_TREASURY_ADDRESS: str | None = None
    USDT_TON_TREASURY_ADDRESS: str | None = None
    DEFAULT_DEPOSIT_ASSET: str | None = "USDT_TON"  # USDT_TON / TON

    # Yield model (accounting)
    DEFAULT_APR: str | None = "0.0"  # e.g. 0.18 for 18%
    LEDGER_DEFAULT_WALLET_TYPE: str | None = "investor"


settings = Settings()
