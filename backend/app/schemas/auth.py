from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(..., min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=256)
    new_password: str = Field(..., min_length=1, max_length=256)


class UserRead(BaseModel):
    id: int
    username: str
    role: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    expires_at: datetime
    user: UserRead
