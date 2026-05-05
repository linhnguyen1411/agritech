from datetime import datetime

from pydantic import BaseModel, Field


class CreateChickenRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UpdateChickenRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)


class ChickenResponse(BaseModel):
    id: str
    user_id: str
    name: str
    level: int
    experience: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
