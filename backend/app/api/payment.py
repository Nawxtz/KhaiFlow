from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.payment import (
    GenerateQRRequest,
    PaymentTriggerRequest,
    PaymentTriggerResponse,
    VerifyQRRequest,
)
from app.services.payment_trigger import process_payment_trigger
from app.services.qr_service import (
    MissingQRSecretError,
    generate_signed_payment_qr,
    verify_payment_qr,
)

router = APIRouter(prefix="/api/payment", tags=["payment"])


@router.post("/trigger", response_model=PaymentTriggerResponse, status_code=status.HTTP_200_OK)
def handle_payment_trigger_endpoint(
    req: PaymentTriggerRequest,
    db: Session = Depends(get_db),
) -> PaymentTriggerResponse:
    """
    Webhook trigger receiver for payment notifications.
    Guarantees exactly-once processing using atomic deduplication on consumed_payment_claims.
    Duplicate triggers return 200 with is_duplicate=True without double-processing.
    """
    result = process_payment_trigger(
        db=db,
        claim_key=req.claim_key,
        order_id=req.order_id,
        shop_id=req.shop_id,
        channel=req.channel,
        payload_json=req.payload,
    )
    return PaymentTriggerResponse(
        status=result.status,
        is_duplicate=result.is_duplicate,
        order_id=result.order_id,
        claim_key=result.claim_key,
        message=result.message,
    )


@router.post("/generate-qr", status_code=status.HTTP_200_OK)
def generate_qr_endpoint(req: GenerateQRRequest) -> dict[str, Any]:
    """Generate per-order HMAC-SHA256 signed payment QR payload."""
    try:
        return generate_signed_payment_qr(
            order_id=req.order_id,
            total=req.total,
            currency=req.currency,
            shop_account=req.shop_account,
        )
    except MissingQRSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post("/verify-qr", status_code=status.HTTP_200_OK)
def verify_qr_endpoint(req: VerifyQRRequest) -> dict[str, bool]:
    """Verify HMAC-SHA256 signature for a payment QR payload."""
    try:
        is_valid = verify_payment_qr(
            order_id=req.order_id,
            total=req.total,
            currency=req.currency,
            shop_account=req.shop_account,
            signature=req.signature,
        )
        return {"valid": is_valid}
    except MissingQRSecretError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
