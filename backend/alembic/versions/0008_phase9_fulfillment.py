"""0008_phase9_fulfillment

Revision ID: 0008_phase9
Revises: 0007_phase8
Create Date: 2026-09-23 07:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0008_phase9"
down_revision: str | None = "0007_phase8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Schema Governance Note:
    # orders.status is stored as sa.String(50). No new tables or columns beyond reference_schema.md.
    # The FULFILLED status transition acts as the sync marker.
    # If a native PostgreSQL enum type exists, add FULFILLED to the enum values.
    conn = op.get_bind()
    enum_check = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus' OR typname = 'order_status');"
        )
    ).scalar()
    if enum_check:
        conn.execute(sa.text("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'FULFILLED';"))


def downgrade() -> None:
    # No new tables or columns to drop.
    pass
