from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from urllib.parse import unquote
from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from redis.exceptions import RedisError
from starlette.requests import Request

from app.core import rate_limiter as rate_limiter_module
from app.core.rate_limiter import get_client_ip, rate_limit
from app.models.user import OAuthAccount, RefreshToken, User
from app.schemas.auth import RegisterRequest
from app.services import auth_service as auth_service_module
from app.services.auth_service import AuthenticationService
from app.services import oauth_service as oauth_service_module
from app.services.oauth_service import OAuthIdentity, build_authorization_url, consume_oauth_state, get_or_create_oauth_user, link_oauth_account_to_user


def _stamp_user(user: User) -> None:
    now = datetime.now(timezone.utc)
    if user.id is None:
        user.id = uuid4()
    if user.created_at is None:
        user.created_at = now
    if user.updated_at is None:
        user.updated_at = now
    if user.is_active is None:
        user.is_active = True
    if user.email_verified is None:
        user.email_verified = False


class FakeSession:
    def __init__(self) -> None:
        self.users: list[User] = []
        self.refresh_tokens: list[RefreshToken] = []
        self.oauth_accounts: list[OAuthAccount] = []
        self.commits = 0

    async def commit(self) -> None:
        self.commits += 1


class FakeUserRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        return next((user for user in self.session.users if user.email == email), None)

    async def get_by_id(self, user_id: UUID) -> User | None:
        return next((user for user in self.session.users if user.id == user_id), None)

    def add(self, user: User) -> None:
        _stamp_user(user)
        self.session.users.append(user)

    async def flush(self) -> None:
        return None

    async def refresh(self, user: User) -> None:
        _stamp_user(user)


class FakeRefreshTokenRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    def add(self, refresh_token: RefreshToken) -> None:
        if refresh_token.id is None:
            refresh_token.id = uuid4()
        if refresh_token.created_at is None:
            refresh_token.created_at = datetime.now(timezone.utc)
        refresh_token.user = next(user for user in self.session.users if user.id == refresh_token.user_id)
        self.session.refresh_tokens.append(refresh_token)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        return next((token for token in self.session.refresh_tokens if token.jti == jti), None)

    async def get_with_user(self, jti: str) -> RefreshToken | None:
        return await self.get_by_jti(jti)

    @staticmethod
    def revoke(refresh_token: RefreshToken, revoked_at: datetime) -> None:
        refresh_token.revoked_at = revoked_at


class FakeOAuthAccountRepository:
    def __init__(self, session: FakeSession) -> None:
        self.session = session

    async def get_by_provider_identity(self, provider: str, provider_user_id: str) -> OAuthAccount | None:
        return next(
            (
                account
                for account in self.session.oauth_accounts
                if account.provider == provider and account.provider_user_id == provider_user_id
            ),
            None,
        )

    def add(self, oauth_account: OAuthAccount) -> None:
        if oauth_account.id is None:
            oauth_account.id = uuid4()
        if oauth_account.created_at is None:
            oauth_account.created_at = datetime.now(timezone.utc)
        self.session.oauth_accounts.append(oauth_account)


class FakePipeline:
    def __init__(self, store: dict[str, str]) -> None:
        self.store = store
        self.operations: list[tuple[str, str]] = []

    async def __aenter__(self) -> FakePipeline:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    def get(self, key: str) -> None:
        self.operations.append(("get", key))

    def delete(self, key: str) -> None:
        self.operations.append(("delete", key))

    async def execute(self) -> list[str | int | None]:
        results: list[str | int | None] = []
        for operation, key in self.operations:
            if operation == "get":
                results.append(self.store.get(key))
            elif operation == "delete":
                results.append(1 if self.store.pop(key, None) is not None else 0)
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def setex(self, key: str, seconds: int, value: str) -> None:
        self.store[key] = value

    def pipeline(self, transaction: bool = True) -> FakePipeline:
        return FakePipeline(self.store)


class FailingRedis:
    async def incr(self, key: str) -> int:
        raise RedisError("down")


