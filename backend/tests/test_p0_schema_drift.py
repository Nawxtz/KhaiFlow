import os

from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import text

from alembic import command
from app.core.database import Base
from tests.conftest import TEST_DATABASE_URL, test_engine

# Redundant objects from older migrations that the models do not declare. The primary keys and
# unique indexes already cover these columns, so they are harmless; anything new must fail.
KNOWN_EXTRA_IN_MIGRATIONS = {
    "ix_consumed_payment_claims_id",
    "uq_consumed_payment_claims_claim_key",
    "ix_payment_events_id",
    "uq_payment_events_event_key",
    "ix_reservations_id",
    "ix_verification_logs_id",
}


def test_migrations_from_empty_database_match_models():
    """Tables built by Alembic alone must match the SQLAlchemy models."""
    with test_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.commit()

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(alembic_cfg, "head")

    with test_engine.connect() as conn:
        drift = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    unexpected = [
        item
        for item in drift
        if not (
            isinstance(item, tuple)
            and item[0] in ("remove_index", "remove_constraint")
            and item[1].name in KNOWN_EXTRA_IN_MIGRATIONS
        )
    ]
    assert unexpected == []
