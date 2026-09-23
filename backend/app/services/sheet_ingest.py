import logging
import re
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.inventory import Inventory
from app.models.snapshot import InventorySheetSnapshot
from app.schemas.inventory import IngestSummary
from app.services.cache import inventory_cache

logger = logging.getLogger(__name__)

# Canonical fields tracked in snapshot
TRACKED_FIELDS = ["name", "category", "price", "image_url", "stock", "active"]


class SheetsAPIError(Exception):
    """Raised when an interaction with Google Sheets API fails."""

    pass


class SheetsClientProtocol(Protocol):
    """Protocol for fetching raw rows from and appending rows to a Google Sheet."""

    def get_sheet_values(self, spreadsheet_id: str, range_name: str) -> list[list[Any]]: ...

    def append_sheet_row(self, spreadsheet_id: str, range_name: str, values: list[Any]) -> None: ...

    def append_sheet_rows(self, spreadsheet_id: str, range_name: str, rows: list[list[Any]]) -> None: ...


class GoogleSheetsClient:
    """Official Google Sheets API client using service account credentials."""

    def __init__(self, service_account_path: str | None = None):
        self.service_account_path = (
            service_account_path or settings.GOOGLE_SERVICE_ACCOUNT_JSON_PATH
        )
        self._service = None

    def _get_service(self):
        if self._service is None:
            if not self.service_account_path:
                raise ValueError("Google service account JSON path is not configured.")
            from google.oauth2 import service_account
            from googleapiclient.discovery import build  # type: ignore[import-untyped]

            creds = service_account.Credentials.from_service_account_file(
                self.service_account_path,
                scopes=["https://www.googleapis.com/auth/spreadsheets"],
            )
            self._service = build("sheets", "v4", credentials=creds)
        return self._service

    def get_sheet_values(self, spreadsheet_id: str, range_name: str) -> list[list[Any]]:
        try:
            service = self._get_service()
            result = (
                service.spreadsheets()
                .values()
                .get(spreadsheetId=spreadsheet_id, range=range_name)
                .execute()
            )
            return result.get("values", [])
        except Exception as e:
            raise SheetsAPIError(f"Failed to get values from sheet: {e}") from e

    def append_sheet_rows(
        self, spreadsheet_id: str, range_name: str, rows: list[list[Any]]
    ) -> None:
        try:
            service = self._get_service()
            body = {"values": rows}
            service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
        except Exception as e:
            raise SheetsAPIError(f"Failed to append rows to sheet: {e}") from e

    def append_sheet_row(self, spreadsheet_id: str, range_name: str, values: list[Any]) -> None:
        self.append_sheet_rows(spreadsheet_id, range_name, [values])

    def append_row(self, spreadsheet_id: str, range_name: str, values: list[Any]) -> None:
        self.append_sheet_row(spreadsheet_id, range_name, values)


def _normalize_header(header: str) -> str:
    return re.sub(r"[\s_-]+", "", header.strip().lower())


def _parse_bool(val: Any) -> bool | None:
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in {"true", "1", "yes", "y", "active", "on"}:
        return True
    if s in {"false", "0", "no", "n", "inactive", "off"}:
        return False
    return None


def _clean_number_str(val: Any) -> str:
    s = str(val).strip()
    # Remove currency symbols and comma separators
    s = re.sub(r"[\u0e3fTHBthb,\s$]", "", s)
    return s


