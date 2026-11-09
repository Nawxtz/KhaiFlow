from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth.deps import CurrentUser, require_user
from app.auth.service import (
    InvalidAccountDataError,
    InvalidCredentialsError,
    InvalidSessionError,
    IssuedTokens,
    change_password,
    login,
    logout,
    refresh_session,
)
from app.core.database import get_db
from app.core.security import rate_limit
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    RefreshRequest,
    TokenResponse,
    UserRead,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Per client address. Account lockout separately protects each username.
LOGIN_REQUESTS_PER_MINUTE = 20
REFRESH_REQUESTS_PER_MINUTE = 60


def _token_response(tokens: IssuedTokens) -> TokenResponse:
    return TokenResponse(
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
        expires_at=tokens.expires_at,
        user=UserRead(id=tokens.user.id, username=tokens.user.username, role=tokens.user.role),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth_login", LOGIN_REQUESTS_PER_MINUTE))],
)
def login_endpoint(req: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        return _token_response(login(db, req.username, req.password))
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc


@router.post(
    "/refresh",
    response_model=TokenResponse,
    dependencies=[Depends(rate_limit("auth_refresh", REFRESH_REQUESTS_PER_MINUTE))],
)
def refresh_endpoint(req: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        return _token_response(refresh_session(db, req.refresh_token))
    except InvalidSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session"
        ) from exc


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout_endpoint(
    current: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    logout(db, current.session_id)


@router.get("/me", response_model=UserRead)
def me_endpoint(current: CurrentUser = Depends(require_user)) -> UserRead:
    return UserRead(id=current.id, username=current.username, role=current.role)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password_endpoint(
    req: ChangePasswordRequest,
    current: CurrentUser = Depends(require_user),
    db: Session = Depends(get_db),
) -> None:
    try:
        change_password(
            db, current.user, req.current_password, req.new_password, current.session_id
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        ) from exc
    except InvalidAccountDataError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
