from fastapi import APIRouter

from app.core.database import DbSession
from app.core.security import CurrentUserId
from app.schemas import ApiResponse, GachaPullRequest, GachaPullResponse
from app.schemas.gacha import GachaPullResult, ItemDefinitionResponse
from app.services.ftk_service import FtkService
from app.services.gacha_service import GachaService

router = APIRouter()


@router.post("/pull", response_model=ApiResponse[GachaPullResponse])
async def pull_gacha(
    body: GachaPullRequest, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[GachaPullResponse]:
    ftk_svc = FtkService(db)
    gacha_svc = GachaService(db, ftk_svc)

    pulls = await gacha_svc.pull(
        user_id=user_id,
        gacha_type=body.gacha_type,
        quantity=body.quantity,
    )

    # Eagerly load item definitions (already in session cache after flush)
    results: list[GachaPullResult] = []
    for pull in pulls:
        item = await db.get(type(pulls[0]).item_received_id.property.mapper.class_, pull.item_received_id)  # type: ignore[attr-defined]
        results.append(
            GachaPullResult(
                pull_id=str(pull.id),
                item=ItemDefinitionResponse.model_validate(item),
                gacha_type=pull.gacha_type,
                cost_ftk=pull.cost_ftk,
                pulled_at=pull.pulled_at,
                tx_hash=pull.tx_hash,
            )
        )

    wallet = await ftk_svc.get_balance(user_id)
    from decimal import Decimal
    total_cost = sum(r.cost_ftk for r in results)

    return ApiResponse.ok(
        GachaPullResponse(
            results=results,
            total_cost_ftk=total_cost,
            new_balance=wallet.ftk_balance,
        )
    )
