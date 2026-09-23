import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.address_book import AddressBook
from app.models.order import Order, OrderStatus
from app.services.address_session import (
    clear_address_session,
    create_or_get_address_session,
    get_address_session,
    reset_address_session_for_edit,
)
from app.services.i18n import get_text

logger = logging.getLogger(__name__)

# Required components for a complete delivery address
REQUIRED_FIELDS = [
    "receiver_name",
    "phone",
    "street",
    "subdistrict",
    "district",
    "province",
    "postcode",
]


class AddressParserProtocol(Protocol):
    def parse(self, text: str) -> Any: ...


@dataclass
class ParsedAddress:
    """Normalized representation of parsed address output."""

    receiver_name: str | None = None
    phone: str | None = None
    house_number: str | None = None
    street: str | None = None
    subdistrict: str | None = None
    district: str | None = None
    province: str | None = None
    postcode: str | None = None
    full_address: str | None = None
    confidence: float = 0.0
    warnings: list[str] = field(default_factory=list)
    has_contradiction: bool = False
    contradiction_details: dict[str, str] | None = None

    @property
    def is_complete(self) -> bool:
        return all(bool(getattr(self, f)) for f in REQUIRED_FIELDS)

    @property
    def missing_fields(self) -> list[str]:
        return [f for f in REQUIRED_FIELDS if not getattr(self, f)]


# Global parser instance & geo lookup cache
_PARSER_INSTANCE: Any = None
_ZIPCODE_TO_PROVINCES: dict[str, set[str]] = {}


def set_parser(parser: Any) -> None:
    """Override parser (used for test mocks)."""
    global _PARSER_INSTANCE
    _PARSER_INSTANCE = parser


def get_parser() -> Any:
    """
    Retrieve or lazily initialize the local ThaiSmartAddress parser.
    Runs 100% locally with zero external network or LLM calls.
    """
    global _PARSER_INSTANCE
    if _PARSER_INSTANCE is not None:
        return _PARSER_INSTANCE

    # Attempt to load root ThaiSmartAddress v7.0 parser
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    if str(root_dir) not in sys.path:
        sys.path.insert(0, str(root_dir))

    try:
        from geo_engine import GeoDatabase
        from parser import SmartAddressParser

        csv_path = root_dir / "data" / "thai_address_full.csv"
        geo = GeoDatabase()
        if csv_path.exists():
            geo.load_csv(str(csv_path))
            _load_zipcode_cache(geo)
        _PARSER_INSTANCE = SmartAddressParser(geo)
        logger.info("ThaiSmartAddress local parser initialized successfully")
    except Exception as exc:
        logger.warning("Failed to load root parser, using fallback: %s", exc)
        _PARSER_INSTANCE = _FallbackAddressParser()

    return _PARSER_INSTANCE


def _load_zipcode_cache(geo_db: Any) -> None:
    """Cache mapping from zipcode to valid provinces for fast contradiction checking."""
    global _ZIPCODE_TO_PROVINCES
    if hasattr(geo_db, "_all_records"):
        for record in geo_db._all_records:
            zipcode = getattr(record, "zipcode", "").strip()
            province = getattr(record, "province", "").strip()
            if zipcode and province:
                _ZIPCODE_TO_PROVINCES.setdefault(zipcode, set()).add(province)


def _ensure_zipcode_cache() -> None:
    """Ensure zipcode to province lookup table is populated from canonical CSV."""
    global _ZIPCODE_TO_PROVINCES
    if _ZIPCODE_TO_PROVINCES:
        return
    root_dir = Path(__file__).resolve().parent.parent.parent.parent
    csv_path = root_dir / "data" / "thai_address_full.csv"
    if csv_path.exists():
        import csv

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                z = row.get("zipcode", "").strip()
                p = row.get("province", "").strip()
                if z and p:
                    _ZIPCODE_TO_PROVINCES.setdefault(z, set()).add(p)


def check_contradiction(postcode: str | None, province: str | None) -> dict[str, str] | None:
    """
    Check if a postcode and province contradict each other.
    Returns contradiction dictionary if mismatch, or None if consistent.
    """
    if not postcode or not province:
        return None

    clean_zip = postcode.strip()
    clean_prov = province.strip()

    _ensure_zipcode_cache()
    valid_provinces = _ZIPCODE_TO_PROVINCES.get(clean_zip)
    if valid_provinces:
        matched = any(clean_prov in p or p in clean_prov for p in valid_provinces)
        if not matched:
            return {"postcode": clean_zip, "province": clean_prov}

    return None


