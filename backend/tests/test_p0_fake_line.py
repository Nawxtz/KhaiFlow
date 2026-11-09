from fastapi.testclient import TestClient

from tests.fakes import FakeLineClient, post_line_events, text_event


def test_signed_event_reaches_bot_and_reply_is_recorded(
    client: TestClient, fake_line: FakeLineClient
):
    response = post_line_events(client, [text_event("evt_p0_001", "Hello", reply_token="tok_1")])

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert [token for token, _ in fake_line.replies] == ["tok_1"]
    assert fake_line.pushes == []


def test_wrong_signature_is_rejected_and_nothing_is_sent(
    client: TestClient, fake_line: FakeLineClient
):
    response = post_line_events(client, [text_event("evt_p0_002", "Hello")], secret="wrong_secret")

    assert response.status_code == 400
    assert fake_line.replies == []
    assert fake_line.pushes == []


def test_repeated_event_id_is_replied_to_once(client: TestClient, fake_line: FakeLineClient):
    event = text_event("evt_p0_003", "Hello")

    post_line_events(client, [event])
    post_line_events(client, [event])

    assert len(fake_line.replies) == 1


def test_processed_events_do_not_leak_between_tests(
    client: TestClient, fake_line: FakeLineClient
):
    """Same event ID as the test above: it must be processed again here."""
    post_line_events(client, [text_event("evt_p0_003", "Hello")])

    assert len(fake_line.replies) == 1


def test_push_is_recorded_without_network(fake_line: FakeLineClient):
    fake_line.send_message("U_fake_buyer", "shipped")

    assert fake_line.pushes == [("U_fake_buyer", [{"type": "text", "text": "shipped"}])]
