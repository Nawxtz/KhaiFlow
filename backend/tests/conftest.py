import os
from collections.abc import Generator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

# Pinned test database URL (PostgreSQL required)
TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/app_test",
)

# Set environment before loading app
os.environ["DATABASE_URL"] = TEST_DATABASE_URL

from app.core.database import Base, get_db
from app.main import app
from app.services.cache import inventory_cache

test_engine = create_engine(TEST_DATABASE_URL, pool_pre_ping=True)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Ensure database schema is cleanly initialized for tests using PostgreSQL."""
    # Ensure tables are created
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_db_and_cache():
    """Clean database rows and in-memory cache before every test."""
    inventory_cache.clear()
    with test_engine.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE inventory_sheet_snapshot, inventory, user_prefs, orders, order_items, address_book, consumed_payment_claims, payment_events, reservations, verification_logs, pdpa_deletions RESTART IDENTITY CASCADE;"
            )
        )
        # Pre-seed consent for legacy Phase 4 test users to maintain test suite backward compatibility
        legacy_phase4_users = [
            "U_crud_test_01",
            "U_high_conf_buyer",
            "U_incomplete_buyer",
            "U_returning_buyer_01",
            "U_contradiction_buyer_01",
            "U_dryrun_correct_buyer",
            "U_dryrun_edit_buyer",
            "U_pii_check_user",
        ]
        for uid in legacy_phase4_users:
            conn.execute(
                text(
                    "INSERT INTO user_prefs (user_id, scope, language, theme, pdpa_consent, pdpa_consent_at, updated_at) "
                    "VALUES (:uid, 'buyer', 'th', 'system', true, NOW(), NOW()) ON CONFLICT (user_id, scope) DO NOTHING;"
                ),
                {"uid": uid},
            )
        conn.commit()
    yield
    inventory_cache.clear()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


class MockSheetsClient:
    """Mock implementation of SheetsClientProtocol with call tracking."""

    def __init__(self, rows: list[list[Any]] | None = None):
        self.rows = rows or []
        self.call_count = 0
        self.last_spreadsheet_id = None
        self.last_range = None
        self.appended_rows: list[list[Any]] = []
        self.append_call_count = 0
        self.last_append_spreadsheet_id = None
        self.last_append_range = None
        self.fail_next_n_appends: int = 0
        self.append_error: Exception | None = None

    def get_sheet_values(self, spreadsheet_id: str, range_name: str) -> list[list[Any]]:
        self.call_count += 1
        self.last_spreadsheet_id = spreadsheet_id
        self.last_range = range_name
        return self.rows

    def append_sheet_rows(
        self, spreadsheet_id: str, range_name: str, rows: list[list[Any]]
    ) -> None:
        self.append_call_count += 1
        self.last_append_spreadsheet_id = spreadsheet_id
        self.last_append_range = range_name
        if self.fail_next_n_appends > 0:
            self.fail_next_n_appends -= 1
            from app.services.sheet_ingest import SheetsAPIError

            error = self.append_error or SheetsAPIError("Simulated Sheets API failure")
            raise error
        self.appended_rows.extend(rows)

    def append_sheet_row(self, spreadsheet_id: str, range_name: str, values: list[Any]) -> None:
        self.append_sheet_rows(spreadsheet_id, range_name, [values])

    def append_row(self, spreadsheet_id: str, range_name: str, values: list[Any]) -> None:
        self.append_sheet_row(spreadsheet_id, range_name, values)


@pytest.fixture
def sample_sheet_data() -> list[list[Any]]:
    return [
        ["SKU", "Name", "Category", "Price", "Image URL", "Stock", "Active"],
        [
            "SKU-001",
            "Thai Silk Scarf",
            "Accessories",
            "450.00",
            "https://example.com/scarf.jpg",
            "20",
            "TRUE",
        ],
        [
            "SKU-002",
            "Handmade Clay Mug",
            "Home",
            "280.00",
            "https://example.com/mug.jpg",
            "15",
            "TRUE",
        ],
        ["SKU-003", "Cotton T-Shirt", "Apparel", "350.00", "", "50", "FALSE"],
    ]
