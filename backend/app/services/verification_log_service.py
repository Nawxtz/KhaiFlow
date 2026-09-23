from typing import Any

from sqlalchemy.orm import Session

from app.models.verification_log import VerificationLog


def log_verification(
    order_id: str,
    slip_hash: str | None,
    risk_score: int,
    result: str,
    db: Session,
    shop_id: str | None = None,
    channel: str = "slip",
    checks_json: dict[str, Any] | None = None,
    decision: str | None = None,
) -> VerificationLog:
    """
    Writes a record to the verification_logs table.
    CRITICAL RULE (Gate 1 Short-Circuit): This function MUST ONLY be called
    AFTER Gate 1 Filter C checks pass. It is NEVER called on Gate 1 failure.
    """
    log_entry = VerificationLog(
        shop_id=shop_id,
        order_id=order_id,
        slip_hash=slip_hash,
        channel=channel,
        checks_json=checks_json,
        risk_score=risk_score,
        decision=decision or result,
        result=result,
    )
    db.add(log_entry)
    db.commit()
    db.refresh(log_entry)
    return log_entry
