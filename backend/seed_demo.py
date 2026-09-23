#!/usr/bin/env python3
"""
Seed script for KhaiFlow LINE Commerce system.

Populates the database with demo inventory, address book entries,
fulfilled orders, and an active awaiting-payment order.

Idempotent: Uses INSERT ... ON CONFLICT DO NOTHING to avoid duplicate data.
"""

import json
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

# Ensure backend directory is on sys.path
backend_path = Path(__file__).resolve().parent.parent / "backend"
if str(backend_path) not in sys.path:
    sys.path.insert(0, str(backend_path))

from app.core.config import settings
from app.core.database import engine, SessionLocal


def seed_demo_data() -> None:
    shop_id = settings.DEFAULT_SHOP_ID or "default"
    now = datetime.now(timezone.utc)

    print("=" * 60)
    print("KhaiFlow - Demo Data Seeder")
    print(f"Target Database: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")
    print(f"Shop ID: {shop_id}")
    print("=" * 60)

    # 1. Demo Inventory Items (T-shirt S/M/L, Mug, Tote Bag)
    inventory_items = [
        {
            "sku": "TSHIRT-M",
            "shop_id": shop_id,
            "name": "Minimalist Cotton T-Shirt (S/M/L)",
            "category": "Apparel",
            "price": Decimal("390.00"),
            "image_url": "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=500",
            "stock": 50,
            "reserved": 1,
            "active": True,
            "version": 1,
        },
        {
            "sku": "MUG-001",
            "shop_id": shop_id,
            "name": "Ceramic Coffee Mug (12oz)",
            "category": "Drinkware",
            "price": Decimal("250.00"),
            "image_url": "https://images.unsplash.com/photo-1514432324607-a09d9b4aefdd?w=500",
            "stock": 30,
            "reserved": 0,
            "active": True,
            "version": 1,
        },
        {
            "sku": "TOTE-001",
            "shop_id": shop_id,
            "name": "Heavyweight Canvas Tote Bag",
            "category": "Accessories",
            "price": Decimal("190.00"),
            "image_url": "https://images.unsplash.com/photo-1544816155-12df9643f363?w=500",
            "stock": 40,
            "reserved": 1,
            "active": True,
            "version": 1,
        },
    ]

    # 2. Demo Address Book Entries
    addresses = [
        {
            "id": 1001,
            "shop_id": shop_id,
            "line_user_id": "U_demo_buyer_01",
            "label": "Home",
            "receiver_name": "Somchai Jaidee",
            "phone": "0812345678",
            "address_json": json.dumps({
                "receiver": "Somchai Jaidee",
                "phone": "0812345678",
                "address_detail": "123/45 Sukhumvit Rd, Soi Thong Lo 10",
                "sub_district": "Khlong Tan Nuea",
                "district": "Watthana",
                "province": "Bangkok",
                "zipcode": "10110",
                "confidence": 0.98,
            }),
            "is_default": True,
            "created_at": now - timedelta(days=2),
        },
        {
            "id": 1002,
            "shop_id": shop_id,
            "line_user_id": "U_demo_buyer_02",
            "label": "Office",
            "receiver_name": "Kanya Rattanaporn",
            "phone": "0898765432",
            "address_json": json.dumps({
                "receiver": "Kanya Rattanaporn",
                "phone": "0898765432",
                "address_detail": "88/2 Silom Complex, 15th Fl, Silom Rd",
                "sub_district": "Silom",
                "district": "Bang Rak",
                "province": "Bangkok",
                "zipcode": "10500",
                "confidence": 0.96,
            }),
            "is_default": True,
            "created_at": now - timedelta(days=1),
        },
    ]

    # 3. Demo Orders: 2 FULFILLED, 1 AWAITING_PAYMENT
    orders = [
        {
            "id": "ORD-DEMO-001",
            "shop_id": shop_id,
            "line_user_id": "U_demo_buyer_01",
            "status": "FULFILLED",
            "total": Decimal("390.00"),
            "currency": "THB",
            "created_at": now - timedelta(days=2),
            "updated_at": now - timedelta(days=2, hours=-1),
            "ttl_expires_at": None,
            "approval_state": "APPROVED",
            "payment_ref": "PP-TXN-98214301",
            "risk_score": 0,
        },
        {
            "id": "ORD-DEMO-002",
            "shop_id": shop_id,
            "line_user_id": "U_demo_buyer_02",
            "status": "FULFILLED",
            "total": Decimal("440.00"),
            "currency": "THB",
            "created_at": now - timedelta(days=1),
            "updated_at": now - timedelta(days=1, hours=-2),
            "ttl_expires_at": None,
            "approval_state": "APPROVED",
            "payment_ref": "PP-TXN-98214302",
            "risk_score": 5,
        },
        {
            "id": "ORD-DEMO-003",
            "shop_id": shop_id,
            "line_user_id": "U_demo_buyer_03",
            "status": "AWAITING_PAYMENT",
            "total": Decimal("580.00"),
            "currency": "THB",
            "created_at": now - timedelta(minutes=10),
            "updated_at": now - timedelta(minutes=10),
            "ttl_expires_at": now + timedelta(minutes=20),
            "approval_state": None,
            "payment_ref": None,
            "risk_score": None,
        },
    ]

    # 4. Demo Order Items
    order_items = [
        {
            "id": 1001,
            "order_id": "ORD-DEMO-001",
            "shop_id": shop_id,
            "sku": "TSHIRT-M",
            "name": "Minimalist Cotton T-Shirt (S/M/L)",
            "size": "M",
            "qty": 1,
            "unit_price": Decimal("390.00"),
            "line_total": Decimal("390.00"),
        },
        {
            "id": 1002,
            "order_id": "ORD-DEMO-002",
            "shop_id": shop_id,
            "sku": "MUG-001",
            "name": "Ceramic Coffee Mug (12oz)",
            "size": None,
            "qty": 1,
            "unit_price": Decimal("250.00"),
            "line_total": Decimal("250.00"),
        },
        {
            "id": 1003,
            "order_id": "ORD-DEMO-002",
            "shop_id": shop_id,
            "sku": "TOTE-001",
            "name": "Heavyweight Canvas Tote Bag",
            "size": None,
            "qty": 1,
            "unit_price": Decimal("190.00"),
            "line_total": Decimal("190.00"),
        },
        {
            "id": 1004,
            "order_id": "ORD-DEMO-003",
            "shop_id": shop_id,
            "sku": "TSHIRT-M",
            "name": "Minimalist Cotton T-Shirt (S/M/L)",
            "size": "L",
            "qty": 1,
            "unit_price": Decimal("390.00"),
            "line_total": Decimal("390.00"),
        },
        {
            "id": 1005,
            "order_id": "ORD-DEMO-003",
            "shop_id": shop_id,
            "sku": "TOTE-001",
            "name": "Heavyweight Canvas Tote Bag",
            "size": None,
            "qty": 1,
            "unit_price": Decimal("190.00"),
            "line_total": Decimal("190.00"),
        },
    ]

    # 5. Demo Stock Reservations (for AWAITING_PAYMENT order)
    reservations = [
        {
            "id": 1001,
            "order_id": "ORD-DEMO-003",
            "shop_id": shop_id,
            "sku": "TSHIRT-M",
            "qty": 1,
            "state": "RESERVED",
            "expires_at": now + timedelta(minutes=20),
            "created_at": now - timedelta(minutes=10),
        },
        {
            "id": 1002,
            "order_id": "ORD-DEMO-003",
            "shop_id": shop_id,
            "sku": "TOTE-001",
            "qty": 1,
            "state": "RESERVED",
            "expires_at": now + timedelta(minutes=20),
            "created_at": now - timedelta(minutes=10),
        },
    ]

    session = SessionLocal()
    try:
        # Insert Inventory
        for item in inventory_items:
            session.execute(
                text("""
                    INSERT INTO inventory (sku, shop_id, name, category, price, image_url, stock, reserved, active, version)
                    VALUES (:sku, :shop_id, :name, :category, :price, :image_url, :stock, :reserved, :active, :version)
                    ON CONFLICT (sku) DO NOTHING;
                """),
                item,
            )

        # Insert Address Book
        for addr in addresses:
            session.execute(
                text("""
                    INSERT INTO address_book (id, shop_id, line_user_id, label, receiver_name, phone, address_json, is_default, created_at)
                    VALUES (:id, :shop_id, :line_user_id, :label, :receiver_name, :phone, :address_json, :is_default, :created_at)
                    ON CONFLICT (id) DO NOTHING;
                """),
                addr,
            )

        # Insert Orders
        for ord_data in orders:
            session.execute(
                text("""
                    INSERT INTO orders (id, shop_id, line_user_id, status, total, currency, created_at, updated_at, ttl_expires_at, approval_state, payment_ref, risk_score)
                    VALUES (:id, :shop_id, :line_user_id, :status, :total, :currency, :created_at, :updated_at, :ttl_expires_at, :approval_state, :payment_ref, :risk_score)
                    ON CONFLICT (id) DO NOTHING;
                """),
                ord_data,
            )

        # Insert Order Items
        for item in order_items:
            session.execute(
                text("""
                    INSERT INTO order_items (id, order_id, shop_id, sku, name, size, qty, unit_price, line_total)
                    VALUES (:id, :order_id, :shop_id, :sku, :name, :size, :qty, :unit_price, :line_total)
                    ON CONFLICT (id) DO NOTHING;
                """),
                item,
            )

        # Insert Reservations
        for res in reservations:
            session.execute(
                text("""
                    INSERT INTO reservations (id, order_id, shop_id, sku, qty, state, expires_at, created_at)
                    VALUES (:id, :order_id, :shop_id, :sku, :qty, :state, :expires_at, :created_at)
                    ON CONFLICT (id) DO NOTHING;
                """),
                res,
            )

        # Sync PostgreSQL sequences if running on PostgreSQL
        if engine.dialect.name == "postgresql":
            for table in ("address_book", "order_items", "reservations"):
                try:
                    session.execute(
                        text(
                            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                            f"COALESCE((SELECT MAX(id) FROM {table}), 1), true);"
                        )
                    )
                except Exception:
                    pass

        session.commit()
        print("\nSeeding Completed Successfully (Idempotent: ON CONFLICT DO NOTHING):")
        print("\n1. Inventory Items (3 items):")
        for item in inventory_items:
            print(f"   - [{item['sku']}] {item['name']} | Price: {item['price']} {item.get('currency', 'THB')} | Stock: {item['stock']} | Reserved: {item['reserved']}")

        print("\n2. Address Book Profiles (2 profiles):")
        for addr in addresses:
            addr_data = json.loads(addr["address_json"])
            print(f"   - {addr['receiver_name']} ({addr['label']}) | {addr['phone']} | {addr_data.get('sub_district')}, {addr_data.get('district')}, {addr_data.get('province')} {addr_data.get('zipcode')}")

        print("\n3. Demo Orders (3 orders):")
        for ord_data in orders:
            print(f"   - {ord_data['id']} [{ord_data['status']}] | Total: {ord_data['total']} {ord_data['currency']} | Buyer: {ord_data['line_user_id']}")

        print("\n4. Stock Reservations:")
        for res in reservations:
            print(f"   - Order: {res['order_id']} | SKU: {res['sku']} | Qty: {res['qty']} | State: {res['state']}")
        print("=" * 60)

    except Exception as e:
        session.rollback()
        print(f"\n[ERROR] Seeding failed: {e}", file=sys.stderr)
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed_demo_data()
