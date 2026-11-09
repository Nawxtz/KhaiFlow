from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.security import SecurityHeadersMiddleware, SlidingWindowLimiter
from tests.fakes import FakeLineClient, post_line_events, text_event


def test_cross_origin_requests_get_no_cors_permission(anon_client: TestClient):
    response = anon_client.get("/health", headers={"Origin": "https://evil.example"})

    assert "access-control-allow-origin" not in response.headers


def test_security_headers_are_set(anon_client: TestClient):
    response = anon_client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


def test_production_adds_csp_and_hsts():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware, production=True)

    response = TestClient(app).get("/missing")

    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert "max-age" in response.headers["strict-transport-security"]


def test_oversized_body_with_length_is_refused(anon_client: TestClient):
    response = anon_client.post("/api/auth/login", content=b"x" * (1024 * 1024 + 1))

    assert response.status_code == 413


def test_oversized_body_without_length_is_refused(anon_client: TestClient):
    def chunks():
        for _ in range(3):
            yield b"x" * (600 * 1024)

    response = anon_client.post("/api/auth/login", content=chunks())

    assert response.status_code in (400, 413)


def test_normal_body_is_accepted(anon_client: TestClient):
    response = anon_client.post("/api/auth/login", json={"username": "nobody", "password": "x"})

    assert response.status_code == 401


def test_login_is_rate_limited_per_client(anon_client: TestClient):
    body = {"username": "nobody", "password": "x"}

    statuses = [anon_client.post("/api/auth/login", json=body).status_code for _ in range(21)]

    assert statuses[:20] == [401] * 20
    assert statuses[20] == 429


def test_limiter_allows_again_after_the_window():
    now = [0.0]
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60, clock=lambda: now[0])

    assert limiter.allow("a") is True
    assert limiter.allow("a") is False
    assert limiter.allow("b") is True
    now[0] = 60.0
    assert limiter.allow("a") is True


def _event_from(source: dict) -> dict:
    return {**text_event(f"evt_{source['type']}", "Hello"), "source": source}


def test_group_and_room_messages_are_ignored(client: TestClient, fake_line: FakeLineClient):
    events = [
        _event_from({"type": "group", "groupId": "C1", "userId": "U1"}),
        _event_from({"type": "room", "roomId": "R1", "userId": "U1"}),
    ]

    response = post_line_events(client, events)

    assert response.status_code == 200
    assert fake_line.replies == []


def test_one_to_one_messages_still_get_a_reply(client: TestClient, fake_line: FakeLineClient):
    post_line_events(client, [_event_from({"type": "user", "userId": "U1"})])

    assert len(fake_line.replies) == 1
