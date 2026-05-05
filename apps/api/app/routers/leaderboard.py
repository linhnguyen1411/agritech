from fastapi import APIRouter, Query

from app.core.database import DbSession
from app.core.redis import cache_get, cache_set
from app.schemas import ApiResponse, LeaderboardEntry
from app.schemas.common import PaginatedData

router = APIRouter()

_CACHE_TTL = 60  # leaderboard refreshes every 60 s


@router.get("/", response_model=ApiResponse[PaginatedData[LeaderboardEntry]])
async def get_leaderboard(
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    sort_by: str = Query("level", pattern=r"^(level|ftk_balance|exp_points)$"),
) -> ApiResponse[PaginatedData[LeaderboardEntry]]:
    cache_key = f"leaderboard:{sort_by}:{page}:{page_size}"
    cached = await cache_get(cache_key)
    if cached:
        return ApiResponse.ok(PaginatedData(**cached))

    from sqlalchemy import desc, select
    from app.models.game_wallet import GameWallet
    from app.models.user import User

    sort_col = {
        "level": GameWallet.level,
        "ftk_balance": GameWallet.ftk_balance,
        "exp_points": GameWallet.exp_points,
    }[sort_by]

    offset = (page - 1) * page_size
    result = await db.execute(
        select(GameWallet, User.username)
        .join(User, GameWallet.user_id == User.id)
        .order_by(desc(sort_col))
        .offset(offset)
        .limit(page_size)
    )
    rows = result.all()

    entries = [
        LeaderboardEntry(
            rank=offset + idx + 1,
            user_id=str(row.GameWallet.user_id),
            username=row.username,
            level=row.GameWallet.level,
            exp_points=row.GameWallet.exp_points,
            ftk_balance=row.GameWallet.ftk_balance,
        )
        for idx, row in enumerate(rows)
    ]

    payload = PaginatedData(
        items=entries, total=len(entries), page=page,
        page_size=page_size, total_pages=-1,
    )
    await cache_set(cache_key, payload.model_dump(), ttl=_CACHE_TTL)
    return ApiResponse.ok(payload)
