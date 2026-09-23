"""0004_phase4_address_book

Revision ID: 0004_phase4
Revises: 0003_phase3
Create Date: 2026-09-23 03:40:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_phase4"
down_revision: str | None = "0003_phase3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Create address_book table
    op.create_table(
        "address_book",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("shop_id", sa.String(length=100), nullable=True),
        sa.Column("line_user_id", sa.String(length=100), nullable=False),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.Column("receiver_name", sa.String(length=255), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=False),
        sa.Column(
            "address_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "is_default",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_address_book_id"), "address_book", ["id"], unique=False)
    op.create_index(op.f("ix_address_book_shop_id"), "address_book", ["shop_id"], unique=False)
    op.create_index(
        op.f("ix_address_book_line_user_id"), "address_book", ["line_user_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_address_book_line_user_id"), table_name="address_book")
    op.drop_index(op.f("ix_address_book_shop_id"), table_name="address_book")
    op.drop_index(op.f("ix_address_book_id"), table_name="address_book")
    op.drop_table("address_book")
