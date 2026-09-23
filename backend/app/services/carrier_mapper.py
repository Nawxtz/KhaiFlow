"""Carrier mapping engine for Phase 12: Carrier CSV export.

Normalizes fulfilled order data into carrier-specific CSV formats according
to pluggable CarrierConfig specifications.
"""

import csv
import io
import re
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class CarrierConfigError(Exception):
    """Raised when carrier configuration is invalid or missing required fields."""

    pass


class CarrierConfigNotFoundError(CarrierConfigError):
    """Raised when requested carrier configuration file cannot be found."""

    pass


class FieldMapping(BaseModel):
    """Maps a single order data attribute to a CSV column header with optional transform."""

    source: str
    header: str
    transform: str = "identity"


class CarrierConfig(BaseModel):
    """Carrier-specific export configuration defining column layout and encoding."""

    carrier_id: str
    carrier_name: str
    fields: list[FieldMapping]
    encoding: str = "utf-8-sig"


class OrderExportRow(BaseModel):
    """Normalized, flat order row assembled from Order, AddressBook, and OrderItem."""

    order_id: str
    receiver_name: str
    phone: str
    full_address: str
    subdistrict: str = ""
    district: str = ""
    province: str = ""
    postcode: str = ""
    total: Decimal | str | float = Decimal("0.00")
    sku: str = ""
    qty: int = 1
    tracking_note: str = ""
    order_date: datetime | date | str | None = None


def transform_identity(val: Any) -> str:
    """Identity transform: converts value to string or empty string if None."""
    if val is None:
        return ""
    if isinstance(val, Decimal):
        return f"{val:.2f}"
    return str(val)


def transform_date_th(val: Any) -> str:
    """Format date/datetime as DD/MM/YYYY."""
    if val is None or val == "":
        return ""
    if isinstance(val, (datetime, date)):
        return val.strftime("%d/%m/%Y")
    if isinstance(val, str):
        # Attempt to parse ISO formats (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS)
        cleaned = val.strip()
        for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d/%m/%Y"):
            try:
                dt = datetime.strptime(cleaned.split(".")[0].replace("Z", ""), fmt)
                return dt.strftime("%d/%m/%Y")
            except ValueError:
                continue
        return cleaned
    return str(val)


def transform_phone_format(val: Any) -> str:
    """Strip non-digits and normalize to standard leading zero (e.g. 0812345678)."""
    if val is None:
        return ""
    raw = str(val).strip()
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return ""

    # Convert international +66 prefix to standard 0
    if digits.startswith("66") and len(digits) >= 11:
        digits = "0" + digits[2:]
    elif not digits.startswith("0"):
        digits = "0" + digits
    return digits


TRANSFORMERS = {
    "identity": transform_identity,
    "date_th": transform_date_th,
    "phone_format": transform_phone_format,
}


def apply_transform(val: Any, transform_name: str) -> str:
    """Apply named transformer or raise CarrierConfigError if unknown."""
    if transform_name not in TRANSFORMERS:
        raise CarrierConfigError(f"Unknown transform '{transform_name}'")
    return TRANSFORMERS[transform_name](val)


def map_orders_to_csv(orders: list[OrderExportRow], config: CarrierConfig) -> str:
    """
    Map a list of OrderExportRow objects into carrier CSV string.

    1. Validates all field.source entries exist on OrderExportRow schema before
       generating any CSV output. Raises CarrierConfigError if any source field is missing.
    2. Writes CSV header row matching config.fields order.
    3. Transforms and writes each order row.
    4. Handles utf-8-sig encoding by prepending BOM (\ufeff).
    """
    valid_fields = set(OrderExportRow.model_fields.keys())

    # Pre-generation validation
    for fm in config.fields:
        if fm.source not in valid_fields:
            raise CarrierConfigError(
                f"Missing required field '{fm.source}' in OrderExportRow schema for carrier '{config.carrier_id}'"
            )
        if fm.transform not in TRANSFORMERS:
            raise CarrierConfigError(
                f"Unknown transform '{fm.transform}' for field '{fm.source}' in carrier '{config.carrier_id}'"
            )

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")

    # Header row
    headers = [fm.header for fm in config.fields]
    writer.writerow(headers)

    # Data rows
    for row in orders:
        row_values = []
        for fm in config.fields:
            raw_val = getattr(row, fm.source, None)
            transformed = apply_transform(raw_val, fm.transform)
            row_values.append(transformed)
        writer.writerow(row_values)

    csv_content = output.getvalue()

    # Prepend BOM for utf-8-sig compatibility if requested
    if config.encoding.lower() in ("utf-8-sig", "utf_8_sig") and not csv_content.startswith("\ufeff"):
        csv_content = "\ufeff" + csv_content

    return csv_content
