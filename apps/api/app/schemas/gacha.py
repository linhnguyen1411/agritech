from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class GachaPullRequest(BaseModel):
    gacha_type: str = Field("standard", pattern=r"^(standard|premium|event)$")
    quantity: int = Field(1, ge=1, le=10)


class ItemDefinitionResponse(BaseModel):
    id: str
    name: str
    rarity: str
    category: str
    effect_type: str | None = None
    effect_value: dict | None = None
    price_ftk: Decimal
    image_url: str | None = None

    model_config = {"from_attributes": True}


class GachaPullResult(BaseModel):
    pull_id: str
    item: ItemDefinitionResponse
    gacha_type: str
    cost_ftk: Decimal
    pulled_at: datetime
    tx_hash: str | None = None


class GachaPullResponse(BaseModel):
    results: list[GachaPullResult]
    total_cost_ftk: Decimal
    new_balance: Decimal
