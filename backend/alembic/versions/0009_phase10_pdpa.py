"""0009_phase10_pdpa

Revision ID: 0009_phase10
Revises: 0008_phase9
Create Date: 2026-09-23 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0009_phase10"
down_revision: str | None = "0008_phase9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create pdpa_deletions table per reference_schema.md
    op.create_table(
        "pdpa_deletions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("line_user_id", sa.String(length=100), nullable=False),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_pdpa_deletions_id"), "pdpa_deletions", ["id"], unique=False)
    op.create_index(
        op.f("ix_pdpa_deletions_shop_id"), "pdpa_deletions", ["shop_id"], unique=False
    )
    op.create_index(
        op.f("ix_pdpa_deletions_line_user_id"),
        "pdpa_deletions",
        ["line_user_id"],
        unique=False,
    )

    # 2. Add pdpa_consent and pdpa_consent_at columns to user_prefs
    op.add_column(
        "user_prefs",
        sa.Column(
            "pdpa_consent",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "user_prefs",
        sa.Column("pdpa_consent_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    # 1. Remove columns from user_prefs
    op.drop_column("user_prefs", "pdpa_consent_at")
    op.drop_column("user_prefs", "pdpa_consent")

    # 2. Drop pdpa_deletions table
    op.drop_index(op.f("ix_pdpa_deletions_line_user_id"), table_name="pdpa_deletions")
    op.drop_index(op.f("ix_pdpa_deletions_shop_id"), table_name="pdpa_deletions")
    op.drop_index(op.f("ix_pdpa_deletions_id"), table_name="pdpa_deletions")
    op.drop_table("pdpa_deletions")
