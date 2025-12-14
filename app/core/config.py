# app/core/config.py
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BOT_TOKEN: str | None = None
    DATABASE_URL: str

    WEBHOOK_URL: str | None = None
    ADMIN_USER_ID: str | None = None

    # תגמולים אופציונליים
    SLHA_REWARD_REFERRAL: str | None = None

    # טקסטים/שפה (לא חובה, אבל נוח)
    DEFAULT_LANGUAGE: str | None = "he"


settings = Settings()
