from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.schemas.payment import (
    GenerateQRRequest,
    VerifyQRRequest,
)
from app.services.qr_service import (
    MissingQRSecretError,
    generate_signed_payment_qr,
    verify_payment_qr,
)

router = APIRouter(prefix="/api/payment", tags=["payment"])


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