@pytest.fixture(autouse=True)
def fake_repositories(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_service_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(auth_service_module, "RefreshTokenRepository", FakeRefreshTokenRepository)
    monkeypatch.setattr(oauth_service_module, "UserRepository", FakeUserRepository)
    monkeypatch.setattr(oauth_service_module, "OAuthAccountRepository", FakeOAuthAccountRepository)


@pytest.mark.asyncio
async def test_register_user_hashes_password_and_normalizes_email() -> None:
    session = FakeSession()
    service = AuthenticationService(session)

    user = await service.register_user(
        RegisterRequest(email="Demo@Example.com", full_name="Demo User", password="StrongPass123")
    )

    assert user.email == "demo@example.com"
    assert user.password_hash != "StrongPass123"
    assert len(session.users) == 1


@pytest.mark.asyncio
async def test_refresh_rotation_and_logout_revoke_tokens() -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        email="demo@example.com",
        full_name="Demo User",
        password_hash="ignored",
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.users.append(user)
    service = AuthenticationService(session)

    issued = await service.issue_token_pair(user)
    first_refresh = session.refresh_tokens[0]
    rotated = await service.refresh_access_pair(issued.refresh_token)

    assert first_refresh.revoked_at is not None
    assert rotated.refresh_token != issued.refresh_token
    assert len(session.refresh_tokens) == 2

    await service.logout_refresh_token(rotated.refresh_token)

    assert session.refresh_tokens[1].revoked_at is not None


@pytest.mark.asyncio
async def test_oauth_login_refuses_auto_link_when_email_already_exists() -> None:
    session = FakeSession()
    existing_user = User(
        id=uuid4(),
        email="demo@example.com",
        full_name="Existing User",
        password_hash="hashed-password",
        is_active=True,
        email_verified=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.users.append(existing_user)

    identity = OAuthIdentity(
        provider_user_id="oauth-123",
        email="demo@example.com",
        full_name="OAuth Demo",
        avatar_url="https://example.com/avatar.png",
        email_verified=True,
    )

    with pytest.raises(HTTPException) as error:
        await get_or_create_oauth_user(session, "github", identity)

    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_oauth_link_flow_links_provider_to_authenticated_user() -> None:
    session = FakeSession()
    user = User(
        id=uuid4(),
        email="demo@example.com",
        full_name="Demo User",
        password_hash="hashed-password",
        is_active=True,
        email_verified=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    session.users.append(user)
    identity = OAuthIdentity(
        provider_user_id="oauth-456",
        email="demo@example.com",
        full_name="Demo User",
        avatar_url="https://example.com/avatar.png",
        email_verified=True,
    )

    linked_user = await link_oauth_account_to_user(session, "google", identity, str(user.id))

    assert linked_user.id == user.id
    assert linked_user.email_verified is True
    assert len(session.oauth_accounts) == 1


@pytest.mark.asyncio
async def test_oauth_state_is_scoped_to_expected_flow(monkeypatch: pytest.MonkeyPatch) -> None:
    redis = FakeRedis()
    monkeypatch.setattr(oauth_service_module.settings, "github_client_id", "client-id")
    monkeypatch.setattr(oauth_service_module.settings, "github_client_secret", "client-secret")

    response = await build_authorization_url("github", redis, flow="link", user_id=str(uuid4()))

    assert "/auth/oauth/github/link/callback" in unquote(response.authorization_url)

    state_payload = await consume_oauth_state("github", response.state, redis, expected_flow="link")
    assert state_payload.flow == "link"
    assert state_payload.user_id is not None


def test_get_client_ip_ignores_forwarded_for_from_untrusted_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limiter_module.settings, "trust_proxy_headers", True)
    monkeypatch.setattr(rate_limiter_module.settings, "trusted_proxy_cidrs", ["10.0.0.0/8"])

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [(b"x-forwarded-for", b"198.51.100.25")],
            "client": ("203.0.113.10", 5000),
        }
    )

    assert get_client_ip(request) == "203.0.113.10"


@pytest.mark.asyncio
async def test_rate_limit_fails_closed_when_redis_is_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rate_limiter_module.settings, "rate_limit_fail_closed", True)
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/auth/login",
            "headers": [],
            "client": ("127.0.0.1", 5000),
            "app": SimpleNamespace(state=SimpleNamespace(redis=FailingRedis())),
        }
    )

    dependency = rate_limit("auth", 5, 60)
    with pytest.raises(HTTPException) as error:
        await dependency(request)

    assert error.value.status_code == 503