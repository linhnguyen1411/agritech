"""FTK token service – all balance mutations go through here.

Every mutation appends an immutable row to ftk_transactions,
keeping game_wallets.ftk_balance in sync atomically (row-level lock).
"""
import uuid
from decimal import Decimal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ftk_ledger import FtkTransaction
from app.models.game_wallet import GameWallet

# EXP needed to reach the next level (simple quadratic formula)
_EXP_PER_LEVEL = 500


def _exp_for_level(level: int) -> int:
    return _EXP_PER_LEVEL * level * level


class FtkService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Wallet ─────────────────────────────────────────────────────────────

    async def get_or_create_wallet(self, user_id: str) -> GameWallet:
        uid = uuid.UUID(user_id)
        wallet = await self._db.get(GameWallet, uid)
        if wallet is None:
            wallet = GameWallet(user_id=uid)
            self._db.add(wallet)
            await self._db.flush()
        return wallet

    async def get_balance(self, user_id: str) -> GameWallet:
        wallet = await self._db.get(GameWallet, uuid.UUID(user_id))
        if wallet is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")
        return wallet

    # ── Mutations (always call inside a transaction) ───────────────────────

    async def credit(
        self,
        user_id: str,
        amount: Decimal,
        tx_type: str,
        reference_id: str | None = None,
        reference_type: str | None = None,
        notes: str | None = None,
    ) -> FtkTransaction:
        if amount <= 0:
            raise ValueError("Credit amount must be positive")
        wallet = await self.get_or_create_wallet(user_id)
        return await self._record(wallet, amount, tx_type, reference_id, reference_type, notes)

    async def debit(
        self,
        user_id: str,
        amount: Decimal,
        tx_type: str,
        reference_id: str | None = None,
        reference_type: str | None = None,
        notes: str | None = None,
    ) -> FtkTransaction:
        if amount <= 0:
            raise ValueError("Debit amount must be positive")
        wallet = await self.get_or_create_wallet(user_id)
        if wallet.ftk_balance < amount:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Insufficient FTK balance. Required: {amount}, available: {wallet.ftk_balance}",
            )
        return await self._record(wallet, -amount, tx_type, reference_id, reference_type, notes)

    async def _record(
        self,
        wallet: GameWallet,
        delta: Decimal,
        tx_type: str,
        reference_id: str | None,
        reference_type: str | None,
        notes: str | None,
    ) -> FtkTransaction:
        balance_before = wallet.ftk_balance
        wallet.ftk_balance = balance_before + delta

        entry = FtkTransaction(
            user_id=wallet.user_id,
            amount=delta,
            tx_type=tx_type,
            reference_id=uuid.UUID(reference_id) if reference_id else None,
            reference_type=reference_type,
            balance_before=balance_before,
            balance_after=wallet.ftk_balance,
            notes=notes,
        )
        self._db.add(entry)
        await self._db.flush()
        return entry

    # ── EXP / Level ────────────────────────────────────────────────────────

    async def add_exp(self, user_id: str, exp: int) -> tuple[int, bool, int | None]:
        """Returns (new_exp, leveled_up, new_level)."""
        wallet = await self.get_or_create_wallet(user_id)
        wallet.exp_points += exp
        leveled_up = False
        new_level: int | None = None

        while wallet.exp_points >= _exp_for_level(wallet.level):
            wallet.exp_points -= _exp_for_level(wallet.level)
            wallet.level += 1
            leveled_up = True
            new_level = wallet.level

        await self._db.flush()
        return wallet.exp_points, leveled_up, new_level

    # ── Ledger history ─────────────────────────────────────────────────────

    async def get_history(
        self, user_id: str, offset: int = 0, limit: int = 20
    ) -> list[FtkTransaction]:
        uid = uuid.UUID(user_id)
        result = await self._db.execute(
            select(FtkTransaction)
            .where(FtkTransaction.user_id == uid)
            .order_by(FtkTransaction.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all())
