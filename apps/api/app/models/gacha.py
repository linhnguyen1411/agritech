import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class GachaPull(Base):
    """Records every gacha draw event."""

    __tablename__ = "gacha_pulls"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    gacha_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # standard/premium/event
    )
    cost_ftk: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    item_received_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("item_definitions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    pulled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    tx_hash: Mapped[str | None] = mapped_column(String(66))

    item_received: Mapped["ItemDefinition"] = relationship(back_populates="gacha_pulls")  # type: ignore[name-defined]
