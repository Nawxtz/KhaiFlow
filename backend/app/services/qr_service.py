import hashlib
import hmac
from decimal import Decimal
from typing import Any

from app.core.config import settings


class QRSigningError(Exception):
    """Base exception for QR signing and verification."""

    pass


class MissingQRSecretError(QRSigningError):
    """Raised when PAYMENT_QR_SECRET is empty or unconfigured."""

    pass


def format_total(total: Decimal | float | str) -> str:
    """Format total amount to 2 decimal places string."""
    try:
        dec = Decimal(str(total))
        return f"{dec:.2f}"
    except Exception as exc:
        raise ValueError(f"Invalid monetary total: {total}") from exc


def build_canonical_payload(
    order_id: str,
    total: Decimal | float | str,
    currency: str = "THB",
    shop_account: str = "default_account",
) -> str:
    """
    Construct canonical QR payload string:
    order_id + total + currency + shop_account
    per v1_buildable_spec.md §13 and Phase 6 requirements.
    """
    total_str = format_total(total)
    return f"{order_id}|{total_str}|{currency}|{shop_account}"


def compute_hmac_sha256(payload: str, secret: str) -> str:
    """Compute HMAC-SHA256 signature for payload string using specified secret."""
    return hmac.new(
        secret.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def generate_signed_payment_qr(
    order_id: str,
    total: Decimal | float | str,
    currency: str = "THB",
    shop_account: str = "default_account",
    secret: str | None = None,
) -> dict[str, Any]:
    """
    Generate a per-order, fixed-amount payment QR payload signed with HMAC-SHA256.
    Signing secret is retrieved from settings.PAYMENT_QR_SECRET (never hardcoded).
    """
    signing_secret = secret if secret is not None else settings.PAYMENT_QR_SECRET
    if not signing_secret:
        raise MissingQRSecretError(
            "PAYMENT_QR_SECRET is not configured. Secret must be loaded from settings / environment."
        )

    canonical_payload = build_canonical_payload(
        order_id=order_id,
        total=total,
        currency=currency,
        shop_account=shop_account,
    )
    signature = compute_hmac_sha256(canonical_payload, signing_secret)
    qr_data = f"THAI_SMART_PAY|{canonical_payload}|SIG={signature}"

    return {
        "order_id": order_id,
        "total": format_total(total),
        "currency": currency,
        "shop_account": shop_account,
        "payload": canonical_payload,
        "signature": signature,
        "qr_data": qr_data,
    }


def verify_payment_qr(
    order_id: str,
    total: Decimal | float | str,
    currency: str,
    shop_account: str,
    signature: str,
    secret: str | None = None,
) -> bool:
    """
    Verify payment QR payload components against provided signature using HMAC-SHA256.
    Uses hmac.compare_digest to prevent timing analysis attacks.
    """
    signing_secret = secret if secret is not None else settings.PAYMENT_QR_SECRET
    if not signing_secret:
        raise MissingQRSecretError("PAYMENT_QR_SECRET is not configured in settings.")

    try:
        canonical_payload = build_canonical_payload(
            order_id=order_id,
            total=total,
            currency=currency,
            shop_account=shop_account,
        )
    except ValueError:
        return False

    expected_signature = compute_hmac_sha256(canonical_payload, signing_secret)
    return hmac.compare_digest(expected_signature, signature)


def verify_qr_data_string(qr_data: str, secret: str | None = None) -> bool:
    """
    Parse and verify a full formatted QR data string (e.g. THAI_SMART_PAY|...|SIG=...).
    Returns True if valid and untampered, False otherwise.
    """
    if not qr_data or not qr_data.startswith("THAI_SMART_PAY|"):
        return False

    parts = qr_data.split("|")
    if len(parts) < 6:
        # Expected: ['THAI_SMART_PAY', order_id, total, currency, shop_account, 'SIG=...']
        return False

    sig_part = parts[-1]
    if not sig_part.startswith("SIG="):
        return False
    signature = sig_part[4:]

    order_id = parts[1]
    total = parts[2]
    currency = parts[3]
    shop_account = parts[4]

    return verify_payment_qr(
        order_id=order_id,
        total=total,
        currency=currency,
        shop_account=shop_account,
        signature=signature,
        secret=secret,
    )
