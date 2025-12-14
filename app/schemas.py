from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    telegram_id: int
    username: Optional[str] = None
    bnb_address: Optional[str] = None


class UserOut(UserBase):
    balance_slh: float
    created_at: datetime

    class Config:
        from_attributes = True


class TransactionBase(BaseModel):
    from_user: Optional[int] = None
    to_user: Optional[int] = None
    amount_slh: float
    status: str
    type: str
    created_at: datetime

    class Config:
        from_attributes = True
