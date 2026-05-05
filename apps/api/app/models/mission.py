import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class MissionDefinition(Base):
    """Master data for all missions."""

    __tablename__ = "mission_definitions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    mission_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # daily/weekly/story/seasonal
    )
    target_value: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reward_ftk: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), nullable=False, default=Decimal("0")
    )
    reward_exp: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reward_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("item_definitions.id", ondelete="SET NULL")
    )
    reset_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="none"  # daily/weekly/none
    )
    level_required: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    user_missions: Mapped[list["UserMission"]] = relationship(
        back_populates="mission_definition"
    )


class UserMission(Base):
    """Per-user mission progress tracker."""

    __tablename__ = "user_missions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    mission_def_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("mission_definitions.id", ondelete="CASCADE"),
        nullable=False,
    )
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reward_claimed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    mission_definition: Mapped["MissionDefinition"] = relationship(
        back_populates="user_missions"
    )
