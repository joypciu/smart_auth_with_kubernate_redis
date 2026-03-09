from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import OAuthAccount, RefreshToken, User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_email(self, email: str) -> User | None:
        return await self.session.scalar(select(User).where(User.email == email))

    async def get_by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    def add(self, user: User) -> None:
        self.session.add(user)

    async def flush(self) -> None:
        await self.session.flush()

    async def refresh(self, user: User) -> None:
        await self.session.refresh(user)


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def add(self, refresh_token: RefreshToken) -> None:
        self.session.add(refresh_token)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        return await self.session.scalar(select(RefreshToken).where(RefreshToken.jti == jti))

    async def get_with_user(self, jti: str) -> RefreshToken | None:
        return await self.session.scalar(
            select(RefreshToken)
            .options(selectinload(RefreshToken.user))
            .where(RefreshToken.jti == jti)
        )

    @staticmethod
    def revoke(refresh_token: RefreshToken, revoked_at: datetime) -> None:
        refresh_token.revoked_at = revoked_at


class OAuthAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider_identity(self, provider: str, provider_user_id: str) -> OAuthAccount | None:
        return await self.session.scalar(
            select(OAuthAccount).where(
                OAuthAccount.provider == provider,
                OAuthAccount.provider_user_id == provider_user_id,
            )
        )

    def add(self, oauth_account: OAuthAccount) -> None:
        self.session.add(oauth_account)
