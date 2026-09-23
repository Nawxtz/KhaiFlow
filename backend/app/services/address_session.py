import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class AddressSession:
    """Transient address collection state per LINE user."""

    line_user_id: str
    order_id: str | None = None
    status: str = "IDLE"  # IDLE, COLLECTING, CONTRADICTION, DRY_RUN, CONFIRMED
    collected_fields: dict[str, str] = field(default_factory=dict)
    pending_field: str | None = None
    contradiction_data: dict[str, str] | None = None
    saved_address_id: int | None = None

    def reset_for_edit(self) -> None:
        """Reset address fields while preserving order and user context."""
        self.status = "COLLECTING"
        self.collected_fields = {}
        self.pending_field = None
        self.contradiction_data = None
        self.saved_address_id = None


# In-memory session store keyed by line_user_id
_USER_ADDRESS_SESSIONS: dict[str, AddressSession] = {}


def get_address_session(line_user_id: str) -> AddressSession | None:
    """Retrieve the active address session for a user."""
    return _USER_ADDRESS_SESSIONS.get(line_user_id)


def create_or_get_address_session(
    line_user_id: str,
    order_id: str | None = None,
) -> AddressSession:
    """Get existing session or initialize a new one."""
    session = _USER_ADDRESS_SESSIONS.get(line_user_id)
    if session is None:
        session = AddressSession(line_user_id=line_user_id, order_id=order_id)
        _USER_ADDRESS_SESSIONS[line_user_id] = session
    elif order_id is not None:
        session.order_id = order_id
    return session


def update_address_session(
    line_user_id: str,
    **kwargs: Any,
) -> AddressSession:
    """Update session attributes."""
    session = create_or_get_address_session(line_user_id)
    for k, v in kwargs.items():
        if hasattr(session, k):
            setattr(session, k, v)
    return session


def reset_address_session_for_edit(line_user_id: str) -> AddressSession | None:
    """
    Reset slot-filling state for the current address only.
    Preserves draft order context and items.
    """
    session = _USER_ADDRESS_SESSIONS.get(line_user_id)
    if session:
        session.reset_for_edit()
    return session


def clear_address_session(line_user_id: str) -> None:
    """Remove address session for a user upon confirmation or cancel."""
    _USER_ADDRESS_SESSIONS.pop(line_user_id, None)


def clear_all_address_sessions() -> None:
    """Clear all in-memory address sessions (useful in tests)."""
    _USER_ADDRESS_SESSIONS.clear()
