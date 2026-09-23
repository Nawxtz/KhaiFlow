from typing import Any

from app.core.config import settings
from app.services.i18n import get_text


def _item_attr(item: Any, key: str, default: Any = None) -> Any:
    """Helper to access attribute from object or dict."""
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def build_product_bubble(item: Any, lang: str = "th") -> dict[str, Any]:
    """
    Build a single product bubble for the Flex Message carousel.
    All text sourced via get_text.
    """
    sku = _item_attr(item, "sku", "")
    name = _item_attr(item, "name", "")
    category = _item_attr(item, "category", "") or ""
    price_val = _item_attr(item, "price", 0)
    try:
        price_str = f"{float(price_val):,.2f}"
    except (ValueError, TypeError):
        price_str = str(price_val)

    stock = int(_item_attr(item, "stock", 0))
    active = bool(_item_attr(item, "active", True))
    image_url = _item_attr(item, "image_url", None)

    is_available = active and stock > 0
    stock_text = (
        get_text("in_stock", lang, count=stock) if is_available else get_text("out_of_stock", lang)
    )
    formatted_price = get_text("price_format", lang, price=price_str)

    bubble: dict[str, Any] = {
        "type": "bubble",
        "size": "micro",
    }

    if image_url:
        bubble["hero"] = {
            "type": "image",
            "url": image_url,
            "size": "full",
            "aspectRatio": "20:13",
            "aspectMode": "cover",
        }

    body_contents: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": name,
            "weight": "bold",
            "size": "md",
            "wrap": True,
        }
    ]

    if category:
        body_contents.append(
            {
                "type": "text",
                "text": category,
                "size": "xxs",
                "color": "#888888",
            }
        )

    body_contents.append(
        {
            "type": "text",
            "text": formatted_price,
            "weight": "bold",
            "size": "md",
            "color": "#1DB446",
            "margin": "sm",
        }
    )

    body_contents.append(
        {
            "type": "text",
            "text": stock_text,
            "size": "xs",
            "color": "#555555" if is_available else "#cc0000",
        }
    )

    bubble["body"] = {
        "type": "box",
        "layout": "vertical",
        "contents": body_contents,
    }

    footer_buttons: list[dict[str, Any]] = []
    if is_available:
        footer_buttons.append(
            {
                "type": "button",
                "style": "primary",
                "height": "sm",
                "action": {
                    "type": "postback",
                    "label": get_text("btn_buy_now", lang),
                    "data": f"action=buy&sku={sku}",
                },
            }
        )
    else:
        footer_buttons.append(
            {
                "type": "button",
                "style": "secondary",
                "height": "sm",
                "action": {
                    "type": "postback",
                    "label": get_text("btn_view_details", lang),
                    "data": f"action=detail&sku={sku}",
                },
            }
        )

    bubble["footer"] = {
        "type": "box",
        "layout": "vertical",
        "spacing": "sm",
        "contents": footer_buttons,
    }

    return bubble


def build_product_carousel(items: list[Any], lang: str = "th") -> dict[str, Any]:
    """
    Build a Flex Message carousel container from inventory items.
    Capped at CAROUSEL_PAGE_SIZE (default 8).
    All labels and text sourced from locale dictionaries.
    """
    page_size = getattr(settings, "CAROUSEL_PAGE_SIZE", 8)
    clamped_items = items[:page_size]

    bubbles = [build_product_bubble(item, lang=lang) for item in clamped_items]

    return {
        "type": "carousel",
        "contents": bubbles,
    }


def build_product_flex_message(items: list[Any], lang: str = "th") -> dict[str, Any]:
    """
    Build a complete LINE Flex Message ready to send in reply_message.
    """
    return {
        "type": "flex",
        "altText": get_text("carousel_title", lang),
        "contents": build_product_carousel(items, lang=lang),
    }
