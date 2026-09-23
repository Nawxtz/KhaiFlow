import json
import re
from pathlib import Path

from app.core.config import settings
from app.services.i18n import (
    get_text,
    resolve_user_language,
    set_user_language,
)


def test_locale_files_exist_and_are_valid_json():
    """Verify th.json and en.json exist and contain valid JSON."""
    locale_dir = Path(__file__).resolve().parent.parent / "app" / "locale"
    for lang in ("th", "en"):
        file_path = locale_dir / f"{lang}.json"
        assert file_path.exists(), f"Locale file {file_path} must exist"
        with open(file_path, encoding="utf-8") as f:
            data = json.load(f)
            assert isinstance(data, dict), f"Locale {lang} must be a dictionary"
            assert len(data) > 0, f"Locale {lang} must not be empty"


def test_locale_keys_complete_and_identical_parity():
    """
    TEST_PLAN.md: Thai and English locale files are both complete (no missing keys).
    Both files must have exact 1:1 key parity.
    """
    locale_dir = Path(__file__).resolve().parent.parent / "app" / "locale"
    with open(locale_dir / "th.json", encoding="utf-8") as f:
        th_data = json.load(f)
    with open(locale_dir / "en.json", encoding="utf-8") as f:
        en_data = json.load(f)

    th_keys = set(th_data.keys())
    en_keys = set(en_data.keys())

    missing_in_en = th_keys - en_keys
    missing_in_th = en_keys - th_keys

    assert not missing_in_en, f"Keys in th.json missing from en.json: {missing_in_en}"
    assert not missing_in_th, f"Keys in en.json missing from th.json: {missing_in_th}"

    # Ensure no values are empty strings
    for k, v in th_data.items():
        assert v and v.strip(), f"Key '{k}' in th.json has empty value"
    for k, v in en_data.items():
        assert v and v.strip(), f"Key '{k}' in en.json has empty value"


def test_get_text_translations_and_fallbacks():
    """Test get_text translation retrieval, fallback to Thai, and parameter formatting."""
    # Direct lookups
    th_welcome = get_text("welcome", "th")
    en_welcome = get_text("welcome", "en")
    assert th_welcome != en_welcome
    assert "ยินดีต้อนรับ" in th_welcome
    assert "Welcome" in en_welcome

    # Fallback to Thai when language is unknown
    fallback_text = get_text("welcome", "fr")
    assert fallback_text == th_welcome

    # Missing key returns key itself
    unknown_key = get_text("non_existent_key_12345", "en")
    assert unknown_key == "non_existent_key_12345"

    # Parameter formatting
    formatted_th = get_text("price_format", "th", price="990.00")
    assert "990.00" in formatted_th
    assert "฿" in formatted_th

    stock_en = get_text("in_stock", "en", count=5)
    assert "5 available" in stock_en


def test_language_resolution_order(db_session):
    """
    A27 resolution order:
    1. stored user_prefs.language
    2. shop default (ui_default_buyer_language)
    3. 'th'
    """
    user_id = "U_test_resolution_123"

    # 1. No stored pref -> returns shop default ('th')
    resolved = resolve_user_language(db_session, user_id)
    assert resolved == settings.UI_DEFAULT_BUYER_LANGUAGE

    # 2. Store preference as 'en' -> returns 'en'
    set_user_language(db_session, user_id=user_id, language="en")
    resolved_after = resolve_user_language(db_session, user_id)
    assert resolved_after == "en"

    # 3. Store preference as 'th' -> returns 'th'
    set_user_language(db_session, user_id=user_id, language="th")
    resolved_th = resolve_user_language(db_session, user_id)
    assert resolved_th == "th"

    # 4. Anonymous user -> returns shop default
    assert resolve_user_language(db_session, None) == settings.UI_DEFAULT_BUYER_LANGUAGE


def test_no_hardcoded_thai_characters_in_source_files():
    """
    TEST_PLAN.md: No hardcoded string literals in template files —
    lint/grep for raw Thai text outside locale/*.json.
    """
    app_dir = Path(__file__).resolve().parent.parent / "app"
    thai_pattern = re.compile(r"[\u0E00-\u0E7F]")

    violations = []
    for py_file in app_dir.rglob("*.py"):
        # Skip locale directory if any py files exist there
        if "locale" in py_file.parts:
            continue

        with open(py_file, encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                # Ignore comment lines if they don't contain UI text
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                if thai_pattern.search(line):
                    violations.append(f"{py_file.name}:{line_no} -> {line.strip()}")

    assert not violations, (
        f"Found {len(violations)} raw Thai characters in source code outside locale:\n"
        + "\n".join(violations)
    )


def test_no_hardcoded_english_ui_strings_in_source_files():
    """
    TEST_PLAN.md: Ensure common buyer-facing English UI strings are sourced from locale/*.json
    and not hardcoded as literals in handler/template code.
    """
    app_dir = Path(__file__).resolve().parent.parent / "app"
    # Target files responsible for buyer templates and messaging
    target_files = [
        app_dir / "services" / "flex_builder.py",
        app_dir / "services" / "rich_menu.py",
        app_dir / "api" / "webhook.py",
    ]

    forbidden_english_ui_strings = [
        "Welcome to our shop",
        "Browse Products",
        "My Orders",
        "Switch to ภาษาไทย",
        "Language has been changed",
        "Buy Now",
        "View Details",
        "In Stock",
        "Out of Stock",
        "Featured Products",
        "Main Menu",
    ]

    violations = []
    for file_path in target_files:
        if not file_path.exists():
            continue
        with open(file_path, encoding="utf-8") as f:
            content = f.read()
            for s in forbidden_english_ui_strings:
                if f'"{s}"' in content or f"'{s}'" in content:
                    violations.append(f"{file_path.name} contains hardcoded string: '{s}'")

    assert not violations, "Found hardcoded English UI strings outside locale:\n" + "\n".join(
        violations
    )
