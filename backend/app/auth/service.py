import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import case, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.auth import AuthSession, User

NowFn = Callable[[], datetime]

ROLES = ("owner", "staff")
MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 256
REFRESH_TTL = timedelta(days=7)
LOCKOUT_DURATION = timedelta(minutes=15)

_hasher = PasswordHasher()
# Verified for unknown or locked accounts so response time does not reveal which case applied.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(32))


class AuthError(Exception):
    """Base class for authentication failures."""


class InvalidCredentialsError(AuthError):
    """Wrong username or password, or the account is locked or inactive."""


class InvalidSessionError(AuthError):
    """Token is unknown, expired or revoked."""


class InvalidAccountDataError(AuthError):
    """A new password, username or role does not meet the rules."""


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str
    expires_at: datetime
    user: User


def _now(now_fn: NowFn | None) -> datetime:
    return now_fn() if now_fn else datetime.now(UTC)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _check_password_rules(password: str) -> None:
    if not MIN_PASSWORD_LENGTH <= len(password) <= MAX_PASSWORD_LENGTH:
        raise InvalidAccountDataError(
            f"Password must be {MIN_PASSWORD_LENGTH} to {MAX_PASSWORD_LENGTH} characters."
        )


def _verify_password(stored_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(stored_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def _record_failed_login(db: Session, user_id: int, now: datetime) -> None:
    """Count a failure in one statement so concurrent attempts cannot undercount."""
    lock_expired = User.locked_until.is_not(None) & (User.locked_until <= now)
    attempts = case((lock_expired, 1), else_=User.failed_attempts + 1)
    db.execute(
        update(User)
        .where(User.id == user_id)
        .values(
            failed_attempts=attempts,
            locked_until=case(
                (attempts >= settings.LOGIN_RATE_LIMIT, now + LOCKOUT_DURATION),
                (lock_expired, None),
                else_=User.locked_until,
            ),
        )
    )
    db.commit()


def _issue_session(db: Session, user: User, now: datetime) -> IssuedTokens:
    access_token = secrets.token_urlsafe(32)
    refresh_token = secrets.token_urlsafe(32)
    expires_at = now + timedelta(hours=settings.SESSION_TTL_HOURS)
    db.add(
        AuthSession(
            shop_id=user.shop_id,
            user_id=user.id,
            token_hash=_hash_token(access_token),
            refresh_hash=_hash_token(refresh_token),
            expires_at=expires_at,
            refresh_expires_at=now + REFRESH_TTL,
        )
    )
    return IssuedTokens(access_token, refresh_token, expires_at, user)


def _revoke_user_sessions(
    db: Session, user_id: int, now: datetime, keep_session_id: int | None = None
) -> None:
    stmt = update(AuthSession).where(
        AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None)
    )
    if keep_session_id is not None:
        stmt = stmt.where(AuthSession.id != keep_session_id)
    db.execute(stmt.values(revoked_at=now))


def create_user(
    db: Session,
    username: str,
    password: str,
    role: str,
    shop_id: str | None = None,
) -> User:
    username = username.strip()
    if not 1 <= len(username) <= 64:
        raise InvalidAccountDataError("Username must be 1 to 64 characters.")
    if role not in ROLES:
        raise InvalidAccountDataError(f"Role must be one of {ROLES}.")
    _check_password_rules(password)
    user = User(
        shop_id=shop_id or settings.DEFAULT_SHOP_ID,
        username=username,
        password_hash=_hasher.hash(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login(
    db: Session, username: str, password: str, now_fn: NowFn | None = None
) -> IssuedTokens:
    now = _now(now_fn)
    user = db.execute(select(User).where(User.username == username)).scalars().first()
    locked = user is not None and user.locked_until is not None and user.locked_until > now
    if user is None or not user.active or locked:
        _verify_password(_DUMMY_HASH, password)
        raise InvalidCredentialsError("Invalid credentials.")
    if not _verify_password(user.password_hash, password):
        _record_failed_login(db, user.id, now)
        raise InvalidCredentialsError("Invalid credentials.")

    user.failed_attempts = 0
    user.locked_until = None
    if _hasher.check_needs_rehash(user.password_hash):
        user.password_hash = _hasher.hash(password)
    tokens = _issue_session(db, user, now)
    db.commit()
    return tokens


def resolve_session(
    db: Session, access_token: str, now_fn: NowFn | None = None
) -> tuple[User, AuthSession]:
    now = _now(now_fn)
    row = db.execute(
        select(User, AuthSession)
        .join(AuthSession, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == _hash_token(access_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
            User.active.is_(True),
        )
    ).first()
    if row is None:
        raise InvalidSessionError("Invalid session.")
    return row[0], row[1]


def refresh_session(
    db: Session, refresh_token: str, now_fn: NowFn | None = None
) -> IssuedTokens:
    """Rotate tokens. The conditional update lets only one caller use a refresh token."""
    now = _now(now_fn)
    user_id = db.execute(
        update(AuthSession)
        .where(
            AuthSession.refresh_hash == _hash_token(refresh_token),
            AuthSession.revoked_at.is_(None),
            AuthSession.refresh_expires_at > now,
        )
        .values(revoked_at=now)
        .returning(AuthSession.user_id)
    ).scalar()
    user = db.get(User, user_id) if user_id is not None else None
    if user is None or not user.active:
        db.commit()
        raise InvalidSessionError("Invalid session.")
    tokens = _issue_session(db, user, now)
    db.commit()
    return tokens


def logout(db: Session, session_id: int, now_fn: NowFn | None = None) -> None:
    db.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=_now(now_fn))
    )
    db.commit()


def change_password(
    db: Session,
    user: User,
    current_password: str,
    new_password: str,
    current_session_id: int,
    now_fn: NowFn | None = None,
) -> None:
    if not _verify_password(user.password_hash, current_password):
        raise InvalidCredentialsError("Invalid credentials.")
    _check_password_rules(new_password)
    user.password_hash = _hasher.hash(new_password)
    _revoke_user_sessions(db, user.id, _now(now_fn), keep_session_id=current_session_id)
    db.commit()


def reset_password(
    db: Session, username: str, new_password: str, now_fn: NowFn | None = None
) -> None:
    """Administrator reset: clears any lockout and ends every session of the account."""
    _check_password_rules(new_password)
    user = db.execute(select(User).where(User.username == username)).scalars().first()
    if user is None:
        raise InvalidAccountDataError("Unknown username.")
    user.password_hash = _hasher.hash(new_password)
    user.failed_attempts = 0
    user.locked_until = None
    _revoke_user_sessions(db, user.id, _now(now_fn))
    db.commit()