class _FallbackAddressParser:
    """Lightweight regex-based fallback parser if root engine is unavailable."""

    def parse(self, text: str) -> dict[str, Any]:
        phone_match = re.search(r"(0[689]\d{8})", text)
        phone = phone_match.group(1) if phone_match else None

        zip_match = re.search(r"(\d{5})", text)
        zipcode = zip_match.group(1) if zip_match else None

        return {
            "receiver": None,
            "phone": phone,
            "address_detail": text,
            "sub_district": None,
            "district": None,
            "province": None,
            "zipcode": zipcode,
            "confidence": 0.5,
            "warnings": ["fallback_parser_used"],
        }


def parse_raw_address(raw_text: str) -> ParsedAddress:
    """
    Parse address text using the configured local parser and return structured ParsedAddress.
    Guarantees no external network transmission.
    """
    parser = get_parser()
    res = parser.parse(raw_text)

    # Handle object or dict return
    if isinstance(res, dict):
        receiver = res.get("receiver") or res.get("receiver_name")
        phone = res.get("phone")
        street = res.get("address_detail") or res.get("street") or res.get("address")
        subdistrict = res.get("sub_district") or res.get("subdistrict")
        district = res.get("district")
        province = res.get("province")
        zipcode = res.get("zipcode") or res.get("postcode")
        confidence = float(res.get("confidence", 0.0))
        warnings = list(res.get("warnings", []))
    else:
        receiver = getattr(res, "receiver", None) or getattr(res, "receiver_name", None)
        phone = getattr(res, "phone", None)
        street = (
            getattr(res, "address_detail", None)
            or getattr(res, "street", None)
            or getattr(res, "address", None)
        )
        subdistrict = getattr(res, "sub_district", None) or getattr(res, "subdistrict", None)
        district = getattr(res, "district", None)
        province = getattr(res, "province", None)
        zipcode = getattr(res, "zipcode", None) or getattr(res, "postcode", None)
        confidence = float(getattr(res, "confidence", 0.0))
        warnings = list(getattr(res, "warnings", []))

    # Extract house number if present in street
    house_number = None
    if street:
        hn_match = re.match(r"^(\d+(?:/\d+)?)(?:\s|$)", street.strip())
        if hn_match:
            house_number = hn_match.group(1)

    # Clean empty strings to None
    def clean(val: str | None) -> str | None:
        if val is None:
            return None
        s = str(val).strip()
        return s if s else None

    receiver = clean(receiver)
    phone = clean(phone)
    street = clean(street)
    subdistrict = clean(subdistrict)
    district = clean(district)
    province = clean(province)
    zipcode = clean(zipcode)

    # Check for contradictions
    contradiction = check_contradiction(zipcode, province)
    has_contradiction = contradiction is not None

    # Construct full address string
    addr_parts = [p for p in (street, subdistrict, district, province, zipcode) if p]
    full_address = " ".join(addr_parts) if addr_parts else None

    parsed = ParsedAddress(
        receiver_name=receiver,
        phone=phone,
        house_number=house_number,
        street=street,
        subdistrict=subdistrict,
        district=district,
        province=province,
        postcode=zipcode,
        full_address=full_address,
        confidence=confidence,
        warnings=warnings,
        has_contradiction=has_contradiction,
        contradiction_details=contradiction,
    )
    # Log metadata only — ZERO PII
    logger.info(
        "Address parsed locally — confidence=%.2f, complete=%s, contradiction=%s, missing=%d",
        parsed.confidence,
        parsed.is_complete,
        parsed.has_contradiction,
        len(parsed.missing_fields),
    )
    return parsed


def format_address_dry_run_summary(
    fields: dict[str, str],
    lang: str = "th",
) -> str:
    """Build the localized dry-run summary message text."""
    receiver = fields.get("receiver_name", "-")
    phone = fields.get("phone", "-")
    addr_parts = [
        fields.get("street"),
        fields.get("subdistrict"),
        fields.get("district"),
        fields.get("province"),
        fields.get("postcode"),
    ]
    addr_str = " ".join([p for p in addr_parts if p]) or fields.get("full_address", "-")

    return get_text(
        "address_dry_run_summary",
        lang,
        name=receiver,
        phone=phone,
        address=addr_str,
    )


