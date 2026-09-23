import logging
import urllib.parse
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.line_client import LineClient
from app.models.inventory import Inventory
from app.schemas.webhook import LineWebhookEvent
from app.services.address_engine import (
    confirm_address_and_save,
    get_active_order_for_address,
    get_saved_address_choice_message,
    handle_address_edit,
    handle_use_saved_address,
    process_address_input,
    resolve_address_contradiction,
)
from app.services.address_session import get_address_session
from app.services.flex_builder import build_product_flex_message
from app.services.i18n import get_text, resolve_user_language, set_user_language
from app.services.intent_cascade import extract_order_intent
from app.services.order_service import (
    EmptyCartError,
    InvalidQuantityError,
    OutOfStockError,
    ProductNotFoundError,
    add_item_to_draft,
    confirm_draft_order,
    format_order_summary,
    product_has_sizes,
)
from app.services.pdpa_service import (
    build_consent_prompt_message,
    execute_pdpa_deletion,
    has_pdpa_consent,
    record_pdpa_consent,
)

logger = logging.getLogger(__name__)

# Transient user ordering selection state (keyed by user_id)
# Schema: {"sku": str, "size": str | None, "step": "size" | "qty"}
_USER_SELECTION_STATE: dict[str, dict[str, Any]] = {}


def get_user_selection(user_id: str) -> dict[str, Any] | None:
    """Get the active pending selection for a user."""
    return _USER_SELECTION_STATE.get(user_id)


def set_user_selection(
    user_id: str,
    sku: str,
    size: str | None = None,
    step: str = "qty",
) -> None:
    """Record current pending product/size selection."""
    _USER_SELECTION_STATE[user_id] = {
        "sku": sku,
        "size": size,
        "step": step,
    }


def clear_user_selection(user_id: str) -> None:
    """Clear transient selection state for a user."""
    _USER_SELECTION_STATE.pop(user_id, None)


def clear_all_user_selections() -> None:
    """Clear all transient selection states (primarily for testing)."""
    _USER_SELECTION_STATE.clear()


async def dispatch_event(
    event: LineWebhookEvent,
    db: Session,
    client: LineClient,
) -> None:
    """
    Main entry point for intent routing.
    Dispatches incoming webhook events (postback / message) to guided ordering handlers.
    """
    user_id = event.source.user_id if event.source else None
    reply_token = event.reply_token

    if event.type == "postback" and event.postback:
        await _handle_postback(event, user_id, reply_token, db, client)
    elif event.type == "message" and event.message and event.message.type == "text":
        await _handle_text_message(event, user_id, reply_token, db, client)


