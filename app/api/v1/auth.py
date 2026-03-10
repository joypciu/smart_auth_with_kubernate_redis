from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, status

from app.api.deps import CurrentUser, DbSession, RedisClient
from app.core.config import settings
from app.core.rate_limiter import rate_limit
from app.schemas.auth import LoginRequest, LogoutRequest, OAuthLinkResponse, OAuthStartResponse, RefreshRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserRead
from app.services.auth_service import authenticate_user, issue_token_pair, logout_refresh_token, refresh_access_pair, register_user
from app.services.oauth_service import build_authorization_url, exchange_code_for_identity, get_or_create_oauth_user, link_oauth_account_to_user

router = APIRouter(prefix="/auth", tags=["auth"])

auth_limit = rate_limit("auth", settings.rate_limit_auth_requests, settings.rate_limit_auth_window_seconds)


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED, dependencies=[Depends(auth_limit)])
async def register(payload: RegisterRequest, db: DbSession) -> TokenResponse:
    user = await register_user(db, payload)
    return await issue_token_pair(db, user)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_limit)])
async def login(payload: LoginRequest, db: DbSession) -> TokenResponse:
    user = await authenticate_user(db, payload.email, payload.password)
    return await issue_token_pair(db, user)


@router.post("/refresh", response_model=TokenResponse, dependencies=[Depends(auth_limit)])
async def refresh(payload: RefreshRequest, db: DbSession) -> TokenResponse:
    return await refresh_access_pair(db, payload.refresh_token)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(auth_limit)])
async def logout(payload: LogoutRequest, db: DbSession) -> None:
    await logout_refresh_token(db, payload.refresh_token)


@router.get("/me", response_model=UserRead)
async def me(current_user: CurrentUser) -> UserRead:
    return UserRead.model_validate(current_user)


@router.get(
    "/oauth/{provider}/login",
    response_model=OAuthStartResponse,
    dependencies=[Depends(auth_limit)],
)
async def oauth_login(
    provider: Annotated[str, Path(pattern="^(google|github)$")],
    redis: RedisClient,
) -> OAuthStartResponse:
    return await build_authorization_url(provider, redis, flow="login")


@router.get(
    "/oauth/{provider}/link",
    response_model=OAuthStartResponse,
    dependencies=[Depends(auth_limit)],
)
async def oauth_link(
    provider: Annotated[str, Path(pattern="^(google|github)$")],
    redis: RedisClient,
    current_user: CurrentUser,
) -> OAuthStartResponse:
    return await build_authorization_url(provider, redis, flow="link", user_id=str(current_user.id))


@router.get(
    "/oauth/{provider}/callback",
    response_model=TokenResponse,
    dependencies=[Depends(auth_limit)],
)
async def oauth_callback(
    provider: Annotated[str, Path(pattern="^(google|github)$")],
    code: str,
    state: str,
    db: DbSession,
    redis: RedisClient,
) -> TokenResponse:
    identity, _ = await exchange_code_for_identity(provider, code, state, redis, expected_flow="login")
    user = await get_or_create_oauth_user(db, provider, identity)
    return await issue_token_pair(db, user)


@router.get(
    "/oauth/{provider}/link/callback",
    response_model=OAuthLinkResponse,
    dependencies=[Depends(auth_limit)],
)
async def oauth_link_callback(
    provider: Annotated[str, Path(pattern="^(google|github)$")],
    code: str,
    state: str,
    db: DbSession,
    redis: RedisClient,
) -> OAuthLinkResponse:
    identity, state_payload = await exchange_code_for_identity(provider, code, state, redis, expected_flow="link")
    user = await link_oauth_account_to_user(db, provider, identity, state_payload.user_id)
    return OAuthLinkResponse(provider=provider, linked=True, user=UserRead.model_validate(user))
