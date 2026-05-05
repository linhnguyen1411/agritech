import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class ItemDefinition(Base):
    """Master data for all items in the game."""

    __tablename__ = "item_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    rarity: Mapped[str] = mapped_column(
        String(20), nullable=False  # common/uncommon/rare/epic/legendary
    )
    category: Mapped[str] = mapped_column(
        String(50), nullable=False  # seed/tool/decoration/consumable/nft
    )
    effect_type: Mapped[str | None] = mapped_column(String(50))
    effect_value: Mapped[dict | None] = mapped_column(JSONB)
    max_supply: Mapped[int | None] = mapped_column(Integer)
    current_supply: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    price_ftk: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB)

    user_items: Mapped[list["UserItem"]] = relationship(back_populates="item_definition")
    gacha_pulls: Mapped[list["GachaPull"]] = relationship(back_populates="item_received")  # type: ignore[name-defined]
    market_listings: Mapped[list["MarketListing"]] = relationship(back_populates="item_definition")  # type: ignore[name-defined]


class UserItem(Base):
    """Items owned by a player."""

    __tablename__ = "user_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    item_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("item_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # gacha/purchase/reward/trade/airdrop
    )
    is_listed_market: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    item_definition: Mapped["ItemDefinition"] = relationship(back_populates="user_items")
