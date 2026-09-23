from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.inventory import Inventory
from app.schemas.inventory import IngestSummary, InventoryItem
from app.services.cache import inventory_cache
from app.services.sheet_ingest import SheetIngestService

router = APIRouter(prefix="/api/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryItem])
def get_inventory(
    shop_id: Annotated[
        str | None,
        Query(description="Shop ID (defaults to configured default)"),
    ] = None,
    db: Session = Depends(get_db),
) -> list[InventoryItem]:
    """
    Get inventory catalog with available stock (available_stock = stock - reserved).
    Reads are served from cache without calling the Google Sheets API per request.
    """
    target_shop_id = shop_id or settings.DEFAULT_SHOP_ID

    # 1. Check cache first
    cached_items = inventory_cache.get(target_shop_id)
    if cached_items is not None:
        return cached_items

    # 2. On cache miss, read from authoritative DB
    rows = (
        db.query(Inventory)
        .filter(
            Inventory.shop_id == target_shop_id,
            Inventory.active.is_(True),
        )
        .all()
    )

    items = [
        InventoryItem(
            sku=row.sku,
            shop_id=row.shop_id,
            name=row.name,
            category=row.category,
            price=float(row.price),
            image_url=row.image_url,
            stock=int(row.stock),
            reserved=int(row.reserved),
            available_stock=max(0, int(row.stock) - int(row.reserved)),
            active=bool(row.active),
            version=int(row.version),
        )
        for row in rows
    ]

    # 3. Store in cache
    inventory_cache.set(
        items=items,
        shop_id=target_shop_id,
        ttl_seconds=settings.CACHE_TTL_SECONDS,
    )

    return items


@router.post("/sync", response_model=IngestSummary)
def sync_inventory(
    shop_id: Annotated[str | None, Query(description="Shop ID")] = None,
    db: Session = Depends(get_db),
) -> IngestSummary:
    """Manually trigger Google Sheets catalog synchronization."""
    target_shop_id = shop_id or settings.DEFAULT_SHOP_ID
    service = SheetIngestService()
    try:
        summary = service.ingest_sheet(db=db, shop_id=target_shop_id)
        return summary
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Sheet ingestion failed: {str(exc)}",
        ) from exc
