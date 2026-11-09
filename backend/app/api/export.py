"""Export API endpoints for Phase 12: Carrier CSV export."""

import io
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_owner
from app.core.config import settings
from app.core.database import get_db
from app.services.carrier_mapper import (
    CarrierConfigError,
    CarrierConfigNotFoundError,
)
from app.services.export_service import (
    InvalidOrderStateForExportError,
    export_fulfilled_orders,
)
from app.services.i18n import get_text

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/csv", dependencies=[Depends(require_owner)])
def export_carrier_csv(
    carrier_id: Annotated[str, Query(description="Carrier configuration ID (e.g. kerry, thailand_post)")],
    shop_id: Annotated[str | None, Query(description="Shop ID (defaults to configured default)")] = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """
    Export fulfilled orders as carrier-formatted CSV.

    - Content-Type: text/csv; charset=utf-8
    - Content-Disposition: attachment; filename="{carrier_id}_{YYYY-MM-DD}.csv"
    - Returns 403 if requested by staff role.
    - Returns 400 if carrier_id is unknown.
    - Returns 200 with headers only if no fulfilled orders exist.
    """
    target_shop_id = shop_id or settings.DEFAULT_SHOP_ID or "default"

    try:
        csv_string, filename = export_fulfilled_orders(
            shop_id=target_shop_id,
            carrier_id=carrier_id,
            db=db,
        )
    except CarrierConfigNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=get_text("export_unknown_carrier", lang="en"),
        ) from exc
    except (CarrierConfigError, InvalidOrderStateForExportError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    csv_bytes = csv_string.encode("utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": "text/csv; charset=utf-8",
    }

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv; charset=utf-8",
        headers=headers,
    )


@router.get("/{carrier_id}", dependencies=[Depends(require_owner)])
@router.post("/{carrier_id}", dependencies=[Depends(require_owner)])
def export_carrier_path_alias(
    carrier_id: str,
    shop_id: Annotated[str | None, Query(description="Shop ID")] = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    """Route alias matching v1_buildable_spec.md §19 POST /api/export/{carrier}."""
    return export_carrier_csv(
        carrier_id=carrier_id,
        shop_id=shop_id,
        db=db,
    )
