import logging
from typing import Any

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.schemas.pdpa import (
    PDPAConsentRequest,
    PDPAConsentResponse,
    PDPADeleteRequest,
    PDPADeleteResponse,
    PDPARetentionJobResponse,
)
from app.services.pdpa_service import (
    execute_pdpa_deletion,
    has_pdpa_consent,
    record_pdpa_consent,
    run_pdpa_retention_job,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/pdpa", tags=["pdpa"])


@router.post("/consent", response_model=PDPAConsentResponse, status_code=status.HTTP_200_OK)
def set_pdpa_consent(
    payload: PDPAConsentRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Record or update buyer PDPA consent.
    """
    pref = record_pdpa_consent(
        db=db,
        line_user_id=payload.line_user_id,
        consent=payload.consent,
        shop_id=payload.shop_id,
    )
    return PDPAConsentResponse(
        line_user_id=pref.user_id,
        consent=pref.pdpa_consent,
        consented_at=pref.pdpa_consent_at,
        status="success",
    )


@router.get("/consent/{line_user_id}", response_model=PDPAConsentResponse)
def get_pdpa_consent(
    line_user_id: str,
    shop_id: str | None = Query(None, description="Shop identifier"),
    db: Session = Depends(get_db),
) -> Any:
    """
    Check current PDPA consent state for a user.
    """
    consented = has_pdpa_consent(db=db, line_user_id=line_user_id, shop_id=shop_id)
    return PDPAConsentResponse(
        line_user_id=line_user_id,
        consent=consented,
        consented_at=None,
        status="active" if consented else "revoked",
    )


@router.post("/delete", response_model=PDPADeleteResponse, status_code=status.HTTP_200_OK)
def delete_user_pdpa_data(
    payload: PDPADeleteRequest,
    db: Session = Depends(get_db),
) -> Any:
    """
    Execute Right-to-Delete under PDPA:
    - Wipes personal data from address_book.
    - Preserves historical orders with line_user_id SHA-256 hashed.
    - Deletes preferences / revokes consent.
    - Logs deletion in pdpa_deletions.
    """
    result = execute_pdpa_deletion(
        db=db,
        line_user_id=payload.line_user_id,
        shop_id=payload.shop_id,
    )
    return PDPADeleteResponse(
        line_user_id=result["line_user_id"],
        anonymized_user_id=result["anonymized_user_id"],
        addresses_deleted=result["addresses_deleted"],
        orders_anonymized=result["orders_anonymized"],
        status="deleted",
    )


@router.post("/retention", response_model=PDPARetentionJobResponse)
def trigger_retention_job(
    retention_months: int | None = Query(None, description="Override retention months"),
    shop_id: str | None = Query(None, description="Shop identifier"),
    db: Session = Depends(get_db),
) -> Any:
    """
    Trigger auto-delete retention job against retention_months setting.
    """
    months = retention_months if retention_months is not None else settings.RETENTION_MONTHS
    deleted_ids = run_pdpa_retention_job(
        db=db,
        retention_months=months,
        shop_id=shop_id,
    )
    return PDPARetentionJobResponse(
        deleted_user_ids=deleted_ids,
        retention_months=months,
        status="completed",
    )