def parse_sheet_rows(
    raw_rows: list[list[Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """
    Parses and validates raw rows from Google Sheets.
    Expected header: SKU | Name | Category | Price | Image URL | Stock | Active
    Returns: (valid_items, error_messages)
    """
    if not raw_rows:
        return [], ["Empty sheet data"]

    headers = [_normalize_header(str(h)) for h in raw_rows[0]]

    # Map column names to indexes
    col_map: dict[str, int] = {}
    for idx, h in enumerate(headers):
        if h == "sku":
            col_map["sku"] = idx
        elif h in {"name", "product", "productname"}:
            col_map["name"] = idx
        elif h == "category":
            col_map["category"] = idx
        elif h in {"price", "unitprice"}:
            col_map["price"] = idx
        elif h in {"imageurl", "image", "img"}:
            col_map["image_url"] = idx
        elif h in {"stock", "quantity", "qty"}:
            col_map["stock"] = idx
        elif h in {"active", "isactive", "status"}:
            col_map["active"] = idx

    required_cols = {"sku", "name", "price", "stock", "active"}
    missing = required_cols - set(col_map.keys())
    if missing:
        msg = f"Sheet is missing required column headers: {sorted(missing)}"
        logger.error(msg)
        return [], [msg]

    valid_items: list[dict[str, Any]] = []
    errors: list[str] = []

    def extract_col(r: list[Any], field_name: str) -> str:
        idx = col_map.get(field_name)
        if idx is not None and idx < len(r):
            return str(r[idx]).strip()
        return ""

    for row_idx, row in enumerate(raw_rows[1:], start=2):
        sku = extract_col(row, "sku")
        if not sku:
            err = f"Row {row_idx}: Skipped due to missing SKU"
            logger.warning(err)
            errors.append(err)
            continue

        name = extract_col(row, "name")
        if not name:
            err = f"Row {row_idx} (SKU {sku}): Skipped due to missing Name"
            logger.warning(err)
            errors.append(err)
            continue

        raw_price = _clean_number_str(extract_col(row, "price"))
        try:
            price = Decimal(raw_price)
            if price < 0:
                raise ValueError("Price cannot be negative")
        except (InvalidOperation, ValueError):
            raw_p = extract_col(row, "price")
            err = f"Row {row_idx} (SKU {sku}): Skipped due to invalid price '{raw_p}'"
            logger.warning(err)
            errors.append(err)
            continue

        raw_stock = _clean_number_str(extract_col(row, "stock"))
        try:
            stock = int(float(raw_stock))
            if stock < 0:
                raise ValueError("Stock cannot be negative")
        except ValueError:
            raw_s = extract_col(row, "stock")
            err = f"Row {row_idx} (SKU {sku}): Skipped due to invalid stock '{raw_s}'"
            logger.warning(err)
            errors.append(err)
            continue

        active_val = _parse_bool(extract_col(row, "active"))
        if active_val is None:
            raw_a = extract_col(row, "active")
            err = f"Row {row_idx} (SKU {sku}): Skipped due to invalid active flag '{raw_a}'"
            logger.warning(err)
            errors.append(err)
            continue

        category = extract_col(row, "category") or None
        image_url = extract_col(row, "image_url") or None

        valid_items.append(
            {
                "sku": sku,
                "name": name,
                "category": category,
                "price": price,
                "image_url": image_url,
                "stock": stock,
                "active": active_val,
            }
        )

    return valid_items, errors


def format_field_for_snapshot(field: str, value: Any) -> str:
    """Canonical string serialization of field value for snapshot comparison."""
    if value is None:
        return ""
    if field == "price":
        return f"{Decimal(str(value)):.2f}"
    if field == "active":
        return "true" if bool(value) else "false"
    if field == "stock":
        return str(int(value))
    return str(value).strip()


class SheetIngestService:
    """
    Ingests inventory catalog from Google Sheets, maintains snapshot per field,
    applies no-clobber rules, and writes to PostgreSQL.
    """

    def __init__(self, sheets_client: SheetsClientProtocol | None = None):
        self.sheets_client = sheets_client or GoogleSheetsClient()

    def ingest_from_values(
        self,
        raw_rows: list[list[Any]],
        db: Session,
        shop_id: str | None = None,
    ) -> IngestSummary:
        """Process raw sheet rows and synchronize with DB."""
        target_shop_id = shop_id or settings.DEFAULT_SHOP_ID
        summary = IngestSummary()
        summary.rows_total = max(0, len(raw_rows) - 1)

        valid_items, errors = parse_sheet_rows(raw_rows)
        summary.rows_valid = len(valid_items)
        summary.rows_skipped = len(errors)
        summary.skipped_reasons = errors

        db_modified = False

        for item in valid_items:
            sku = item["sku"]

            # Current values normalized to string for snapshot comparison
            cur_fields_str: dict[str, str] = {
                field: format_field_for_snapshot(field, item[field]) for field in TRACKED_FIELDS
            }

            # Fetch existing snapshots for this SKU
            snapshots = (
                db.query(InventorySheetSnapshot)
                .filter(
                    InventorySheetSnapshot.sku == sku,
                    InventorySheetSnapshot.shop_id == target_shop_id,
                )
                .all()
            )
            snap_map: dict[str, str] = {str(s.field): (s.last_value or "") for s in snapshots}

            existing_inv = (
                db.query(Inventory)
                .filter(
                    Inventory.sku == sku,
                    Inventory.shop_id == target_shop_id,
                )
                .first()
            )

            # Case A: First run for this SKU (no snapshot exists)
            if not snapshots:
                if not existing_inv:
                    new_inv = Inventory(
                        sku=sku,
                        shop_id=target_shop_id,
                        name=item["name"],
                        category=item["category"],
                        price=item["price"],
                        image_url=item["image_url"],
                        stock=item["stock"],
                        reserved=0,
                        active=item["active"],
                        version=1,
                    )
                    db.add(new_inv)
                else:
                    # Existing DB item without snapshot: bring physical fields in line
                    existing_inv.name = item["name"]
                    existing_inv.category = item["category"]
                    existing_inv.price = item["price"]
                    existing_inv.image_url = item["image_url"]
                    existing_inv.stock = item["stock"]
                    existing_inv.active = item["active"]
                    existing_inv.version = int(existing_inv.version) + 1

                # Create snapshots for all tracked fields
                for field, val_str in cur_fields_str.items():
                    snap = InventorySheetSnapshot(
                        sku=sku,
                        field=field,
                        shop_id=target_shop_id,
                        last_value=val_str,
                    )
                    db.add(snap)

                summary.rows_inserted += 1
                db_modified = True
                continue

            # Case B & C: Snapshot exists -> compare cur with snap per field
            changed_fields: dict[str, str] = {
                field: cur_str
                for field, cur_str in cur_fields_str.items()
                if cur_str != snap_map.get(field, "")
            }

            # Case B: cur == snap -> NO WRITE (no-clobber rule)
            if not changed_fields:
                summary.rows_unchanged += 1
                continue

            # Case C: cur != snap -> seller modified these fields in Google Sheet
            if existing_inv:
                for field in changed_fields:
                    if field == "name":
                        existing_inv.name = item["name"]
                    elif field == "category":
                        existing_inv.category = item["category"]
                    elif field == "price":
                        existing_inv.price = item["price"]
                    elif field == "image_url":
                        existing_inv.image_url = item["image_url"]
                    elif field == "stock":
                        existing_inv.stock = item["stock"]
                    elif field == "active":
                        existing_inv.active = item["active"]

                existing_inv.version = int(existing_inv.version) + 1

            # Update snapshots for changed fields
            now_dt = datetime.now(UTC)
            for s in snapshots:
                field_key = str(s.field)
                if field_key in changed_fields:
                    s.last_value = changed_fields[field_key]
                    s.updated_at = now_dt

            summary.rows_updated += 1
            db_modified = True

        db.commit()

        # Invalidate cache so subsequent reads reflect fresh DB data
        if db_modified:
            inventory_cache.invalidate(target_shop_id)

        return summary

    def ingest_sheet(
        self,
        db: Session,
        spreadsheet_id: str | None = None,
        range_name: str | None = None,
        shop_id: str | None = None,
    ) -> IngestSummary:
        """Fetches from Google Sheets API client and synchronizes with DB."""
        sheet_id = spreadsheet_id or settings.GOOGLE_SHEET_ID
        sheet_range = range_name or settings.GOOGLE_SHEET_INVENTORY_RANGE

        if not sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is not configured.")

        raw_rows = self.sheets_client.get_sheet_values(sheet_id, sheet_range)
        return self.ingest_from_values(raw_rows, db=db, shop_id=shop_id)