async def _handle_postback(
    event: LineWebhookEvent,
    user_id: str | None,
    reply_token: str | None,
    db: Session,
    client: LineClient,
) -> None:
    """Route postback events by action payload."""
    raw_data = event.postback.data if event.postback else ""
    parsed = urllib.parse.parse_qs(raw_data)
    action = parsed.get("action", [None])[0]

    if not user_id:
        user_id = "anonymous"

    # Language switch handling
    if action == "set_lang":
        target_lang = parsed.get("lang", [None])[0]
        if target_lang:
            set_user_language(db, user_id=user_id, language=target_lang)
            active_lang = target_lang
        else:
            active_lang = resolve_user_language(db, user_id)
        if reply_token:
            msg_text = get_text("language_changed", active_lang)
            client.reply_message(reply_token, [{"type": "text", "text": msg_text}])
        return

    lang = resolve_user_language(db, user_id)

    # 1. Browse catalog (action=browse)
    if action == "browse":
        await handle_browse(db, user_id, reply_token, client, lang)
        return

    # 2. Select product (action=select_product or action=buy)
    if action in ("select_product", "buy"):
        sku = parsed.get("sku", [None])[0]
        if not sku:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("unknown_command", lang)}]
                )
            return
        await handle_select_product(db, user_id, sku, reply_token, client, lang)
        return

    # 3. Select size (action=select_size)
    if action == "select_size":
        size = parsed.get("size", [None])[0]
        sku = parsed.get("sku", [None])[0]
        if not sku:
            pending = get_user_selection(user_id)
            sku = pending.get("sku") if pending else None

        if not sku or not size:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("unknown_command", lang)}]
                )
            return
        await handle_select_size(db, user_id, sku, size, reply_token, client, lang)
        return

    # 4. Set quantity (action=set_qty)
    if action == "set_qty":
        qty_str = parsed.get("qty", [None])[0]
        sku = parsed.get("sku", [None])[0]
        size = parsed.get("size", [None])[0]

        pending = get_user_selection(user_id)
        if not sku and pending:
            sku = pending.get("sku")
        if not size and pending:
            size = pending.get("size")

        if not sku or not qty_str:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("unknown_command", lang)}]
                )
            return

        try:
            qty = int(qty_str)
        except ValueError:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("invalid_qty_error", lang)}]
                )
            return

        await handle_set_qty(db, user_id, sku, size, qty, reply_token, client, lang)
        return

    # 5. Order more (action=add_more) - returns to product carousel loop
    if action == "add_more":
        await handle_browse(db, user_id, reply_token, client, lang)
        return

    # 6. Confirm order (action=confirm_order)
    if action == "confirm_order":
        await handle_confirm_order(db, user_id, reply_token, client, lang)
        return

    # Phase 4 Address Postbacks
    if action == "address_confirm":
        _, _, reply_msgs = confirm_address_and_save(db, user_id, lang=lang)
        if reply_token:
            client.reply_message(reply_token, reply_msgs)
        return

    if action == "address_edit":
        reply_msgs = handle_address_edit(db, user_id, lang=lang)
        if reply_token:
            client.reply_message(reply_token, reply_msgs)
        return

    if action == "use_saved_address":
        if not has_pdpa_consent(db, user_id):
            if reply_token:
                client.reply_message(reply_token, [build_consent_prompt_message(lang)])
            return
        aid = parsed.get("address_id", [None])[0]
        addr_id = int(aid) if aid and aid.isdigit() else None
        reply_msgs = handle_use_saved_address(db, user_id, address_id=addr_id, lang=lang)
        if reply_token:
            client.reply_message(reply_token, reply_msgs)
        return

    if action == "enter_new_address":
        if not has_pdpa_consent(db, user_id):
            if reply_token:
                client.reply_message(reply_token, [build_consent_prompt_message(lang)])
            return
        handle_address_edit(db, user_id, lang=lang)
        prompt_msg = {"type": "text", "text": get_text("enter_address_prompt", lang)}
        if reply_token:
            client.reply_message(reply_token, [prompt_msg])
        return

    # Phase 10 PDPA Postbacks
    if action == "pdpa_consent_accept":
        record_pdpa_consent(db, user_id, consent=True)
        ack_text = get_text("pdpa_consent_accepted", lang)
        saved_choice = get_saved_address_choice_message(db, user_id=user_id, lang=lang)
        if saved_choice and "quickReply" in saved_choice:
            ack_msg = {"type": "text", "text": ack_text, "quickReply": saved_choice["quickReply"]}
            reply_messages = [ack_msg]
        else:
            prompt_msg = {"type": "text", "text": get_text("enter_address_prompt", lang)}
            reply_messages = [{"type": "text", "text": ack_text}, prompt_msg]
        if reply_token:
            client.reply_message(reply_token, reply_messages)
        return

    if action in ("pdpa_consent_decline", "pdpa_consent_withdraw"):
        record_pdpa_consent(db, user_id, consent=False)
        if reply_token:
            client.reply_message(
                reply_token,
                [{"type": "text", "text": get_text("pdpa_consent_declined", lang)}],
            )
        return

    if action == "pdpa_delete_request":
        execute_pdpa_deletion(db, user_id)
        if reply_token:
            client.reply_message(
                reply_token,
                [{"type": "text", "text": get_text("pdpa_delete_done", lang)}],
            )
        return

    if action == "resolve_contradiction":
        choice = parsed.get("choice", [None])[0] or "postcode"
        val = parsed.get("val", [None])[0]
        reply_msgs = resolve_address_contradiction(db, user_id, choice=choice, value=val, lang=lang)
        if reply_token:
            client.reply_message(reply_token, reply_msgs)
        return

    # Auxiliary actions
    if action == "orders":
        if reply_token:
            msg_text = get_text("order_history_empty", lang)
            client.reply_message(reply_token, [{"type": "text", "text": msg_text}])
        return

    if action == "help":
        if reply_token:
            msg_text = get_text("help_text", lang)
            client.reply_message(reply_token, [{"type": "text", "text": msg_text}])
        return

    # Fallback for unrecognized postback
    if reply_token:
        client.reply_message(
            reply_token, [{"type": "text", "text": get_text("unknown_command", lang)}]
        )


