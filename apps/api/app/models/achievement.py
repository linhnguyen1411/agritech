import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AchievementDefinition(Base):
    """Master data for all achievements."""

    __tablename__ = "achievement_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    condition_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # harvest_count/gacha_count/level_reached/...
    )
    condition_value: Mapped[int] = mapped_column(Integer, nullable=False)
    reward_ftk: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    reward_exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    badge_image_url: Mapped[str | None] = mapped_column(Text)


class UserAchievement(Base):
    """Earned achievements per user (composite PK – earned once)."""

    __tablename__ = "user_achievements"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    achievement_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("achievement_definitions.id", ondelete="CASCADE"),
        primary_key=True,
        nullable=False,
    )
    earned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tx_hash: Mapped[str | None] = mapped_column(String(66))
