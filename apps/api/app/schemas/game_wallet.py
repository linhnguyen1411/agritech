from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# ── Wallet overview ───────────────────────────────────────────────────────────

class WalletMeResponse(BaseModel):
    """Enriched wallet response including aggregated game stats."""

    user_id: str
    ftk_balance: Decimal
    exp_points: int
    level: int
    # streak
    current_streak: int
    longest_streak: int
    streak_multiplier: Decimal
    last_login_date: str | None       # ISO date or null
    # counts
    chickens_owned: int
    items_count: int

    model_config = {"from_attributes": True}


class WalletResponse(BaseModel):
    """Lightweight balance-only response (used internally)."""

    user_id: str
    ftk_balance: Decimal
    exp_points: int
    level: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Transaction history ───────────────────────────────────────────────────────

TxTypeFilter = Literal["earn", "spend", "burn", "transfer", "all"]

# Maps human-readable filter → concrete tx_type values stored in DB
TX_TYPE_GROUPS: dict[str, list[str]] = {
    "earn":     ["mint", "reward", "sale", "daily_checkin", "achievement", "mission"],
    "spend":    ["gacha", "purchase", "fee"],
    "burn":     ["burn"],
    "transfer": ["transfer"],
}


class FtkTransactionResponse(BaseModel):
    id: str
    amount: Decimal                 # positive = credit, negative = debit
    tx_type: str
    reference_id: str | None = None
    reference_type: str | None = None
    balance_before: Decimal
    balance_after: Decimal
    created_at: datetime
    notes: str | None = None

    model_config = {"from_attributes": True}


# ── Daily check-in ────────────────────────────────────────────────────────────

class CheckinResponse(BaseModel):
    already_claimed: bool           # True = idempotent hit, no FTK awarded again
    ftk_earned: Decimal             # 0 if already_claimed
    streak_day: int                 # current consecutive day count after this check-in
    bonus_multiplier: Decimal       # 1.0 or 2.0+
    streak_reward: Decimal | None = Field(
        None, description="Extra FTK awarded on 7-day milestone; None otherwise"
    )
    new_balance: Decimal
    next_milestone_in: int          # days until next 7-day milestone bonus


# ── Leaderboard entry (used by leaderboard router too) ───────────────────────

class LeaderboardEntry(BaseModel):
    rank: int
    user_id: str
    username: str
    level: int
    exp_points: int
    ftk_balance: Decimal
