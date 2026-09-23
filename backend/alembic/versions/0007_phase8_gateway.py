"""0007_phase8_gateway

Revision ID: 0007_phase8
Revises: 0006_phase7
Create Date: 2026-09-23 06:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0007_phase8"
down_revision: str | None = "0006_phase7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # orders.status is stored as sa.String(50). If a native PostgreSQL enum exists,
    # add PAYMENT_RECONCILE to the enum values.
    conn = op.get_bind()
    enum_check = conn.execute(
        sa.text(
            "SELECT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'orderstatus' OR typname = 'order_status');"
        )
    ).scalar()
    if enum_check:
        conn.execute(sa.text("ALTER TYPE orderstatus ADD VALUE IF NOT EXISTS 'PAYMENT_RECONCILE';"))


def downgrade() -> None:
    # No schema change to revert since status is stored as sa.String(50)
    pass
