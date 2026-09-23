import logging
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.snapshot import InventorySheetSnapshot
from app.services.cache import inventory_cache
from app.services.sheet_ingest import SheetIngestService
from tests.conftest import MockSheetsClient


def test_ingest_reads_sheet_correctly_on_first_run(
    db_session: Session, sample_sheet_data: list[list[Any]]
):
    """
    Test 1 (TEST_PLAN.md): Ingest reads the sheet correctly into DB on first run.
    Verifies that rows are parsed, models are inserted into PostgreSQL, and snapshots are populated.
    """
    mock_client = MockSheetsClient(sample_sheet_data)
    service = SheetIngestService(sheets_client=mock_client)

    summary = service.ingest_from_values(sample_sheet_data, db=db_session, shop_id="default")

    assert summary.rows_total == 3
    assert summary.rows_valid == 3
    assert summary.rows_inserted == 3
    assert summary.rows_updated == 0
    assert summary.rows_unchanged == 0
    assert summary.rows_skipped == 0

    # Verify inventory records in DB
    items = db_session.query(Inventory).order_by(Inventory.sku).all()
    assert len(items) == 3

    item1 = items[0]
    assert item1.sku == "SKU-001"
    assert item1.name == "Thai Silk Scarf"
    assert item1.category == "Accessories"
    assert item1.price == Decimal("450.00")
    assert item1.image_url == "https://example.com/scarf.jpg"
    assert item1.stock == 20
    assert item1.reserved == 0
    assert item1.active is True
    assert item1.version == 1

    item3 = items[2]
    assert item3.sku == "SKU-003"
    assert item3.active is False

    # Verify snapshots populated for all tracked fields
    snapshots = db_session.query(InventorySheetSnapshot).filter_by(sku="SKU-001").all()
    assert len(snapshots) == 6
    snap_dict = {s.field: s.last_value for s in snapshots}
    assert snap_dict["price"] == "450.00"
    assert snap_dict["stock"] == "20"
    assert snap_dict["active"] == "true"


def test_cache_serves_reads_without_calling_sheets_api(
    client: TestClient,
    db_session: Session,
    sample_sheet_data: list[list[Any]],
):
    """
    Test 2 (TEST_PLAN.md): Cache serves reads without calling the Sheets API per request.
    Verifies that the GET /api/inventory endpoint serves cached data and never touches Sheets API.
    """
    mock_client = MockSheetsClient(sample_sheet_data)
    service = SheetIngestService(sheets_client=mock_client)
    service.ingest_from_values(sample_sheet_data, db=db_session, shop_id="default")

    # Invalidate and reset cache stats to observe behavior
    inventory_cache.clear()

    # Request 1: Cache miss -> loads from PostgreSQL DB into cache
    resp1 = client.get("/api/inventory?shop_id=default")
    assert resp1.status_code == 200
    data1 = resp1.json()
    # Note: SKU-003 has active=False, so active=True catalog returns 2 items
    assert len(data1) == 2
    assert inventory_cache.misses == 1
    assert inventory_cache.hits == 0

    # Request 2: Served directly from cache
    resp2 = client.get("/api/inventory?shop_id=default")
    assert resp2.status_code == 200
    assert resp2.json() == data1
    assert inventory_cache.hits == 1
    assert inventory_cache.misses == 1

    # Request 3: Served directly from cache
    resp3 = client.get("/api/inventory?shop_id=default")
    assert resp3.status_code == 200
    assert inventory_cache.hits == 2

    # CRITICAL: Sheets API client call count is 0 for all GET requests!
    assert mock_client.call_count == 0


def test_no_clobber_cur_equals_snap_no_write(
    db_session: Session, sample_sheet_data: list[list[Any]]
):
    """
    Test 3 (TEST_PLAN.md): cur == snap -> no write (base case for the no-clobber rule).
    Verifies that when sheet values match the snapshot, subsequent ingests do NOT write
    to the DB, preserving any local/portal changes made in the database.
    """
    mock_client = MockSheetsClient(sample_sheet_data)
    service = SheetIngestService(sheets_client=mock_client)

    # 1. Initial ingest
    summary1 = service.ingest_from_values(sample_sheet_data, db=db_session, shop_id="default")
    assert summary1.rows_inserted == 3

    # 2. Simulate local DB modification (e.g. portal edit: price modified to 599.00)
    item = db_session.query(Inventory).filter_by(sku="SKU-001").first()
    assert item is not None
    item.price = Decimal("599.00")
    item.version = 2
    db_session.commit()

    # 3. Second ingest with the identical sheet data (cur == snap)
    summary2 = service.ingest_from_values(sample_sheet_data, db=db_session, shop_id="default")

    # Ingest should report rows_unchanged and 0 updates/inserts
    assert summary2.rows_inserted == 0
    assert summary2.rows_updated == 0
    assert summary2.rows_unchanged == 3

    # 4. Verify no-clobber rule: the local DB price of 599.00 was NOT overwritten by the sheet!
    db_session.refresh(item)
    assert item.price == Decimal("599.00")
    assert item.version == 2


