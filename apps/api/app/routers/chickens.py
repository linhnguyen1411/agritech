"""Chicken router.

Endpoints
---------
GET  /chickens
     Danh sách gà của user đang login.

GET  /chickens/public/leaderboard
     Top 20 gà health_score cao nhất – public, cached Redis 5 min.
     ⚠ Route must be declared BEFORE /{chicken_id} to avoid path collision.

GET  /chickens/{chicken_id}
     Chi tiết gà: full 30-ngày history, achievement badges, feeding schedule,
     blockchain metadata.

POST /chickens/{chicken_id}/feed
     Đặt lệnh cho ăn.
     • Chỉ Silver NFT trở lên.
     • Validate owner + quota hàng ngày theo tier.
     • Ghi ChickenLog, credit +15 FTK / +10 EXP.
     • Publish MQTT /farm/nft/{chip_id}/feed (fire-and-forget).

GET  /chickens/{chicken_id}/livestream-token
     Tạo JWT livestream token hết hạn 1 giờ.
     • Owner luôn được phép.
     • Subscriber cũng được phép (checked via subscription flag in future).
"""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from jose import jwt
from sqlalchemy import and_, func, select

from app.core.config import settings
from app.core.database import DbSession
from app.core.mqtt import publish_feed_command
from app.core.redis import cache_get, cache_set
from app.core.security import CurrentUserId, make_rate_limit_dep
from app.models.chicken_log import ChickenLog
from app.models.user import Chicken, NFT_TIER_RANK, User
from app.schemas import ApiResponse
from app.schemas.chicken import (
    AchievementBadge,
    ChickenDetail,
    ChickenLeaderboardEntry,
    ChickenListItem,
    ChickenLogEntry,
    FeedResponse,
    FeedingScheduleEntry,
    LivestreamTokenResponse,
)
from app.schemas.common import PaginatedData
from app.services.ftk_service import FtkService

router = APIRouter()

_LEADERBOARD_TTL = 300          # Redis cache: 5 minutes
_LEADERBOARD_LIMIT = 20
_FEED_REWARD_FTK = Decimal(str(settings.FEED_REWARD_FTK))
_FEED_REWARD_EXP = settings.FEED_REWARD_EXP

# Per-endpoint rate limits
_ChickenReadRL = Depends(make_rate_limit_dep(limit=30))
_ChickenWriteRL = Depends(make_rate_limit_dep(limit=10))


# ── Helper: verify ownership ──────────────────────────────────────────────────

async def _get_owned_chicken(chicken_id: str, user_id: str, db: DbSession) -> Chicken:
    chicken = await db.get(Chicken, uuid.UUID(chicken_id))
    if chicken is None or str(chicken.user_id) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chicken not found")
    return chicken


# ── Helper: build list item ───────────────────────────────────────────────────

def _to_list_item(c: Chicken) -> ChickenListItem:
    return ChickenListItem(
        id=str(c.id),
        nft_token_id=c.nft_token_id,
        name=c.name,
        health_score=c.health_score,
        weight_kg=c.weight_kg,
        age_days=c.age_days,
        zone=c.zone,
        status=c.status,
        nft_tier=c.nft_tier,
        live_cam_url=c.live_cam_url,
        last_fed_at=c.last_fed_at,
        steps_today=c.steps_today,
        owner_since=c.owner_since,
        level=c.level,
        experience=c.experience,
    )


# ── Helper: compute achievement badges ───────────────────────────────────────

async def _compute_badges(chicken: Chicken, db: DbSession) -> list[AchievementBadge]:
    uid = chicken.id

    # Count total feeds
    feed_count: int = await db.scalar(
        select(func.count(ChickenLog.id)).where(
            ChickenLog.chicken_id == uid,
            ChickenLog.log_type == "fed",
        )
    ) or 0

    badges: list[AchievementBadge] = [
        AchievementBadge(
            key="well_fed",
            label="Well Fed",
            earned=feed_count >= 10,
        ),
        AchievementBadge(
            key="healthy",
            label="Healthy Star",
            earned=chicken.health_score >= Decimal("90"),
        ),
        AchievementBadge(
            key="marathon_runner",
            label="Marathon Runner",
            earned=chicken.steps_today >= 1000,
        ),
        AchievementBadge(
            key="elder",
            label="Elder Chicken",
            earned=chicken.age_days >= 180,
        ),
        AchievementBadge(
            key="champion",
            label="Farm Champion",
            earned=(
                chicken.health_score >= Decimal("95")
                and NFT_TIER_RANK.get(chicken.nft_tier, 0) >= NFT_TIER_RANK["gold"]
            ),
        ),
        AchievementBadge(
            key="nft_owner",
            label="NFT Owner",
            earned=chicken.nft_token_id is not None,
        ),
    ]
    return badges


