import pytest
from pydantic import ValidationError

import app.main as main_module
from app.core.config import Settings, check_runtime_settings
from app.models import Base

PRODUCTION_DB = "postgresql://u:p@db.example/prod"
COMPLETE = {
    "DATABASE_URL": PRODUCTION_DB,
    "LINE_CHANNEL_SECRET": "value-a",
    "LINE_CHANNEL_ACCESS_TOKEN": "value-b",
    "PAYMENT_QR_SECRET": "value-c",
}


def _settings(**values) -> Settings:
    return Settings(_env_file=None, **values)


def test_production_refuses_to_start_without_secrets_and_names_only_the_keys():
    values = {**COMPLETE, "LINE_CHANNEL_SECRET": ""}

    with pytest.raises(RuntimeError) as err:
        check_runtime_settings(_settings(APP_ENV="production", **values))

    assert "LINE_CHANNEL_SECRET" in str(err.value)
    assert "value-b" not in str(err.value)


def test_production_refuses_the_default_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    values = {k: v for k, v in COMPLETE.items() if k != "DATABASE_URL"}

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        check_runtime_settings(_settings(APP_ENV="production", **values))


def test_production_starts_when_everything_is_set():
    check_runtime_settings(_settings(APP_ENV="production", **COMPLETE))


def test_development_needs_no_secrets():
    check_runtime_settings(_settings(APP_ENV="development"))


def test_misspelled_environment_fails_instead_of_running_as_development():
    with pytest.raises((RuntimeError, ValidationError)):
        check_runtime_settings(_settings(APP_ENV="prod"))


def test_failed_migration_stops_startup_and_never_creates_tables(monkeypatch):
    created: list[bool] = []

    def failing_upgrade(*_args, **_kwargs):
        raise ValueError("migration failed")

    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setattr(main_module.command, "upgrade", failing_upgrade)
    monkeypatch.setattr(Base.metadata, "create_all", lambda **_kwargs: created.append(True))

    with pytest.raises(ValueError, match="migration failed"):
        main_module.run_migrations()

    assert created == []


def test_startup_does_not_seed_demo_data():
    assert not hasattr(main_module, "run_migrations_and_seed")
