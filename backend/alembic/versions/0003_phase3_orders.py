"""0003_phase3_orders

Revision ID: 0003_phase3
Revises: 0002_phase2
Create Date: 2026-09-23 03:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_phase3"
down_revision: str | None = "0002_phase2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create orders table
    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("line_user_id", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.String(length=50),
            nullable=False,
            server_default="BROWSING",
        ),
        sa.Column(
            "total",
            sa.Numeric(precision=10, scale=2),
            nullable=False,
            server_default="0.00",
        ),
        sa.Column(
            "currency",
            sa.String(length=10),
            nullable=False,
            server_default="THB",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("ttl_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approval_state", sa.String(length=50), nullable=True),
        sa.Column("payment_ref", sa.String(length=100), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_id"), "orders", ["id"], unique=False)
    op.create_index(op.f("ix_orders_shop_id"), "orders", ["shop_id"], unique=False)
    op.create_index(op.f("ix_orders_line_user_id"), "orders", ["line_user_id"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_index(op.f("ix_orders_payment_ref"), "orders", ["payment_ref"], unique=False)

    # 2. Create order_items table
    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("size", sa.String(length=50), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("line_total", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_order_items_order_id"), "order_items", ["order_id"], unique=False)
    op.create_index(op.f("ix_order_items_shop_id"), "order_items", ["shop_id"], unique=False)
    op.create_index(op.f("ix_order_items_sku"), "order_items", ["sku"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_order_items_sku"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_shop_id"), table_name="order_items")
    op.drop_index(op.f("ix_order_items_order_id"), table_name="order_items")
    op.drop_table("order_items")

    op.drop_index(op.f("ix_orders_payment_ref"), table_name="orders")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_line_user_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_shop_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_id"), table_name="orders")
    op.drop_table("orders")
