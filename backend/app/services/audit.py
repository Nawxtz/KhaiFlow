from typing import Any

from sqlalchemy.orm import Session

from app.models.audit import AuditLog


def record_audit(
    db: Session,
    actor_user_id: int | None,
    action: str,
    entity: str,
    entity_id: str,
    old_value: dict[str, Any] | None,
    new_value: dict[str, Any] | None,
    shop_id: str | None = None,
) -> None:
    """Add an audit row to the caller's transaction, so it commits with the change itself.

    Values must never hold personal data such as names, phone numbers or addresses.
    """
    db.add(
        AuditLog(
            shop_id=shop_id,
            actor_user_id=actor_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            old_value=old_value,
            new_value=new_value,
        )
    )
