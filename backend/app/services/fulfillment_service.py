"""Fulfillment service for Phase 9: Fulfillment Sheet write + buyer notify."""

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.line_client import LineClient, line_client
from app.models.address_book import AddressBook
from app.models.order import Order, OrderStatus
from app.schemas.order import FulfillmentResult
from app.services.i18n import get_text, resolve_user_language
from app.services.sheet_ingest import GoogleSheetsClient, SheetsAPIError, SheetsClientProtocol

logger = logging.getLogger(__name__)

DEFAULT_FULFILLMENT_RANGE = "Fulfillment!A1:K"


class FulfillmentError(Exception):
    """Base exception for fulfillment operations."""

    pass


class OrderNotFoundError(FulfillmentError):
    """Raised when the specified order cannot be found in the database."""

    pass


class InvalidOrderStateForFulfillmentError(FulfillmentError):
    """Raised when an order is not in PAYMENT_RECEIVED status for fulfillment."""

    pass


def _notify_buyer_fulfilled(
    db: Session,
    order: Order,
    line_client_instance: LineClient | None = None,
) -> bool:
    """
    Send order_fulfilled push notification to buyer via LINE.
    Fires strictly after successful sheet write and DB commit.
    Catches and logs any push failure so it does not crash the fulfillment job.
    """
    if not order.line_user_id:
        logger.warning("Order %s has no line_user_id; skipping buyer notification", order.id)
        return False

    client = line_client_instance or line_client
    try:
        lang = resolve_user_language(db, order.line_user_id)
    except Exception:
        lang = getattr(settings, "UI_DEFAULT_BUYER_LANGUAGE", "th")

    msg_text = get_text("order_fulfilled", lang=lang, order_id=order.id)
    try:
        client.push_message(
            to=order.line_user_id,
            messages=[{"type": "text", "text": msg_text}],
        )
        logger.info(
            "Sent fulfillment notification to user %s for order %s",
            order.line_user_id,
            order.id,
        )
        return True
    except Exception as exc:
        logger.error(
            "Failed to send LINE fulfillment notification for order %s: %s",
            order.id,
            exc,
        )
        return False


