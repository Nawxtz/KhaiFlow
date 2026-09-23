import uuid
from decimal import Decimal

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus
from app.services.i18n import get_text


class OrderServiceError(Exception):
    """Base exception for order service errors."""

    pass


class EmptyCartError(OrderServiceError):
    """Raised when an operation requires items in the cart but none exist."""

    pass


class OutOfStockError(OrderServiceError):
    """Raised when requested quantity exceeds available stock."""

    def __init__(
        self,
        sku: str,
        name: str,
        requested_qty: int,
        available_stock: int,
    ) -> None:
        super().__init__(
            f"Product {name} ({sku}) is out of stock. Requested: {requested_qty}, Available: {available_stock}"
        )
        self.sku = sku
        self.name = name
        self.requested_qty = requested_qty
        self.available_stock = available_stock


class ProductNotFoundError(OrderServiceError):
    """Raised when the specified product SKU is not found or inactive."""

    def __init__(self, sku: str) -> None:
        super().__init__(f"Product with SKU '{sku}' not found or inactive.")
        self.sku = sku


class InvalidQuantityError(OrderServiceError):
    """Raised when quantity is invalid (non-positive or non-numeric)."""

    def __init__(self, qty_val: object) -> None:
        super().__init__(f"Invalid quantity: {qty_val}")
        self.qty_val = qty_val


def generate_order_id() -> str:
    """Generate a clean, collision-resistant unique order ID."""
    token = uuid.uuid4().hex[:10].upper()
    return f"ORD-{token}"


def product_has_sizes(product: Inventory) -> list[str]:
    """
    Check if a product has available size variants based on its category or attributes.
    Returns list of size codes (e.g. ['S', 'M', 'L', 'XL']) or empty list if no sizes.
    """
    category = (product.category or "").strip().lower()
    apparel_categories = {"apparel", "clothing", "fashion", "shirt", "shoes"}
    if category in apparel_categories or any(cat in category for cat in ("shirt", "apparel")):
        return ["S", "M", "L", "XL"]
    return []


def get_active_draft_order(
    db: Session,
    line_user_id: str,
    shop_id: str | None = None,
) -> Order | None:
    """Retrieve an active draft order for the user, if one exists."""
    stmt = (
        select(Order)
        .where(
            Order.line_user_id == line_user_id,
            Order.status == OrderStatus.ORDER_DRAFT.value,
        )
        .order_by(Order.created_at.desc())
    )
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    return db.execute(stmt).scalars().first()


def get_or_create_draft_order(
    db: Session,
    line_user_id: str,
    shop_id: str | None = None,
) -> Order:
    """
    Retrieve existing draft order for this user or create a new one.
    Initializes status as ORDER_DRAFT.
    """
    order = get_active_draft_order(db, line_user_id, shop_id=shop_id)
    if order is not None:
        return order

    order = Order(
        id=generate_order_id(),
        shop_id=shop_id,
        line_user_id=line_user_id,
        status=OrderStatus.ORDER_DRAFT.value,
        total=Decimal("0.00"),
        currency="THB",
    )
    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def add_item_to_draft(
    db: Session,
    line_user_id: str,
    sku: str,
    qty: int,
    size: str | None = None,
    shop_id: str | None = None,
) -> tuple[OrderItem, Order]:
    """
    Add a line item to the buyer's draft order.
    Validates stock availability (stock - reserved >= qty).
    Recalculates total and maintains ORDER_DRAFT state.
    """
    if qty <= 0:
        raise InvalidQuantityError(qty)

    # 1. Fetch product
    stmt = select(Inventory).where(Inventory.sku == sku)
    if shop_id:
        stmt = stmt.where(or_(Inventory.shop_id == shop_id, Inventory.shop_id.is_(None)))
    product = db.execute(stmt).scalars().first()

    if not product or not product.active:
        raise ProductNotFoundError(sku)

    # 2. Check stock guard: available = stock - reserved
    available_stock = product.stock - product.reserved
    if available_stock < qty:
        raise OutOfStockError(
            sku=product.sku,
            name=product.name,
            requested_qty=qty,
            available_stock=available_stock,
        )

    # 3. Get or create draft order
    order = get_or_create_draft_order(db, line_user_id, shop_id=shop_id)

    # 4. Check if line item already exists in this draft (matching sku and size)
    existing_item: OrderItem | None = None
    for item in order.items:
        if item.sku == sku and (item.size or None) == (size or None):
            existing_item = item
            break

    if existing_item:
        new_qty = existing_item.qty + qty
        if available_stock < new_qty:
            raise OutOfStockError(
                sku=product.sku,
                name=product.name,
                requested_qty=new_qty,
                available_stock=available_stock,
            )
        existing_item.qty = new_qty
        existing_item.line_total = Decimal(existing_item.qty) * Decimal(existing_item.unit_price)
        target_item = existing_item
    else:
        target_item = OrderItem(
            order_id=order.id,
            shop_id=shop_id,
            sku=product.sku,
            name=product.name,
            size=size,
            qty=qty,
            unit_price=Decimal(product.price),
            line_total=Decimal(qty) * Decimal(product.price),
        )
        db.add(target_item)
        order.items.append(target_item)

    # 5. Recalculate order total
    order.total = sum((item.line_total for item in order.items), Decimal("0.00"))
    order.status = OrderStatus.ORDER_DRAFT.value

    db.commit()
    db.refresh(order)
    db.refresh(target_item)
    return target_item, order