def build_dry_run_line_message(
    fields: dict[str, str],
    lang: str = "th",
) -> dict[str, Any]:
    """Construct LINE message with [Correct] and [Edit] quick-action postback buttons."""
    text_content = format_address_dry_run_summary(fields, lang=lang)
    quick_replies = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("btn_address_correct", lang),
                "data": "action=address_confirm",
                "displayText": get_text("btn_address_correct", lang),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("btn_address_edit", lang),
                "data": "action=address_edit",
                "displayText": get_text("btn_address_edit", lang),
            },
        },
    ]
    return {
        "type": "text",
        "text": text_content,
        "quickReply": {"items": quick_replies},
    }


def build_contradiction_line_message(
    postcode: str,
    province: str,
    lang: str = "th",
) -> dict[str, Any]:
    """Construct contradiction disambiguation prompt with choice buttons."""
    prompt_text = get_text(
        "address_contradiction_prompt",
        lang,
        postcode=postcode,
        province=province,
    )
    quick_replies = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("choice_postcode", lang, postcode=postcode),
                "data": f"action=resolve_contradiction&choice=postcode&val={postcode}",
                "displayText": get_text("choice_postcode", lang, postcode=postcode),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("choice_province", lang, province=province),
                "data": f"action=resolve_contradiction&choice=province&val={province}",
                "displayText": get_text("choice_province", lang, province=province),
            },
        },
    ]
    return {
        "type": "text",
        "text": prompt_text,
        "quickReply": {"items": quick_replies},
    }


def get_active_order_for_address(db: Session, line_user_id: str) -> Order | None:
    """Retrieve the order awaiting address collection or confirmed."""
    stmt = (
        select(Order)
        .where(
            Order.line_user_id == line_user_id,
            Order.status.in_(
                [
                    OrderStatus.ORDER_CONFIRMED.value,
                    OrderStatus.ADDRESS_COLLECTION.value,
                ]
            ),
        )
        .order_by(Order.created_at.desc())
    )
    return db.execute(stmt).scalars().first()


def process_address_input(
    db: Session,
    user_id: str,
    text: str,
    lang: str = "th",
    shop_id: str | None = None,
) -> list[dict[str, Any]]:
    """
    Main slot-filling entry point for free-text address inputs and responses:
    1. Tracks fields collected across multiple messages.
    2. Handles missing fields one at a time.
    3. Handles contradictions with disambiguation prompt.
    4. Triggers dry run when complete.
    """
    order = get_active_order_for_address(db, user_id)
    order_id = order.id if order else None

    # Transition order state from ORDER_CONFIRMED to ADDRESS_COLLECTION
    if order and order.status == OrderStatus.ORDER_CONFIRMED.value:
        order.status = OrderStatus.ADDRESS_COLLECTION.value
        db.commit()
        db.refresh(order)

    session = create_or_get_address_session(user_id, order_id=order_id)

    # 1. User is replying to a contradiction prompt via text
    if session.status == "CONTRADICTION" and session.contradiction_data:
        contra = session.contradiction_data
        postcode_val = contra.get("postcode", "")
        province_val = contra.get("province", "")
        clean_input = text.strip()
        if postcode_val and postcode_val in clean_input:
            return resolve_address_contradiction(
                db, user_id, choice="postcode", value=postcode_val, lang=lang
            )
        if province_val and province_val in clean_input:
            return resolve_address_contradiction(
                db, user_id, choice="province", value=province_val, lang=lang
            )
        # Re-send contradiction prompt
        return [build_contradiction_line_message(postcode_val, province_val, lang=lang)]

    # 2. User is providing input for a specific pending missing field
    if session.pending_field:
        field_name = session.pending_field
        clean_text = text.strip()

        # Specific extraction/validation for field types
        if field_name == "phone":
            phone_match = re.search(r"\b(0[689]\d{8})\b", clean_text)
            field_val = phone_match.group(1) if phone_match else clean_text
        elif field_name == "postcode":
            zip_match = re.search(r"\b(\d{5})\b", clean_text)
            field_val = zip_match.group(1) if zip_match else clean_text
        else:
            field_val = clean_text

        session.collected_fields[field_name] = field_val
        session.pending_field = None

        # Also attempt to parse text to fill any other remaining gaps simultaneously
        if len(clean_text.split()) > 1:
            multi_parsed = parse_raw_address(clean_text)
            for f in REQUIRED_FIELDS:
                if not session.collected_fields.get(f) and getattr(multi_parsed, f, None):
                    session.collected_fields[f] = getattr(multi_parsed, f)

        # Check contradiction between postcode and province
        contra_check = check_contradiction(
            session.collected_fields.get("postcode"),
            session.collected_fields.get("province"),
        )
        if contra_check:
            session.status = "CONTRADICTION"
            session.contradiction_data = contra_check
            return [
                build_contradiction_line_message(
                    contra_check["postcode"], contra_check["province"], lang=lang
                )
            ]

        # Check for remaining missing fields
        for f in REQUIRED_FIELDS:
            if not session.collected_fields.get(f):
                session.pending_field = f
                session.status = "COLLECTING"
                return [{"type": "text", "text": get_text(f"enter_missing_{f}", lang)}]

        # All fields complete!
        session.status = "DRY_RUN"
        session.pending_field = None
        return [build_dry_run_line_message(session.collected_fields, lang=lang)]

    # 3. Fresh address input: parse through ThaiSmartAddress
    parsed = parse_raw_address(text)

    # Populate session with parsed tokens
    for f in REQUIRED_FIELDS:
        val = getattr(parsed, f, None)
        if val:
            session.collected_fields[f] = val

    if parsed.house_number:
        session.collected_fields["house_number"] = parsed.house_number
    if parsed.full_address:
        session.collected_fields["full_address"] = parsed.full_address

    # Contradiction gate
    if parsed.has_contradiction and parsed.contradiction_details:
        session.status = "CONTRADICTION"
        session.contradiction_data = parsed.contradiction_details
        contra = parsed.contradiction_details
        return [build_contradiction_line_message(contra["postcode"], contra["province"], lang=lang)]

    # High-confidence & complete address: skip slot-filling directly to dry-run
    if parsed.is_complete and parsed.confidence >= 0.8:
        session.status = "DRY_RUN"
        session.pending_field = None
        return [build_dry_run_line_message(session.collected_fields, lang=lang)]

    # Incomplete: prompt for the first missing field
    for f in REQUIRED_FIELDS:
        if not session.collected_fields.get(f):
            session.pending_field = f
            session.status = "COLLECTING"
            return [{"type": "text", "text": get_text(f"enter_missing_{f}", lang)}]

    # Fallback to dry run
    session.status = "DRY_RUN"
    session.pending_field = None
    return [build_dry_run_line_message(session.collected_fields, lang=lang)]


