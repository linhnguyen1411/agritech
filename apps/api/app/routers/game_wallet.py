from fastapi import APIRouter, Query

from app.core.database import DbSession
from app.core.security import CurrentUserId
from app.schemas import ApiResponse, FtkTransactionResponse, PaginatedData, WalletResponse
from app.services.ftk_service import FtkService

router = APIRouter()


@router.get("/", response_model=ApiResponse[WalletResponse])
async def get_wallet(user_id: CurrentUserId, db: DbSession) -> ApiResponse[WalletResponse]:
    svc = FtkService(db)
    wallet = await svc.get_or_create_wallet(user_id)
    return ApiResponse.ok(WalletResponse.model_validate(wallet))


@router.get("/history", response_model=ApiResponse[PaginatedData[FtkTransactionResponse]])
async def get_history(
    user_id: CurrentUserId,
    db: DbSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse[PaginatedData[FtkTransactionResponse]]:
    svc = FtkService(db)
    offset = (page - 1) * page_size
    entries = await svc.get_history(user_id, offset=offset, limit=page_size)
    items = [FtkTransactionResponse.model_validate(e) for e in entries]
    return ApiResponse.ok(
        PaginatedData(
            items=items,
            total=len(items),  # exact count via separate query in production
            page=page,
            page_size=page_size,
            total_pages=-1,  # use -1 to signal "unknown" until pagination is wired
        )
    )
