"""T-153: pending phone/postcode answers are validated, not stored raw (quality Q-8)"""
import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "backend"))
import app.services.address_engine as m
from app.services.address_session import AddressSession, _USER_ADDRESS_SESSIONS
from app.services.i18n import get_text


def _run(field, text, monkeypatch):
    monkeypatch.setattr(m, "get_active_order_for_address", lambda db, uid: None)
    s = AddressSession(line_user_id="u153", status="COLLECTING", pending_field=field)
    _USER_ADDRESS_SESSIONS["u153"] = s
    try:
        out = m.process_address_input(None, "u153", text, lang="th")
    finally:
        _USER_ADDRESS_SESSIONS.pop("u153", None)
    return s, out


def test_garbage_phone_reasks(monkeypatch):
    s, out = _run("phone", "ไม่มีเบอร์ค่ะ", monkeypatch)
    assert s.pending_field == "phone" and not s.collected_fields.get("phone")
    assert out[0]["text"] == get_text("enter_missing_phone", "th")


def test_prefixed_and_dashed_phone_accepted(monkeypatch):
    s, _ = _run("phone", "โทร0812345678", monkeypatch)
    assert s.collected_fields["phone"] == "0812345678"
    s, _ = _run("phone", "081-234-5678", monkeypatch)
    assert s.collected_fields["phone"] == "0812345678"


def test_garbage_postcode_reasks(monkeypatch):
    s, out = _run("postcode", "ไม่รู้ค่ะ", monkeypatch)
    assert s.pending_field == "postcode" and not s.collected_fields.get("postcode")
    assert out[0]["text"] == get_text("enter_missing_postcode", "th")


def test_plain_phone_still_stored(monkeypatch):
    s, _ = _run("phone", "0819876543", monkeypatch)
    assert s.collected_fields["phone"] == "0819876543"
