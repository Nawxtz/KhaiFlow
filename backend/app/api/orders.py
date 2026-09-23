import logging
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.line_client import LineClient, line_client
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.schemas.order import FulfillmentResult, OrderCreate, OrderRead
from app.services.fulfillment_service import (
    InvalidOrderStateForFulfillmentError,
    fulfill_order_with_retry,
)
from app.services.fulfillment_service import (
    OrderNotFoundError as FulfillmentOrderNotFoundError,
)
from app.services.order_service import (
    generate_order_id,
    get_order_by_id,
    list_orders,
)
from app.services.sheet_ingest import GoogleSheetsClient, SheetsClientProtocol

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orders", tags=["orders"])


def get_sheets_client() -> SheetsClientProtocol:
    return GoogleSheetsClient()


def get_line_client() -> LineClient:
    return line_client


@router.get("", response_model=list[OrderRead])
def get_orders(
    shop_id: str | None = Query(None, description="Filter by shop ID"),
    line_user_id: str | None = Query(None, description="Filter by LINE user ID"),
    status_filter: str | None = Query(None, alias="status", description="Filter by order status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> Any:
    """
    List orders for a shop (Phase 3 subset).
    Supports filtering by line_user_id and status.
    """
    return list_orders(
        db,
        shop_id=shop_id,
        line_user_id=line_user_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_id}", response_model=OrderRead)
def get_order(
    order_id: str,
    shop_id: str | None = Query(None, description="Filter by shop ID"),
    db: Session = Depends(get_db),
) -> Any:
    """
    Retrieve a specific order by ID with its line items.
    """
    order = get_order_by_id(db, order_id=order_id, shop_id=shop_id)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order '{order_id}' not found",
        )
    return order


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
def create_order(
    payload: OrderCreate,
    db: Session = Depends(get_db),
) -> Any:
    """
    Create an order programmatically with line items (used by tests and internal admin).
    """
    order_id = generate_order_id()
    order = Order(
        id=order_id,
        shop_id=payload.shop_id,
        line_user_id=payload.line_user_id,
        status=OrderStatus.ORDER_DRAFT.value,
        total=Decimal("0.00"),
        currency="THB",
    )
    db.add(order)

    total_amount = Decimal("0.00")
    for item_data in payload.items:
        # Validate product
        stmt = db.query(Inventory).filter(Inventory.sku == item_data.sku)
        if payload.shop_id:
            from sqlalchemy import or_

            stmt = stmt.filter(
                or_(Inventory.shop_id == payload.shop_id, Inventory.shop_id.is_(None))
            )
        product = stmt.first()

        if not product or not product.active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Product SKU '{item_data.sku}' not found or inactive",
            )

        # Check stock
        available_stock = product.stock - product.reserved
        if available_stock < item_data.qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Product '{product.name}' is out of stock. "
                    f"Requested: {item_data.qty}, Available: {available_stock}"
                ),
            )

        unit_price = item_data.unit_price if item_data.unit_price is not None else product.price
        line_total = Decimal(item_data.qty) * Decimal(unit_price)

        order_item = OrderItem(
            order_id=order_id,
            shop_id=payload.shop_id,
            sku=product.sku,
            name=item_data.name or product.name,
            size=item_data.size,
            qty=item_data.qty,
            unit_price=Decimal(unit_price),
            line_total=line_total,
        )
        db.add(order_item)
        order.items.append(order_item)
        total_amount += line_total

    order.total = total_amount
    db.commit()
    db.refresh(order)
    return order


@router.post(
    "/{order_id}/fulfill",
    response_model=FulfillmentResult,
    status_code=status.HTTP_200_OK,
)
def fulfill_order_endpoint(
    order_id: str,
    db: Session = Depends(get_db),
    sheets_client: SheetsClientProtocol = Depends(get_sheets_client),
    line_client_instance: LineClient = Depends(get_line_client),
) -> Any:
    """
    Trigger fulfillment for an order (Phase 9).
    Internal/admin only; writes to Google Sheets and notifies buyer.
    Idempotent: if already fulfilled, skips safely.
    """
    try:
        result = fulfill_order_with_retry(
            order_id=order_id,
            db=db,
            sheets_client=sheets_client,
            line_client_instance=line_client_instance,
        )
    except FulfillmentOrderNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except InvalidOrderStateForFulfillmentError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return result
