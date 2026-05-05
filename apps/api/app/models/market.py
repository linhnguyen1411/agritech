import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MarketListing(Base):
    """Active / historical marketplace listings."""

    __tablename__ = "market_listings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    seller_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    item_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("item_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    nft_token_id: Mapped[str | None] = mapped_column(String(100))
    listing_type: Mapped[str] = mapped_column(
        String(20), nullable=False  # fixed/auction
    )
    price_ftk: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"  # active/sold/cancelled/expired
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    item_definition: Mapped["ItemDefinition"] = relationship(back_populates="market_listings")  # type: ignore[name-defined]
    transactions: Mapped[list["MarketTransaction"]] = relationship(
        back_populates="listing", foreign_keys="MarketTransaction.listing_id"
    )


class MarketTransaction(Base):
    """Completed marketplace trades with fee / burn accounting."""

    __tablename__ = "market_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("market_listings.id", ondelete="RESTRICT"),
        nullable=False,
    )
    buyer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    seller_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    price_ftk: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    fee_ftk: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    burned_ftk: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tx_hash: Mapped[str | None] = mapped_column(String(66))

    listing: Mapped["MarketListing"] = relationship(
        back_populates="transactions", foreign_keys=[listing_id]
    )
