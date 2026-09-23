from decimal import Decimal

from app.core.config import settings
from app.models.inventory import Inventory
from app.services.flex_builder import (
    build_product_bubble,
    build_product_carousel,
    build_product_flex_message,
)
from app.services.i18n import get_text


def test_build_product_bubble_in_stock():
    """Verify bubble generation for in-stock item in English and Thai."""
    item = {
        "sku": "SKU-BUBBLE-01",
        "name": "Ceramic Tea Set",
        "category": "Home",
        "price": 850.0,
        "stock": 12,
        "active": True,
        "image_url": "https://example.com/tea.jpg",
    }

    # English
    bubble_en = build_product_bubble(item, lang="en")
    assert bubble_en["type"] == "bubble"
    assert bubble_en["hero"]["url"] == "https://example.com/tea.jpg"

    # Body texts
    body_texts = [c.get("text") for c in bubble_en["body"]["contents"] if "text" in c]
    assert "Ceramic Tea Set" in body_texts
    assert "Home" in body_texts
    assert get_text("in_stock", "en", count=12) in body_texts

    # Footer button
    footer_btn = bubble_en["footer"]["contents"][0]
    assert footer_btn["action"]["label"] == get_text("btn_buy_now", "en")
    assert footer_btn["action"]["label"] == "Buy Now"
    assert footer_btn["action"]["data"] == "action=buy&sku=SKU-BUBBLE-01"

    # Thai
    bubble_th = build_product_bubble(item, lang="th")
    body_texts_th = [c.get("text") for c in bubble_th["body"]["contents"] if "text" in c]
    assert get_text("in_stock", "th", count=12) in body_texts_th
    footer_btn_th = bubble_th["footer"]["contents"][0]
    assert footer_btn_th["action"]["label"] == get_text("btn_buy_now", "th")
    assert footer_btn_th["action"]["label"] == "สั่งซื้อทันที"


def test_build_product_bubble_out_of_stock():
    """Verify bubble generation for out-of-stock item."""
    item = Inventory(
        sku="SKU-OUT-01",
        name="Rare Artifact",
        category="Collectibles",
        price=Decimal("1500.00"),
        stock=0,
        active=True,
    )

    bubble_en = build_product_bubble(item, lang="en")
    body_texts = [c.get("text") for c in bubble_en["body"]["contents"] if "text" in c]
    assert get_text("out_of_stock", "en") in body_texts

    footer_btn = bubble_en["footer"]["contents"][0]
    assert footer_btn["action"]["label"] == get_text("btn_view_details", "en")
    assert footer_btn["action"]["data"] == "action=detail&sku=SKU-OUT-01"


def test_carousel_page_size_clamping():
    """Verify carousel clamps items to CAROUSEL_PAGE_SIZE (default 8)."""
    items = [
        {
            "sku": f"SKU-{i:03d}",
            "name": f"Product {i}",
            "price": 100.0 * i,
            "stock": 5,
            "active": True,
        }
        for i in range(1, 15)  # 14 items
    ]

    page_size = settings.CAROUSEL_PAGE_SIZE
    assert page_size == 8

    carousel = build_product_carousel(items, lang="th")
    assert carousel["type"] == "carousel"
    assert len(carousel["contents"]) == 8


def test_build_product_flex_message():
    """Verify complete Flex Message output with altText from locale."""
    items = [{"sku": "SKU-1", "name": "Item 1", "price": 100.0, "stock": 5, "active": True}]

    msg_en = build_product_flex_message(items, lang="en")
    assert msg_en["type"] == "flex"
    assert msg_en["altText"] == get_text("carousel_title", "en")
    assert msg_en["altText"] == "Featured Products"
    assert msg_en["contents"]["type"] == "carousel"

    msg_th = build_product_flex_message(items, lang="th")
    assert msg_th["altText"] == get_text("carousel_title", "th")
    assert msg_th["altText"] == "รายการสินค้าแนะนำ"
