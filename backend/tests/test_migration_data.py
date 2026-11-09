import importlib
import os

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text

from alembic import command
from tests.conftest import TEST_DATABASE_URL, test_engine

# Migrations that existed when this check was added. Every later one needs tests/migration_data/<revision>.py with:
#   seed(conn): insert rows at the previous revision, including rows outside the happy path
#   check(conn): assert the data is right after the migration
#   ROW_CHANGES (optional): {table: expected change in row count}
#   DROPPED (optional): tables the migration removes on purpose
BASELINE = {
    "0001_phase1", "0002_phase2", "0003_phase3", "0004_phase4", "0005_phase6", "0006_phase7",
    "0007_phase8", "0008_phase9", "0009_phase10", "0010_auth", "0011_audit",
}
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BACKEND_DIR, "tests", "migration_data")


def alembic_config():
    cfg = Config(os.path.join(BACKEND_DIR, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(BACKEND_DIR, "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    return cfg


def new_revisions():
    script = ScriptDirectory.from_config(alembic_config())
    return [s for s in reversed(list(script.walk_revisions())) if s.revision not in BASELINE]


def reset_schema():
    with test_engine.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.commit()


def table_counts(conn):
    tables = [t for t in inspect(conn).get_table_names() if t != "alembic_version"]
    return {t: conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar_one() for t in tables}


def test_every_new_migration_has_a_data_check():
    missing = [s.revision for s in new_revisions() if not os.path.exists(os.path.join(DATA_DIR, f"{s.revision}.py"))]
    assert not missing, f"add tests/migration_data/<revision>.py for: {missing}"


@pytest.mark.parametrize("script", new_revisions(), ids=lambda s: s.revision)
def test_new_migration_keeps_rows(script):
    data = importlib.import_module(f"tests.migration_data.{script.revision}")
    changes, dropped = getattr(data, "ROW_CHANGES", {}), getattr(data, "DROPPED", ())
    cfg = alembic_config()
    reset_schema()
    try:
        command.upgrade(cfg, script.down_revision)
        with test_engine.begin() as conn:
            data.seed(conn)
            before = table_counts(conn)
        assert any(before.values()), "seed() must insert rows"

        command.upgrade(cfg, script.revision)
        with test_engine.begin() as conn:
            after = table_counts(conn)
            for table, count in before.items():
                if table not in after:
                    assert table in dropped, f"{table} disappeared without being declared in DROPPED"
                    continue
                assert after[table] == count + changes.get(table, 0), f"{table}: {count} rows became {after[table]}"
            data.check(conn)
    finally:
        reset_schema()
        command.upgrade(cfg, "head")