# ══════════════════════════════════════════════════════════════════════════════
# 1. GET /  – List user's chickens
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/",
    response_model=ApiResponse[PaginatedData[ChickenListItem]],
    summary="List all chickens owned by the current user",
    dependencies=[_ChickenReadRL],
)
async def list_chickens(
    user_id: CurrentUserId,
    db: DbSession,
    status_filter: str | None = Query(None, alias="status"),
    tier_filter: str | None = Query(None, alias="tier"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse[PaginatedData[ChickenListItem]]:
    uid = uuid.UUID(user_id)
    q = select(Chicken).where(Chicken.user_id == uid)

    if status_filter:
        q = q.where(Chicken.status == status_filter)
    if tier_filter:
        q = q.where(Chicken.nft_tier == tier_filter)

    # Total count
    count_q = select(func.count()).select_from(q.subquery())
    total: int = await db.scalar(count_q) or 0

    # Paginated rows
    rows = (
        await db.execute(
            q.order_by(Chicken.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    import math
    return ApiResponse.ok(
        PaginatedData(
            items=[_to_list_item(c) for c in rows],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        )
    )


# ══════════════════════════════════════════════════════════════════════════════
# 2. GET /public/leaderboard  – Top 20 by health score (no auth, cached)
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/public/leaderboard",
    response_model=ApiResponse[list[ChickenLeaderboardEntry]],
    summary="Top 20 chickens by health score (public, cached 5 min)",
)
async def public_leaderboard(db: DbSession) -> ApiResponse[list[ChickenLeaderboardEntry]]:
    cache_key = "chicken:leaderboard:health"
    cached = await cache_get(cache_key)
    if cached:
        return ApiResponse.ok([ChickenLeaderboardEntry(**row) for row in cached])

    rows = (
        await db.execute(
            select(Chicken, User.username)
            .join(User, Chicken.user_id == User.id)
            .where(Chicken.status == "active")
            .order_by(Chicken.health_score.desc())
            .limit(_LEADERBOARD_LIMIT)
        )
    ).all()

    entries = [
        ChickenLeaderboardEntry(
            rank=idx + 1,
            chicken_id=str(row.Chicken.id),
            chicken_name=row.Chicken.name,
            nft_tier=row.Chicken.nft_tier,
            health_score=row.Chicken.health_score,
            owner_username=row.username,
            zone=row.Chicken.zone,
            steps_today=row.Chicken.steps_today,
        )
        for idx, row in enumerate(rows)
    ]

    await cache_set(cache_key, [e.model_dump() for e in entries], ttl=_LEADERBOARD_TTL)
    return ApiResponse.ok(entries)


# ══════════════════════════════════════════════════════════════════════════════
# 3. GET /{chicken_id}  – Full detail
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{chicken_id}",
    response_model=ApiResponse[ChickenDetail],
    summary="Full chicken detail with 30-day history and achievement badges",
    dependencies=[_ChickenReadRL],
)
async def get_chicken(
    chicken_id: str,
    user_id: CurrentUserId,
    db: DbSession,
) -> ApiResponse[ChickenDetail]:
    chicken = await _get_owned_chicken(chicken_id, user_id, db)
    cid = uuid.UUID(chicken_id)

    # 30-day history (all log types)
    since_30d = datetime.now(UTC) - timedelta(days=30)
    history_rows = (
        await db.execute(
            select(ChickenLog)
            .where(
                ChickenLog.chicken_id == cid,
                ChickenLog.created_at >= since_30d,
            )
            .order_by(ChickenLog.created_at.desc())
            .limit(200)
        )
    ).scalars().all()
    history = [ChickenLogEntry.model_validate(r) for r in history_rows]

    # Feeding schedule – last 7 days "fed" events
    since_7d = datetime.now(UTC) - timedelta(days=7)
    feed_rows = (
        await db.execute(
            select(ChickenLog)
            .where(
                ChickenLog.chicken_id == cid,
                ChickenLog.log_type == "fed",
                ChickenLog.created_at >= since_7d,
            )
            .order_by(ChickenLog.created_at.desc())
        )
    ).scalars().all()

    feeding_schedule = [
        FeedingScheduleEntry(
            fed_at=r.created_at,
            performed_by="user" if r.performed_by_user_id else "iot",
            amount_grams=(r.data or {}).get("amount_grams"),
        )
        for r in feed_rows
    ]

    badges = await _compute_badges(chicken, db)

    detail = ChickenDetail(
        **_to_list_item(chicken).model_dump(),
        chip_id=chicken.chip_id,
        blockchain_metadata_url=chicken.blockchain_metadata_url,
        history_30d=history,
        achievement_badges=badges,
        feeding_schedule=feeding_schedule,
    )
    return ApiResponse.ok(detail)


# ══════════════════════════════════════════════════════════════════════════════
# 4. POST /{chicken_id}/feed
# ══════════════════════════════════════════════════════════════════════════════

@router.post(
    "/{chicken_id}/feed",
    response_model=ApiResponse[FeedResponse],
    summary="Feed a chicken (Silver NFT or above). Rewards +15 FTK, +10 EXP.",
    dependencies=[_ChickenWriteRL],
)
async def feed_chicken(
    chicken_id: str,
    user_id: CurrentUserId,
    db: DbSession,
) -> ApiResponse[FeedResponse]:
    # ── 1. Ownership check ────────────────────────────────────────────────
    chicken = await _get_owned_chicken(chicken_id, user_id, db)

    # ── 2. Tier permission check ──────────────────────────────────────────
    if not chicken.can_feed():
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Feeding requires Silver NFT or above. "
            f"Current tier: {chicken.nft_tier}.",
        )

    # ── 3. Daily quota check (SELECT FOR UPDATE on chicken row) ───────────
    locked_result = await db.execute(
        select(Chicken)
        .where(Chicken.id == uuid.UUID(chicken_id))
        .with_for_update()
    )
    chicken = locked_result.scalar_one()   # re-fetch with lock

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    feeds_today: int = await db.scalar(
        select(func.count(ChickenLog.id)).where(
            and_(
                ChickenLog.chicken_id == chicken.id,
                ChickenLog.log_type == "fed",
                ChickenLog.created_at >= today_start,
            )
        )
    ) or 0

    quota = chicken.daily_feed_quota
    if feeds_today >= quota:
        # Calculate reset time (tomorrow 00:00 UTC)
        tomorrow = today_start + timedelta(days=1)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Daily feed quota exhausted ({feeds_today}/{quota}). "
            f"Resets at {tomorrow.isoformat()}.",
        )

    # ── 4. Record ChickenLog ──────────────────────────────────────────────
    correlation_id = str(uuid.uuid4())
    log = ChickenLog(
        chicken_id=chicken.id,
        performed_by_user_id=uuid.UUID(user_id),
        log_type="fed",
        data={
            "amount_grams": 50,
            "correlation_id": correlation_id,
            "chip_id": chicken.chip_id,
            "nft_token_id": chicken.nft_token_id,
        },
        notes=f"Fed via game app by user {user_id}",
    )
    db.add(log)
    chicken.last_fed_at = datetime.now(UTC)
    await db.flush()

    # ── 5. Reward FTK + EXP ───────────────────────────────────────────────
    ftk_svc = FtkService(db)
    await ftk_svc.credit(
        user_id=user_id,
        amount=_FEED_REWARD_FTK,
        tx_type="reward",
        reference_id=str(log.id),
        reference_type="chicken_feed",
        notes=f"Feed reward for chicken {chicken.name}",
    )
    _, leveled_up, _ = await ftk_svc.add_exp(user_id=user_id, exp=_FEED_REWARD_EXP)

    # ── 6. MQTT publish (fire-and-forget) ─────────────────────────────────
    mqtt_ok = False
    if chicken.chip_id:
        mqtt_ok = await publish_feed_command(
            chip_id=chicken.chip_id,
            chicken_id=str(chicken.id),
            nft_token_id=chicken.nft_token_id,
            ordered_by_user_id=user_id,
            correlation_id=correlation_id,
        )

    # ── 7. Build response ─────────────────────────────────────────────────
    feeds_after = feeds_today + 1
    quota_remaining = max(0, quota - feeds_after)

    next_feed_available_at: datetime | None = None
    if quota_remaining == 0:
        # No more feeds today
        next_feed_available_at = (today_start + timedelta(days=1))
    else:
        next_feed_available_at = datetime.now(UTC) + timedelta(minutes=5)

    return ApiResponse.ok(
        FeedResponse(
            ftk_earned=_FEED_REWARD_FTK,
            exp_earned=_FEED_REWARD_EXP,
            feeds_today=feeds_after,
            quota_remaining=quota_remaining,
            next_feed_available_at=next_feed_available_at,
            mqtt_dispatched=mqtt_ok,
        )
    )


# ══════════════════════════════════════════════════════════════════════════════
# 5. GET /{chicken_id}/livestream-token
# ══════════════════════════════════════════════════════════════════════════════

@router.get(
    "/{chicken_id}/livestream-token",
    response_model=ApiResponse[LivestreamTokenResponse],
    summary="Issue a 1-hour JWT for watching the chicken's WebRTC / HLS stream",
    dependencies=[_ChickenReadRL],
)
async def get_livestream_token(
    chicken_id: str,
    user_id: CurrentUserId,
    db: DbSession,
) -> ApiResponse[LivestreamTokenResponse]:
    chicken = await db.get(Chicken, uuid.UUID(chicken_id))
    if chicken is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chicken not found")

    # Access rules: owner always allowed; non-owners need a subscription
    # (subscription logic placeholder – expand with UserSubscription table)
    is_owner = str(chicken.user_id) == user_id
    if not is_owner:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Access denied. Only the owner or subscribers can watch the livestream.",
        )

    ttl = settings.LIVESTREAM_TOKEN_TTL_SECONDS
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=ttl)

    # Sign a short-lived JWT (same secret, dedicated type)
    token_payload = {
        "sub": chicken_id,
        "type": "livestream",
        "user_id": user_id,
        "iat": now,
        "exp": expires_at,
    }
    token = jwt.encode(
        token_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    # Compose stream URL from the chicken's live_cam_url if available
    stream_url: str | None = None
    if chicken.live_cam_url:
        stream_url = f"{chicken.live_cam_url}?token={token}"

    return ApiResponse.ok(
        LivestreamTokenResponse(
            token=token,
            stream_url=stream_url,
            expires_at=expires_at,
            ttl_seconds=ttl,
        )
    )
