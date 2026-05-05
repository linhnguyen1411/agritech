from fastapi import APIRouter, Query

from app.core.database import DbSession
from app.core.security import CurrentUserId
from app.schemas import ApiResponse, BuyListingRequest, CreateListingRequest, MarketListingResponse, MarketStatsResponse, MarketTransactionResponse
from app.schemas.common import PaginatedData
from app.services.ftk_service import FtkService
from app.services.market_service import MarketService

router = APIRouter()


def _svc(db: DbSession) -> MarketService:  # type: ignore[type-arg]
    return MarketService(db, FtkService(db))


@router.get("/", response_model=ApiResponse[PaginatedData[MarketListingResponse]])
async def list_listings(
    db: DbSession,
    item_def_id: str | None = None,
    sort_by: str = Query("price_asc", pattern=r"^(price_asc|price_desc|newest)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> ApiResponse[PaginatedData[MarketListingResponse]]:
    svc = _svc(db)
    offset = (page - 1) * page_size
    listings = await svc.list_active(item_def_id=item_def_id, sort_by=sort_by,
                                     offset=offset, limit=page_size)
    items = []
    for listing in listings:
        item_def = await db.get(listing.__class__.item_def_id.property.mapper.class_, listing.item_def_id)  # type: ignore[attr-defined]
        items.append(
            MarketListingResponse(
                id=str(listing.id),
                seller_user_id=str(listing.seller_user_id),
                item_def_id=str(listing.item_def_id),
                item_name=item_def.name if item_def else "Unknown",
                item_rarity=item_def.rarity if item_def else "common",
                listing_type=listing.listing_type,
                price_ftk=listing.price_ftk,
                quantity=listing.quantity,
                status=listing.status,
                created_at=listing.created_at,
                expires_at=listing.expires_at,
            )
        )
    return ApiResponse.ok(
        PaginatedData(items=items, total=len(items), page=page,
                      page_size=page_size, total_pages=-1)
    )


@router.post("/listings", response_model=ApiResponse[MarketListingResponse], status_code=201)
async def create_listing(
    body: CreateListingRequest, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[MarketListingResponse]:
    svc = _svc(db)
    listing = await svc.create_listing(
        seller_id=user_id,
        item_def_id=body.item_def_id,
        listing_type=body.listing_type,
        price_ftk=body.price_ftk,
        quantity=body.quantity,
        expires_hours=body.expires_hours,
    )
    item_def = await db.get(listing.__class__.item_def_id.property.mapper.class_, listing.item_def_id)  # type: ignore[attr-defined]
    return ApiResponse.ok(
        MarketListingResponse(
            id=str(listing.id),
            seller_user_id=str(listing.seller_user_id),
            item_def_id=str(listing.item_def_id),
            item_name=item_def.name if item_def else "Unknown",
            item_rarity=item_def.rarity if item_def else "common",
            listing_type=listing.listing_type,
            price_ftk=listing.price_ftk,
            quantity=listing.quantity,
            status=listing.status,
            created_at=listing.created_at,
            expires_at=listing.expires_at,
        )
    )


@router.post("/listings/{listing_id}/buy", response_model=ApiResponse[MarketTransactionResponse])
async def buy_listing(
    listing_id: str, body: BuyListingRequest, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[MarketTransactionResponse]:
    svc = _svc(db)
    tx = await svc.buy(buyer_id=user_id, listing_id=listing_id, quantity=body.quantity)
    return ApiResponse.ok(MarketTransactionResponse.model_validate(tx))


@router.delete("/listings/{listing_id}", response_model=ApiResponse[None])
async def cancel_listing(
    listing_id: str, user_id: CurrentUserId, db: DbSession
) -> ApiResponse[None]:
    svc = _svc(db)
    await svc.cancel_listing(seller_id=user_id, listing_id=listing_id)
    return ApiResponse.ok(None)


@router.get("/stats", response_model=ApiResponse[MarketStatsResponse])
async def market_stats(db: DbSession) -> ApiResponse[MarketStatsResponse]:
    svc = _svc(db)
    stats = await svc.get_stats()
    return ApiResponse.ok(MarketStatsResponse(**stats))