async def _handle_text_message(
    event: LineWebhookEvent,
    user_id: str | None,
    reply_token: str | None,
    db: Session,
    client: LineClient,
) -> None:
    """Handle text message events (e.g. numeric quantity inputs or keywords)."""
    if not event.message or not event.message.text:
        return

    if not user_id:
        user_id = "anonymous"

    text = event.message.text.strip()
    lang = resolve_user_language(db, user_id)
    pending = get_user_selection(user_id)

    # 1. Check if user has a pending quantity step and typed a number
    if pending and pending.get("step") == "qty":
        sku = pending.get("sku")
        size = pending.get("size")
        try:
            qty = int(text)
            if sku:
                await handle_set_qty(db, user_id, sku, size, qty, reply_token, client, lang)
                return
        except ValueError:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("invalid_qty_error", lang)}]
                )
                return

    # 2. Keywords for navigation
    lower_text = text.lower()
    browse_keywords = {
        "browse",
        "catalog",
        "shop",
        get_text("menu_browse", "th").lower(),
        get_text("menu_browse", "en").lower(),
    }
    if lower_text in browse_keywords:
        await handle_browse(db, user_id, reply_token, client, lang)
        return

    confirm_keywords = {
        "confirm",
        get_text("confirm_order", "th").lower(),
        get_text("confirm_order", "en").lower(),
    }
    if lower_text in confirm_keywords:
        await handle_confirm_order(db, user_id, reply_token, client, lang)
        return

    welcome_keywords = {
        "hello",
        "hi",
        "hey",
        "menu",
        "show menu",
        "start",
        "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35",
        "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e04\u0e23\u0e31\u0e1a",
        "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e04\u0e48\u0e30",
        "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35\u0e2d\u0e35\u0e01\u0e04\u0e23\u0e31\u0e49\u0e07",
    }
    if lower_text in welcome_keywords:
        if reply_token:
            client.reply_message(reply_token, [{"type": "text", "text": get_text("welcome", lang)}])
        return

    # 3. Address slot-filling or address collection
    addr_session = get_address_session(user_id)
    active_order = get_active_order_for_address(db, user_id)
    if active_order or (
        addr_session and (addr_session.pending_field or addr_session.status != "IDLE")
    ):
        if not has_pdpa_consent(db, user_id):
            if reply_token:
                client.reply_message(reply_token, [build_consent_prompt_message(lang)])
            return

        reply_msgs = process_address_input(db, user_id, text, lang=lang)
        if reply_token:
            client.reply_message(reply_token, reply_msgs)
        return

    # 4. Phase 5: Free-text order intent cascade
    draft_intent = extract_order_intent(text, db, shop_id=None, lang=lang)
    if draft_intent:
        try:
            item, _ = add_item_to_draft(
                db,
                line_user_id=user_id,
                sku=draft_intent.sku,
                qty=draft_intent.qty,
                size=draft_intent.size,
            )
            subtotal_str = f"{item.line_total:,.2f}"
            line_msg = get_text(
                "line_subtotal",
                lang,
                name=item.name,
                qty=item.qty,
                subtotal=subtotal_str,
            )
            prompt_msg = get_text("add_more_or_confirm", lang)

            quick_replies = [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": get_text("btn_order_more", lang),
                        "data": "action=add_more",
                        "displayText": get_text("btn_order_more", lang),
                    },
                },
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": get_text("btn_confirm_order", lang),
                        "data": "action=confirm_order",
                        "displayText": get_text("btn_confirm_order", lang),
                    },
                },
            ]

            response_text = f"{line_msg}\n\n{prompt_msg}"
            msg = {
                "type": "text",
                "text": response_text,
                "quickReply": {"items": quick_replies},
            }
            if reply_token:
                client.reply_message(reply_token, [msg])
            return
        except OutOfStockError:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("out_of_stock_error", lang)}]
                )
            return
        except ProductNotFoundError:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("product_not_found", lang)}]
                )
            return
        except InvalidQuantityError:
            if reply_token:
                client.reply_message(
                    reply_token, [{"type": "text", "text": get_text("invalid_qty_error", lang)}]
                )
            return

    # 5. Fallback for unrecognized text / low confidence
    if reply_token:
        client.reply_message(
            reply_token, [{"type": "text", "text": get_text("free_text_fallback", lang)}]
        )


