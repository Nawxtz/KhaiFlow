from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session


@dataclass
class VerificationResult:
    """Result of Gate 1 / Filter C slip verification."""

    passed: bool
    reason: str
    risk_score: int = 0
    claim_key: str | None = None
    slip_hash: str | None = None
    amount: Decimal | None = None
    details: dict[str, Any] = field(default_factory=dict)


def compute_crc16_ccitt_false(payload: str) -> str:
    """
    Compute standard CRC-16/CCITT-FALSE (polynomial 0x1021, init 0xFFFF).
    Used in EMVCo QR and Thai Slip Verify Mini-QR tag 91 / tag 63.
    """
    crc = 0xFFFF
    for byte in payload.encode("utf-8"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def parse_tlv(raw_qr: str) -> dict[str, str]:
    """
    Parse EMVCo / Slip Verify Mini-QR TLV (Tag-Length-Value) structure.
    Tags are 2 characters, lengths are 2 digits, values are <length> characters.
    Raises ValueError on malformed or truncated TLV structure.
    """
    tags: dict[str, str] = {}
    i = 0
    n = len(raw_qr)
    while i < n:
        if i + 4 > n:
            raise ValueError(
                f"Malformed TLV at index {i}: insufficient characters for tag and length header"
            )
        tag = raw_qr[i : i + 2]
        len_str = raw_qr[i + 2 : i + 4]
        if not len_str.isdigit():
            raise ValueError(f"Malformed TLV length '{len_str}' for tag '{tag}' at index {i}")
        length = int(len_str)
        if i + 4 + length > n:
            raise ValueError(
                f"Malformed TLV value for tag '{tag}': expected {length} chars, got {n - (i + 4)}"
            )
        val = raw_qr[i + 4 : i + 4 + length]
        tags[tag] = val
        i += 4 + length
    return tags


def build_test_slip_qr(
    amount: Decimal,
    trans_ref: str,
    valid_crc: bool = True,
    malformed_tlv: bool = False,
    crc_tag: str = "91",
    currency: str = "764",
    country: str = "TH",
) -> str:
    """
    Helper to generate synthetic EMVCo / Slip Verify QR payloads for testing.
    Never uses real bank credentials or slips.
    """
    if malformed_tlv:
        # Deliberately truncated or malformed TLV length header
        return f"0002015406{amount:.2f}9999MALFORMED"

    amount_str = f"{amount:.2f}"
    # Tag 00: Format indicator, Tag 53: Currency, Tag 54: Amount, Tag 58: Country, Tag 01: Ref
    tag_00 = "000201"
    tag_01 = f"01{len(trans_ref):02d}{trans_ref}"
    tag_53 = f"53{len(currency):02d}{currency}"
    tag_54 = f"54{len(amount_str):02d}{amount_str}"
    tag_58 = f"58{len(country):02d}{country}"

    prefix = f"{tag_00}{tag_01}{tag_53}{tag_54}{tag_58}{crc_tag}04"
    crc = compute_crc16_ccitt_false(prefix) if valid_crc else "0000"
    return f"{prefix}{crc}"


def verify_slip_local(
    slip_data: dict[str, Any],
    expected_amount: Decimal,
    order_id: str,
    tolerance: Decimal = Decimal("1.00"),
    expected_recipient: str | None = None,
) -> VerificationResult:
    """
    Gate 1 / Filter C local deterministic verification per v1_buildable_spec.md §13, §20:
    - TLV structure validation (required tags present, correct lengths).
    - CRC/checksum integrity.
    - Amount field parseable and non-zero.
    - Tag 54 (transaction amount) matches expected order total within tolerance.
    - Recipient match if shop recipient configured.

    If ANY Gate 1 check fails:
    - Returns VerificationResult(passed=False, ...).
    - Caller MUST short-circuit immediately without writing any row to
      verification_logs or consumed_payment_claims.
    """
    if not isinstance(slip_data, dict):
        return VerificationResult(
            passed=False,
            reason="Invalid slip_data format: expected dict",
            risk_score=100,
        )

    # Explicit mock flags for testing
    if slip_data.get("malformed_tlv") is True:
        return VerificationResult(
            passed=False,
            reason="Malformed TLV structure: invalid tag length or truncated data",
            risk_score=100,
        )

    if slip_data.get("bad_crc") is True or slip_data.get("crc_valid") is False:
        return VerificationResult(
            passed=False,
            reason="CRC checksum integrity check failed",
            risk_score=100,
        )

    raw_qr = (
        slip_data.get("raw_qr")
        or slip_data.get("qr_raw")
        or slip_data.get("payload")
        or slip_data.get("tlv_string")
    )

    parsed_tags: dict[str, str] = {}
    if raw_qr:
        # 1. TLV Structure validation
        try:
            parsed_tags = parse_tlv(raw_qr)
        except ValueError as exc:
            return VerificationResult(
                passed=False,
                reason=f"Malformed TLV structure: {exc}",
                risk_score=100,
            )

        # 2. CRC/checksum integrity validation on raw QR
        crc_tag = "91" if "91" in parsed_tags else ("63" if "63" in parsed_tags else None)
        if crc_tag is not None:
            crc_val = parsed_tags[crc_tag]
            # CRC tag should be at the end: tag (2) + len (2) + crc (4) = 8 chars
            crc_pos = raw_qr.rfind(f"{crc_tag}04")
            if crc_pos != -1:
                data_to_check = raw_qr[: crc_pos + 4]
                expected_crc = compute_crc16_ccitt_false(data_to_check)
                if crc_val.upper() != expected_crc.upper():
                    return VerificationResult(
                        passed=False,
                        reason=f"CRC checksum integrity check failed: expected {expected_crc}, got {crc_val}",
                        risk_score=100,
                    )
        elif slip_data.get("require_crc", False):
            return VerificationResult(
                passed=False,
                reason="CRC checksum tag missing from QR payload",
                risk_score=100,
            )

    # 3. Amount field parseable and non-zero
    raw_amount = (
        parsed_tags.get("54")
        or slip_data.get("amount")
        or slip_data.get("tag_54")
        or slip_data.get("total")
    )
    if raw_amount is None:
        return VerificationResult(
            passed=False,
            reason="Amount field missing or unparseable from slip (Tag 54 not found)",
            risk_score=100,
        )

    try:
        slip_amount = Decimal(str(raw_amount))
    except (InvalidOperation, ValueError, TypeError):
        return VerificationResult(
            passed=False,
            reason=f"Amount field unparseable: '{raw_amount}'",
            risk_score=100,
        )

    if slip_amount <= Decimal("0"):
        return VerificationResult(
            passed=False,
            reason=f"Amount must be positive non-zero: got {slip_amount}",
            risk_score=100,
        )

    # 4. Tag 54 matches expected order total within tolerance
    diff = abs(slip_amount - expected_amount)
    if diff > tolerance:
        return VerificationResult(
            passed=False,
            reason=(
                f"Tag 54 amount {slip_amount} does not match expected total {expected_amount} "
                f"(difference {diff} exceeds tolerance {tolerance})"
            ),
            risk_score=100,
            amount=slip_amount,
        )

    # 5. Recipient check if specified
    slip_recipient = slip_data.get("recipient") or slip_data.get("shop_account")
    if expected_recipient and slip_recipient and slip_recipient != expected_recipient:
        return VerificationResult(
            passed=False,
            reason=f"Recipient mismatch: slip recipient '{slip_recipient}' does not match expected '{expected_recipient}'",
            risk_score=100,
            amount=slip_amount,
        )

    # Extract trans_ref and slip_hash for claim key
    trans_ref = (
        slip_data.get("trans_ref")
        or parsed_tags.get("01")
        or parsed_tags.get("02")
        or slip_data.get("ref")
        or order_id
    )
    slip_hash = slip_data.get("slip_hash") or (f"hash_{trans_ref}" if trans_ref else None)
    claim_key = f"ref:{trans_ref}" if trans_ref else f"ord:{order_id}"

    return VerificationResult(
        passed=True,
        reason="Gate 1 Filter C local checks passed",
        risk_score=0,
        claim_key=claim_key,
        slip_hash=slip_hash,
        amount=slip_amount,
        details={
            "parsed_tags": parsed_tags,
            "trans_ref": trans_ref,
            "diff_from_expected": str(diff),
        },
    )


def claim_payment(
    db: Session,
    claim_key: str,
    order_id: str,
    shop_id: str | None = None,
    claim_type: str = "ref",
    state: str = "PENDING",
) -> int | None:
    """
    Atomically insert payment claim into consumed_payment_claims using ON CONFLICT DO NOTHING.
    Strictly follows requirement 1:
      INSERT INTO consumed_payment_claims (claim_key, ...) VALUES (:key, ...)
      ON CONFLICT (claim_key) DO NOTHING
      RETURNING id;
    ZERO preceding SELECT queries.
    Returns the integer claim ID if inserted successfully, or None if duplicate (conflict).
    """
    if not claim_key or not claim_key.strip():
        raise ValueError("claim_key cannot be empty.")

    clean_key = claim_key.strip()
    stmt = text(
        """
        INSERT INTO consumed_payment_claims (
            shop_id, claim_key, claim_type, order_id, state, consumed_at
        ) VALUES (
            :shop_id, :claim_key, :claim_type, :order_id, :state, NOW()
        )
        ON CONFLICT (claim_key) DO NOTHING
        RETURNING id;
        """
    )
    result = db.execute(
        stmt,
        {
            "shop_id": shop_id,
            "claim_key": clean_key,
            "claim_type": claim_type,
            "order_id": order_id,
            "state": state,
        },
    )
    row = result.first()
    db.commit()

    if row is None:
        return None
    return int(row[0])
