"""Expand chickens table with NFT/IoT fields; add chicken_logs table.

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a2
Create Date: 2026-05-05 02:00:00.000000

Changes
-------
chickens
  + nft_token_id      VARCHAR(100) UNIQUE NULL  – on-chain token ID
  + nft_tier          VARCHAR(20)  NOT NULL DEFAULT 'bronze'
  + chip_id           VARCHAR(50)  UNIQUE NULL  – IoT device identifier
  + health_score      NUMERIC(5,2) NOT NULL DEFAULT 100
  + weight_kg         NUMERIC(6,3) NOT NULL DEFAULT 0
  + birth_date        DATE NULL
  + zone              VARCHAR(20)  NULL
  + status            VARCHAR(20)  NOT NULL DEFAULT 'active'
  + steps_today       INTEGER      NOT NULL DEFAULT 0
  + live_cam_url      TEXT NULL
  + blockchain_metadata_url TEXT NULL
  + last_fed_at       TIMESTAMPTZ NULL

chicken_logs (new table)
  id, chicken_id FK, performed_by_user_id FK, log_type,
  data JSONB, notes, created_at

Indexes
-------
  ix_chickens_nft_tier             → fast tier-based filtering
  ix_chickens_status               → farm health dashboard
  ix_chickens_health_leaderboard   → TOP health_score DESC
  ix_chickens_user_status          → per-user active list
  ix_chicken_logs_chicken_id       → log history per chicken
  ix_chicken_logs_type_created     → (chicken_id, log_type, created_at) for quota check
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b7c8d9e0f1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NOW = sa.text("now()")
_UUID_DEFAULT = sa.text("gen_random_uuid()")


def upgrade() -> None:
    # ══════════════════════════════════════════════════════════════════════════
    # 1. Expand chickens
    # ══════════════════════════════════════════════════════════════════════════
    with op.batch_alter_table("chickens") as batch:
        batch.add_column(
            sa.Column("nft_token_id", sa.String(100), nullable=True)
        )
        batch.add_column(
            sa.Column("nft_tier", sa.String(20), nullable=False, server_default="bronze")
        )
        batch.add_column(
            sa.Column("chip_id", sa.String(50), nullable=True)
        )
        batch.add_column(
            sa.Column(
                "health_score", sa.Numeric(5, 2), nullable=False, server_default="100.00"
            )
        )
        batch.add_column(
            sa.Column(
                "weight_kg", sa.Numeric(6, 3), nullable=False, server_default="0.000"
            )
        )
        batch.add_column(sa.Column("birth_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("zone", sa.String(20), nullable=True))
        batch.add_column(
            sa.Column("status", sa.String(20), nullable=False, server_default="active")
        )
        batch.add_column(
            sa.Column("steps_today", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(sa.Column("live_cam_url", sa.Text(), nullable=True))
        batch.add_column(
            sa.Column("blockchain_metadata_url", sa.Text(), nullable=True)
        )
        batch.add_column(
            sa.Column("last_fed_at", sa.DateTime(timezone=True), nullable=True)
        )
        # Unique constraints
        batch.create_unique_constraint("uq_chickens_nft_token_id", ["nft_token_id"])
        batch.create_unique_constraint("uq_chickens_chip_id", ["chip_id"])

    # Indexes on chickens
    op.create_index("ix_chickens_nft_tier", "chickens", ["nft_tier"])
    op.create_index("ix_chickens_status", "chickens", ["status"])
    op.create_index(
        "ix_chickens_health_leaderboard",
        "chickens",
        ["health_score"],
        postgresql_ops={"health_score": "DESC"},
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "ix_chickens_user_status",
        "chickens",
        ["user_id", "status"],
    )

    # ══════════════════════════════════════════════════════════════════════════
    # 2. Create chicken_logs
    # ══════════════════════════════════════════════════════════════════════════
    op.create_table(
        "chicken_logs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=_UUID_DEFAULT
        ),
        sa.Column(
            "chicken_id",
            UUID(as_uuid=True),
            sa.ForeignKey("chickens.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "performed_by_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("log_type", sa.String(30), nullable=False),
        sa.Column("data", JSONB, nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_NOW,
        ),
    )

    # Indexes on chicken_logs
    op.create_index("ix_chicken_logs_chicken_id", "chicken_logs", ["chicken_id"])
    op.create_index(
        "ix_chicken_logs_type_created",
        "chicken_logs",
        ["chicken_id", "log_type", "created_at"],
        postgresql_ops={"created_at": "DESC"},
    )
    # Fast quota check: count today's "fed" events per chicken
    op.create_index(
        "ix_chicken_logs_fed_today",
        "chicken_logs",
        ["chicken_id", "created_at"],
        postgresql_where=sa.text("log_type = 'fed'"),
    )
    # Health history: 30-day range scan
    op.create_index(
        "ix_chicken_logs_health_created",
        "chicken_logs",
        ["chicken_id", "created_at"],
        postgresql_where=sa.text("log_type = 'health_check'"),
    )


def downgrade() -> None:
    op.drop_table("chicken_logs")

    with op.batch_alter_table("chickens") as batch:
        batch.drop_constraint("uq_chickens_chip_id", type_="unique")
        batch.drop_constraint("uq_chickens_nft_token_id", type_="unique")
        for col in (
            "last_fed_at",
            "blockchain_metadata_url",
            "live_cam_url",
            "steps_today",
            "status",
            "zone",
            "birth_date",
            "weight_kg",
            "health_score",
            "chip_id",
            "nft_tier",
            "nft_token_id",
        ):
            batch.drop_column(col)
