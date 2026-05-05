import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.core.database import DbSession
from app.core.security import CurrentUserId
from app.models.user import Chicken
from app.schemas import ApiResponse, ChickenResponse, CreateChickenRequest, UpdateChickenRequest
from app.schemas.common import PaginatedData

router = APIRouter()


@router.get("/", response_model=ApiResponse[PaginatedData[ChickenResponse]])
async def list_chickens(user_id: CurrentUserId, db: DbSession) -> ApiResponse[PaginatedData[ChickenResponse]]:
    result = await db.execute(
        select(Chicken).where(Chicken.user_id == uuid.UUID(user_id))
    )
    chickens = [ChickenResponse.model_validate(c) for c in result.scalars().all()]
    return ApiResponse.ok(
        PaginatedData(items=chickens, total=len(chickens), page=1, page_size=len(chickens), total_pages=1)
    )


@router.post("/", response_model=ApiResponse[ChickenResponse], status_code=status.HTTP_201_CREATED)
async def create_chicken(
    body: CreateChickenRequest, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[ChickenResponse]:
    chicken = Chicken(user_id=uuid.UUID(user_id), name=body.name)
    db.add(chicken)
    await db.flush()
    return ApiResponse.ok(ChickenResponse.model_validate(chicken))


@router.get("/{chicken_id}", response_model=ApiResponse[ChickenResponse])
async def get_chicken(
    chicken_id: str, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[ChickenResponse]:
    chicken = await db.get(Chicken, uuid.UUID(chicken_id))
    if chicken is None or str(chicken.user_id) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chicken not found")
    return ApiResponse.ok(ChickenResponse.model_validate(chicken))


@router.patch("/{chicken_id}", response_model=ApiResponse[ChickenResponse])
async def update_chicken(
    chicken_id: str, body: UpdateChickenRequest, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[ChickenResponse]:
    chicken = await db.get(Chicken, uuid.UUID(chicken_id))
    if chicken is None or str(chicken.user_id) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chicken not found")
    if body.name is not None:
        chicken.name = body.name
    await db.flush()
    return ApiResponse.ok(ChickenResponse.model_validate(chicken))


@router.delete("/{chicken_id}", response_model=ApiResponse[None])
async def delete_chicken(
    chicken_id: str, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[None]:
    chicken = await db.get(Chicken, uuid.UUID(chicken_id))
    if chicken is None or str(chicken.user_id) != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Chicken not found")
    await db.delete(chicken)
    return ApiResponse.ok(None)
