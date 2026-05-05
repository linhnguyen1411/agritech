from fastapi import APIRouter, Query

from app.core.database import DbSession
from app.core.security import CurrentUserId
from app.models.mission import MissionDefinition
from app.schemas import ApiResponse, ClaimRewardResponse, MissionDefinitionResponse, UserMissionResponse
from app.schemas.common import PaginatedData
from app.services.ftk_service import FtkService
from app.services.mission_service import MissionService

router = APIRouter()


@router.get("/definitions", response_model=ApiResponse[PaginatedData[MissionDefinitionResponse]])
async def list_definitions(
    db: DbSession,
    mission_type: str | None = None,
) -> ApiResponse[PaginatedData[MissionDefinitionResponse]]:
    from sqlalchemy import select
    q = select(MissionDefinition)
    if mission_type:
        q = q.where(MissionDefinition.mission_type == mission_type)
    result = await db.execute(q)
    items = [MissionDefinitionResponse.model_validate(m) for m in result.scalars().all()]
    return ApiResponse.ok(PaginatedData(items=items, total=len(items), page=1, page_size=len(items), total_pages=1))


@router.get("/my", response_model=ApiResponse[PaginatedData[UserMissionResponse]])
async def my_missions(
    user_id: CurrentUserId,
    db: DbSession,
    mission_type: str | None = Query(None),
) -> ApiResponse[PaginatedData[UserMissionResponse]]:
    svc = MissionService(db, FtkService(db))
    missions = await svc.get_user_missions(user_id, mission_type)

    items: list[UserMissionResponse] = []
    for um in missions:
        md = await db.get(MissionDefinition, um.mission_def_id)
        assert md is not None
        items.append(
            UserMissionResponse(
                id=str(um.id),
                mission_def_id=str(um.mission_def_id),
                mission_name=md.name,
                mission_type=md.mission_type,
                progress=um.progress,
                target_value=md.target_value,
                progress_percent=round(um.progress / md.target_value * 100, 1),
                is_completed=um.is_completed,
                completed_at=um.completed_at,
                reward_claimed=um.reward_claimed,
                reward_ftk=md.reward_ftk,
                reward_exp=md.reward_exp,
            )
        )
    return ApiResponse.ok(PaginatedData(items=items, total=len(items), page=1, page_size=len(items), total_pages=1))


@router.post("/my/{user_mission_id}/claim", response_model=ApiResponse[ClaimRewardResponse])
async def claim_reward(
    user_mission_id: str, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[ClaimRewardResponse]:
    svc = MissionService(db, FtkService(db))
    um, leveled_up, new_level = await svc.claim_reward(user_id, user_mission_id)

    md = await db.get(MissionDefinition, um.mission_def_id)
    assert md is not None
    wallet = await FtkService(db).get_balance(user_id)

    return ApiResponse.ok(
        ClaimRewardResponse(
            mission_id=str(um.id),
            ftk_awarded=md.reward_ftk,
            exp_awarded=md.reward_exp,
            new_balance=wallet.ftk_balance,
            new_exp=wallet.exp_points,
            leveled_up=leveled_up,
            new_level=new_level,
        )
    )