def confirm_draft_order(
    db: Session,
    line_user_id: str,
    shop_id: str | None = None,
) -> Order:
    """
    Confirm buyer's draft order:
    1. Rejects empty cart.
    2. Validates stock for all items.
    3. Sets status to ORDER_CONFIRMED (order confirmed before address collection).
    """
    order = get_active_draft_order(db, line_user_id, shop_id=shop_id)
    if not order or not order.items:
        raise EmptyCartError("Cannot confirm an empty cart.")

    # Re-verify stock for every item
    for item in order.items:
        stmt = select(Inventory).where(Inventory.sku == item.sku)
        if shop_id:
            stmt = stmt.where(or_(Inventory.shop_id == shop_id, Inventory.shop_id.is_(None)))
        product = db.execute(stmt).scalars().first()

        if not product or not product.active:
            raise ProductNotFoundError(item.sku)

        available_stock = product.stock - product.reserved
        if available_stock < item.qty:
            raise OutOfStockError(
                sku=item.sku,
                name=item.name,
                requested_qty=item.qty,
                available_stock=available_stock,
            )

    # Advance state machine: ORDER_DRAFT -> ORDER_CONFIRMED
    order.status = OrderStatus.ORDER_CONFIRMED.value
    db.commit()
    db.refresh(order)
    return order


def get_order_by_id(
    db: Session,
    order_id: str,
    shop_id: str | None = None,
) -> Order | None:
    """Retrieve an order by ID."""
    stmt = select(Order).where(Order.id == order_id)
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    return db.execute(stmt).scalars().first()


def list_orders(
    db: Session,
    shop_id: str | None = None,
    line_user_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    """List orders with optional filters."""
    stmt = select(Order).order_by(Order.created_at.desc())
    if shop_id:
        stmt = stmt.where(Order.shop_id == shop_id)
    if line_user_id:
        stmt = stmt.where(Order.line_user_id == line_user_id)
    if status:
        stmt = stmt.where(Order.status == status)
    stmt = stmt.limit(limit).offset(offset)
    return list(db.execute(stmt).scalars().all())


def format_order_summary(order: Order, lang: str = "th") -> str:
    """Format human-readable order summary text using localized templates."""
    line_entries: list[str] = []
    for item in order.items:
        size_str = f" ({item.size})" if item.size else ""
        subtotal_str = f"{item.line_total:,.2f}"
        line_entries.append(f"- {item.name}{size_str} x{item.qty}: \u0e3f{subtotal_str}")

    items_block = "\n".join(line_entries)
    total_str = f"{order.total:,.2f}"
    return get_text(
        "order_summary",
        lang,
        order_id=order.id,
        items=items_block,
        total=total_str,
    )
