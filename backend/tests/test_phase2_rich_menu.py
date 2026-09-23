from unittest.mock import MagicMock

from app.core.line_client import LineClient
from app.services.i18n import get_text
from app.services.rich_menu import build_rich_menu_object, create_and_link_rich_menu


def test_build_rich_menu_object_thai():
    """Verify Thai rich menu structure and localized labels."""
    menu = build_rich_menu_object("th")
    assert menu["size"] == {"width": 2500, "height": 843}
    assert menu["selected"] is True
    assert menu["chatBarText"] == get_text("chat_bar_menu", "th")
    assert len(menu["areas"]) == 4

    areas = menu["areas"]
    # 1. Browse
    assert areas[0]["action"]["type"] == "postback"
    assert areas[0]["action"]["data"] == "action=browse"
    assert areas[0]["action"]["displayText"] == get_text("menu_browse", "th")

    # 2. Orders
    assert areas[1]["action"]["data"] == "action=orders"
    assert areas[1]["action"]["displayText"] == get_text("menu_orders", "th")

    # 3. Help
    assert areas[2]["action"]["data"] == "action=help"
    assert areas[2]["action"]["displayText"] == get_text("menu_help", "th")

    # 4. Language switch to English
    assert areas[3]["action"]["data"] == "action=set_lang&lang=en"
    assert areas[3]["action"]["displayText"] == get_text("menu_language", "th")


def test_build_rich_menu_object_english():
    """Verify English rich menu structure and localized labels."""
    menu = build_rich_menu_object("en")
    assert menu["size"] == {"width": 2500, "height": 843}
    assert menu["selected"] is True
    assert menu["chatBarText"] == get_text("chat_bar_menu", "en")
    assert len(menu["areas"]) == 4

    areas = menu["areas"]
    assert areas[0]["action"]["displayText"] == get_text("menu_browse", "en")
    assert areas[1]["action"]["displayText"] == get_text("menu_orders", "en")
    assert areas[2]["action"]["displayText"] == get_text("menu_help", "en")
    assert areas[3]["action"]["data"] == "action=set_lang&lang=th"
    assert areas[3]["action"]["displayText"] == get_text("menu_language", "en")


def test_create_and_link_rich_menu():
    """Verify creation and user linking through LineClient wrapper."""
    mock_client = MagicMock(spec=LineClient)
    mock_client.create_rich_menu.return_value = "richmenu-123456"

    user_id = "U_user_rich_menu_test"
    result_menu_id = create_and_link_rich_menu(user_id=user_id, lang="th", client=mock_client)

    assert result_menu_id == "richmenu-123456"
    assert mock_client.create_rich_menu.call_count == 1
    mock_client.link_rich_menu_to_user.assert_called_once_with(user_id, "richmenu-123456")
