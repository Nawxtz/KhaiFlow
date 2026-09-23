"""Export service for Phase 12: Carrier CSV export.

Handles loading carrier configurations, assembling OrderExportRow models from
Order, AddressBook, and OrderItem data, verifying order fulfillment status,
and producing downloadable carrier CSV exports.
"""

import logging
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.address_book import AddressBook
from app.models.order import Order, OrderStatus
from app.services.carrier_mapper import (
    CarrierConfig,
    CarrierConfigError,
    CarrierConfigNotFoundError,
    OrderExportRow,
    map_orders_to_csv,
)

logger = logging.getLogger(__name__)
logger.disabled = False
logger.propagate = True

CARRIER_CONFIGS_DIR = Path(__file__).resolve().parent / "carrier_configs"


class InvalidOrderStateForExportError(Exception):
    """Raised when an unfulfilled order is attempted to be exported."""

    pass


def load_carrier_config(
    carrier_id: str,
    configs_dir: Path | None = None,
) -> CarrierConfig:
    """Load CarrierConfig from JSON file."""
    base_dir = configs_dir or CARRIER_CONFIGS_DIR
    target_path = base_dir / f"{carrier_id}.json"

    if not target_path.exists():
        raise CarrierConfigNotFoundError(
            f"Carrier configuration '{carrier_id}' not found at {target_path}"
        )

    try:
        with open(target_path, encoding="utf-8") as f:
            content = f.read()
        return CarrierConfig.model_validate_json(content)
    except Exception as exc:
        raise CarrierConfigError(
            f"Failed to parse carrier config for '{carrier_id}': {exc}"
        ) from exc


def build_export_rows_from_order(
    order: Order,
    db: Session,
) -> list[OrderExportRow]:
    """
    Assemble OrderExportRow instances from Order + AddressBook + OrderItem.
    """
    addr_stmt = (
        select(AddressBook)
        .where(AddressBook.line_user_id == order.line_user_id)
        .order_by(AddressBook.is_default.desc(), AddressBook.created_at.desc())
    )
    address = db.execute(addr_stmt).scalars().first()

    receiver_name = address.receiver_name if address else ""
    phone = address.phone if address else ""
    full_address = ""
    subdistrict = ""
    district = ""
    province = ""
    postcode = ""

    if address and isinstance(address.address_json, dict):
        aj = address.address_json
        receiver_name = receiver_name or aj.get("receiver_name", "")
        phone = phone or aj.get("phone", "")
        full_address = aj.get("full_address", "")
        subdistrict = aj.get("subdistrict", "")
        district = aj.get("district", "")
        province = aj.get("province", "")
        postcode = aj.get("postcode", "")

    rows: list[OrderExportRow] = []
    if order.items:
        for item in order.items:
            rows.append(
                OrderExportRow(
                    order_id=order.id,
                    receiver_name=receiver_name,
                    phone=phone,
                    full_address=full_address,
                    subdistrict=subdistrict,
                    district=district,
                    province=province,
                    postcode=postcode,
                    total=item.line_total,
                    sku=item.sku,
                    qty=item.qty,
                    tracking_note="",
                    order_date=order.created_at,
                )
            )
    else:
        rows.append(
            OrderExportRow(
                order_id=order.id,
                receiver_name=receiver_name,
                phone=phone,
                full_address=full_address,
                subdistrict=subdistrict,
                district=district,
                province=province,
                postcode=postcode,
                total=order.total,
                sku="",
                qty=1,
                tracking_note="",
                order_date=order.created_at,
            )
        )
    return rows


def export_fulfilled_orders(
    shop_id: str,
    carrier_id: str,
    db: Session,
    order_ids: list[str] | None = None,
    orders: list[Order] | None = None,
    configs_dir: Path | None = None,
) -> tuple[str, str]:
    """
    Export fulfilled orders for a shop to carrier CSV.

    - Rejects any order that is not in FULFILLED status.
    - Loads carrier config.
    - Produces (csv_string, filename) with filename = {carrier_id}_{YYYY-MM-DD}.csv.
    """
    config = load_carrier_config(carrier_id=carrier_id, configs_dir=configs_dir)

    target_orders: list[Order] = []

    if orders is not None:
        for o in orders:
            if o.status != OrderStatus.FULFILLED.value:
                raise InvalidOrderStateForExportError(
                    f"Order '{o.id}' is in status '{o.status}'. "
                    f"Only {OrderStatus.FULFILLED.value} orders can be exported."
                )
        target_orders = orders
    elif order_ids is not None:
        for oid in order_ids:
            order = db.query(Order).filter(Order.id == oid).first()
            if not order:
                raise InvalidOrderStateForExportError(f"Order '{oid}' not found.")
            if order.status != OrderStatus.FULFILLED.value:
                raise InvalidOrderStateForExportError(
                    f"Order '{order.id}' is in status '{order.status}'. "
                    f"Only {OrderStatus.FULFILLED.value} orders can be exported."
                )
            target_orders.append(order)
    else:
        stmt = (
            select(Order)
            .where(
                Order.shop_id == shop_id,
                Order.status == OrderStatus.FULFILLED.value,
            )
            .order_by(Order.created_at.asc())
        )
        target_orders = list(db.execute(stmt).scalars().all())

    # Build flat OrderExportRow items
    export_rows: list[OrderExportRow] = []
    for o in target_orders:
        export_rows.extend(build_export_rows_from_order(order=o, db=db))

    csv_string = map_orders_to_csv(export_rows, config)
    date_str = datetime.now(UTC).strftime("%Y-%m-%d")
    filename = f"{carrier_id}_{date_str}.csv"

    logger.info(
        "AUDIT_EXPORT_CSV: shop_id=%s carrier_id=%s orders_count=%d rows_count=%d filename=%s",
        shop_id,
        carrier_id,
        len(target_orders),
        len(export_rows),
        filename,
        extra={
            "event": "AUDIT_EXPORT_CSV",
            "shop_id": shop_id,
            "carrier_id": carrier_id,
            "orders_count": len(target_orders),
            "rows_count": len(export_rows),
            "export_filename": filename,
        },
    )

    return csv_string, filename
