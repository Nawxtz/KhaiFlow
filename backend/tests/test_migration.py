import os

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from tests.conftest import TEST_DATABASE_URL, test_engine


def test_alembic_migrations_clean_upgrade_and_downgrade():
    """
    Migration test (TEST_PLAN.md): Migrations run cleanly from an empty database.
    Verifies upgrade head and downgrade base execute without error.
    """
    # Start with a pristine schema on the test DB
    with test_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.commit()

    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)

    # 1. Upgrade to head from clean scratch
    command.upgrade(alembic_cfg, "head")

    # 2. Downgrade to base
    command.downgrade(alembic_cfg, "base")

    # 3. Re-upgrade to head so remaining tests have tables
    command.upgrade(alembic_cfg, "head")
