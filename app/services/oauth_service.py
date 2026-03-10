from __future__ import annotations

from dataclasses import dataclass
import json
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import UUID

import httpx
from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import OAuthAccount, User
from app.repositories.auth import OAuthAccountRepository, UserRepository
from app.schemas.auth import OAuthStartResponse


@dataclass(slots=True)
class OAuthIdentity:
    provider_user_id: str
    email: str
    full_name: str
    avatar_url: str | None
    email_verified: bool


@dataclass(frozen=True, slots=True)
class OAuthProviderConfig:
    client_id: str
    client_secret: str
    authorize_url: str
    token_url: str
    userinfo_url: str
    scope: str


@dataclass(frozen=True, slots=True)
class OAuthState:
    flow: str
    user_id: str | None = None


def _callback_url(provider: str, flow: str) -> str:
    base_path = f"{settings.public_backend_url}{settings.api_v1_prefix}/auth/oauth/{provider}"
    if flow == "link":
        return f"{base_path}/link/callback"
    return f"{base_path}/callback"


def _state_key(provider: str, state: str) -> str:
    return f"oauth:state:{provider}:{state}"


def _provider_config(provider: str) -> OAuthProviderConfig:
    configs = {
        "google": OAuthProviderConfig(
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
            token_url="https://oauth2.googleapis.com/token",
            userinfo_url="https://openidconnect.googleapis.com/v1/userinfo",
            scope="openid email profile",
        ),
        "github": OAuthProviderConfig(
            client_id=settings.github_client_id,
            client_secret=settings.github_client_secret,
            authorize_url="https://github.com/login/oauth/authorize",
            token_url="https://github.com/login/oauth/access_token",
            userinfo_url="https://api.github.com/user",
            scope="read:user user:email",
        ),
    }
    config = configs.get(provider)
    if config is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unsupported OAuth provider")
    if not config.client_id or not config.client_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{provider.title()} OAuth credentials are not configured",
        )
    return config


