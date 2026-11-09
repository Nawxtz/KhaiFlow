import logging

import pytest
from sqlalchemy.orm import Session

from app.core.line_client import LineClient
from app.services import intent_cascade, llm_router

PHONE = "0812345678"
NAME = "สมชาย ใจดี"
BUYER_TEXT = f"{NAME} {PHONE}"


@pytest.fixture(autouse=True)
def capture_info_logs(caplog: pytest.LogCaptureFixture):
    caplog.set_level(logging.DEBUG)


def _assert_clean(caplog: pytest.LogCaptureFixture) -> None:
    assert PHONE not in caplog.text
    assert NAME not in caplog.text


def test_line_client_does_not_log_message_content(caplog):
    client = LineClient(channel_access_token="", channel_secret="fake")
    client.channel_access_token = None
    messages = [{"type": "text", "text": BUYER_TEXT}]

    client.reply_message("fake_token", messages)
    client.push_message("U_fake_buyer", messages)

    _assert_clean(caplog)
    assert "U_fake_buyer" not in caplog.text


def test_unmatched_buyer_text_is_not_logged(caplog, db_session: Session, monkeypatch):
    monkeypatch.setattr(intent_cascade, "get_active_inventory_products", lambda *_a, **_k: [object()])
    monkeypatch.setattr(intent_cascade, "match_product_rules", lambda *_a, **_k: None)
    monkeypatch.setattr(intent_cascade, "search_products_embeddings", lambda *_a, **_k: None)
    monkeypatch.setattr(intent_cascade, "extract_intent_llm", lambda *_a, **_k: None)

    intent, _stage = intent_cascade.extract_order_intent_with_stage(BUYER_TEXT, db_session)

    assert intent is None
    _assert_clean(caplog)


@pytest.mark.parametrize(
    "raw_response",
    [BUYER_TEXT, f'{{"sku": 5, "name": "{BUYER_TEXT}", "confidence": "x"}}'],
)
def test_bad_llm_output_is_not_logged(caplog, monkeypatch, raw_response: str):
    monkeypatch.setattr(llm_router, "call_openrouter", lambda *_a, **_k: raw_response)
    monkeypatch.setattr(llm_router, "build_system_prompt", lambda _p: "prompt")

    assert llm_router.extract_intent_llm(BUYER_TEXT, [object()]) is None

    _assert_clean(caplog)
