import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.gateway_webhook import GatewayWebhookResponse
from app.services.gateway_webhook_service import (
    InvalidSignatureError,
    MalformedPayloadError,
    process_gateway_webhook,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["gateway_webhook"])


@router.post(
    "/api/gateway/webhook",
    response_model=GatewayWebhookResponse,
    status_code=status.HTTP_200_OK,
)
@router.post(
    "/api/payment/webhook",
    response_model=GatewayWebhookResponse,
    status_code=status.HTTP_200_OK,
)
async def gateway_webhook_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    x_gateway_signature: str | None = Header(None, alias="X-Gateway-Signature"),
) -> GatewayWebhookResponse:
    """
    Gateway/bank payment webhook endpoint (Option A confirmation).
    Follows strict order of operations per v1_buildable_spec.md §13, §20, and SECURITY.md:
    1. Read raw request bytes BEFORE any JSON parsing.
    2. Validate gateway signature (HMAC-SHA256 against settings.GATEWAY_WEBHOOK_SECRET).
       If signature invalid/missing -> return HTTP 400 immediately.
       Zero DB queries, zero JSON parsing, zero order lookups.
    3. Parse JSON payload into GatewayWebhookPayload.
    4. Idempotency check via atomic INSERT INTO payment_events ON CONFLICT DO NOTHING.
    5. Confirm-time atomic inventory decrement with rowcount check.
    6. Advance state machine to PAYMENT_RECEIVED (success) or PAYMENT_RECONCILE (lost stock).
    """
    if not x_gateway_signature:
        logger.warning("Gateway webhook rejected: missing X-Gateway-Signature header.")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required X-Gateway-Signature header.",
        )

    # 1. Read raw request body bytes before any JSON parsing
    raw_body = await request.body()

    # 2. Process webhook through service with strict signature verification
    try:
        result = process_gateway_webhook(
            raw_body=raw_body,
            signature=x_gateway_signature,
            db=db,
            raise_on_error=True,
        )
    except InvalidSignatureError as exc:
        logger.warning("Gateway webhook rejected due to invalid signature: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except MalformedPayloadError as exc:
        logger.warning("Gateway webhook rejected due to malformed payload: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if result.status == "INVALID_SIGNATURE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )
    if result.status == "MALFORMED_PAYLOAD":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=result.message,
        )

    return GatewayWebhookResponse(
        status=result.status,
        is_duplicate=result.is_duplicate,
        order_id=result.order_id,
        event_key=result.event_key,
        order_status=result.order_status,
        message=result.message,
    )
