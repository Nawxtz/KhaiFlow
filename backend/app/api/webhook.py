import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.line_client import LineClient, line_client
from app.schemas.webhook import LineWebhookEvent, LineWebhookPayload
from app.services.intent_router import dispatch_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/line", tags=["line"])

# In-memory processed webhook event IDs for idempotency
_PROCESSED_EVENT_IDS: set[str] = set()


def clear_processed_events() -> None:
    """Clear processed event IDs (primarily for testing)."""
    _PROCESSED_EVENT_IDS.clear()


def get_line_client() -> LineClient:
    return line_client


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def line_webhook(
    request: Request,
    x_line_signature: str | None = Header(None, alias="X-Line-Signature"),
    db: Session = Depends(get_db),
    client: LineClient = Depends(get_line_client),
) -> dict[str, Any]:
    """
    Handle incoming LINE webhook events.
    1. Validates X-Line-Signature header (400 if invalid).
    2. Enforces event idempotency (skips duplicate webhookEventId).
    3. Safely ignores unsupported event types.
    4. Handles message and postback events with locale-keyed replies.
    """
    body = await request.body()

    # 1. Validate signature
    if not x_line_signature or not client.validate_signature(body, x_line_signature):
        logger.warning("Rejected LINE webhook with invalid signature")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid LINE signature",
        )

    # 2. Parse payload
    try:
        payload_data = json.loads(body.decode("utf-8"))
        payload = LineWebhookPayload(**payload_data)
    except Exception as e:
        logger.error("Failed to parse LINE webhook payload: %s", e)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Malformed webhook payload",
        ) from e

    # 3. Process events
    for event in payload.events:
        await _process_single_event(event, db, client)

    return {"status": "ok"}


async def _process_single_event(
    event: LineWebhookEvent,
    db: Session,
    client: LineClient,
) -> None:
    """Process an individual webhook event."""
    event_id = event.webhook_event_id

    # Idempotency check: ignore duplicate events
    if event_id in _PROCESSED_EVENT_IDS:
        logger.info("Duplicate webhook event ID %s ignored", event_id)
        return
    _PROCESSED_EVENT_IDS.add(event_id)

    # Ignore unsupported event types safely
    if event.type not in ("message", "postback"):
        logger.info("Ignored unsupported event type: %s (event_id=%s)", event.type, event_id)
        return

    # Dispatch to intent router for guided ordering flow

    await dispatch_event(event, db, client)
