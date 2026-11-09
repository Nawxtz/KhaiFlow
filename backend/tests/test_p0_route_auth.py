import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import api_docs_urls, app
from tests.conftest import auth_headers

PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("POST", "/line/webhook"),
    ("POST", "/api/payment/webhook"),
    ("POST", "/api/gateway/webhook"),
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/refresh"),
}

OWNER_ONLY_ROUTES = [
    ("POST", "/api/verification/approve/ORD-X", {}),
    ("POST", "/api/verification/reject/ORD-X", {"reason": "bad slip"}),
    ("GET", "/api/export/csv?carrier_id=kerry", None),
    ("GET", "/api/export/kerry", None),
    ("POST", "/api/export/kerry", None),
    ("POST", "/api/pdpa/delete", {"line_user_id": "U_x"}),
    ("POST", "/api/pdpa/retention", None),
    ("POST", "/api/inventory/sync", None),
]


def _all_routes() -> set[tuple[str, str]]:
    """Every route FastAPI serves, including those on included routers."""
    return {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
    }


def test_route_list_is_complete_and_allowlist_is_real():
    routes = _all_routes()

    assert len(routes) >= 30
    assert PUBLIC_ROUTES <= routes


def test_anonymous_request_is_refused_on_every_route_outside_the_allowlist(
    anon_client: TestClient,
):
    for method, path in _all_routes() - PUBLIC_ROUTES:
        url = re.sub(r"{[^}]+}", "x", path)
        response = anon_client.request(method, url)
        assert response.status_code == 401, (method, path)


@pytest.mark.parametrize(("method", "url", "body"), OWNER_ONLY_ROUTES)
def test_staff_is_refused_on_owner_only_routes(
    client: TestClient, db_session: Session, method: str, url: str, body: Any
):
    response = client.request(method, url, json=body, headers=auth_headers(db_session, "staff"))

    assert response.status_code == 403


@pytest.mark.parametrize(("method", "url", "body"), OWNER_ONLY_ROUTES[:2])
def test_owner_passes_the_permission_check(client: TestClient, method: str, url: str, body: Any):
    """The order does not exist, so reaching 404 proves the role check let the owner through."""
    assert client.request(method, url, json=body).status_code == 404


def test_staff_can_work_with_orders(client: TestClient, db_session: Session):
    response = client.get("/api/orders", headers=auth_headers(db_session, "staff"))

    assert response.status_code == 200


def test_role_header_cannot_raise_permission(client: TestClient, db_session: Session):
    headers = {**auth_headers(db_session, "staff"), "X-User-Role": "owner"}

    response = client.get("/api/export/csv?carrier_id=kerry&role=owner", headers=headers)

    assert response.status_code == 403


def test_reviewer_comes_from_the_session_not_the_body(client: TestClient, monkeypatch):
    seen: dict[str, str] = {}

    class FakeOrder:
        id = "ORD-X"
        status = "PAYMENT_RECEIVED"
        approval_state = "APPROVED"

    def fake_approve(order_id: str, reviewer_id: str, db: Session) -> FakeOrder:
        seen["reviewer_id"] = reviewer_id
        return FakeOrder()

    monkeypatch.setattr("app.api.verification.approve_manual", fake_approve)

    response = client.post("/api/verification/approve/ORD-X", json={"reviewer_id": "someone_else"})

    assert response.status_code == 200
    assert seen["reviewer_id"] == "test_owner"


def test_api_docs_are_closed_only_in_production():
    assert api_docs_urls("production") == {"docs_url": None, "redoc_url": None, "openapi_url": None}
    assert api_docs_urls("development") == {}
