import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.webhook import clear_processed_events, get_line_client
from app.core.line_client import LineClient
from app.main import app
from app.models.address_book import AddressBook
from app.models.order import Order, OrderStatus
from app.models.pdpa import PDPADeletion
from app.models.user_prefs import UserPrefs
from app.services.address_engine import set_parser
from app.services.address_session import clear_all_address_sessions
from app.services.i18n import get_text
from app.services.pdpa_service import (
    has_pdpa_consent,
    record_pdpa_consent,
    run_pdpa_retention_job,
)

TEST_SECRET = "test_channel_secret_key_12345"


def generate_line_signature(body: bytes, secret: str = TEST_SECRET) -> str:
    computed_mac = hmac.new(
        secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).digest()
    return base64.b64encode(computed_mac).decode("utf-8")


@pytest.fixture(autouse=True)
def setup_teardown():
    clear_processed_events()
    clear_all_address_sessions()
    yield
    clear_processed_events()
    clear_all_address_sessions()
    set_parser(None)


def _send_text(client: TestClient, user_id: str, text: str, reply_token: str = "t_txt"):
    payload = {
        "events": [
            {
                "webhookEventId": f"wh_{user_id}_{reply_token}",
                "type": "message",
                "source": {"type": "user", "userId": user_id},
                "replyToken": reply_token,
                "message": {"id": f"msg_{reply_token}", "type": "text", "text": text},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}
    return client.post("/line/webhook", content=body, headers=headers)


def _send_postback(client: TestClient, user_id: str, data: str, reply_token: str = "t_pb"):
    payload = {
        "events": [
            {
                "webhookEventId": f"wh_pb_{user_id}_{reply_token}",
                "type": "postback",
                "source": {"type": "user", "userId": user_id},
                "replyToken": reply_token,
                "postback": {"data": data},
            }
        ]
    }
    body = json.dumps(payload).encode("utf-8")
    headers = {"X-Line-Signature": generate_line_signature(body, TEST_SECRET)}
    return client.post("/line/webhook", content=body, headers=headers)


def test_consent_gate_intercepts_before_address_collection_in_intent_router(
    client: TestClient,
    db_session: Session,
):
    """
    Acceptance Criteria 1:
    Attempting to enter address collection flow without consent is intercepted in intent_router.py.
    - Sends consent prompt with Accept/Decline buttons.
    - Order state does NOT transition to ADDRESS_COLLECTION (remains ORDER_CONFIRMED).
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_gate_test_buyer_01"

        order = Order(
            id="ORD-PDPA-GATE-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
            total=Decimal("500.00"),
        )
        db_session.add(order)
        db_session.commit()

        # Buyer attempts to enter delivery address via text
        res = _send_text(
            client,
            user_id,
            "Somchai 0812345678 123 Sukhumvit Bangkok 10110",
            reply_token="tok_gate_1",
        )
        assert res.status_code == 200

        # Verify: intercepted with consent prompt
        assert mock_line_client.reply_message.called
        replies = mock_line_client.reply_message.call_args[0][1]
        assert len(replies) == 1
        prompt_text = replies[0]["text"]
        assert prompt_text == get_text("pdpa_consent_prompt", "th")
        quick_replies = replies[0]["quickReply"]["items"]
        assert any(
            qr["action"]["data"] == "action=pdpa_consent_accept" for qr in quick_replies
        )
        assert any(
            qr["action"]["data"] == "action=pdpa_consent_decline" for qr in quick_replies
        )

        # Crucial check: Order status must NOT have transitioned to ADDRESS_COLLECTION
        db_session.refresh(order)
        assert order.status == OrderStatus.ORDER_CONFIRMED.value

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_consent_gate_intercepts_saved_address_and_enter_new_address_postbacks(
    client: TestClient,
    db_session: Session,
):
    """
    Acceptance Criteria 1: Postbacks attempting to choose saved address or enter new address
    without consent are intercepted by the consent gate.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_gate_postback_buyer"

        order = Order(
            id="ORD-PDPA-PB-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # 1. Postback enter_new_address without consent
        res1 = _send_postback(client, user_id, "action=enter_new_address", reply_token="tok_pb_1")
        assert res1.status_code == 200
        replies1 = mock_line_client.reply_message.call_args[0][1]
        assert replies1[0]["text"] == get_text("pdpa_consent_prompt", "th")

        # 2. Postback use_saved_address without consent
        res2 = _send_postback(client, user_id, "action=use_saved_address&address_id=1", reply_token="tok_pb_2")
        assert res2.status_code == 200
        replies2 = mock_line_client.reply_message.call_args[0][1]
        assert replies2[0]["text"] == get_text("pdpa_consent_prompt", "th")

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_consent_gate_not_bypassable_via_direct_api(client: TestClient, db_session: Session):
    """
    Acceptance Criteria 1:
    Attempting to create an address entry via direct API call without consent is rejected with 403 Forbidden.
    """
    user_id = "U_unconsented_api_user"

    payload = {
        "shop_id": "default",
        "line_user_id": user_id,
        "label": "Office",
        "receiver_name": "Nawin Tester",
        "phone": "0891112233",
        "address_json": {
            "receiver_name": "Nawin Tester",
            "phone": "0891112233",
            "street": "Silom Rd",
            "subdistrict": "Silom",
            "district": "Bang Rak",
            "province": "Bangkok",
            "postcode": "10500",
            "full_address": "Silom Rd Silom Bang Rak Bangkok 10500",
        },
        "is_default": True,
    }

    # Direct API call without consent must fail
    res = client.post("/api/address-book", json=payload)
    assert res.status_code == 403
    assert "PDPA consent required" in res.json()["detail"]


def test_consent_accept_and_withdrawal_flow(client: TestClient, db_session: Session):
    """
    Acceptance Criteria 1 & Withdrawal:
    1. Buyer accepts consent via postback -> consent is recorded.
    2. Buyer can now proceed with address collection.
    3. Buyer withdraws consent -> subsequent address collection attempts are blocked again.
    """
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_consent_lifecycle_user"

        order = Order(
            id="ORD-PDPA-FLOW-01",
            line_user_id=user_id,
            status=OrderStatus.ORDER_CONFIRMED.value,
        )
        db_session.add(order)
        db_session.commit()

        # Step 1: Accept consent via postback
        res_accept = _send_postback(
            client, user_id, "action=pdpa_consent_accept", reply_token="tok_accept"
        )
        assert res_accept.status_code == 200
        assert has_pdpa_consent(db_session, user_id) is True

        replies_accept = mock_line_client.reply_message.call_args[0][1]
        assert replies_accept[0]["text"] == get_text("pdpa_consent_accepted", "th")

        # Step 2: Now send address text -> should be accepted and transition order
        mock_parser = MagicMock()
        mock_parser.parse.return_value = {
            "receiver": "Wichai",
            "phone": "0812345678",
            "address_detail": "99 Rama 9",
            "sub_district": "Huai Khwang",
            "district": "Huai Khwang",
            "province": "Bangkok",
            "zipcode": "10310",
            "confidence": 0.95,
            "warnings": [],
        }
        set_parser(mock_parser)

        res_addr = _send_text(
            client, user_id, "Wichai 0812345678 99 Rama 9 10310", reply_token="tok_addr"
        )
        assert res_addr.status_code == 200

        # Step 3: Direct API call now succeeds with consent
        api_payload = {
            "shop_id": "default",
            "line_user_id": user_id,
            "label": "Home",
            "receiver_name": "Wichai",
            "phone": "0812345678",
            "address_json": {
                "receiver_name": "Wichai",
                "phone": "0812345678",
                "street": "99 Rama 9",
                "subdistrict": "Huai Khwang",
                "district": "Huai Khwang",
                "province": "Bangkok",
                "postcode": "10310",
                "full_address": "99 Rama 9 Huai Khwang Bangkok 10310",
            },
        }
        res_api = client.post("/api/address-book", json=api_payload)
        assert res_api.status_code == 201

        # Step 4: Buyer withdraws consent via postback
        res_withdraw = _send_postback(
            client, user_id, "action=pdpa_consent_withdraw", reply_token="tok_withdraw"
        )
        assert res_withdraw.status_code == 200
        assert has_pdpa_consent(db_session, user_id) is False

        # Step 5: Direct API call is now blocked again
        res_api_blocked = client.post("/api/address-book", json=api_payload)
        assert res_api_blocked.status_code == 403

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_pdpa_consent_api_endpoints(client: TestClient, db_session: Session):
    """Verify REST API /api/pdpa/consent endpoints for granting, checking, and revoking."""
    user_id = "U_api_consent_buyer"

    # 1. Check initial consent (none)
    res_get1 = client.get(f"/api/pdpa/consent/{user_id}")
    assert res_get1.status_code == 200
    assert res_get1.json()["consent"] is False
    assert res_get1.json()["status"] == "revoked"

    # 2. Grant consent via POST
    res_grant = client.post(
        "/api/pdpa/consent",
        json={"line_user_id": user_id, "consent": True, "shop_id": "default"},
    )
    assert res_grant.status_code == 200
    assert res_grant.json()["consent"] is True

    # 3. Check updated consent
    res_get2 = client.get(f"/api/pdpa/consent/{user_id}")
    assert res_get2.status_code == 200
    assert res_get2.json()["consent"] is True
    assert res_get2.json()["status"] == "active"

    # 4. Revoke consent via POST
    res_revoke = client.post(
        "/api/pdpa/consent",
        json={"line_user_id": user_id, "consent": False, "shop_id": "default"},
    )
    assert res_revoke.status_code == 200
    assert res_revoke.json()["consent"] is False


def test_right_to_delete_audit_preservation_and_clean_slate(
    client: TestClient,
    db_session: Session,
):
    """
    Acceptance Criteria 2: Right-to-delete (audit preservation)
    - Wipes personal data from address_book.
    - Preserves historical orders with line_user_id SHA-256 hashed (never deleted).
    - Deletes user_prefs and revokes consent.
    - Logs deletion event in pdpa_deletions.
    - User can start fresh (new consent, new address book).
    """
    user_id = "U_delete_audit_user_01"
    expected_hash = hashlib.sha256(user_id.encode("utf-8")).hexdigest()

    # 1. Seed user preferences, address book entries, and historical orders
    record_pdpa_consent(db_session, user_id, consent=True)

    addr1 = AddressBook(
        shop_id="default",
        line_user_id=user_id,
        label="Home",
        receiver_name="Anan Tester",
        phone="0899990000",
        address_json={"full_address": "123 Test St"},
    )
    addr2 = AddressBook(
        shop_id="default",
        line_user_id=user_id,
        label="Work",
        receiver_name="Anan Tester",
        phone="0899990000",
        address_json={"full_address": "456 Office Tower"},
    )
    db_session.add_all([addr1, addr2])

    order1 = Order(
        id="ORD-HIST-001",
        shop_id="default",
        line_user_id=user_id,
        status=OrderStatus.FULFILLED.value,
        total=Decimal("1250.00"),
    )
    order2 = Order(
        id="ORD-HIST-002",
        shop_id="default",
        line_user_id=user_id,
        status=OrderStatus.PAYMENT_RECEIVED.value,
        total=Decimal("890.00"),
    )
    db_session.add_all([order1, order2])
    db_session.commit()

    # 2. Execute deletion request via API
    res_del = client.post("/api/pdpa/delete", json={"line_user_id": user_id, "shop_id": "default"})
    assert res_del.status_code == 200
    db_session.expire_all()
    del_data = res_del.json()
    assert del_data["status"] == "deleted"
    assert del_data["addresses_deleted"] == 2
    assert del_data["orders_anonymized"] == 2
    assert del_data["anonymized_user_id"] == expected_hash

    # 3. Assert address_book rows are completely wiped for this user
    remaining_addrs = db_session.execute(
        select(AddressBook).where(AddressBook.line_user_id == user_id)
    ).scalars().all()
    assert len(remaining_addrs) == 0

    # 4. Assert orders rows REMAIN intact in database with line_user_id hashed (financial ledger preserved)
    all_orders = db_session.execute(select(Order)).scalars().all()
    assert len(all_orders) == 2

    order1_db = db_session.execute(select(Order).where(Order.id == "ORD-HIST-001")).scalar_one()
    order2_db = db_session.execute(select(Order).where(Order.id == "ORD-HIST-002")).scalar_one()
    assert order1_db.line_user_id == expected_hash
    assert order1_db.total == Decimal("1250.00")
    assert order2_db.line_user_id == expected_hash
    assert order2_db.total == Decimal("890.00")

    # 5. Assert user_prefs deleted / consent revoked
    assert has_pdpa_consent(db_session, user_id) is False

    # 6. Assert deletion event is recorded in pdpa_deletions table
    log_entry = db_session.execute(
        select(PDPADeletion).where(PDPADeletion.line_user_id == user_id)
    ).scalars().first()
    assert log_entry is not None
    assert log_entry.requested_at is not None
    assert log_entry.completed_at is not None

    # 7. Clean slate: user can start completely fresh
    record_pdpa_consent(db_session, user_id, consent=True)
    assert has_pdpa_consent(db_session, user_id) is True

    new_addr = AddressBook(
        shop_id="default",
        line_user_id=user_id,
        label="New Home",
        receiver_name="Anan Fresh",
        phone="0811112222",
        address_json={"full_address": "789 New St"},
    )
    db_session.add(new_addr)
    db_session.commit()

    fresh_addrs = db_session.execute(
        select(AddressBook).where(AddressBook.line_user_id == user_id)
    ).scalars().all()
    assert len(fresh_addrs) == 1
    assert fresh_addrs[0].receiver_name == "Anan Fresh"


def test_right_to_delete_postback_action_in_intent_router(
    client: TestClient,
    db_session: Session,
):
    """Verify right-to-delete triggered via LINE postback action=pdpa_delete_request."""
    mock_line_client = MagicMock(spec=LineClient)
    app.dependency_overrides[get_line_client] = lambda: mock_line_client
    try:
        user_id = "U_delete_postback_user"

        record_pdpa_consent(db_session, user_id, consent=True)
        addr = AddressBook(
            shop_id="default",
            line_user_id=user_id,
            label="Home",
            receiver_name="Postback Del",
            phone="0800000000",
            address_json={"full_address": "123 Del Way"},
        )
        db_session.add(addr)
        db_session.commit()

        res = _send_postback(client, user_id, "action=pdpa_delete_request", reply_token="tok_del")
        assert res.status_code == 200

        # Verify reply message confirms deletion
        replies = mock_line_client.reply_message.call_args[0][1]
        assert replies[0]["text"] == get_text("pdpa_delete_done", "th")

        # Verify address deleted
        db_session.expire_all()
        addrs = db_session.execute(
            select(AddressBook).where(AddressBook.line_user_id == user_id)
        ).scalars().all()
        assert len(addrs) == 0

    finally:
        app.dependency_overrides.pop(get_line_client, None)


def test_retention_job_dynamic_retention_months_two_values(db_session: Session):
    """
    Acceptance Criteria 3:
    Retention job reads retention_months dynamically from settings.
    Tested with two different values: 6 months and 12 months.
    Uses injected now_fn for time travel (no time.sleep).
    """
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)

    # User A: last activity 8 months ago
    user_a = "U_stale_8_months"
    time_8m_ago = now - timedelta(days=8 * 30)

    # User B: last activity 15 months ago
    user_b = "U_stale_15_months"
    time_15m_ago = now - timedelta(days=15 * 30)

    # Seed User A data 8 months ago
    pref_a = UserPrefs(
        user_id=user_a,
        scope="buyer",
        pdpa_consent=True,
        updated_at=time_8m_ago,
    )
    addr_a = AddressBook(
        shop_id="default",
        line_user_id=user_a,
        receiver_name="User A",
        phone="0810000001",
        address_json={"full_address": "Addr A"},
        created_at=time_8m_ago,
    )
    order_a = Order(
        id="ORD-STALE-A",
        line_user_id=user_a,
        status=OrderStatus.FULFILLED.value,
        total=Decimal("200.00"),
        created_at=time_8m_ago,
        updated_at=time_8m_ago,
    )

    # Seed User B data 15 months ago
    pref_b = UserPrefs(
        user_id=user_b,
        scope="buyer",
        pdpa_consent=True,
        updated_at=time_15m_ago,
    )
    addr_b = AddressBook(
        shop_id="default",
        line_user_id=user_b,
        receiver_name="User B",
        phone="0810000002",
        address_json={"full_address": "Addr B"},
        created_at=time_15m_ago,
    )
    order_b = Order(
        id="ORD-STALE-B",
        line_user_id=user_b,
        status=OrderStatus.FULFILLED.value,
        total=Decimal("400.00"),
        created_at=time_15m_ago,
        updated_at=time_15m_ago,
    )

    db_session.add_all([pref_a, addr_a, order_a, pref_b, addr_b, order_b])
    db_session.commit()

    # Run 1: Test with retention_months = 12
    # User B (15m old) should be deleted; User A (8m old) must NOT be deleted.
    deleted_12 = run_pdpa_retention_job(
        db_session,
        retention_months=12,
        now_fn=lambda: now,
    )
    assert user_b in deleted_12
    assert user_a not in deleted_12

    # Check User B was anonymized and address wiped
    addrs_b = db_session.execute(
        select(AddressBook).where(AddressBook.line_user_id == user_b)
    ).scalars().all()
    assert len(addrs_b) == 0

    order_b_db = db_session.execute(select(Order).where(Order.id == "ORD-STALE-B")).scalar_one()
    assert order_b_db.line_user_id == hashlib.sha256(user_b.encode("utf-8")).hexdigest()

    # Check User A remains intact
    addrs_a = db_session.execute(
        select(AddressBook).where(AddressBook.line_user_id == user_a)
    ).scalars().all()
    assert len(addrs_a) == 1

    order_a_db = db_session.execute(select(Order).where(Order.id == "ORD-STALE-A")).scalar_one()
    assert order_a_db.line_user_id == user_a

    # Run 2: Test with retention_months = 6
    # Now User A (8m old) IS eligible and should be deleted.
    deleted_6 = run_pdpa_retention_job(
        db_session,
        retention_months=6,
        now_fn=lambda: now,
    )
    assert user_a in deleted_6

    # Verify User A address wiped and order anonymized
    addrs_a_after = db_session.execute(
        select(AddressBook).where(AddressBook.line_user_id == user_a)
    ).scalars().all()
    assert len(addrs_a_after) == 0

    order_a_after = db_session.execute(select(Order).where(Order.id == "ORD-STALE-A")).scalar_one()
    assert order_a_after.line_user_id == hashlib.sha256(user_a.encode("utf-8")).hexdigest()


def test_retention_job_preserves_active_users_with_recent_orders(db_session: Session):
    """
    Acceptance Criteria 3:
    Users whose account is older than retention_months but who placed an order recently
    within the retention window MUST NOT be deleted.
    """
    now = datetime(2026, 9, 23, 12, 0, 0, tzinfo=UTC)
    time_14m_ago = now - timedelta(days=14 * 30)
    time_1m_ago = now - timedelta(days=1 * 30)

    user_active = "U_active_buyer_recent_order"

    # User created address 14 months ago
    addr = AddressBook(
        shop_id="default",
        line_user_id=user_active,
        receiver_name="Active Buyer",
        phone="0819998888",
        address_json={"full_address": "Recent St"},
        created_at=time_14m_ago,
    )
    # Old order 14 months ago
    old_order = Order(
        id="ORD-ACT-OLD",
        line_user_id=user_active,
        status=OrderStatus.FULFILLED.value,
        total=Decimal("300.00"),
        created_at=time_14m_ago,
    )
    # Recent order 1 month ago
    recent_order = Order(
        id="ORD-ACT-RECENT",
        line_user_id=user_active,
        status=OrderStatus.FULFILLED.value,
        total=Decimal("600.00"),
        created_at=time_1m_ago,
    )

    db_session.add_all([addr, old_order, recent_order])
    db_session.commit()

    deleted = run_pdpa_retention_job(
        db_session,
        retention_months=12,
        now_fn=lambda: now,
    )

    # Active user must NOT be deleted
    assert user_active not in deleted

    # Address and orders must remain untouched
    active_addrs = db_session.execute(
        select(AddressBook).where(AddressBook.line_user_id == user_active)
    ).scalars().all()
    assert len(active_addrs) == 1

    active_orders = db_session.execute(
        select(Order).where(Order.line_user_id == user_active)
    ).scalars().all()
    assert len(active_orders) == 2


def test_retention_job_for_update_skip_locked_batch_safety(db_session: Session):
    """
    Verify retention job uses FOR UPDATE SKIP LOCKED batch queries for multi-worker safety.
    """
    import inspect as py_inspect

    source_code = py_inspect.getsource(run_pdpa_retention_job)
    assert "with_for_update(skip_locked=True)" in source_code
    assert "retention_months" in source_code
