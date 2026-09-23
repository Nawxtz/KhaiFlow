from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.order import Order
from app.schemas.verification import (
    ManualActionResponse,
    ManualApprovalRequest,
    ManualRejectRequest,
    SlipVerificationRequest,
    SlipVerificationResponse,
)
from app.services.escalation_service import (
    OrderNotFoundError,
    approve_manual,
    escalate_for_manual_review,
    reject_manual,
)
from app.services.verification_log_service import log_verification
from app.services.verification_service import claim_payment, verify_slip_local

router = APIRouter(prefix="/api/verification", tags=["verification"])


@router.post("/slip", response_model=SlipVerificationResponse, status_code=status.HTTP_200_OK)
def verify_slip_endpoint(
    req: SlipVerificationRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Gate 1 / Filter C verification endpoint per v1_buildable_spec.md §13, §20.
    1. Runs deterministic local checks (TLV, CRC, positive amount, Tag 54 match).
    2. Short-circuit: IF ANY Gate 1 check fails, returns hard reject immediately
       with ZERO DB writes to verification_logs or consumed_payment_claims.
    3. IF Gate 1 passes:
       - Serializes claim via atomic INSERT ... ON CONFLICT DO NOTHING (no SELECT before INSERT).
       - Logs record to verification_logs.
       - Advances order to AWAITING_SELLER_APPROVAL (Option B).
    """
    stmt = select(Order).where(Order.id == req.order_id)
    if req.shop_id:
        stmt = stmt.where(Order.shop_id == req.shop_id)
    order = db.execute(stmt).scalars().first()

    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{req.order_id}' not found.",
        )

    # 1. Gate 1 deterministic local verification
    result = verify_slip_local(
        slip_data=req.slip_data,
        expected_amount=order.total,
        order_id=order.id,
    )

    # 2. Gate 1 short-circuit on failure: ZERO DB WRITES!
    if not result.passed:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "passed": False,
                "reason": result.reason,
                "risk_score": result.risk_score,
                "order_id": order.id,
                "claim_key": None,
                "approval_state": None,
                "amount": str(result.amount) if result.amount is not None else None,
            },
        )

    # 3. Gate 1 passed: Atomic claim serialization via ON CONFLICT (no SELECT before INSERT)
    claim_key = result.claim_key or f"ref:{order.id}"
    claim_id = claim_payment(
        db=db,
        claim_key=claim_key,
        order_id=order.id,
        shop_id=req.shop_id or order.shop_id,
        claim_type="ref",
        state="PENDING",
    )

    if claim_id is None:
        # Duplicate claim detected atomically at database level
        # Record duplicate attempt in verification_logs
        log_verification(
            order_id=order.id,
            slip_hash=req.slip_hash or result.slip_hash,
            risk_score=100,
            result="duplicate",
            db=db,
            shop_id=req.shop_id or order.shop_id,
            decision="REJECTED_DUPLICATE",
            checks_json={"reason": "Duplicate claim_key detected"},
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "passed": False,
                "reason": "Duplicate payment claim: reference already consumed by another order.",
                "risk_score": 100,
                "order_id": order.id,
                "claim_key": claim_key,
                "approval_state": "REJECTED_DUPLICATE",
                "amount": str(result.amount) if result.amount is not None else None,
            },
        )

    # 4. Write audit entry to verification_logs (ONLY AFTER Gate 1 passes)
    log_verification(
        order_id=order.id,
        slip_hash=req.slip_hash or result.slip_hash,
        risk_score=result.risk_score,
        result="passed",
        db=db,
        shop_id=req.shop_id or order.shop_id,
        decision="AWAITING_SELLER_APPROVAL",
        checks_json=result.details,
    )

    # 5. Escalate for Option B manual approval
    order.payment_ref = claim_key
    order.risk_score = result.risk_score
    escalate_for_manual_review(order_id=order.id, db=db, shop_id=req.shop_id or order.shop_id)

    return SlipVerificationResponse(
        passed=True,
        reason=result.reason,
        risk_score=result.risk_score,
        order_id=order.id,
        claim_key=claim_key,
        approval_state=order.approval_state,
        amount=result.amount,
    )


@router.post(
    "/approve/{order_id}", response_model=ManualActionResponse, status_code=status.HTTP_200_OK
)
def manual_approve_endpoint(
    order_id: str,
    req: ManualApprovalRequest,
    db: Session = Depends(get_db),
) -> ManualActionResponse:
    """Option B seller manual approval endpoint."""
    try:
        order = approve_manual(
            order_id=order_id,
            reviewer_id=req.reviewer_id,
            db=db,
        )
        return ManualActionResponse(
            status="approved",
            order_id=order.id,
            order_status=order.status,
            approval_state=order.approval_state,
            message="Order payment approved manually by seller.",
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.post(
    "/reject/{order_id}", response_model=ManualActionResponse, status_code=status.HTTP_200_OK
)
def manual_reject_endpoint(
    order_id: str,
    req: ManualRejectRequest,
    db: Session = Depends(get_db),
) -> ManualActionResponse:
    """Option B seller manual rejection endpoint."""
    try:
        order = reject_manual(
            order_id=order_id,
            reviewer_id=req.reviewer_id,
            reason=req.reason,
            db=db,
        )
        return ManualActionResponse(
            status="rejected",
            order_id=order.id,
            order_status=order.status,
            approval_state=order.approval_state,
            message=f"Order payment rejected: {req.reason}",
        )
    except OrderNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
