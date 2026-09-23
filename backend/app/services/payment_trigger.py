from dataclasses import dataclass
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models.order import Order, OrderStatus


@dataclass
class TriggerProcessingResult:
    """Result of processing an incoming payment trigger."""

    status: str  # "processed" or "duplicate" or "order_not_found"
    is_duplicate: bool
    order_id: str | None
    claim_key: str
    message: str


def process_payment_trigger(
    db: Session,
    claim_key: str,
    order_id: str | None = None,
    shop_id: str | None = None,
    channel: str = "webhook",
    payload_json: dict[str, Any] | None = None,
) -> TriggerProcessingResult:
    """
    Process incoming payment trigger idempotently per v1_buildable_spec.md §13,
    reference_schema.md, and CONCURRENCY.md.

    1. Atomic insert-conflict on consumed_payment_claims (claim_key UNIQUE):
       INSERT INTO consumed_payment_claims (...) ON CONFLICT (claim_key) DO NOTHING RETURNING id;
       If no row returned, this claim was already consumed -> duplicate trigger.
    2. Any trigger received stops the TTL by transitioning order status:
       AWAITING_PAYMENT -> PAYMENT_RECEIVED, and clearing order.ttl_expires_at.
    3. Guarantees exactly-once processing with no double stock-decrement or state corruption.
    """
    if not claim_key or not claim_key.strip():
        raise ValueError("claim_key cannot be empty.")

    clean_claim_key = claim_key.strip()

    # 1. Atomic claim deduplication per CONCURRENCY.md and reference_schema.md
    insert_claim_stmt = text(
        """
        INSERT INTO consumed_payment_claims (
            shop_id, claim_key, claim_type, order_id, state, consumed_at
        ) VALUES (
            :shop_id, :claim_key, :claim_type, :order_id, :state, NOW()
        )
        ON CONFLICT (claim_key) DO NOTHING
        RETURNING id;
        """
    )
    result = db.execute(
        insert_claim_stmt,
        {
            "shop_id": shop_id,
            "claim_key": clean_claim_key,
            "claim_type": "ref",
            "order_id": order_id,
            "state": "CONFIRMED",
        },
    )
    inserted_row = result.first()

    if inserted_row is None:
        # Atomic conflict: claim_key already exists in consumed_payment_claims -> duplicate trigger
        db.commit()
        return TriggerProcessingResult(
            status="duplicate",
            is_duplicate=True,
            order_id=order_id,
            claim_key=clean_claim_key,
            message="Duplicate payment trigger received; ignored idempotently without reprocessing.",
        )

    # 2. Record payment event for auditability and retry idempotency
    event_key = f"evt_{clean_claim_key}"
    insert_event_stmt = text(
        """
        INSERT INTO payment_events (
            shop_id, order_id, event_key, event_type, channel, payload_json, received_at, created_at
        ) VALUES (
            :shop_id, :order_id, :event_key, :event_type, :channel, :payload_json, NOW(), NOW()
        )
        ON CONFLICT (event_key) DO NOTHING;
        """
    )
    import json

    db.execute(
        insert_event_stmt,
        {
            "shop_id": shop_id,
            "order_id": order_id,
            "event_key": event_key,
            "event_type": "PAYMENT_TRIGGER",
            "channel": channel,
            "payload_json": json.dumps(payload_json) if payload_json else None,
        },
    )

    # 3. Stop TTL on the order if in AWAITING_PAYMENT state
    if order_id:
        stmt = select(Order).where(Order.id == order_id)
        if shop_id:
            stmt = stmt.where(Order.shop_id == shop_id)
        order = db.execute(stmt).scalars().first()

        if order and order.status == OrderStatus.AWAITING_PAYMENT.value:
            # Advance state machine: AWAITING_PAYMENT -> PAYMENT_RECEIVED (stops TTL)
            order.status = OrderStatus.PAYMENT_RECEIVED.value
            order.ttl_expires_at = None

    db.commit()

    return TriggerProcessingResult(
        status="processed",
        is_duplicate=False,
        order_id=order_id,
        claim_key=clean_claim_key,
        message="Payment trigger processed successfully; TTL stopped.",
    )
