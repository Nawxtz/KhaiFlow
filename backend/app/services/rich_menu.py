from typing import Any

from app.core.line_client import LineClient, line_client
from app.services.i18n import get_text


def build_rich_menu_object(lang: str = "th") -> dict[str, Any]:
    """
    Build LINE Rich Menu definition using locale dictionary strings.
    No hardcoded UI strings.
    """
    alt_lang = "en" if lang == "th" else "th"

    return {
        "size": {"width": 2500, "height": 843},
        "selected": True,
        "name": f"rich_menu_{lang}",
        "chatBarText": get_text("chat_bar_menu", lang),
        "areas": [
            {
                "bounds": {"x": 0, "y": 0, "width": 625, "height": 843},
                "action": {
                    "type": "postback",
                    "data": "action=browse",
                    "displayText": get_text("menu_browse", lang),
                },
            },
            {
                "bounds": {"x": 625, "y": 0, "width": 625, "height": 843},
                "action": {
                    "type": "postback",
                    "data": "action=orders",
                    "displayText": get_text("menu_orders", lang),
                },
            },
            {
                "bounds": {"x": 1250, "y": 0, "width": 625, "height": 843},
                "action": {
                    "type": "postback",
                    "data": "action=help",
                    "displayText": get_text("menu_help", lang),
                },
            },
            {
                "bounds": {"x": 1875, "y": 0, "width": 625, "height": 843},
                "action": {
                    "type": "postback",
                    "data": f"action=set_lang&lang={alt_lang}",
                    "displayText": get_text("menu_language", lang),
                },
            },
        ],
    }


def create_and_link_rich_menu(
    user_id: str,
    lang: str = "th",
    client: LineClient | None = None,
) -> str:
    """
    Create a localized rich menu and link it to the user.
    """
    active_client = client or line_client
    menu_data = build_rich_menu_object(lang)
    menu_id = active_client.create_rich_menu(menu_data)
    active_client.link_rich_menu_to_user(user_id, menu_id)
    return menu_id
