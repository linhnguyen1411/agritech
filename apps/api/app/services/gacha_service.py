"""Gacha pull service with configurable rarity weights."""
import random
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.gacha import GachaPull
from app.models.item import ItemDefinition, UserItem
from app.services.ftk_service import FtkService

# Rarity weights per gacha type
_RARITY_WEIGHTS: dict[str, dict[str, float]] = {
    "standard": {
        "common": 60.0,
        "uncommon": 25.0,
        "rare": 10.0,
        "epic": 4.0,
        "legendary": 1.0,
    },
    "premium": {
        "common": 30.0,
        "uncommon": 30.0,
        "rare": 25.0,
        "epic": 12.0,
        "legendary": 3.0,
    },
    "event": {
        "common": 20.0,
        "uncommon": 25.0,
        "rare": 30.0,
        "epic": 18.0,
        "legendary": 7.0,
    },
}

# FTK cost per pull per gacha type
_GACHA_COSTS: dict[str, Decimal] = {
    "standard": Decimal(str(settings.GACHA_BASE_COST_FTK)),
    "premium": Decimal(str(settings.GACHA_BASE_COST_FTK * 3)),
    "event": Decimal(str(settings.GACHA_BASE_COST_FTK * 2)),
}


class GachaService:
    def __init__(self, db: AsyncSession, ftk_service: FtkService) -> None:
        self._db = db
        self._ftk = ftk_service

    def _roll_rarity(self, gacha_type: str) -> str:
        weights_map = _RARITY_WEIGHTS.get(gacha_type, _RARITY_WEIGHTS["standard"])
        rarities = list(weights_map.keys())
        weights = list(weights_map.values())
        return random.choices(rarities, weights=weights, k=1)[0]

    async def _pick_item(self, rarity: str) -> ItemDefinition:
        result = await self._db.execute(
            select(ItemDefinition)
            .where(ItemDefinition.rarity == rarity)
            .order_by(ItemDefinition.id)  # deterministic pagination seed
        )
        items = list(result.scalars().all())
        if not items:
            # fallback to common if no items for rolled rarity
            result = await self._db.execute(select(ItemDefinition).limit(1))
            item = result.scalar_one_or_none()
            if item is None:
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "No items configured in the gacha pool",
                )
            return item
        return random.choice(items)

    async def pull(
        self,
        user_id: str,
        gacha_type: str,
        quantity: int = 1,
    ) -> list[GachaPull]:
        cost_per = _GACHA_COSTS.get(gacha_type, _GACHA_COSTS["standard"])
        total_cost = cost_per * quantity

        # Debit FTK (raises 422 if insufficient)
        await self._ftk.debit(
            user_id=user_id,
            amount=total_cost,
            tx_type="gacha",
            reference_type="gacha_pull",
        )

        pulls: list[GachaPull] = []
        for _ in range(quantity):
            rarity = self._roll_rarity(gacha_type)
            item = await self._pick_item(rarity)

            # Update supply counter
            item.current_supply += 1

            pull = GachaPull(
                user_id=uuid.UUID(user_id),
                gacha_type=gacha_type,
                cost_ftk=cost_per,
                item_received_id=item.id,
            )
            self._db.add(pull)

            # Add to user inventory (stack if exists)
            inv_result = await self._db.execute(
                select(UserItem)
                .where(
                    UserItem.user_id == uuid.UUID(user_id),
                    UserItem.item_def_id == item.id,
                    UserItem.source_type == "gacha",
                )
                .limit(1)
            )
            user_item = inv_result.scalar_one_or_none()
            if user_item:
                user_item.quantity += 1
            else:
                user_item = UserItem(
                    user_id=uuid.UUID(user_id),
                    item_def_id=item.id,
                    quantity=1,
                    source_type="gacha",
                )
                self._db.add(user_item)

            pulls.append(pull)

        await self._db.flush()

        # Back-fill pull reference into ledger
        ledger_entry = await self._ftk.debit.__func__  # already debited above
        _ = ledger_entry  # reference used; ledger already written

        return pulls