def resolve_address_contradiction(
    db: Session,
    user_id: str,
    choice: str,
    value: str | None = None,
    lang: str = "th",
) -> list[dict[str, Any]]:
    """Resolve postcode vs province contradiction according to buyer selection."""
    session = create_or_get_address_session(user_id)
    session.status = "COLLECTING"
    contra = session.contradiction_data or {}
    session.contradiction_data = None

    if choice == "postcode":
        postcode_val = value or contra.get("postcode")
        if postcode_val:
            session.collected_fields["postcode"] = postcode_val
            # Update province to valid matching province from geo db if available
            _ensure_zipcode_cache()
            valid_provs = _ZIPCODE_TO_PROVINCES.get(postcode_val)
            if valid_provs:
                session.collected_fields["province"] = sorted(valid_provs)[0]

        # Check if other fields missing
        for f in REQUIRED_FIELDS:
            if not session.collected_fields.get(f):
                session.pending_field = f
                return [{"type": "text", "text": get_text(f"enter_missing_{f}", lang)}]

        session.status = "DRY_RUN"
        session.pending_field = None
        return [build_dry_run_line_message(session.collected_fields, lang=lang)]

    elif choice == "province":
        province_val = value or contra.get("province")
        if province_val:
            session.collected_fields["province"] = province_val
        # Clear the conflicting postcode
        session.collected_fields.pop("postcode", None)
        session.pending_field = "postcode"
        return [{"type": "text", "text": get_text("enter_missing_postcode", lang)}]

    return [{"type": "text", "text": get_text("enter_address_prompt", lang)}]


