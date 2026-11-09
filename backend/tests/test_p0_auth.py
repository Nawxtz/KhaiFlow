from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import cli
from app.auth.service import (
    InvalidAccountDataError,
    InvalidCredentialsError,
    InvalidSessionError,
    create_user,
    login,
    refresh_session,
    reset_password,
    resolve_session,
)
from app.core.config import settings
from app.models.auth import AuthSession, User
from tests.conftest import TestingSessionLocal

PASSWORD = "correct horse battery"
OTHER_PASSWORD = "another long passphrase"


@pytest.fixture
def owner(db_session: Session) -> User:
    return create_user(db_session, "owner_a", PASSWORD, "owner")


def _login(client: TestClient, password: str = PASSWORD):
    return client.post("/api/auth/login", json={"username": "owner_a", "password": password})


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_password_is_stored_as_argon2id(owner: User):
    assert owner.password_hash.startswith("$argon2id$")
    assert PASSWORD not in owner.password_hash


def test_login_returns_tokens_and_me_works(client: TestClient, owner: User):
    response = _login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"id": owner.id, "username": "owner_a", "role": "owner"}
    me = client.get("/api/auth/me", headers=_bearer(body["access_token"]))
    assert me.json()["username"] == "owner_a"


def test_tokens_are_stored_only_as_hashes(client: TestClient, owner: User, db_session: Session):
    body = _login(client).json()

    row = db_session.execute(select(AuthSession)).scalars().one()
    assert body["access_token"] not in (row.token_hash, row.refresh_hash)
    assert body["refresh_token"] not in (row.token_hash, row.refresh_hash)


def test_wrong_password_and_unknown_user_look_the_same(client: TestClient, owner: User):
    wrong = _login(client, "wrong password here")
    unknown = client.post("/api/auth/login", json={"username": "nobody", "password": PASSWORD})

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_me_requires_a_valid_token(client: TestClient):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/auth/me", headers=_bearer("nonsense")).status_code == 401


def test_logout_ends_the_session(client: TestClient, owner: User):
    headers = _bearer(_login(client).json()["access_token"])

    assert client.post("/api/auth/logout", headers=headers).status_code == 204
    assert client.get("/api/auth/me", headers=headers).status_code == 401


def test_session_expires_after_configured_ttl(owner: User, db_session: Session):
    start = datetime(2026, 11, 9, tzinfo=UTC)
    tokens = login(db_session, "owner_a", PASSWORD, now_fn=lambda: start)
    ttl = timedelta(hours=settings.SESSION_TTL_HOURS)

    resolve_session(db_session, tokens.access_token, now_fn=lambda: start + ttl - timedelta(1 / 86400))
    with pytest.raises(InvalidSessionError):
        resolve_session(db_session, tokens.access_token, now_fn=lambda: start + ttl)


def test_refresh_rotation_invalidates_the_old_tokens(client: TestClient, owner: User):
    first = _login(client).json()

    second = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})
    reused = client.post("/api/auth/refresh", json={"refresh_token": first["refresh_token"]})

    assert second.status_code == 200
    assert reused.status_code == 401
    assert client.get("/api/auth/me", headers=_bearer(first["access_token"])).status_code == 401
    me = client.get("/api/auth/me", headers=_bearer(second.json()["access_token"]))
    assert me.status_code == 200


def test_refresh_token_cannot_be_used_after_expiry(owner: User, db_session: Session):
    start = datetime(2026, 11, 9, tzinfo=UTC)
    tokens = login(db_session, "owner_a", PASSWORD, now_fn=lambda: start)

    with pytest.raises(InvalidSessionError):
        refresh_session(db_session, tokens.refresh_token, now_fn=lambda: start + timedelta(days=8))


def test_lockout_after_threshold_blocks_even_the_right_password(owner: User, db_session: Session):
    start = datetime(2026, 11, 9, tzinfo=UTC)
    for _ in range(settings.LOGIN_RATE_LIMIT):
        with pytest.raises(InvalidCredentialsError):
            login(db_session, "owner_a", "wrong password here", now_fn=lambda: start)

    with pytest.raises(InvalidCredentialsError):
        login(db_session, "owner_a", PASSWORD, now_fn=lambda: start)


def test_lock_ends_after_the_lockout_time_and_success_clears_count(
    owner: User, db_session: Session
):
    start = datetime(2026, 11, 9, tzinfo=UTC)
    for _ in range(settings.LOGIN_RATE_LIMIT):
        with pytest.raises(InvalidCredentialsError):
            login(db_session, "owner_a", "wrong password here", now_fn=lambda: start)

    login(db_session, "owner_a", PASSWORD, now_fn=lambda: start + timedelta(minutes=16))

    db_session.refresh(owner)
    assert owner.failed_attempts == 0
    assert owner.locked_until is None


def test_failed_attempts_below_threshold_do_not_lock(owner: User, db_session: Session):
    with pytest.raises(InvalidCredentialsError):
        login(db_session, "owner_a", "wrong password here")

    assert login(db_session, "owner_a", PASSWORD).access_token


def test_inactive_user_cannot_login_and_loses_sessions(
    client: TestClient, owner: User, db_session: Session
):
    headers = _bearer(_login(client).json()["access_token"])

    owner.active = False
    db_session.commit()

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert _login(client).status_code == 401


def test_change_password_keeps_this_session_and_ends_others(client: TestClient, owner: User):
    this_session = _bearer(_login(client).json()["access_token"])
    other_session = _bearer(_login(client).json()["access_token"])

    response = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": OTHER_PASSWORD},
        headers=this_session,
    )

    assert response.status_code == 204
    assert client.get("/api/auth/me", headers=this_session).status_code == 200
    assert client.get("/api/auth/me", headers=other_session).status_code == 401
    assert _login(client, OTHER_PASSWORD).status_code == 200


def test_change_password_rejects_wrong_current_and_short_new(client: TestClient, owner: User):
    headers = _bearer(_login(client).json()["access_token"])

    wrong = client.post(
        "/api/auth/change-password",
        json={"current_password": "not the password", "new_password": OTHER_PASSWORD},
        headers=headers,
    )
    short = client.post(
        "/api/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=headers,
    )

    assert wrong.status_code == 401
    assert short.status_code == 400


def test_reset_password_clears_lock_and_ends_sessions(owner: User, db_session: Session):
    tokens = login(db_session, "owner_a", PASSWORD)
    for _ in range(settings.LOGIN_RATE_LIMIT):
        with pytest.raises(InvalidCredentialsError):
            login(db_session, "owner_a", "wrong password here")

    reset_password(db_session, "owner_a", OTHER_PASSWORD)

    with pytest.raises(InvalidSessionError):
        resolve_session(db_session, tokens.access_token)
    assert login(db_session, "owner_a", OTHER_PASSWORD).access_token


@pytest.mark.parametrize(
    ("username", "password", "role"),
    [("a", "short", "owner"), ("", PASSWORD, "owner"), ("a", PASSWORD, "admin")],
)
def test_create_user_validates_input(db_session: Session, username, password, role):
    with pytest.raises(InvalidAccountDataError):
        create_user(db_session, username, password, role)


def test_cli_creates_user_without_printing_password(monkeypatch, capsys, db_session: Session):
    monkeypatch.setattr(cli, "SessionLocal", TestingSessionLocal)
    monkeypatch.setattr(cli.getpass, "getpass", lambda _prompt: PASSWORD)

    assert cli.main(["create-user", "staff_a", "--role", "staff"]) == 0

    user = db_session.execute(select(User).where(User.username == "staff_a")).scalars().one()
    assert user.role == "staff"
    assert PASSWORD not in capsys.readouterr().out
