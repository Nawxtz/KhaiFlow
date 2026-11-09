from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from tests.fakes import FakeLineClient, post_line_events, text_event


def test_debug_endpoint_is_gone(client: TestClient):
    assert client.get("/line/debug").status_code == 404


def test_webhook_failure_response_has_no_internal_details(
    client: TestClient, fake_line: FakeLineClient
):
    fake_line.validate_signature = MagicMock(side_effect=RuntimeError("secret internal detail"))

    response = post_line_events(client, [text_event("evt_p0_err", "Hello")])

    assert response.status_code == 200
    assert response.json() == {"status": "error"}
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text


def test_invalid_signature_still_returns_400(client: TestClient, fake_line: FakeLineClient):
    response = post_line_events(client, [text_event("evt_p0_bad", "Hello")], secret="wrong")

    assert response.status_code == 400