def confirm_address_and_save(
    db: Session,
    user_id: str,
    lang: str = "th",
    shop_id: str | None = None,
) -> tuple[AddressBook | None, Order | None, list[dict[str, Any]]]:
    """
    Confirm address dry-run ([Correct] button):
    1. Builds structured address_json.
    2. Saves to address_book table.
    3. Transitions order: ADDRESS_COLLECTION -> ADDRESS_CONFIRMED.
    4. Clears address session.
    5. Replies with address_confirmed message.
    """
    session = get_address_session(user_id)
    collected = dict(session.collected_fields) if session else {}

    order = get_active_order_for_address(db, user_id)
    if not order:
        # Fallback search for any recent confirmed/collection order
        stmt = select(Order).where(Order.line_user_id == user_id).order_by(Order.created_at.desc())
        order = db.execute(stmt).scalars().first()

    receiver_name = collected.get("receiver_name", "")
    phone = collected.get("phone", "")
    house_number = collected.get("house_number")
    street = collected.get("street", "")
    subdistrict = collected.get("subdistrict", "")
    district = collected.get("district", "")
    province = collected.get("province", "")
    postcode = collected.get("postcode", "")

    addr_parts = [p for p in (street, subdistrict, district, province, postcode) if p]
    full_address = collected.get("full_address") or (" ".join(addr_parts) if addr_parts else "")

    address_json = {
        "receiver_name": receiver_name,
        "phone": phone,
        "house_number": house_number,
        "street": street,
        "subdistrict": subdistrict,
        "district": district,
        "province": province,
        "postcode": postcode,
        "full_address": full_address,
    }

    # Save to address book
    entry = AddressBook(
        shop_id=shop_id or (order.shop_id if order else settings.DEFAULT_SHOP_ID),
        line_user_id=user_id,
        label=None,
        receiver_name=receiver_name or "Customer",
        phone=phone or "0000000000",
        address_json=address_json,
        is_default=True,
    )
    db.add(entry)

    # Transition order state: ADDRESS_COLLECTION -> ADDRESS_CONFIRMED
    if order:
        order.status = OrderStatus.ADDRESS_CONFIRMED.value

    db.commit()
    if order:
        db.refresh(order)
    db.refresh(entry)

    # Clear address session
    clear_address_session(user_id)

    reply_msgs = [{"type": "text", "text": get_text("address_confirmed", lang)}]
    return entry, order, reply_msgs


def handle_address_edit(
    db: Session,
    user_id: str,
    lang: str = "th",
) -> list[dict[str, Any]]:
    """
    Handle [Edit] button:
    1. Loops in ADDRESS_COLLECTION state.
    2. Resets address slot-filling for this address only.
    3. Preserves draft order and order items.
    4. Replies with restart prompt.
    """
    order = get_active_order_for_address(db, user_id)
    if order and order.status == OrderStatus.ORDER_CONFIRMED.value:
        order.status = OrderStatus.ADDRESS_COLLECTION.value
        db.commit()

    reset_address_session_for_edit(user_id)
    return [{"type": "text", "text": get_text("address_edit_restart", lang)}]


def handle_use_saved_address(
    db: Session,
    user_id: str,
    address_id: int | None = None,
    lang: str = "th",
) -> list[dict[str, Any]]:
    """
    Returning buyer chooses to use a saved address:
    Skips slot-filling and displays dry-run summary directly.
    """
    order = get_active_order_for_address(db, user_id)
    if order and order.status == OrderStatus.ORDER_CONFIRMED.value:
        order.status = OrderStatus.ADDRESS_COLLECTION.value
        db.commit()

    stmt = select(AddressBook).where(AddressBook.line_user_id == user_id)
    if address_id:
        stmt = stmt.where(AddressBook.id == address_id)
    else:
        stmt = stmt.order_by(AddressBook.is_default.desc(), AddressBook.created_at.desc())

    saved = db.execute(stmt).scalars().first()
    if not saved:
        return [{"type": "text", "text": get_text("enter_address_prompt", lang)}]

    session = create_or_get_address_session(user_id, order_id=order.id if order else None)
    session.status = "DRY_RUN"
    session.collected_fields = dict(saved.address_json)
    session.saved_address_id = saved.id
    session.pending_field = None

    return [build_dry_run_line_message(session.collected_fields, lang=lang)]


def get_saved_address_choice_message(
    db: Session,
    user_id: str,
    lang: str = "th",
) -> dict[str, Any] | None:
    """
    Check if buyer has saved addresses in address_book.
    If so, returns saved_address_prompt with [Use Saved Address] and [Enter New Address] quick replies.
    """
    if not settings.ADDRESS_BOOK_ENABLED:
        return None

    stmt = (
        select(AddressBook)
        .where(AddressBook.line_user_id == user_id)
        .order_by(AddressBook.is_default.desc(), AddressBook.created_at.desc())
    )
    saved = db.execute(stmt).scalars().first()
    if not saved:
        return None

    prompt_text = get_text("saved_address_prompt", lang)
    quick_replies = [
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("use_saved_address", lang),
                "data": f"action=use_saved_address&address_id={saved.id}",
                "displayText": get_text("use_saved_address", lang),
            },
        },
        {
            "type": "action",
            "action": {
                "type": "postback",
                "label": get_text("enter_new_address", lang),
                "data": "action=enter_new_address",
                "displayText": get_text("enter_new_address", lang),
            },
        },
    ]
    return {
        "type": "text",
        "text": prompt_text,
        "quickReply": {"items": quick_replies},
    }
