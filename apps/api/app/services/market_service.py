"""Marketplace service – listing creation, purchase, cancellation."""
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.item import ItemDefinition, UserItem
from app.models.market import MarketListing, MarketTransaction
from app.services.ftk_service import FtkService


class MarketService:
    def __init__(self, db: AsyncSession, ftk_service: FtkService) -> None:
        self._db = db
        self._ftk = ftk_service

    # ── Create listing ─────────────────────────────────────────────────────

    async def create_listing(
        self,
        seller_id: str,
        item_def_id: str,
        listing_type: str,
        price_ftk: Decimal,
        quantity: int,
        expires_hours: int | None,
    ) -> MarketListing:
        # Verify seller has enough un-listed items
        inv = await self._db.execute(
            select(UserItem).where(
                UserItem.user_id == uuid.UUID(seller_id),
                UserItem.item_def_id == uuid.UUID(item_def_id),
                UserItem.is_listed_market.is_(False),
            )
        )
        user_item = inv.scalar_one_or_none()
        if user_item is None or user_item.quantity < quantity:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                "Not enough items in inventory to list",
            )

        user_item.quantity -= quantity
        user_item.is_listed_market = quantity > 0

        expires_at: datetime | None = None
        if expires_hours:
            expires_at = datetime.now(UTC) + timedelta(hours=expires_hours)

        listing = MarketListing(
            seller_user_id=uuid.UUID(seller_id),
            item_def_id=uuid.UUID(item_def_id),
            listing_type=listing_type,
            price_ftk=price_ftk,
            quantity=quantity,
            expires_at=expires_at,
        )
        self._db.add(listing)
        await self._db.flush()
        return listing

    # ── Buy listing ────────────────────────────────────────────────────────

    async def buy(
        self,
        buyer_id: str,
        listing_id: str,
        quantity: int,
    ) -> MarketTransaction:
        listing = await self._db.get(MarketListing, uuid.UUID(listing_id))
        if listing is None or listing.status != "active":
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found or inactive")
        if listing.seller_user_id == uuid.UUID(buyer_id):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot buy your own listing")
        if listing.quantity < quantity:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Only {listing.quantity} available",
            )

        total_price = listing.price_ftk * quantity
        fee = (total_price * Decimal(str(settings.MARKET_FEE_PERCENT)) / 100).quantize(
            Decimal("0.00000001")
        )
        burned = (fee * Decimal(str(settings.MARKET_BURN_PERCENT)) / 100).quantize(
            Decimal("0.00000001")
        )
        seller_receives = total_price - fee

        # Debit buyer
        await self._ftk.debit(
            user_id=buyer_id,
            amount=total_price,
            tx_type="purchase",
            reference_type="market_transaction",
        )
        # Credit seller (net of fees)
        await self._ftk.credit(
            user_id=str(listing.seller_user_id),
            amount=seller_receives,
            tx_type="sale",
            reference_type="market_transaction",
        )

        # Update listing quantity / status
        listing.quantity -= quantity
        if listing.quantity == 0:
            listing.status = "sold"

        # Add items to buyer inventory
        inv_result = await self._db.execute(
            select(UserItem).where(
                UserItem.user_id == uuid.UUID(buyer_id),
                UserItem.item_def_id == listing.item_def_id,
            )
        )
        buyer_item = inv_result.scalar_one_or_none()
        if buyer_item:
            buyer_item.quantity += quantity
        else:
            buyer_item = UserItem(
                user_id=uuid.UUID(buyer_id),
                item_def_id=listing.item_def_id,
                quantity=quantity,
                source_type="purchase",
            )
            self._db.add(buyer_item)

        tx = MarketTransaction(
            listing_id=listing.id,
            buyer_user_id=uuid.UUID(buyer_id),
            seller_user_id=listing.seller_user_id,
            price_ftk=total_price,
            fee_ftk=fee,
            burned_ftk=burned,
        )
        self._db.add(tx)
        await self._db.flush()
        return tx

    # ── Cancel listing ─────────────────────────────────────────────────────

    async def cancel_listing(self, seller_id: str, listing_id: str) -> MarketListing:
        listing = await self._db.get(MarketListing, uuid.UUID(listing_id))
        if listing is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Listing not found")
        if str(listing.seller_user_id) != seller_id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your listing")
        if listing.status != "active":
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Listing is not active")

        listing.status = "cancelled"

        # Return items to seller inventory
        inv_result = await self._db.execute(
            select(UserItem).where(
                UserItem.user_id == uuid.UUID(seller_id),
                UserItem.item_def_id == listing.item_def_id,
            )
        )
        inv = inv_result.scalar_one_or_none()
        if inv:
            inv.quantity += listing.quantity
        else:
            inv = UserItem(
                user_id=uuid.UUID(seller_id),
                item_def_id=listing.item_def_id,
                quantity=listing.quantity,
                source_type="cancelled_listing",
            )
            self._db.add(inv)

        await self._db.flush()
        return listing

    # ── Queries ────────────────────────────────────────────────────────────

    async def list_active(
        self,
        item_def_id: str | None = None,
        sort_by: str = "price_asc",
        offset: int = 0,
        limit: int = 20,
    ) -> list[MarketListing]:
        q = select(MarketListing).where(MarketListing.status == "active")
        if item_def_id:
            q = q.where(MarketListing.item_def_id == uuid.UUID(item_def_id))
        if sort_by == "price_asc":
            q = q.order_by(MarketListing.price_ftk.asc())
        elif sort_by == "price_desc":
            q = q.order_by(MarketListing.price_ftk.desc())
        else:
            q = q.order_by(MarketListing.created_at.desc())
        result = await self._db.execute(q.offset(offset).limit(limit))
        return list(result.scalars().all())

    async def get_stats(self) -> dict:
        from datetime import timedelta
        since = datetime.now(UTC) - timedelta(hours=24)
        result = await self._db.execute(
            select(
                func.sum(MarketTransaction.price_ftk),
                func.count(MarketTransaction.id),
                func.sum(MarketTransaction.burned_ftk),
            ).where(MarketTransaction.completed_at >= since)
        )
        row = result.one()
        active_count = await self._db.scalar(
            select(func.count(MarketListing.id)).where(MarketListing.status == "active")
        )
        return {
            "total_volume_24h": row[0] or Decimal("0"),
            "total_transactions_24h": row[1] or 0,
            "total_burned_24h": row[2] or Decimal("0"),
            "active_listings": active_count or 0,
        }
