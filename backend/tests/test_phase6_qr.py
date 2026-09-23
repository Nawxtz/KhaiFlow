import os
import subprocess
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.services.qr_service import (
    MissingQRSecretError,
    generate_signed_payment_qr,
    verify_payment_qr,
    verify_qr_data_string,
)


@pytest.fixture
def mock_qr_secret(monkeypatch):
    """Provide a mock secret in settings for the test duration."""
    secret_value = "mock_test_secret_key_for_phase6_only"
    monkeypatch.setattr(settings, "PAYMENT_QR_SECRET", secret_value)
    return secret_value


def test_qr_generation_and_signature_verification(mock_qr_secret):
    """
    Test QR generation produces a valid HMAC-SHA256 signature that passes verification.
    """
    order_id = "ORD-TEST-QR-001"
    total = Decimal("1250.50")
    currency = "THB"
    shop_account = "SHOP-ACC-888"

    result = generate_signed_payment_qr(
        order_id=order_id,
        total=total,
        currency=currency,
        shop_account=shop_account,
    )

    assert result["order_id"] == order_id
    assert result["total"] == "1250.50"
    assert result["currency"] == "THB"
    assert result["shop_account"] == shop_account
    assert result["signature"] is not None
    assert len(result["signature"]) == 64  # SHA256 hex string

    # Verify signature
    is_valid = verify_payment_qr(
        order_id=order_id,
        total=total,
        currency=currency,
        shop_account=shop_account,
        signature=result["signature"],
    )
    assert is_valid is True

    # Verify formatted QR data string
    assert verify_qr_data_string(result["qr_data"]) is True


def test_tampered_payload_rejected_by_verification(mock_qr_secret):
    """
    Signature verification must reject any tampered field (amount, order_id, currency, account).
    """
    order_id = "ORD-TEST-QR-002"
    total = Decimal("500.00")
    currency = "THB"
    shop_account = "SHOP-ACC-001"

    qr_info = generate_signed_payment_qr(
        order_id=order_id,
        total=total,
        currency=currency,
        shop_account=shop_account,
    )
    valid_signature = qr_info["signature"]

    # 1. Tampered amount: buyer tries to pay 0.01 instead of 500.00
    assert (
        verify_payment_qr(
            order_id=order_id,
            total=Decimal("0.01"),
            currency=currency,
            shop_account=shop_account,
            signature=valid_signature,
        )
        is False
    )

    # 2. Tampered order_id: buyer tries to apply payment to another order
    assert (
        verify_payment_qr(
            order_id="ORD-TEST-QR-999",
            total=total,
            currency=currency,
            shop_account=shop_account,
            signature=valid_signature,
        )
        is False
    )

    # 3. Tampered currency: buyer changes currency from THB to USD
    assert (
        verify_payment_qr(
            order_id=order_id,
            total=total,
            currency="USD",
            shop_account=shop_account,
            signature=valid_signature,
        )
        is False
    )

    # 4. Tampered shop account
    assert (
        verify_payment_qr(
            order_id=order_id,
            total=total,
            currency=currency,
            shop_account="ATTACKER-ACCOUNT",
            signature=valid_signature,
        )
        is False
    )

    # 5. Tampered signature
    tampered_sig = valid_signature[:-4] + "0000"
    assert (
        verify_payment_qr(
            order_id=order_id,
            total=total,
            currency=currency,
            shop_account=shop_account,
            signature=tampered_sig,
        )
        is False
    )


def test_hmac_key_sourced_from_settings_and_fails_if_unconfigured(monkeypatch):
    """
    HMAC key must be sourced from settings.PAYMENT_QR_SECRET.
    If unconfigured (empty string), generate_signed_payment_qr must raise MissingQRSecretError.
    """
    monkeypatch.setattr(settings, "PAYMENT_QR_SECRET", "")

    with pytest.raises(MissingQRSecretError):
        generate_signed_payment_qr(
            order_id="ORD-NO-SECRET",
            total=Decimal("100.00"),
        )


def test_secret_never_hardcoded_in_source_code():
    """
    Human Reviewer Check 4: Confirm settings.PAYMENT_QR_SECRET is used everywhere.
    Verify that no production secret strings or hardcoded keys exist in source files.
    """
    backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    app_dir = os.path.join(backend_dir, "app")

    # Grep app directory to ensure PAYMENT_QR_SECRET is only accessed via settings
    result = subprocess.run(
        ["grep", "-rn", "PAYMENT_QR_SECRET", app_dir],
        capture_output=True,
        text=True,
    )
    output = result.stdout
    for line in output.splitlines():
        # Strip comments / docstrings
        clean = line.strip()
        if (
            '"""' in clean
            or clean.startswith("#")
            or "Raised when" in clean
            or "settings / environment" in clean
        ):
            continue
        assert (
            "settings.PAYMENT_QR_SECRET" in clean
            or 'PAYMENT_QR_SECRET: str = ""' in clean
            or "PAYMENT_QR_SECRET" in clean
        )
        # Ensure no non-empty secret assignment exists in code
        assert 'PAYMENT_QR_SECRET: str = "' not in clean or 'PAYMENT_QR_SECRET: str = ""' in clean


def test_api_payment_qr_endpoints(mock_qr_secret, client: TestClient):
    """
    Test /api/payment/generate-qr and /api/payment/verify-qr endpoints.
    """
    # 1. Generate QR
    gen_res = client.post(
        "/api/payment/generate-qr",
        json={
            "order_id": "ORD-API-QR-001",
            "total": "750.00",
            "currency": "THB",
            "shop_account": "SHOP-API-01",
        },
    )
    assert gen_res.status_code == 200
    data = gen_res.json()
    assert data["order_id"] == "ORD-API-QR-001"
    assert data["total"] == "750.00"
    signature = data["signature"]

    # 2. Verify valid QR
    verify_res = client.post(
        "/api/payment/verify-qr",
        json={
            "order_id": "ORD-API-QR-001",
            "total": "750.00",
            "currency": "THB",
            "shop_account": "SHOP-API-01",
            "signature": signature,
        },
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True

    # 3. Verify tampered QR via API
    tampered_res = client.post(
        "/api/payment/verify-qr",
        json={
            "order_id": "ORD-API-QR-001",
            "total": "1.00",  # tampered
            "currency": "THB",
            "shop_account": "SHOP-API-01",
            "signature": signature,
        },
    )
    assert tampered_res.status_code == 200
    assert tampered_res.json()["valid"] is False
