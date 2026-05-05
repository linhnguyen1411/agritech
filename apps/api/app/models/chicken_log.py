"""ChickenLog – immutable event log for every chicken action.

log_type values
---------------
fed             – feed command executed (by user or IoT ack)
health_check    – health score recorded by sensor / vet
weight_update   – weight reading from scale
activity        – step count snapshot
event           – arbitrary farm event (vaccine, medicine, etc.)
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

LOG_TYPES = frozenset({"fed", "health_check", "weight_update", "activity", "event"})


class ChickenLog(Base):
    __tablename__ = "chicken_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    chicken_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chickens.id", ondelete="CASCADE"),
        nullable=False,
    )
    # null = IoT system / automated
    performed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    log_type: Mapped[str] = mapped_column(String(30), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    chicken: Mapped["Chicken"] = relationship(back_populates="logs")  # type: ignore[name-defined]
