"""0001_phase1_inventory

Revision ID: 0001_phase1
Revises:
Create Date: 2026-09-23 02:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_phase1"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "inventory",
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("image_url", sa.String(length=1024), nullable=True),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("reserved", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.PrimaryKeyConstraint("sku"),
    )
    op.create_index(op.f("ix_inventory_sku"), "inventory", ["sku"], unique=False)
    op.create_index(op.f("ix_inventory_shop_id"), "inventory", ["shop_id"], unique=False)
    op.create_index(op.f("ix_inventory_category"), "inventory", ["category"], unique=False)

    op.create_table(
        "inventory_sheet_snapshot",
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("field", sa.String(length=50), nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("last_value", sa.String(length=1024), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("sku", "field"),
    )
    op.create_index(
        op.f("ix_inventory_sheet_snapshot_shop_id"),
        "inventory_sheet_snapshot",
        ["shop_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_inventory_sheet_snapshot_shop_id"), table_name="inventory_sheet_snapshot"
    )
    op.drop_table("inventory_sheet_snapshot")
    op.drop_index(op.f("ix_inventory_category"), table_name="inventory")
    op.drop_index(op.f("ix_inventory_shop_id"), table_name="inventory")
    op.drop_index(op.f("ix_inventory_sku"), table_name="inventory")
    op.drop_table("inventory")
