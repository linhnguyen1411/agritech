import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class FtkTransaction(Base):
    """Immutable audit ledger for every FTK balance change."""

    __tablename__ = "ftk_transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # positive = credit, negative = debit
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    tx_type: Mapped[str] = mapped_column(
        String(50), nullable=False  # gacha/purchase/reward/transfer/burn/mint/fee
    )
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reference_type: Mapped[str | None] = mapped_column(
        String(50)  # gacha_pull/market_transaction/mission/achievement
    )
    balance_before: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    balance_after: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)

    user_wallet: Mapped["GameWallet"] = relationship(  # type: ignore[name-defined]
        back_populates="ftk_transactions",
        primaryjoin="FtkTransaction.user_id == GameWallet.user_id",
        foreign_keys="FtkTransaction.user_id",
    )
