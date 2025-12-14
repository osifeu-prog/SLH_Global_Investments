# app/schemas.py
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    bnb_address: Optional[str] = None


class UserOut(UserBase):
    model_config = ConfigDict(from_attributes=True)

    balance_slh: float
    created_at: datetime


class TransactionBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_user: Optional[int] = None
    to_user: Optional[int] = None
    amount_slh: float
    status: str
    type: str
    created_at: datetime
