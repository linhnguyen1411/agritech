"""Game Wallet router.

Endpoints
---------
GET  /wallet/me
     Full player dashboard: balance, XP, level, streak,
     chickens_owned, items_count.

GET  /wallet/transactions?page&limit&type
     Paginated FTK ledger with earn / spend / burn / transfer filter.

POST /wallet/daily-checkin
     Idempotent daily check-in with streak × multiplier logic:
       - days 1-6   → base FTK × 1.0
       - day 7+     → base FTK × 2.0
       - every 7th  → extra streak milestone bonus
     Race-condition-safe: SELECT FOR UPDATE on game_wallets row.

Rate limit: 10 req / 60 s per user (WalletRateLimit).
"""
import math
import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select

from app.core.config import settings
from app.core.database import DbSession
from app.core.redis import cache_get, cache_set
from app.core.security import CurrentUserId, WalletRateLimit
from app.models.game_wallet import GameWallet
from app.models.item import UserItem
from app.models.streak import UserStreak
from app.models.user import Chicken
from app.schemas import ApiResponse
from app.schemas.game_wallet import (
    CheckinResponse,
    FtkTransactionResponse,
    TxTypeFilter,
    WalletMeResponse,
)
from app.schemas.common import PaginatedData
from app.services.ftk_service import FtkService

router = APIRouter()

_RATE = {"dependencies": [WalletRateLimit]}


# ── /me ───────────────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=ApiResponse[WalletMeResponse],
    summary="Full player wallet overview",
    **_RATE,
)
async def wallet_me(user_id: CurrentUserId, db: DbSession) -> ApiResponse[WalletMeResponse]:
    uid = uuid.UUID(user_id)

    # Wallet (create on first access)
    ftk = FtkService(db)
    wallet = await ftk.get_or_create_wallet(user_id)

    # Streak (may not exist yet)
    streak = await db.get(UserStreak, uid)

    # Aggregate counts in a single query each
    chicken_count: int = await db.scalar(
        select(func.count(Chicken.id)).where(Chicken.user_id == uid)
    ) or 0

    items_count: int = await db.scalar(
        select(func.coalesce(func.sum(UserItem.quantity), 0))
        .where(UserItem.user_id == uid)
    ) or 0

    return ApiResponse.ok(
        WalletMeResponse(
            user_id=user_id,
            ftk_balance=wallet.ftk_balance,
            exp_points=wallet.exp_points,
            level=wallet.level,
            current_streak=streak.current_streak if streak else 0,
            longest_streak=streak.longest_streak if streak else 0,
            streak_multiplier=streak.streak_multiplier if streak else Decimal("1.00"),
            last_login_date=streak.last_login_date.isoformat() if streak and streak.last_login_date else None,
            chickens_owned=chicken_count,
            items_count=items_count,
        )
    )


# ── /transactions ─────────────────────────────────────────────────────────────

@router.get(
    "/transactions",
    response_model=ApiResponse[PaginatedData[FtkTransactionResponse]],
    summary="Paginated FTK transaction history",
    **_RATE,
)
async def get_transactions(
    user_id: CurrentUserId,
    db: DbSession,
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=100, alias="limit", description="Items per page"),
    type: TxTypeFilter = Query("all", description="earn | spend | burn | transfer | all"),
) -> ApiResponse[PaginatedData[FtkTransactionResponse]]:
    svc = FtkService(db)
    offset = (page - 1) * limit
    rows, total = await svc.get_history(user_id, tx_filter=type, offset=offset, limit=limit)

    items = [FtkTransactionResponse.model_validate(r) for r in rows]
    total_pages = math.ceil(total / limit) if total else 0

    return ApiResponse.ok(
        PaginatedData(
            items=items,
            total=total,
            page=page,
            page_size=limit,
            total_pages=total_pages,
        )
    )


# ── /daily-checkin ────────────────────────────────────────────────────────────

