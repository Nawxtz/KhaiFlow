import hashlib
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.address_book import AddressBook
from app.models.order import Order
from app.models.pdpa import PDPADeletion
from app.models.user_prefs import UserPrefs
from app.services.i18n import get_text

logger = logging.getLogger(__name__)


def get_current_time(now_fn: Callable[[], datetime] | None = None) -> datetime:
    """Helper to return current UTC time or injected test clock."""
    if now_fn:
        return now_fn()
    return datetime.now(UTC)


def hash_user_id(line_user_id: str) -> str:
    """Hash line_user_id using SHA-256 for PDPA audit-compliant anonymization."""
    return hashlib.sha256(line_user_id.encode("utf-8")).hexdigest()


def has_pdpa_consent(
    db: Session,
    line_user_id: str,
    shop_id: str | None = None,
) -> bool:
    """
    Check if user has given valid, active PDPA consent.
    If consent_required is disabled in configuration, consent is implicitly granted.
    """
    if not settings.CONSENT_REQUIRED:
        return True

    stmt = select(UserPrefs).where(
        UserPrefs.user_id == line_user_id,
        UserPrefs.scope == "buyer",
    )
    pref = db.execute(stmt).scalars().first()
    return bool(pref and pref.pdpa_consent)


def record_pdpa_consent(
    db: Session,
    line_user_id: str,
    consent: bool,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> UserPrefs:
    """
    Persist or update PDPA consent decision in user_prefs.
    """
    now_dt = get_current_time(now_fn)

    stmt = select(UserPrefs).where(
        UserPrefs.user_id == line_user_id,
        UserPrefs.scope == "buyer",
    )
    pref = db.execute(stmt).scalars().first()
    if pref:
        pref.pdpa_consent = consent
        pref.pdpa_consent_at = now_dt if consent else None
        pref.updated_at = now_dt
        if shop_id and not pref.shop_id:
            pref.shop_id = shop_id
    else:
        pref = UserPrefs(
            user_id=line_user_id,
            scope="buyer",
            shop_id=shop_id,
            language=settings.UI_DEFAULT_BUYER_LANGUAGE,
            theme=settings.UI_DEFAULT_THEME,
            pdpa_consent=consent,
            pdpa_consent_at=now_dt if consent else None,
            updated_at=now_dt,
        )
        db.add(pref)

    db.commit()
    db.refresh(pref)
    return pref


def execute_pdpa_deletion(
    db: Session,
    line_user_id: str,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> dict[str, Any]:
    """
    Right-to-delete implementation per v1_buildable_spec.md §14 and reference_schema.md:
    1. Wipes all rows from address_book for this user.
    2. Anonymizes orders.line_user_id with SHA-256 hash (preserves financial ledger rows).
    3. Deletes user_prefs for this user (revoking consent and clearing preferences).
    4. Logs deletion event into pdpa_deletions table.
    5. After deletion, the user can start fresh.
    """
    now_dt = get_current_time(now_fn)
    anon_id = hash_user_id(line_user_id)

    # 1. Wipe address_book entries for this user
    addr_stmt = select(AddressBook).where(AddressBook.line_user_id == line_user_id)
    addresses = list(db.execute(addr_stmt).scalars().all())
    address_count = len(addresses)
    for addr in addresses:
        db.delete(addr)

    # 2. Anonymize orders (do NOT delete order rows — financial ledger preserved)
    orders_stmt = select(Order).where(Order.line_user_id == line_user_id)
    orders = list(db.execute(orders_stmt).scalars().all())
    order_count = len(orders)
    for order in orders:
        order.line_user_id = anon_id

    # 3. Delete user preferences (clears language/theme and revokes consent)
    prefs_stmt = select(UserPrefs).where(UserPrefs.user_id == line_user_id)
    prefs = list(db.execute(prefs_stmt).scalars().all())
    for pref in prefs:
        db.delete(pref)

    # 4. Log deletion in pdpa_deletions table
    log_entry = PDPADeletion(
        shop_id=shop_id,
        line_user_id=line_user_id,
        requested_at=now_dt,
        completed_at=now_dt,
    )
    db.add(log_entry)

    db.commit()

    logger.info(
        "PDPA deletion completed for user (anonymized to %s...): %d addresses wiped, %d orders anonymized",
        anon_id[:12],
        address_count,
        order_count,
    )

    return {
        "line_user_id": line_user_id,
        "anonymized_user_id": anon_id,
        "addresses_deleted": address_count,
        "orders_anonymized": order_count,
    }


def run_pdpa_retention_job(
    db: Session,
    retention_months: int | None = None,
    shop_id: str | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> list[str]:
    """
    Automated retention policy job:
    1. Computes cutoff time based on retention_months (reads from settings dynamically).
    2. Identifies users whose records are older than cutoff and who have placed no recent orders.
    3. Uses SELECT ... FOR UPDATE SKIP LOCKED for multi-worker concurrency safety.
    4. Executes PDPA deletion / anonymization on eligible users.
    Returns list of deleted/anonymized line_user_ids.
    """
    now_dt = get_current_time(now_fn)
    months = retention_months if retention_months is not None else settings.RETENTION_MONTHS
    cutoff = now_dt - timedelta(days=months * 30)

    # Gather candidate users from address_book and user_prefs older than cutoff
    # Using FOR UPDATE SKIP LOCKED on address_book
    addr_stmt = (
        select(AddressBook)
        .where(AddressBook.created_at < cutoff)
        .with_for_update(skip_locked=True)
    )
    if shop_id:
        addr_stmt = addr_stmt.where(AddressBook.shop_id == shop_id)

    stale_addrs = list(db.execute(addr_stmt).scalars().all())

    # Using FOR UPDATE SKIP LOCKED on user_prefs
    prefs_stmt = (
        select(UserPrefs)
        .where(UserPrefs.updated_at < cutoff)
        .with_for_update(skip_locked=True)
    )
    if shop_id:
        prefs_stmt = prefs_stmt.where(UserPrefs.shop_id == shop_id)

    stale_prefs = list(db.execute(prefs_stmt).scalars().all())

    candidate_user_ids = {a.line_user_id for a in stale_addrs} | {
        p.user_id for p in stale_prefs if p.scope == "buyer"
    }

    # Also check orders older than cutoff where user is not yet anonymized
    orders_stmt = (
        select(Order)
        .where(
            Order.created_at < cutoff,
            ~Order.line_user_id.startswith("ANON_"),
        )
        .with_for_update(skip_locked=True)
    )
    if shop_id:
        orders_stmt = orders_stmt.where(Order.shop_id == shop_id)
    stale_orders = list(db.execute(orders_stmt).scalars().all())
    for o in stale_orders:
        # Check if line_user_id is already a SHA-256 hash (64 hex characters)
        if len(o.line_user_id) != 64:
            candidate_user_ids.add(o.line_user_id)

    deleted_user_ids: list[str] = []

    for user_id in candidate_user_ids:
        # Check if this user has any active/recent orders placed within retention period
        recent_order_stmt = select(Order).where(
            Order.line_user_id == user_id,
            Order.created_at >= cutoff,
        )
        recent_order = db.execute(recent_order_stmt).scalars().first()
        if recent_order:
            # User is active; do not delete
            continue

        # Eligible for deletion
        execute_pdpa_deletion(db, line_user_id=user_id, shop_id=shop_id, now_fn=now_fn)
        deleted_user_ids.append(user_id)

    return deleted_user_ids


def build_consent_prompt_message(lang: str = "th") -> dict[str, Any]:
    """
    Build LINE consent prompt message with Accept and Decline postback buttons.
    """
    return {
        "type": "text",
        "text": get_text("pdpa_consent_prompt", lang),
        "quickReply": {
            "items": [
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": get_text("btn_pdpa_accept", lang),
                        "data": "action=pdpa_consent_accept",
                        "displayText": get_text("btn_pdpa_accept", lang),
                    },
                },
                {
                    "type": "action",
                    "action": {
                        "type": "postback",
                        "label": get_text("btn_pdpa_decline", lang),
                        "data": "action=pdpa_consent_decline",
                        "displayText": get_text("btn_pdpa_decline", lang),
                    },
                },
            ]
        },
    }