async def handle_browse(
    db: Session,
    user_id: str,
    reply_token: str | None,
    client: LineClient,
    lang: str,
) -> None:
    """Send product catalog Flex carousel to buyer."""
    items = (
        db.query(Inventory)
        .filter(Inventory.active == True)  # noqa: E712
        .limit(settings.CAROUSEL_PAGE_SIZE)
        .all()
    )
    if reply_token:
        flex_msg = build_product_flex_message(items, lang=lang)
        client.reply_message(reply_token, [flex_msg])


async def handle_select_product(
    db: Session,
    user_id: str,
    sku: str,
    reply_token: str | None,
    client: LineClient,
    lang: str,
) -> None:
    """
    Handle buyer selecting a product.
    If product has sizes, ask for size.
    Otherwise, ask for quantity directly.
    """
    product = db.query(Inventory).filter(Inventory.sku == sku).first()
    if not product or not product.active:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("product_not_found", lang)}]
            )
        return

    available_stock = product.stock - product.reserved
    if available_stock <= 0:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("out_of_stock_error", lang)}]
            )
        return

    sizes = product_has_sizes(product)
    if sizes:
        set_user_selection(user_id, sku=sku, size=None, step="size")
        prompt_text = get_text("pick_size", lang, name=product.name)

        # Quick reply items for sizes
        quick_replies = [
            {
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": size,
                    "data": f"action=select_size&sku={sku}&size={size}",
                    "displayText": size,
                },
            }
            for size in sizes
        ]
        msg = {
            "type": "text",
            "text": prompt_text,
            "quickReply": {"items": quick_replies},
        }
        if reply_token:
            client.reply_message(reply_token, [msg])
    else:
        set_user_selection(user_id, sku=sku, size=None, step="qty")
        prompt_text = get_text("enter_qty", lang, name=product.name)

        # Quick reply options for common quantities
        qty_options = [1, 2, 3, 5]
        valid_qtys = [q for q in qty_options if q <= available_stock] or [1]
        quick_replies = [
            {
                "type": "action",
                "action": {
                    "type": "postback",
                    "label": str(q),
                    "data": f"action=set_qty&sku={sku}&qty={q}",
                    "displayText": str(q),
                },
            }
            for q in valid_qtys
        ]
        msg = {
            "type": "text",
            "text": prompt_text,
            "quickReply": {"items": quick_replies},
        }
        if reply_token:
            client.reply_message(reply_token, [msg])


