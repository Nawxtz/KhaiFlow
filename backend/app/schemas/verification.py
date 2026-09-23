from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class SlipVerificationRequest(BaseModel):
    """Payload for submitting payment slip for Gate 1 verification."""

    model_config = ConfigDict(extra="forbid")

    order_id: str = Field(..., description="Order ID to verify slip against")
    slip_data: dict[str, Any] = Field(..., description="Slip QR data, tags, or fields")
    slip_hash: str | None = Field(default=None, description="SHA-256 hash of slip image")
    shop_id: str | None = Field(default=None, description="Shop tenancy identifier")


class SlipVerificationResponse(BaseModel):
    """Response returned after Gate 1 verification and claim processing."""

    passed: bool
    reason: str
    risk_score: int = 0
    order_id: str | None = None
    claim_key: str | None = None
    approval_state: str | None = None
    amount: Decimal | None = None


class ManualApprovalRequest(BaseModel):
    """Payload for Option B seller manual approval."""

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(..., description="ID or username of the reviewer/seller")


class ManualRejectRequest(BaseModel):
    """Payload for Option B seller manual rejection."""

    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(..., description="ID or username of the reviewer/seller")
    reason: str = Field(..., description="Rejection reason")


class ManualActionResponse(BaseModel):
    """Response returned after manual approval or rejection."""

    status: str
    order_id: str
    order_status: str
    approval_state: str | None = None
    message: str | None = None
