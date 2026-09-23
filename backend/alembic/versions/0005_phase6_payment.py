"""0005_phase6_payment

Revision ID: 0005_phase6
Revises: 0004_phase4
Create Date: 2026-09-23 04:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005_phase6"
down_revision: str | None = "0004_phase4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create consumed_payment_claims table
    op.create_table(
        "consumed_payment_claims",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("claim_key", sa.String(length=255), nullable=False),
        sa.Column("claim_type", sa.String(length=50), nullable=True, server_default="ref"),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=50), nullable=True, server_default="CONFIRMED"),
        sa.Column(
            "consumed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("claim_key", name="uq_consumed_payment_claims_claim_key"),
    )
    op.create_index(
        op.f("ix_consumed_payment_claims_id"), "consumed_payment_claims", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_consumed_payment_claims_shop_id"),
        "consumed_payment_claims",
        ["shop_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_consumed_payment_claims_claim_key"),
        "consumed_payment_claims",
        ["claim_key"],
        unique=True,
    )
    op.create_index(
        op.f("ix_consumed_payment_claims_order_id"),
        "consumed_payment_claims",
        ["order_id"],
        unique=False,
    )

    # 2. Create payment_events table
    op.create_table(
        "payment_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("event_key", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=True),
        sa.Column(
            "payload_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("payload_hash", sa.String(length=64), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key", name="uq_payment_events_event_key"),
    )
    op.create_index(op.f("ix_payment_events_id"), "payment_events", ["id"], unique=False)
    op.create_index(op.f("ix_payment_events_shop_id"), "payment_events", ["shop_id"], unique=False)
    op.create_index(
        op.f("ix_payment_events_order_id"), "payment_events", ["order_id"], unique=False
    )
    op.create_index(
        op.f("ix_payment_events_event_key"), "payment_events", ["event_key"], unique=True
    )

    # 3. Create reservations table
    op.create_table(
        "reservations",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=False),
        sa.Column("sku", sa.String(length=100), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "state",
            sa.String(length=50),
            nullable=False,
            server_default="RESERVED",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reservations_id"), "reservations", ["id"], unique=False)
    op.create_index(op.f("ix_reservations_shop_id"), "reservations", ["shop_id"], unique=False)
    op.create_index(op.f("ix_reservations_order_id"), "reservations", ["order_id"], unique=False)
    op.create_index(op.f("ix_reservations_sku"), "reservations", ["sku"], unique=False)
    op.create_index(op.f("ix_reservations_state"), "reservations", ["state"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_reservations_state"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_sku"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_order_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_shop_id"), table_name="reservations")
    op.drop_index(op.f("ix_reservations_id"), table_name="reservations")
    op.drop_table("reservations")

    op.drop_index(op.f("ix_payment_events_event_key"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_order_id"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_shop_id"), table_name="payment_events")
    op.drop_index(op.f("ix_payment_events_id"), table_name="payment_events")
    op.drop_table("payment_events")

    op.drop_index(op.f("ix_consumed_payment_claims_order_id"), table_name="consumed_payment_claims")
    op.drop_index(
        op.f("ix_consumed_payment_claims_claim_key"), table_name="consumed_payment_claims"
    )
    op.drop_index(op.f("ix_consumed_payment_claims_shop_id"), table_name="consumed_payment_claims")
    op.drop_index(op.f("ix_consumed_payment_claims_id"), table_name="consumed_payment_claims")
    op.drop_table("consumed_payment_claims")
