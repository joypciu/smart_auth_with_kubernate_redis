from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client is None:
        return "unknown"
    return request.client.host


def rate_limit(scope: str, max_requests: int, window_seconds: int) -> Callable[[Request], Awaitable[None]]:
    async def dependency(request: Request) -> None:
        redis = request.app.state.redis
        identifier = get_client_ip(request)
        key = f"ratelimit:{scope}:{identifier}"

        try:
            current_count = await redis.incr(key)
            if current_count == 1:
                await redis.expire(key, window_seconds)
            if current_count > max_requests:
                retry_after = await redis.ttl(key)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail={
                        "message": "Too many requests. Try again later.",
                        "retry_after_seconds": max(retry_after, 0),
                    },
                )
        except RedisError:
            return

    return dependency