def test_invalid_rows_are_skipped_and_logged_without_crashing(db_session: Session, caplog: Any):
    """
    Test 4 (TEST_PLAN.md): Invalid rows are skipped and logged; they do not crash the ingest.
    Verifies graceful skipping of missing SKU, missing Name, invalid Price, invalid Stock,
    and invalid Active flag.
    """
    sheet_with_invalid_rows = [
        ["SKU", "Name", "Category", "Price", "Image URL", "Stock", "Active"],
        # Valid row 1
        ["SKU-OK1", "Good Item 1", "Misc", "100.00", "", "10", "TRUE"],
        # Missing SKU
        ["", "Missing SKU Item", "Misc", "100.00", "", "10", "TRUE"],
        # Missing Name
        ["SKU-NONAME", "", "Misc", "100.00", "", "10", "TRUE"],
        # Invalid Price (text)
        ["SKU-BADP1", "Bad Price Text", "Misc", "FREE", "", "10", "TRUE"],
        # Invalid Price (negative)
        ["SKU-BADP2", "Bad Price Neg", "Misc", "-50.00", "", "10", "TRUE"],
        # Invalid Stock (text)
        ["SKU-BADS1", "Bad Stock Text", "Misc", "100.00", "", "many", "TRUE"],
        # Invalid Stock (negative)
        ["SKU-BADS2", "Bad Stock Neg", "Misc", "100.00", "", "-5", "TRUE"],
        # Invalid Active flag
        ["SKU-BADA", "Bad Active", "Misc", "100.00", "", "10", "PERHAPS"],
        # Valid row 2
        ["SKU-OK2", "Good Item 2", "Misc", "250.00", "", "5", "FALSE"],
    ]

    service = SheetIngestService(sheets_client=MockSheetsClient())
    caplog.set_level(logging.WARNING)

    summary = service.ingest_from_values(sheet_with_invalid_rows, db=db_session, shop_id="default")

    # Ingest completed without crashing
    assert summary.rows_total == 9
    assert summary.rows_valid == 2
    assert summary.rows_skipped == 7
    assert summary.rows_inserted == 2

    # DB contains only valid rows
    items = db_session.query(Inventory).order_by(Inventory.sku).all()
    assert len(items) == 2
    assert items[0].sku == "SKU-OK1"
    assert items[1].sku == "SKU-OK2"

    # Verify that warnings were logged and recorded for invalid rows
    all_reasons = " ".join(summary.skipped_reasons) + " " + caplog.text
    assert "missing SKU" in all_reasons
    assert "missing Name" in all_reasons
    assert "invalid price" in all_reasons
    assert "invalid stock" in all_reasons
    assert "invalid active flag" in all_reasons


def test_no_real_credentials_needed_in_tests(
    db_session: Session, sample_sheet_data: list[list[Any]]
):
    """
    Test 5 (TEST_PLAN.md): No real Google credentials are needed in tests (mock the Sheets client).
    Verifies that the entire ingest workflow functions using mock client with no Google credentials.
    """
    mock_client = MockSheetsClient(sample_sheet_data)
    service = SheetIngestService(sheets_client=mock_client)

    # Calling ingest_sheet using mock client
    summary = service.ingest_sheet(
        db=db_session,
        spreadsheet_id="mock-sheet-12345",
        range_name="Inventory!A1:G",
        shop_id="default",
    )

    assert mock_client.call_count == 1
    assert mock_client.last_spreadsheet_id == "mock-sheet-12345"
    assert mock_client.last_range == "Inventory!A1:G"
    assert summary.rows_valid == 3


def test_stock_endpoint_returns_available_stock(client: TestClient, db_session: Session):
    """
    Acceptance criterion (§20): Stock endpoint returns available stock (stock - reserved).
    """
    item1 = Inventory(
        sku="SKU-STOCK1",
        shop_id="default",
        name="Reserved Item",
        category="Test",
        price=Decimal("100.00"),
        stock=10,
        reserved=3,
        active=True,
        version=1,
    )
    item2 = Inventory(
        sku="SKU-STOCK2",
        shop_id="default",
        name="Fully Held Item",
        category="Test",
        price=Decimal("200.00"),
        stock=5,
        reserved=5,
        active=True,
        version=1,
    )
    db_session.add_all([item1, item2])
    db_session.commit()

    resp = client.get("/api/inventory?shop_id=default")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    by_sku = {d["sku"]: d for d in data}
    assert by_sku["SKU-STOCK1"]["stock"] == 10
    assert by_sku["SKU-STOCK1"]["reserved"] == 3
    assert by_sku["SKU-STOCK1"]["available_stock"] == 7

    assert by_sku["SKU-STOCK2"]["stock"] == 5
    assert by_sku["SKU-STOCK2"]["reserved"] == 5
    assert by_sku["SKU-STOCK2"]["available_stock"] == 0


def test_sheet_edits_update_db_when_cur_differs_from_snap(
    db_session: Session, sample_sheet_data: list[list[Any]]
):
    """
    Verifies that when a genuine sheet edit occurs (cur != snap), the DB is updated
    and snapshot is advanced.
    """
    mock_client = MockSheetsClient(sample_sheet_data)
    service = SheetIngestService(sheets_client=mock_client)

    # Initial ingest
    service.ingest_from_values(sample_sheet_data, db=db_session, shop_id="default")

    # Seller updates stock and price in Google Sheet
    updated_sheet_data = [
        ["SKU", "Name", "Category", "Price", "Image URL", "Stock", "Active"],
        [
            "SKU-001",
            "Thai Silk Scarf",
            "Accessories",
            "499.00",
            "https://example.com/scarf.jpg",
            "35",
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

    summary = service.ingest_from_values(updated_sheet_data, db=db_session, shop_id="default")
    assert summary.rows_updated == 1
    assert summary.rows_unchanged == 2

    item = db_session.query(Inventory).filter_by(sku="SKU-001").first()
    assert item is not None
    assert item.price == Decimal("499.00")
    assert item.stock == 35
    assert item.version == 2

    # Snapshot advanced
    snap_p = (
        db_session.query(InventorySheetSnapshot).filter_by(sku="SKU-001", field="price").first()
    )
    assert snap_p is not None
    assert snap_p.last_value == "499.00"