def fulfill_order(
    order_id: str,
    db: Session,
    sheets_client: SheetsClientProtocol | None = None,
    line_client_instance: LineClient | None = None,
    range_name: str | None = None,
) -> FulfillmentResult:
    """
    Fulfill a single order:
    1. Guard: if order status is already FULFILLED -> return early without writing.
    2. Guard: if order status is not PAYMENT_RECEIVED -> raise InvalidOrderStateForFulfillmentError.
    3. Write row(s) to Fulfillment Sheet matching reference_schema.md:
       Order ID | Date | Receiver | Phone | Full Address | SKU | Product | Qty | Note | Paid | Tracking No.
    4. On SheetsAPIError -> raise so the caller can retry. Order remains in PAYMENT_RECEIVED.
    5. On success -> transition order to FULFILLED in an atomic DB commit.
    6. Send buyer notification strictly after successful sheet write commit.
    """
    order = db.query(Order).filter(Order.id == order_id).first()
    if not order:
        raise OrderNotFoundError(f"Order '{order_id}' not found.")

    # Guard 1: Idempotency marker check
    if order.status == OrderStatus.FULFILLED.value:
        logger.info(
            "Order %s is already in FULFILLED status; skipping sheet write and notification.",
            order_id,
        )
        return FulfillmentResult(
            success=True,
            order_id=order.id,
            status=OrderStatus.FULFILLED.value,
            rows_written=0,
            already_fulfilled=True,
            message="Order is already fulfilled.",
        )

    # Guard 2: Order must be in PAYMENT_RECEIVED state
    if order.status != OrderStatus.PAYMENT_RECEIVED.value:
        raise InvalidOrderStateForFulfillmentError(
            f"Cannot fulfill order '{order_id}' in status '{order.status}'. "
            f"Order must be in '{OrderStatus.PAYMENT_RECEIVED.value}'."
        )

    # Resolve delivery address from AddressBook
    addr_stmt = (
        select(AddressBook)
        .where(AddressBook.line_user_id == order.line_user_id)
        .order_by(AddressBook.is_default.desc(), AddressBook.created_at.desc())
    )
    address = db.execute(addr_stmt).scalars().first()
    receiver = address.receiver_name if address else ""
    phone = address.phone if address else ""
    full_address = ""
    if address and isinstance(address.address_json, dict):
        full_address = address.address_json.get("full_address", "")

    date_str = (
        order.created_at.strftime("%Y-%m-%d %H:%M:%S")
        if order.created_at
        else datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
    )

    # Build rows per reference_schema.md
    # Order ID | Date | Receiver | Phone | Full Address | SKU | Product | Qty | Note | Paid | Tracking No.
    rows: list[list[Any]] = []
    if order.items:
        for item in order.items:
            rows.append(
                [
                    order.id,
                    date_str,
                    receiver,
                    phone,
                    full_address,
                    item.sku,
                    item.name,
                    item.qty,
                    "",  # Note
                    str(item.line_total),  # Paid
                    "",  # Tracking No.
                ]
            )
    else:
        rows.append(
            [
                order.id,
                date_str,
                receiver,
                phone,
                full_address,
                "",  # SKU
                "",  # Product
                1,  # Qty
                "",  # Note
                str(order.total),  # Paid
                "",  # Tracking No.
            ]
        )

    active_sheets_client = sheets_client or GoogleSheetsClient()
    spreadsheet_id = settings.GOOGLE_SHEET_ID or "default_sheet_id"
    target_range = range_name or DEFAULT_FULFILLMENT_RANGE

    # Execute sheet write — on SheetsAPIError, this raises and leaves order in PAYMENT_RECEIVED
    for r in rows:
        if hasattr(active_sheets_client, "append_sheet_row"):
            active_sheets_client.append_sheet_row(spreadsheet_id, target_range, r)
        elif hasattr(active_sheets_client, "append_row"):
            active_sheets_client.append_row(spreadsheet_id, target_range, r)
        elif hasattr(active_sheets_client, "append_sheet_rows"):
            active_sheets_client.append_sheet_rows(spreadsheet_id, target_range, [r])
        else:
            raise SheetsAPIError("Sheets client does not support row appending.")

    # Atomic DB state transition: PAYMENT_RECEIVED -> FULFILLED
    now_dt = datetime.now(UTC)
    order.status = OrderStatus.FULFILLED.value
    order.updated_at = now_dt
    db.commit()
    db.refresh(order)

    logger.info(
        "Order %s successfully fulfilled and transitioned to FULFILLED. %d row(s) written.",
        order.id,
        len(rows),
    )

    # Buyer notification fires strictly after successful commit
    _notify_buyer_fulfilled(db, order, line_client_instance)

    return FulfillmentResult(
        success=True,
        order_id=order.id,
        status=OrderStatus.FULFILLED.value,
        rows_written=len(rows),
        already_fulfilled=False,
        message=f"Order '{order.id}' fulfilled successfully with {len(rows)} row(s) written.",
    )


def fulfill_order_with_retry(
    order_id: str,
    db: Session,
    sheets_client: SheetsClientProtocol | None = None,
    line_client_instance: LineClient | None = None,
    max_attempts: int = 3,
    range_name: str | None = None,
) -> FulfillmentResult:
    """
    Retry wrapper around fulfill_order:
    - Retries up to max_attempts on SheetsAPIError.
    - Each retry calls fulfill_order again — the FULFILLED guard prevents double-write.
    - After exhausting retries: logs structured error; leaves order in PAYMENT_RECEIVED; does NOT crash.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fulfill_order(
                order_id=order_id,
                db=db,
                sheets_client=sheets_client,
                line_client_instance=line_client_instance,
                range_name=range_name,
            )
        except SheetsAPIError as exc:
            last_error = exc
            logger.warning(
                "Fulfillment sheet write attempt %d/%d failed for order %s: %s",
                attempt,
                max_attempts,
                order_id,
                exc,
                extra={
                    "order_id": order_id,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "error": str(exc),
                },
            )
            if attempt == max_attempts:
                break
        except (OrderNotFoundError, InvalidOrderStateForFulfillmentError):
            # Business errors are non-retryable
            raise

    logger.error(
        "Exhausted all %d fulfillment attempts for order %s. Order remains in %s.",
        max_attempts,
        order_id,
        OrderStatus.PAYMENT_RECEIVED.value,
        extra={
            "order_id": order_id,
            "attempts": max_attempts,
            "error": str(last_error),
            "event": "FULFILLMENT_EXHAUSTED",
        },
    )
    return FulfillmentResult(
        success=False,
        order_id=order_id,
        status=OrderStatus.PAYMENT_RECEIVED.value,
        rows_written=0,
        already_fulfilled=False,
        message=f"Fulfillment failed after {max_attempts} attempts: {last_error}",
    )
