import base64
import hashlib
import hmac
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast

from pydantic import ValidationError
from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.line_client import LineClient, line_client
from app.models.order import Order, OrderStatus
from app.models.payment import ConsumedPaymentClaim, Reservation
from app.schemas.gateway_webhook import GatewayWebhookPayload, WebhookResult
from app.services.i18n import get_text, resolve_user_language

logger = logging.getLogger(__name__)


class GatewayWebhookError(Exception):
    """Base exception for gateway webhook processing errors."""

    pass


class InvalidSignatureError(GatewayWebhookError, ValueError):
    """Raised when webhook signature verification fails."""

    pass


class MalformedPayloadError(GatewayWebhookError, ValueError):
    """Raised when webhook payload JSON is invalid or fails schema validation."""

    pass


def get_current_time(now_fn: Callable[[], datetime] | None = None) -> datetime:
    """Return current UTC timestamp using injected now_fn or default system time."""
    if now_fn is not None:
        return now_fn()
    return datetime.now(UTC)


def compute_gateway_signature(raw_body: bytes, secret: str) -> str:
    """
    Compute HMAC-SHA256 signature (hex) for raw request body bytes.
    Used for signature verification and test payload signing.
    """
    return hmac.new(
        secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()


def verify_gateway_signature(
    raw_body: bytes,
    signature: str | None,
    secret: str | None = None,
) -> bool:
    """
    Validate gateway HMAC-SHA256 signature against raw body bytes using constant-time comparison.
    Supports standard hex digest, 'sha256=' prefix, and base64 encoded digest.
    Secret is loaded from settings.GATEWAY_WEBHOOK_SECRET (never hardcoded).
    """
    if not signature:
        return False

    active_secret = secret if secret is not None else settings.GATEWAY_WEBHOOK_SECRET
    if not active_secret:
        logger.error("GATEWAY_WEBHOOK_SECRET is not configured; rejecting webhook.")
        return False

    sig_clean = signature.strip()

    # Handle standard 'sha256=' prefix
    if sig_clean.lower().startswith("sha256="):
        sig_clean = sig_clean[7:].strip()

    expected_hex = compute_gateway_signature(raw_body, active_secret)

    # 1. Compare hex digest (constant time)
    if hmac.compare_digest(expected_hex.lower(), sig_clean.lower()):
        return True

    # 2. Compare base64 digest (constant time)
    expected_b64 = base64.b64encode(
        hmac.new(active_secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
    ).decode("utf-8")
    if hmac.compare_digest(expected_b64, sig_clean):
        return True

    return False


def _notify_buyer(
    db: Session,
    order: Order,
    message_key: str,
    line_client_instance: LineClient | None = None,
) -> None:
    """Send transactional notification to buyer in preferred language via LINE."""
    if not order.line_user_id:
        return

    client = line_client_instance or line_client
    try:
        lang = resolve_user_language(db, order.line_user_id)
    except Exception:
        lang = getattr(settings, "UI_DEFAULT_BUYER_LANGUAGE", "th")
    msg_text = get_text(message_key, lang=lang, order_id=order.id)
    try:
        client.send_message(to=order.line_user_id, text=msg_text)
    except Exception as exc:
        logger.error("Failed to notify buyer via LINE for order %s: %s", order.id, exc)


def process_gateway_webhook(
    raw_body: bytes,
    signature: str | None,
    db: Session,
    secret: str | None = None,
    line_client_instance: LineClient | None = None,
    raise_on_error: bool = False,
    now_fn: Callable[[], datetime] | None = None,
) -> WebhookResult:
    """
    Process incoming payment gateway / bank webhook (Option A confirmation)
    per v1_buildable_spec.md §13, §20, PAYMENT_RULES.md, and SECURITY.md.

    Strict Order of Operations:
    1. Validate gateway signature BEFORE any DB query or payload parse.
       If invalid -> return INVALID_SIGNATURE / HTTP 400 immediately.
    2. Parse JSON payload into GatewayWebhookPayload schema.
    3. Idempotency check via atomic INSERT INTO payment_events ON CONFLICT DO NOTHING.
       If duplicate -> return DUPLICATE immediately without reprocessing.
    4. Confirm-time atomic inventory stock decrement.
    5. Check rowcount:
       - rowcount == 1: transition order to PAYMENT_RECEIVED.
       - rowcount == 0: stock was lost -> transition order to PAYMENT_RECONCILE.
    6. Reply to buyer via LINE in preferred language.
    """
    # -------------------------------------------------------------------------
    # Step 1: Verify signature BEFORE any DB query or payload parse
    # -------------------------------------------------------------------------
    if not verify_gateway_signature(raw_body=raw_body, signature=signature, secret=secret):
        logger.warning("Gateway webhook signature verification failed.")
        if raise_on_error:
            raise InvalidSignatureError("Invalid or missing gateway webhook signature.")
        return WebhookResult(
            status="INVALID_SIGNATURE",
            success=False,
            is_duplicate=False,
            order_id=None,
            event_key=None,
            message="Invalid or missing gateway webhook signature.",
        )

    # -------------------------------------------------------------------------
    # Step 2: Parse JSON payload into GatewayWebhookPayload
    # -------------------------------------------------------------------------
    try:
        raw_text = raw_body.decode("utf-8")
        payload_dict = json.loads(raw_text)
    except Exception as exc:
        logger.warning("Failed to decode webhook JSON body: %s", exc)
        if raise_on_error:
            raise MalformedPayloadError(f"Malformed webhook JSON body: {exc}") from exc
        return WebhookResult(
            status="MALFORMED_PAYLOAD",
            success=False,
            is_duplicate=False,
            order_id=None,
            event_key=None,
            message=f"Malformed webhook JSON body: {exc}",
        )

    try:
        payload = GatewayWebhookPayload.model_validate(payload_dict)
    except ValidationError as exc:
        logger.warning("Gateway webhook payload validation failed: %s", exc)
        if raise_on_error:
            raise MalformedPayloadError(f"Payload schema validation error: {exc}") from exc
        return WebhookResult(
            status="MALFORMED_PAYLOAD",
            success=False,
            is_duplicate=False,
            order_id=None,
            event_key=None,
            message=f"Payload schema validation error: {exc}",
        )

    event_key = payload.event_key
    assert event_key is not None, "event_key must be resolved by GatewayWebhookPayload"

    # -------------------------------------------------------------------------
    # Step 3: Idempotency check via payment_events (event_key UNIQUE)
    # Zero SELECT before INSERT — atomic ON CONFLICT DO NOTHING RETURNING id
    # -------------------------------------------------------------------------
    payload_hash = hashlib.sha256(raw_body).hexdigest()
    insert_event_stmt = text(
        """
        INSERT INTO payment_events (
            shop_id, order_id, event_key, event_type, channel,
            payload_json, payload_hash, decision, received_at, created_at
        ) VALUES (
            :shop_id, :order_id, :event_key, :event_type, :channel,
            :payload_json, :payload_hash, :decision, NOW(), NOW()
        )
        ON CONFLICT (event_key) DO NOTHING
        RETURNING id;
        """
    )
    result = db.execute(
        insert_event_stmt,
        {
            "shop_id": payload.shop_id,
            "order_id": payload.order_id,
            "event_key": event_key,
            "event_type": "GATEWAY_WEBHOOK",
            "channel": payload.channel or "gateway",
            "payload_json": json.dumps(payload_dict),
            "payload_hash": payload_hash,
            "decision": "PENDING",
        },
    )
    inserted_event = result.first()

    if inserted_event is None:
        # Atomic duplicate: event_key already exists in payment_events.
        # Zero SELECT before INSERT; return HTTP 200 immediately without reprocessing.
        db.commit()
        logger.info(
            "Duplicate gateway webhook event '%s' ignored idempotently without reprocessing.",
            event_key,
        )
        return WebhookResult(
            status="DUPLICATE",
            success=True,
            is_duplicate=True,
            order_id=payload.order_id,
            event_key=event_key,
            message="Duplicate webhook event ignored idempotently.",
        )

    # -------------------------------------------------------------------------
    # Step 4: Order lookup
    # -------------------------------------------------------------------------
    stmt = select(Order).where(Order.id == payload.order_id)
    if payload.shop_id:
        stmt = stmt.where(Order.shop_id == payload.shop_id)
    order = db.execute(stmt).scalars().first()

    if not order:
        logger.warning("Gateway webhook received for non-existent order_id=%s", payload.order_id)
        db.execute(
            text("UPDATE payment_events SET decision = :decision WHERE event_key = :event_key"),
            {"decision": "ORDER_NOT_FOUND", "event_key": event_key},
        )
        db.commit()
        return WebhookResult(
            status="ORDER_NOT_FOUND",
            success=False,
            is_duplicate=False,
            order_id=payload.order_id,
            event_key=event_key,
            message=f"Order '{payload.order_id}' not found.",
        )

    now_dt = get_current_time(now_fn)

    # Determine line items to decrement
    items_to_decrement: list[tuple[str, int]] = []
    if order.items:
        items_to_decrement = [(item.sku, item.qty) for item in order.items]
    else:
        # Fallback to active reservations if items relationship is unpopulated
        res_stmt = select(Reservation).where(
            Reservation.order_id == order.id,
            Reservation.state == "RESERVED",
        )
        reservations = list(db.execute(res_stmt).scalars().all())
        items_to_decrement = [(r.sku, r.qty) for r in reservations]

    # -------------------------------------------------------------------------
    # Step 5: Confirm-time atomic inventory stock decrement
    # CRITICAL: If result.rowcount == 0 -> route to PAYMENT_RECONCILE
    # -------------------------------------------------------------------------
    savepoint = db.begin_nested()
    decrement_failed = False
    failed_sku: str | None = None
    failed_qty: int = 0

    for sku, qty in items_to_decrement:
        if order.shop_id is not None:
            update_stmt = text(
                """
                UPDATE inventory
                SET stock = stock - :qty, reserved = reserved - :qty, version = version + 1
                WHERE sku = :sku
                  AND shop_id = :shop_id
                  AND reserved >= :qty
                  AND stock >= :qty
                """
            )
            params: dict[str, Any] = {"sku": sku, "qty": qty, "shop_id": order.shop_id}
        else:
            update_stmt = text(
                """
                UPDATE inventory
                SET stock = stock - :qty, reserved = reserved - :qty, version = version + 1
                WHERE sku = :sku
                  AND reserved >= :qty
                  AND stock >= :qty
                """
            )
            params = {"sku": sku, "qty": qty}

        result = cast(CursorResult[Any], db.execute(update_stmt, params))

        # Explicit rowcount check required by v1_buildable_spec.md §12, §20
        if result.rowcount == 0:
            decrement_failed = True
            failed_sku = sku
            failed_qty = qty
            break

    if decrement_failed:
        # Stock was lost (TTL race, manual override, or corruption)
        # Roll back any partial decrements within the savepoint
        savepoint.rollback()

        # Transition order to PAYMENT_RECONCILE.
        # Hold is kept: reservations are NOT released and NOT confirmed.
        # Do NOT raise an exception. Do NOT leave order in AWAITING_PAYMENT. Do NOT ignore.
        order.status = OrderStatus.PAYMENT_RECONCILE.value
        order.ttl_expires_at = None
        order.approval_state = "RECONCILE_REQUIRED"
        if payload.payment_ref or payload.transaction_id:
            order.payment_ref = payload.payment_ref or payload.transaction_id
        order.updated_at = now_dt

        # Record decision in payment_events
        db.execute(
            text("UPDATE payment_events SET decision = :decision WHERE event_key = :event_key"),
            {"decision": "PAYMENT_RECONCILE", "event_key": event_key},
        )
        db.commit()

        # Log structured warning with order_id for ops visibility
        logger.warning(
            "Confirm-time stock decrement failed (rowcount=0) for order_id=%s, sku=%s, qty=%d. "
            "Order transitioned to PAYMENT_RECONCILE.",
            order.id,
            failed_sku,
            failed_qty,
            extra={
                "order_id": order.id,
                "sku": failed_sku,
                "qty": failed_qty,
                "status": OrderStatus.PAYMENT_RECONCILE.value,
                "event": "CONFIRM_DECREMENT_FAILED",
            },
        )

        # Notify buyer via LINE
        _notify_buyer(db, order, "payment_reconcile_alert", line_client_instance)

        return WebhookResult(
            status=OrderStatus.PAYMENT_RECONCILE.value,
            success=False,
            is_duplicate=False,
            order_id=order.id,
            event_key=event_key,
            order_status=OrderStatus.PAYMENT_RECONCILE.value,
            message=(
                f"Confirm-time stock decrement failed (rowcount=0) for SKU '{failed_sku}'. "
                f"Order routed to PAYMENT_RECONCILE."
            ),
        )

    # -------------------------------------------------------------------------
    # Decrement succeeded (rowcount == 1 for all items)
    # -------------------------------------------------------------------------
    savepoint.commit()

    # Flip active reservations to CONFIRMED
    res_stmt = select(Reservation).where(
        Reservation.order_id == order.id,
        Reservation.state == "RESERVED",
    )
    for res in db.execute(res_stmt).scalars().all():
        res.state = "CONFIRMED"

    # Flip any PENDING consumed_payment_claims to CONFIRMED
    claims_stmt = select(ConsumedPaymentClaim).where(
        ConsumedPaymentClaim.order_id == order.id,
        ConsumedPaymentClaim.state == "PENDING",
    )
    for claim in db.execute(claims_stmt).scalars().all():
        claim.state = "CONFIRMED"

    # Advance state machine: AWAITING_PAYMENT -> PAYMENT_RECEIVED
    order.status = OrderStatus.PAYMENT_RECEIVED.value
    order.ttl_expires_at = None
    order.approval_state = "AUTO_CONFIRMED"
    if payload.payment_ref or payload.transaction_id:
        order.payment_ref = payload.payment_ref or payload.transaction_id
    order.updated_at = now_dt

    # Update payment_events decision
    db.execute(
        text("UPDATE payment_events SET decision = :decision WHERE event_key = :event_key"),
        {"decision": "CONFIRMED", "event_key": event_key},
    )
    db.commit()

    logger.info(
        "Payment confirmed via gateway webhook for order_id=%s, event_key=%s. Order status: %s",
        order.id,
        event_key,
        OrderStatus.PAYMENT_RECEIVED.value,
    )

    # -------------------------------------------------------------------------
    # Step 6: Reply to buyer via LINE
    # -------------------------------------------------------------------------
    _notify_buyer(db, order, "payment_confirmed", line_client_instance)

    return WebhookResult(
        status=OrderStatus.PAYMENT_RECEIVED.value,
        success=True,
        is_duplicate=False,
        order_id=order.id,
        event_key=event_key,
        order_status=OrderStatus.PAYMENT_RECEIVED.value,
        message="Payment confirmed and stock decremented successfully.",
    )
