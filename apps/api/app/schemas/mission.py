from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class MissionDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str | None = None
    mission_type: str
    target_value: int
    reward_ftk: Decimal
    reward_exp: int
    reward_item_id: str | None = None
    reset_type: str
    level_required: int

    model_config = {"from_attributes": True}


class UserMissionResponse(BaseModel):
    id: str
    mission_def_id: str
    mission_name: str
    mission_type: str
    progress: int
    target_value: int
    progress_percent: float
    is_completed: bool
    completed_at: datetime | None = None
    reward_claimed: bool
    reward_ftk: Decimal
    reward_exp: int

    model_config = {"from_attributes": True}


class ClaimRewardResponse(BaseModel):
    mission_id: str
    ftk_awarded: Decimal
    exp_awarded: int
    new_balance: Decimal
    new_exp: int
    leveled_up: bool
    new_level: int | None = None
