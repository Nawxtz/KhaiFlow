"""0002_phase2_user_prefs

Revision ID: 0002_phase2
Revises: 0001_phase1
Create Date: 2026-09-23 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_phase2"
down_revision: str | None = "0001_phase1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_prefs",
        sa.Column("user_id", sa.String(length=100), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="buyer"),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False, server_default="th"),
        sa.Column("theme", sa.String(length=20), nullable=False, server_default="system"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("user_id", "scope"),
    )
    op.create_index(op.f("ix_user_prefs_shop_id"), "user_prefs", ["shop_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_prefs_shop_id"), table_name="user_prefs")
    op.drop_table("user_prefs")
