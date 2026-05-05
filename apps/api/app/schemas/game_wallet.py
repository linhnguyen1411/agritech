from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class WalletResponse(BaseModel):
    user_id: str
    ftk_balance: Decimal
    exp_points: int
    level: int
    created_at: datetime

    model_config = {"from_attributes": True}


class FtkTransactionResponse(BaseModel):
    id: str
    amount: Decimal
    tx_type: str
    reference_type: str | None = None
    balance_before: Decimal
    balance_after: Decimal
    created_at: datetime
    notes: str | None = None

    model_config = {"from_attributes": True}


class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    level: int
    exp_points: int
    ftk_balance: Decimal
