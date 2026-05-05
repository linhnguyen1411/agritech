from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class CreateListingRequest(BaseModel):
    item_def_id: str
    listing_type: str = Field("fixed", pattern=r"^(fixed|auction)$")
    price_ftk: Decimal = Field(..., gt=0)
    quantity: int = Field(1, ge=1)
    expires_hours: int | None = Field(None, ge=1, le=168)  # max 7 days


class MarketListingResponse(BaseModel):
    id: str
    seller_user_id: str
    item_def_id: str
    item_name: str
    item_rarity: str
    listing_type: str
    price_ftk: Decimal
    quantity: int
    status: str
    created_at: datetime
    expires_at: datetime | None = None

    model_config = {"from_attributes": True}


class BuyListingRequest(BaseModel):
    quantity: int = Field(1, ge=1)


class MarketTransactionResponse(BaseModel):
    id: str
    listing_id: str
    price_ftk: Decimal
    fee_ftk: Decimal
    burned_ftk: Decimal
    completed_at: datetime
    tx_hash: str | None = None

    model_config = {"from_attributes": True}


class MarketStatsResponse(BaseModel):
    total_volume_24h: Decimal
    total_transactions_24h: int
    total_burned_24h: Decimal
    active_listings: int
