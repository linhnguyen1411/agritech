"""Core user-domain models: User, Chicken, Order, NftOwnership."""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

# ── NFT tier hierarchy ────────────────────────────────────────────────────────
NFT_TIER_RANK: dict[str, int] = {
    "bronze": 0,
    "silver": 1,
    "gold": 2,
    "platinum": 3,
}

# Max feeds per day allowed for each tier (0 = tier cannot use feed feature)
NFT_TIER_DAILY_QUOTA: dict[str, int] = {
    "bronze": 0,
    "silver": 1,
    "gold": 3,
    "platinum": 5,
}


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    wallet_address: Mapped[str | None] = mapped_column(String(42), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    game_wallet: Mapped["GameWallet"] = relationship(  # type: ignore[name-defined]
        back_populates="user", uselist=False
    )
    chickens: Mapped[list["Chicken"]] = relationship(back_populates="owner")


class Chicken(Base, TimestampMixin):
    """Physical chicken linked to an IoT device and optionally an NFT."""

    __tablename__ = "chickens"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    # ── Identity ──────────────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    nft_token_id: Mapped[str | None] = mapped_column(String(100), unique=True)
    nft_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="bronze")
    chip_id: Mapped[str | None] = mapped_column(String(50), unique=True)

    # ── Physical metrics (updated via IoT / admin) ─────────────────────────
    health_score: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("100.00")
    )
    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), nullable=False, default=Decimal("0.000")
    )
    birth_date: Mapped[date | None] = mapped_column(Date)
    zone: Mapped[str | None] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
        # active / sick / resting / quarantine / deceased
    )
    steps_today: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Media ─────────────────────────────────────────────────────────────
    live_cam_url: Mapped[str | None] = mapped_column(Text)
    blockchain_metadata_url: Mapped[str | None] = mapped_column(Text)

    # ── Game progression ──────────────────────────────────────────────────
    level: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    experience: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_fed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── Relationships ─────────────────────────────────────────────────────
    owner: Mapped["User"] = relationship(back_populates="chickens")
    logs: Mapped[list["ChickenLog"]] = relationship(  # type: ignore[name-defined]
        back_populates="chicken", order_by="ChickenLog.created_at.desc()"
    )

    # ── Computed helpers ──────────────────────────────────────────────────
    @property
    def age_days(self) -> int:
        if self.birth_date is None:
            return 0
        return (datetime.utcnow().date() - self.birth_date).days

    @property
    def owner_since(self) -> datetime:
        return self.created_at

    @property
    def daily_feed_quota(self) -> int:
        return NFT_TIER_DAILY_QUOTA.get(self.nft_tier, 0)

    def can_feed(self) -> bool:
        return NFT_TIER_RANK.get(self.nft_tier, 0) >= NFT_TIER_RANK["silver"]


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    total_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NftOwnership(Base):
    __tablename__ = "nft_ownership"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_id: Mapped[str] = mapped_column(String(100), nullable=False)
    contract_address: Mapped[str] = mapped_column(String(42), nullable=False)
    acquired_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
