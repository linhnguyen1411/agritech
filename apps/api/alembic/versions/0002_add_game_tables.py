"""Add game tables: wallets, items, gacha, market, missions,
achievements, streaks, FTK ledger.

Revision ID: b7c8d9e0f1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-05 01:00:00.000000

Schema additions
----------------
game_wallets          – FTK balance + XP + level (1-to-1 with users)
item_definitions      – master catalog of all game items
user_items            – player inventory
gacha_pulls           – gacha draw history
market_listings       – active / historical listings
market_transactions   – completed trades (fee + burn accounting)
mission_definitions   – mission master data
user_missions         – per-user mission progress
achievement_definitions – achievement master data
user_achievements     – earned achievements (composite PK)
user_streaks          – daily login streaks
ftk_transactions      – immutable FTK balance ledger

Indexes
-------
- All user_id FK columns → fast player-centric lookups
- market_listings (status, item_def_id, price_ftk) → market browse / sort
- market_listings (seller_user_id, status) → seller dashboard
- ftk_transactions (user_id, created_at DESC) → wallet history pagination
- ftk_transactions (tx_type) → analytics / reporting
- user_items (user_id, item_def_id) → inventory dedup check
- gacha_pulls (user_id, pulled_at DESC) → pull history
- user_missions (user_id, is_completed) → active mission list
- game_wallets (level DESC, exp_points DESC) → leaderboard
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_UUID_DEFAULT = sa.text("gen_random_uuid()")
_NOW = sa.text("now()")


def _uuid(col: str, **kw: object) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(col, UUID(as_uuid=True), **kw)  # type: ignore[arg-type]


def _uuid_pk(col: str = "id") -> sa.Column:  # type: ignore[type-arg]
    return _uuid(col, primary_key=True, server_default=_UUID_DEFAULT, nullable=False)


def _ftk_col(col: str, **kw: object) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(col, sa.Numeric(18, 8), **kw)  # type: ignore[arg-type]


def _ts(col: str, nullable: bool = False) -> sa.Column:  # type: ignore[type-arg]
    return sa.Column(col, sa.DateTime(timezone=True), nullable=nullable,
                     server_default=_NOW if not nullable else None)


# ---------------------------------------------------------------------------
# upgrade
# ---------------------------------------------------------------------------


def upgrade() -> None:
    # ══════════════════════════════════════════════════════════════════════════
    # 1. game_wallets
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "game_wallets",
        _uuid("user_id", primary_key=True, nullable=False),
        _ftk_col("ftk_balance", nullable=False, server_default="0"),
        sa.Column("exp_points", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("level", sa.Integer(), nullable=False, server_default="1"),
        _ts("created_at"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_game_wallets_user_id",
            ondelete="CASCADE",
        ),
    )
    # leaderboard: top players by level then exp
    op.create_index("ix_game_wallets_level_exp", "game_wallets", ["level", "exp_points"],
                    postgresql_ops={"level": "DESC", "exp_points": "DESC"})

    # ══════════════════════════════════════════════════════════════════════════
    # 2. item_definitions
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "item_definitions",
        _uuid_pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("rarity", sa.String(20), nullable=False),       # common/uncommon/rare/epic/legendary
        sa.Column("category", sa.String(50), nullable=False),     # seed/tool/decoration/consumable/nft
        sa.Column("effect_type", sa.String(50), nullable=True),
        sa.Column("effect_value", JSONB, nullable=True),
        sa.Column("max_supply", sa.Integer(), nullable=True),
        sa.Column("current_supply", sa.Integer(), nullable=False, server_default="0"),
        _ftk_col("price_ftk", nullable=False),
        sa.Column("image_url", sa.Text(), nullable=True),
        sa.Column("metadata_json", JSONB, nullable=True),
        sa.UniqueConstraint("name", name="uq_item_definitions_name"),
    )
    op.create_index("ix_item_definitions_rarity", "item_definitions", ["rarity"])
    op.create_index("ix_item_definitions_category", "item_definitions", ["category"])
    op.create_index("ix_item_definitions_rarity_category", "item_definitions",
                    ["rarity", "category"])

    # ══════════════════════════════════════════════════════════════════════════
    # 3. user_items  (player inventory)
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "user_items",
        _uuid_pk(),
        _uuid("user_id", nullable=False),
        _uuid("item_def_id", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        _ts("acquired_at"),
        sa.Column("source_type", sa.String(50), nullable=False),  # gacha/purchase/reward/trade/airdrop
        sa.Column("is_listed_market", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_user_items_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_def_id"], ["item_definitions.id"],
            name="fk_user_items_item_def_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_user_items_user_id", "user_items", ["user_id"])
    op.create_index("ix_user_items_item_def_id", "user_items", ["item_def_id"])
    # fast dedup / stack lookup
    op.create_index("ix_user_items_user_item", "user_items", ["user_id", "item_def_id"])
    # filter listed items in marketplace flow
    op.create_index("ix_user_items_user_listed", "user_items",
                    ["user_id", "is_listed_market"])

    # ══════════════════════════════════════════════════════════════════════════
    # 4. gacha_pulls
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "gacha_pulls",
        _uuid_pk(),
        _uuid("user_id", nullable=False),
        sa.Column("gacha_type", sa.String(50), nullable=False),   # standard/premium/event
        _ftk_col("cost_ftk", nullable=False),
        _uuid("item_received_id", nullable=False),
        _ts("pulled_at"),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_gacha_pulls_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_received_id"], ["item_definitions.id"],
            name="fk_gacha_pulls_item_received_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_gacha_pulls_user_id", "gacha_pulls", ["user_id"])
    # paginated pull history (most recent first)
    op.create_index("ix_gacha_pulls_user_pulled_at", "gacha_pulls",
                    ["user_id", "pulled_at"],
                    postgresql_ops={"pulled_at": "DESC"})
    op.create_index("ix_gacha_pulls_item_received_id", "gacha_pulls", ["item_received_id"])
    op.create_index("ix_gacha_pulls_tx_hash", "gacha_pulls", ["tx_hash"],
                    postgresql_where=sa.text("tx_hash IS NOT NULL"))

    # ══════════════════════════════════════════════════════════════════════════
    # 5. market_listings
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "market_listings",
        _uuid_pk(),
        _uuid("seller_user_id", nullable=False),
        _uuid("item_def_id", nullable=False),
        sa.Column("nft_token_id", sa.String(100), nullable=True),
        sa.Column("listing_type", sa.String(20), nullable=False),  # fixed/auction
        _ftk_col("price_ftk", nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),  # active/sold/cancelled/expired
        _ts("created_at"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["seller_user_id"], ["users.id"],
            name="fk_market_listings_seller_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["item_def_id"], ["item_definitions.id"],
            name="fk_market_listings_item_def_id",
            ondelete="RESTRICT",
        ),
    )
    # browse active listings by item
    op.create_index("ix_market_listings_status_item", "market_listings",
                    ["status", "item_def_id"])
    # price sort for active listings
    op.create_index("ix_market_listings_status_price", "market_listings",
                    ["status", "price_ftk"],
                    postgresql_ops={"price_ftk": "ASC"})
    # seller dashboard
    op.create_index("ix_market_listings_seller_status", "market_listings",
                    ["seller_user_id", "status"])
    # expiry sweep (background job)
    op.create_index("ix_market_listings_expires_at", "market_listings", ["expires_at"],
                    postgresql_where=sa.text("status = 'active'"))

    # ══════════════════════════════════════════════════════════════════════════
    # 6. market_transactions
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "market_transactions",
        _uuid_pk(),
        _uuid("listing_id", nullable=False),
        _uuid("buyer_user_id", nullable=False),
        _uuid("seller_user_id", nullable=False),
        _ftk_col("price_ftk", nullable=False),
        _ftk_col("fee_ftk", nullable=False, server_default="0"),
        _ftk_col("burned_ftk", nullable=False, server_default="0"),
        _ts("completed_at"),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["market_listings.id"],
            name="fk_market_transactions_listing_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["buyer_user_id"], ["users.id"],
            name="fk_market_transactions_buyer_user_id",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["seller_user_id"], ["users.id"],
            name="fk_market_transactions_seller_user_id",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_market_transactions_listing_id", "market_transactions", ["listing_id"])
    op.create_index("ix_market_transactions_buyer_user_id", "market_transactions", ["buyer_user_id"])
    op.create_index("ix_market_transactions_seller_user_id", "market_transactions", ["seller_user_id"])
    op.create_index("ix_market_transactions_tx_hash", "market_transactions", ["tx_hash"],
                    postgresql_where=sa.text("tx_hash IS NOT NULL"))
    # revenue analytics
    op.create_index("ix_market_transactions_completed_at", "market_transactions", ["completed_at"])

    # ══════════════════════════════════════════════════════════════════════════
    # 7. mission_definitions
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "mission_definitions",
        _uuid_pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("mission_type", sa.String(50), nullable=False),  # daily/weekly/story/seasonal
        sa.Column("target_value", sa.Integer(), nullable=False, server_default="1"),
        _ftk_col("reward_ftk", nullable=False, server_default="0"),
        sa.Column("reward_exp", sa.Integer(), nullable=False, server_default="0"),
        _uuid("reward_item_id", nullable=True),
        sa.Column("reset_type", sa.String(20), nullable=False, server_default="none"),  # daily/weekly/none
        sa.Column("level_required", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["reward_item_id"], ["item_definitions.id"],
            name="fk_mission_definitions_reward_item_id",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_mission_definitions_mission_type", "mission_definitions", ["mission_type"])
    op.create_index("ix_mission_definitions_level_required", "mission_definitions", ["level_required"])

    # ══════════════════════════════════════════════════════════════════════════
    # 8. user_missions
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "user_missions",
        _uuid_pk(),
        _uuid("user_id", nullable=False),
        _uuid("mission_def_id", nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_completed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reward_claimed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_user_missions_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["mission_def_id"], ["mission_definitions.id"],
            name="fk_user_missions_mission_def_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_user_missions_user_id", "user_missions", ["user_id"])
    # active mission list
    op.create_index("ix_user_missions_user_completed", "user_missions",
                    ["user_id", "is_completed"])
    # unclaimed rewards sweep
    op.create_index("ix_user_missions_completed_unclaimed", "user_missions",
                    ["user_id", "is_completed", "reward_claimed"],
                    postgresql_where=sa.text("is_completed = true AND reward_claimed = false"))

    # ══════════════════════════════════════════════════════════════════════════
    # 9. achievement_definitions
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "achievement_definitions",
        _uuid_pk(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("condition_type", sa.String(50), nullable=False),
        sa.Column("condition_value", sa.Integer(), nullable=False),
        _ftk_col("reward_ftk", nullable=False, server_default="0"),
        sa.Column("reward_exp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("badge_image_url", sa.Text(), nullable=True),
        sa.UniqueConstraint("name", name="uq_achievement_definitions_name"),
    )
    op.create_index("ix_achievement_definitions_condition_type", "achievement_definitions",
                    ["condition_type"])

    # ══════════════════════════════════════════════════════════════════════════
    # 10. user_achievements  (composite PK – earned once per user)
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "user_achievements",
        _uuid("user_id", primary_key=True, nullable=False),
        _uuid("achievement_def_id", primary_key=True, nullable=False),
        _ts("earned_at"),
        sa.Column("tx_hash", sa.String(66), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_user_achievements_user_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["achievement_def_id"], ["achievement_definitions.id"],
            name="fk_user_achievements_achievement_def_id",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_user_achievements_user_id", "user_achievements", ["user_id"])
    # recent achievements feed
    op.create_index("ix_user_achievements_earned_at", "user_achievements",
                    ["earned_at"],
                    postgresql_ops={"earned_at": "DESC"})

    # ══════════════════════════════════════════════════════════════════════════
    # 11. user_streaks
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "user_streaks",
        _uuid("user_id", primary_key=True, nullable=False),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_login_date", sa.Date(), nullable=True),
        sa.Column("streak_multiplier", sa.Numeric(4, 2), nullable=False, server_default="1.00"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_user_streaks_user_id",
            ondelete="CASCADE",
        ),
    )
    # streak leaderboard
    op.create_index("ix_user_streaks_current_streak", "user_streaks",
                    ["current_streak"],
                    postgresql_ops={"current_streak": "DESC"})
    op.create_index("ix_user_streaks_longest_streak", "user_streaks",
                    ["longest_streak"],
                    postgresql_ops={"longest_streak": "DESC"})

    # ══════════════════════════════════════════════════════════════════════════
    # 12. ftk_transactions  (immutable ledger – no ondelete CASCADE)
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "ftk_transactions",
        _uuid_pk(),
        _uuid("user_id", nullable=False),
        _ftk_col("amount", nullable=False),                        # +credit / -debit
        sa.Column("tx_type", sa.String(50), nullable=False),       # gacha/purchase/reward/transfer/burn/mint/fee
        _uuid("reference_id", nullable=True),
        sa.Column("reference_type", sa.String(50), nullable=True), # gacha_pull/market_transaction/mission/achievement
        _ftk_col("balance_before", nullable=False),
        _ftk_col("balance_after", nullable=False),
        _ts("created_at"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"],
            name="fk_ftk_transactions_user_id",
            ondelete="CASCADE",
        ),
    )
    # wallet history (paginated, most recent first)
    op.create_index("ix_ftk_transactions_user_created_at", "ftk_transactions",
                    ["user_id", "created_at"],
                    postgresql_ops={"created_at": "DESC"})
    # type-level analytics / reporting
    op.create_index("ix_ftk_transactions_tx_type", "ftk_transactions", ["tx_type"])
    op.create_index("ix_ftk_transactions_tx_type_created_at", "ftk_transactions",
                    ["tx_type", "created_at"])
    # reference lookup (e.g. find ledger entry for a gacha_pull id)
    op.create_index("ix_ftk_transactions_reference", "ftk_transactions",
                    ["reference_id", "reference_type"],
                    postgresql_where=sa.text("reference_id IS NOT NULL"))


# ---------------------------------------------------------------------------
# downgrade  (drop in reverse dependency order)
# ---------------------------------------------------------------------------


def downgrade() -> None:
    op.drop_table("ftk_transactions")
    op.drop_table("user_streaks")
    op.drop_table("user_achievements")
    op.drop_table("achievement_definitions")
    op.drop_table("user_missions")
    op.drop_table("mission_definitions")
    op.drop_table("market_transactions")
    op.drop_table("market_listings")
    op.drop_table("gacha_pulls")
    op.drop_table("user_items")
    op.drop_table("item_definitions")
    op.drop_table("game_wallets")