@router.post(
    "/daily-checkin",
    response_model=ApiResponse[CheckinResponse],
    summary="Claim daily login reward (idempotent within the same UTC day)",
    **_RATE,
)
async def daily_checkin(
    user_id: CurrentUserId, db: DbSession
) -> ApiResponse[CheckinResponse]:
    """Streak logic
    ──────────────
    • First check-in ever or broken streak → streak resets to 1.
    • Last check-in was yesterday           → streak increments.
    • Last check-in was today               → idempotent (no double credit).

    Multiplier
    ──────────
    streak_day < STREAK_DOUBLE_THRESHOLD  → multiplier = 1.0
    streak_day ≥ STREAK_DOUBLE_THRESHOLD  → multiplier = 2.0

    Milestone bonus
    ───────────────
    Every STREAK_DOUBLE_THRESHOLD days (7, 14, 21 …)
    an extra STREAK_MILESTONE_FTK is awarded.

    Race conditions
    ───────────────
    Uses SELECT … FOR UPDATE on both game_wallets and user_streaks
    so concurrent requests for the same user are serialised by Postgres.
    """
    uid = uuid.UUID(user_id)
    today = datetime.now(UTC).date()

    # ── 1. Idempotency check via Redis (fast path, avoids DB round-trip) ──
    idem_key = f"checkin:{user_id}:{today.isoformat()}"
    if await cache_get(idem_key):
        # Already claimed today – return current state without DB write
        wallet = await FtkService(db).get_balance(user_id)
        streak = await db.get(UserStreak, uid)
        current_streak = streak.current_streak if streak else 1
        multiplier = _calc_multiplier(current_streak)
        return ApiResponse.ok(
            CheckinResponse(
                already_claimed=True,
                ftk_earned=Decimal("0"),
                streak_day=current_streak,
                bonus_multiplier=multiplier,
                streak_reward=None,
                new_balance=wallet.ftk_balance,
                next_milestone_in=_days_to_next_milestone(current_streak),
            )
        )

    # ── 2. Acquire row-level locks (prevents double-spend race) ───────────
    wallet_result = await db.execute(
        select(GameWallet).where(GameWallet.user_id == uid).with_for_update()
    )
    wallet = wallet_result.scalar_one_or_none()
    if wallet is None:
        ftk_svc = FtkService(db)
        wallet = await ftk_svc.get_or_create_wallet(user_id)

    streak_result = await db.execute(
        select(UserStreak).where(UserStreak.user_id == uid).with_for_update()
    )
    streak = streak_result.scalar_one_or_none()

    # ── 3. Compute new streak state ───────────────────────────────────────
    if streak is None:
        streak = UserStreak(user_id=uid)
        db.add(streak)

    already_checked_in = streak.last_login_date == today
    if already_checked_in:
        # DB confirms already claimed (Redis key may have expired) → idempotent
        multiplier = _calc_multiplier(streak.current_streak)
        return ApiResponse.ok(
            CheckinResponse(
                already_claimed=True,
                ftk_earned=Decimal("0"),
                streak_day=streak.current_streak,
                bonus_multiplier=multiplier,
                streak_reward=None,
                new_balance=wallet.ftk_balance,
                next_milestone_in=_days_to_next_milestone(streak.current_streak),
            )
        )

    yesterday = _yesterday(today)
    if streak.last_login_date == yesterday:
        streak.current_streak += 1
    else:
        streak.current_streak = 1  # broken streak – reset

    streak.last_login_date = today
    if streak.current_streak > streak.longest_streak:
        streak.longest_streak = streak.current_streak

    # ── 4. Calculate reward ───────────────────────────────────────────────
    multiplier = _calc_multiplier(streak.current_streak)
    streak.streak_multiplier = multiplier

    base = Decimal(str(settings.DAILY_CHECKIN_BASE_FTK))
    ftk_earned = (base * multiplier).quantize(Decimal("0.00000001"))

    milestone_reward: Decimal | None = None
    if streak.current_streak % settings.STREAK_DOUBLE_THRESHOLD == 0:
        milestone_reward = Decimal(str(settings.STREAK_MILESTONE_FTK))
        ftk_earned += milestone_reward

    # ── 5. Persist FTK changes (inside existing transaction) ─────────────
    ftk_svc = FtkService(db)
    await ftk_svc._record(
        wallet=wallet,
        delta=ftk_earned,
        tx_type="daily_checkin",
        reference_id=None,
        reference_type="streak",
        notes=(
            f"Day {streak.current_streak} streak"
            + (f" – {settings.STREAK_DOUBLE_THRESHOLD}-day milestone bonus" if milestone_reward else "")
        ),
    )

    await db.flush()

    # ── 6. Set Redis idempotency key (expire at midnight UTC) ─────────────
    seconds_until_midnight = _seconds_until_midnight(today)
    await cache_set(idem_key, "1", ttl=seconds_until_midnight)

    return ApiResponse.ok(
        CheckinResponse(
            already_claimed=False,
            ftk_earned=ftk_earned,
            streak_day=streak.current_streak,
            bonus_multiplier=multiplier,
            streak_reward=milestone_reward,
            new_balance=wallet.ftk_balance,
            next_milestone_in=_days_to_next_milestone(streak.current_streak),
        )
    )


# ── Private helpers ───────────────────────────────────────────────────────────

def _calc_multiplier(streak_day: int) -> Decimal:
    if streak_day >= settings.STREAK_DOUBLE_THRESHOLD:
        return Decimal("2.00")
    return Decimal("1.00")


def _days_to_next_milestone(current: int) -> int:
    threshold = settings.STREAK_DOUBLE_THRESHOLD
    return threshold - (current % threshold)


def _yesterday(today: date) -> date:
    from datetime import timedelta
    return today - timedelta(days=1)


def _seconds_until_midnight(today: date) -> int:
    """Seconds from now until 00:00:00 UTC tomorrow."""
    from datetime import timedelta
    now = datetime.now(UTC)
    tomorrow_midnight = datetime(today.year, today.month, today.day, tzinfo=UTC) + timedelta(days=1)
    delta = tomorrow_midnight - now
    return max(int(delta.total_seconds()), 1)
