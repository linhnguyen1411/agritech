"""Pydantic schemas for the chicken router."""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

# ── Shared / embedded ─────────────────────────────────────────────────────────

class ChickenLogEntry(BaseModel):
    id: str
    log_type: str
    data: dict | None = None
    notes: str | None = None
    performed_by_user_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class FeedingScheduleEntry(BaseModel):
    """One feeding event as shown in the schedule."""
    fed_at: datetime
    performed_by: str          # "user" | "iot"
    amount_grams: int | None = None


class AchievementBadge(BaseModel):
    key: str                   # machine-readable identifier
    label: str                 # human-readable
    earned: bool


# ── List item (GET /chickens) ─────────────────────────────────────────────────

class ChickenListItem(BaseModel):
    """Compact view for the chicken list endpoint."""
    id: str
    nft_token_id: str | None
    name: str
    health_score: Decimal
    weight_kg: Decimal
    age_days: int
    zone: str | None
    status: str
    nft_tier: str
    live_cam_url: str | None
    last_fed_at: datetime | None
    steps_today: int
    owner_since: datetime       # = created_at
    level: int
    experience: int

    model_config = {"from_attributes": True}


# ── Detail (GET /chickens/{id}) ───────────────────────────────────────────────

class ChickenDetail(ChickenListItem):
    """Full detail view with history and metadata."""
    chip_id: str | None
    blockchain_metadata_url: str | None
    history_30d: list[ChickenLogEntry] = Field(default_factory=list)
    achievement_badges: list[AchievementBadge] = Field(default_factory=list)
    feeding_schedule: list[FeedingScheduleEntry] = Field(
        default_factory=list,
        description="Feeding events from the last 7 days",
    )


# ── Feed response (POST /chickens/{id}/feed) ──────────────────────────────────

class FeedResponse(BaseModel):
    ftk_earned: Decimal
    exp_earned: int
    feeds_today: int
    quota_remaining: int
    next_feed_available_at: datetime | None = Field(
        None, description="None if quota already exhausted for today"
    )
    mqtt_dispatched: bool = Field(
        description="Whether the IoT command was sent to the broker"
    )


# ── Livestream token (GET /chickens/{id}/livestream-token) ────────────────────

class LivestreamTokenResponse(BaseModel):
    token: str
    stream_url: str | None     # composed HLS/WebRTC URL, None if cam not configured
    expires_at: datetime
    ttl_seconds: int


# ── Leaderboard (GET /chickens/public/leaderboard) ───────────────────────────

class ChickenLeaderboardEntry(BaseModel):
    rank: int
    chicken_id: str
    chicken_name: str
    nft_tier: str
    health_score: Decimal
    owner_username: str
    zone: str | None
    steps_today: int


# ── CRUD helpers (kept for backward-compat with existing POST / PATCH) ────────

class CreateChickenRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class UpdateChickenRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)


class ChickenResponse(BaseModel):
    """Legacy lightweight schema used by the old CRUD endpoints."""
    id: str
    user_id: str
    name: str
    level: int
    experience: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
