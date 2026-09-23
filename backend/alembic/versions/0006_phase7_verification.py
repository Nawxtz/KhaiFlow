"""0006_phase7_verification

Revision ID: 0006_phase7
Revises: 0005_phase6
Create Date: 2026-09-23 05:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006_phase7"
down_revision: str | None = "0005_phase6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create verification_logs table matching reference_schema.md and Phase 7 spec
    op.create_table(
        "verification_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("order_id", sa.String(length=100), nullable=True),
        sa.Column("slip_hash", sa.String(length=64), nullable=True),
        sa.Column("channel", sa.String(length=50), nullable=True, server_default="slip"),
        sa.Column(
            "checks_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(length=50), nullable=True),
        sa.Column("result", sa.String(length=50), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_verification_logs_id"), "verification_logs", ["id"], unique=False)
    op.create_index(
        op.f("ix_verification_logs_shop_id"),
        "verification_logs",
        ["shop_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verification_logs_order_id"),
        "verification_logs",
        ["order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_verification_logs_slip_hash"),
        "verification_logs",
        ["slip_hash"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_verification_logs_slip_hash"), table_name="verification_logs")
    op.drop_index(op.f("ix_verification_logs_order_id"), table_name="verification_logs")
    op.drop_index(op.f("ix_verification_logs_shop_id"), table_name="verification_logs")
    op.drop_index(op.f("ix_verification_logs_id"), table_name="verification_logs")
    op.drop_table("verification_logs")