async def handle_select_size(
    db: Session,
    user_id: str,
    sku: str,
    size: str,
    reply_token: str | None,
    client: LineClient,
    lang: str,
) -> None:
    """Handle buyer selecting a size. Prompts for quantity."""
    product = db.query(Inventory).filter(Inventory.sku == sku).first()
    if not product or not product.active:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("product_not_found", lang)}]
            )
        return

    available_stock = product.stock - product.reserved
    if available_stock <= 0:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("out_of_stock_error", lang)}]
            )
        return

    set_user_selection(user_id, sku=sku, size=size, step="qty")
    prompt_text = get_text("enter_qty_with_size", lang, name=product.name, size=size)

    qty_options = [1, 2, 3, 5]
    valid_qtys = [q for q in qty_options if q <= available_stock] or [1]
    quick_replies = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": str(q),
                "data": f"action=set_qty&sku={sku}&size={size}&qty={q}",
                "displayText": str(q),
            },
        }
        for q in valid_qtys
    ]
    msg = {
        "type": "text",
        "text": prompt_text,
        "quickReply": {"items": quick_replies},
    }
    if reply_token:
        client.reply_message(reply_token, [msg])


async def handle_set_qty(
    db: Session,
    user_id: str,
    sku: str,
    size: str | None,
    qty: int,
    reply_token: str | None,
    client: LineClient,
    lang: str,
) -> None:
    """
    Handle quantity input:
    1. Adds item to draft order.
    2. Shows line subtotal.
    3. Asks 'Add more or confirm?' with quick actions.
    """
    if qty <= 0:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("invalid_qty_error", lang)}]
            )
        return

    try:
        item, _ = add_item_to_draft(
            db,
            line_user_id=user_id,
            sku=sku,
            qty=qty,
            size=size,
        )
    except OutOfStockError:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("out_of_stock_error", lang)}]
            )
        return
    except ProductNotFoundError:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("product_not_found", lang)}]
            )
        return
    except InvalidQuantityError:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("invalid_qty_error", lang)}]
            )
        return

    # Clear pending selection
    clear_user_selection(user_id)

    subtotal_str = f"{item.line_total:,.2f}"
    line_msg = get_text(
        "line_subtotal",
        lang,
        name=item.name,
        qty=item.qty,
        subtotal=subtotal_str,
    )
    prompt_msg = get_text("add_more_or_confirm", lang)

    quick_replies = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("btn_order_more", lang),
                "data": "action=add_more",
                "displayText": get_text("btn_order_more", lang),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("btn_confirm_order", lang),
                "data": "action=confirm_order",
                "displayText": get_text("btn_confirm_order", lang),
            },
        },
    ]

    response_text = f"{line_msg}\n\n{prompt_msg}"
    msg = {
        "type": "text",
        "text": response_text,
        "quickReply": {"items": quick_replies},
    }

    if reply_token:
        client.reply_message(reply_token, [msg])


async def handle_confirm_order(
    db: Session,
    user_id: str,
    reply_token: str | None,
    client: LineClient,
    lang: str,
) -> None:
    """
    Handle order confirmation:
    1. Checks empty cart.
    2. Validates available stock.
    3. Advances status to ORDER_CONFIRMED.
    4. Replies with order summary and next step hint.
    """
    try:
        order = confirm_draft_order(db, line_user_id=user_id)
    except EmptyCartError:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("empty_cart_error", lang)}]
            )
        return
    except OutOfStockError:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("out_of_stock_error", lang)}]
            )
        return
    except ProductNotFoundError:
        if reply_token:
            client.reply_message(
                reply_token, [{"type": "text", "text": get_text("product_not_found", lang)}]
            )
        return

    clear_user_selection(user_id)

    summary_text = format_order_summary(order, lang=lang)
    next_step_text = get_text("order_confirmed_next_step", lang)

    step2_msg: dict[str, Any] = {"type": "text", "text": next_step_text}
    saved_choice = get_saved_address_choice_message(db, user_id=user_id, lang=lang)
    if saved_choice and "quickReply" in saved_choice:
        step2_msg["quickReply"] = saved_choice["quickReply"]

    messages = [
        {"type": "text", "text": summary_text},
        step2_msg,
    ]
    if reply_token:
        client.reply_message(reply_token, messages)