async def _fetch_google_identity(
    client: httpx.AsyncClient,
    config: OAuthProviderConfig,
    code: str,
    redirect_uri: str,
) -> OAuthIdentity:
    token_response = await client.post(
        config.token_url,
        data={
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]
    user_response = await client.get(
        config.userinfo_url,
        headers={"Authorization": f"Bearer {access_token}"},
    )
    user_response.raise_for_status()
    profile = user_response.json()
    return OAuthIdentity(
        provider_user_id=profile["sub"],
        email=profile["email"].lower(),
        full_name=profile.get("name") or profile["email"].split("@")[0],
        avatar_url=profile.get("picture"),
        email_verified=bool(profile.get("email_verified", False)),
    )


async def _fetch_github_identity(
    client: httpx.AsyncClient,
    config: OAuthProviderConfig,
    code: str,
    redirect_uri: str,
) -> OAuthIdentity:
    token_response = await client.post(
        config.token_url,
        headers={"Accept": "application/json"},
        data={
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )
    token_response.raise_for_status()
    access_token = token_response.json()["access_token"]
    user_response = await client.get(
        config.userinfo_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    user_response.raise_for_status()
    profile = user_response.json()

    email_response = await client.get(
        "https://api.github.com/user/emails",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github+json",
        },
    )
    email_response.raise_for_status()
    emails = email_response.json()
    primary_email = next((item for item in emails if item.get("primary")), None)
    email = (primary_email or emails[0])["email"].lower() if emails else f"{profile['id']}@users.noreply.github.com"
    verified = bool((primary_email or {}).get("verified", False))

    return OAuthIdentity(
        provider_user_id=str(profile["id"]),
        email=email,
        full_name=profile.get("name") or profile.get("login") or email.split("@")[0],
        avatar_url=profile.get("avatar_url"),
        email_verified=verified,
    )


async def get_authorization_url(provider: str, redis: Redis) -> OAuthStartResponse:
    return await build_authorization_url(provider, redis, flow="login")


async def build_authorization_url(
    provider: str,
    redis: Redis,
    *,
    flow: str,
    user_id: str | None = None,
) -> OAuthStartResponse:
    config = _provider_config(provider)
    if flow == "link" and not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth link flow requires a user context")

    state = token_urlsafe(24)
    await redis.setex(_state_key(provider, state), 600, json.dumps({"flow": flow, "user_id": user_id}))

    params = {
        "client_id": config.client_id,
        "redirect_uri": _callback_url(provider, flow),
        "response_type": "code",
        "scope": config.scope,
        "state": state,
    }
    if provider == "google":
        params["prompt"] = "select_account"
        params["access_type"] = "offline"

    authorization_url = f"{config.authorize_url}?{urlencode(params)}"
    return OAuthStartResponse(provider=provider, authorization_url=authorization_url, state=state)


async def consume_oauth_state(provider: str, state: str, redis: Redis, *, expected_flow: str) -> OAuthState:
    async with redis.pipeline(transaction=True) as pipe:
        pipe.get(_state_key(provider, state))
        pipe.delete(_state_key(provider, state))
        raw_state, _ = await pipe.execute()

    if not raw_state:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired OAuth state")

    if isinstance(raw_state, bytes):
        raw_state = raw_state.decode("utf-8")

    try:
        payload = json.loads(raw_state)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed OAuth state payload") from error

    if payload.get("flow") != expected_flow:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unexpected OAuth flow state")

    user_id = payload.get("user_id")
    if expected_flow == "link" and not user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth link state is missing the target user")

    return OAuthState(flow=expected_flow, user_id=user_id)


async def exchange_code_for_identity(
    provider: str,
    code: str,
    state: str,
    redis: Redis,
    *,
    expected_flow: str,
) -> tuple[OAuthIdentity, OAuthState]:
    config = _provider_config(provider)
    state_payload = await consume_oauth_state(provider, state, redis, expected_flow=expected_flow)
    redirect_uri = _callback_url(provider, expected_flow)

    async with httpx.AsyncClient(timeout=20.0) as client:
        if provider == "google":
            identity = await _fetch_google_identity(client, config, code, redirect_uri)
        else:
            identity = await _fetch_github_identity(client, config, code, redirect_uri)

    return identity, state_payload


async def get_or_create_oauth_user(db: AsyncSession, provider: str, identity: OAuthIdentity) -> User:
    users = UserRepository(db)
    oauth_accounts = OAuthAccountRepository(db)

    oauth_account = await oauth_accounts.get_by_provider_identity(provider, identity.provider_user_id)
    if oauth_account is not None:
        user = await users.get_by_id(oauth_account.user_id)
        if user is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="OAuth account is linked to a missing user")

        user.full_name = identity.full_name
        user.avatar_url = identity.avatar_url
        user.email_verified = user.email_verified or identity.email_verified
        await db.commit()
        await users.refresh(user)
        return user

    existing_user = await users.get_by_email(identity.email)
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Sign in first, then use the OAuth link endpoint.",
        )

    user = User(
        email=identity.email,
        full_name=identity.full_name,
        avatar_url=identity.avatar_url,
        email_verified=identity.email_verified,
    )
    users.add(user)
    await users.flush()
    oauth_accounts.add(
        OAuthAccount(
            user_id=user.id,
            provider=provider,
            provider_user_id=identity.provider_user_id,
        )
    )

    await db.commit()
    await users.refresh(user)
    return user


async def link_oauth_account_to_user(db: AsyncSession, provider: str, identity: OAuthIdentity, user_id: str | None) -> User:
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth link flow is missing the target user")

    users = UserRepository(db)
    oauth_accounts = OAuthAccountRepository(db)

    user = await users.get_by_id(UUID(user_id))
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User for OAuth linking was not found")

    existing_email_user = await users.get_by_email(identity.email)
    if existing_email_user is not None and existing_email_user.id != user.id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That provider email already belongs to a different local account.",
        )

    oauth_account = await oauth_accounts.get_by_provider_identity(provider, identity.provider_user_id)
    if oauth_account is not None and oauth_account.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That OAuth account is already linked elsewhere")

    if oauth_account is None:
        oauth_accounts.add(
            OAuthAccount(
                user_id=user.id,
                provider=provider,
                provider_user_id=identity.provider_user_id,
            )
        )

    if not user.avatar_url and identity.avatar_url:
        user.avatar_url = identity.avatar_url
    user.email_verified = user.email_verified or identity.email_verified

    await db.commit()
    await users.refresh(user)
    return user

