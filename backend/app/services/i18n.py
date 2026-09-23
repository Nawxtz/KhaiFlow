import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.user_prefs import UserPrefs

logger = logging.getLogger(__name__)

SUPPORTED_LANGUAGES = {"th", "en"}
DEFAULT_LANGUAGE = "th"

_LOCALE_DIR = Path(__file__).resolve().parent.parent / "locale"
_LOCALES: dict[str, dict[str, str]] = {}


def load_locales() -> None:
    """Load all JSON locale dictionaries into memory."""
    global _LOCALES
    loaded: dict[str, dict[str, str]] = {}
    for lang in SUPPORTED_LANGUAGES:
        file_path = _LOCALE_DIR / f"{lang}.json"
        if file_path.exists():
            try:
                with open(file_path, encoding="utf-8") as f:
                    loaded[lang] = json.load(f)
            except Exception as e:
                logger.error("Failed to load locale file %s: %s", file_path, e)
                loaded[lang] = {}
        else:
            logger.warning("Locale file not found: %s", file_path)
            loaded[lang] = {}
    _LOCALES = loaded


# Load locales at module import / startup
load_locales()


def get_text(key: str, lang: str = DEFAULT_LANGUAGE, **kwargs: Any) -> str:
    """
    Return translated text for the given key in the specified language.
    Falls back to Thai ('th') if key is missing in requested language.
    Falls back to key itself if not found in any locale.
    """
    normalized_lang = lang if lang in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE

    text = _LOCALES.get(normalized_lang, {}).get(key)
    if text is None and normalized_lang != DEFAULT_LANGUAGE:
        # Fall back to Thai
        text = _LOCALES.get(DEFAULT_LANGUAGE, {}).get(key)

    if text is None:
        logger.warning("Missing translation key: %s (lang=%s)", key, lang)
        return key

    if kwargs:
        try:
            return text.format(**kwargs)
        except KeyError as e:
            logger.warning("Missing format argument %s for translation key %s", e, key)
            return text

    return text


def resolve_user_language(
    db: Session,
    user_id: str | None,
    scope: str = "buyer",
    shop_id: str | None = None,
) -> str:
    """
    Resolve buyer language per v1_buildable_spec.md §9 / A27:
    stored user_prefs.language -> shop default (ui_default_buyer_language) -> 'th'.
    """
    if user_id:
        pref = (
            db.query(UserPrefs)
            .filter(UserPrefs.user_id == user_id, UserPrefs.scope == scope)
            .first()
        )
        if pref and pref.language in SUPPORTED_LANGUAGES:
            return pref.language

    shop_default = getattr(settings, "UI_DEFAULT_BUYER_LANGUAGE", DEFAULT_LANGUAGE)
    if shop_default in SUPPORTED_LANGUAGES:
        return shop_default

    return DEFAULT_LANGUAGE


def set_user_language(
    db: Session,
    user_id: str,
    language: str,
    scope: str = "buyer",
    shop_id: str | None = None,
) -> UserPrefs:
    """Update or insert user language preference."""
    target_lang = language.lower() if language.lower() in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    effective_shop_id = shop_id or settings.DEFAULT_SHOP_ID

    pref = (
        db.query(UserPrefs).filter(UserPrefs.user_id == user_id, UserPrefs.scope == scope).first()
    )
    if pref:
        pref.language = target_lang
        if shop_id:
            pref.shop_id = effective_shop_id
    else:
        pref = UserPrefs(
            user_id=user_id,
            scope=scope,
            shop_id=effective_shop_id,
            language=target_lang,
            theme=settings.UI_DEFAULT_THEME,
        )
        db.add(pref)

    db.commit()
    db.refresh(pref)
    return pref
