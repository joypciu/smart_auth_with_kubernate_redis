from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, create_refresh_token, decode_token, hash_password, verify_password
from app.models.user import RefreshToken, User
from app.repositories.auth import RefreshTokenRepository, UserRepository
from app.schemas.auth import RegisterRequest, TokenResponse
from app.schemas.user import UserRead


class AuthenticationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.refresh_tokens = RefreshTokenRepository(db)

    async def register_user(self, payload: RegisterRequest) -> User:
        email = payload.email.lower()
        existing_user = await self.users.get_by_email(email)
        if existing_user is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email is already registered")

        user = User(
            email=email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
            email_verified=False,
        )
        self.users.add(user)
        await self.db.commit()
        await self.users.refresh(user)
        return user

    async def authenticate_user(self, email: str, password: str) -> User:
        user = await self.users.get_by_email(email.lower())
        if user is None or not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")
        return user

    async def issue_token_pair(self, user: User) -> TokenResponse:
        access_token, access_expires_at = create_access_token(str(user.id))
        refresh_token, refresh_jti, refresh_expires_at = create_refresh_token(str(user.id))

        self.refresh_tokens.add(
            RefreshToken(
                user_id=user.id,
                jti=refresh_jti,
                expires_at=refresh_expires_at,
            )
        )
        await self.db.commit()

        expires_in = int((access_expires_at - datetime.now(timezone.utc)).total_seconds())
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=max(expires_in, 1),
            user=UserRead.model_validate(user),
        )

    async def refresh_access_pair(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = payload.get("jti")
        subject = payload.get("sub")
        if not jti or not subject:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")

        refresh_record = await self.refresh_tokens.get_with_user(jti)
        if refresh_record is None or refresh_record.revoked_at is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has been revoked")
        if refresh_record.expires_at <= datetime.now(timezone.utc):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token has expired")
        if str(refresh_record.user_id) != subject:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token subject mismatch")
        if not refresh_record.user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User account is inactive")

        self.refresh_tokens.revoke(refresh_record, datetime.now(timezone.utc))
        await self.db.commit()
        return await self.issue_token_pair(refresh_record.user)

    async def logout_refresh_token(self, refresh_token: str) -> None:
        payload = decode_token(refresh_token, expected_type="refresh")
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token payload")

        refresh_record = await self.refresh_tokens.get_by_jti(jti)
        if refresh_record is None:
            return

        self.refresh_tokens.revoke(refresh_record, datetime.now(timezone.utc))
        await self.db.commit()


async def register_user(db: AsyncSession, payload: RegisterRequest) -> User:
    return await AuthenticationService(db).register_user(payload)


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User:
    return await AuthenticationService(db).authenticate_user(email, password)


async def issue_token_pair(db: AsyncSession, user: User) -> TokenResponse:
    return await AuthenticationService(db).issue_token_pair(user)


async def refresh_access_pair(db: AsyncSession, refresh_token: str) -> TokenResponse:
    return await AuthenticationService(db).refresh_access_pair(refresh_token)


async def logout_refresh_token(db: AsyncSession, refresh_token: str) -> None:
    await AuthenticationService(db).logout_refresh_token(refresh_token)
