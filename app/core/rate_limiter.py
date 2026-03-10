from __future__ import annotations

from collections.abc import Awaitable, Callable
from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request, status
from redis.exceptions import RedisError
import structlog

from app.core.config import settings

logger = structlog.get_logger(__name__)


def _is_trusted_proxy(request: Request) -> bool:
    if not settings.trust_proxy_headers or request.client is None:
        return False

    try:
        proxy_ip = ip_address(request.client.host)
    except ValueError:
        return False

    for cidr in settings.trusted_proxy_cidrs:
        try:
            if proxy_ip in ip_network(cidr, strict=False):
                return True
        except ValueError:
            continue

    return False


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for and _is_trusted_proxy(request):
        candidate = forwarded_for.split(",")[0].strip()
        try:
            ip_address(candidate)
            return candidate
        except ValueError:
            logger.warning("invalid_forwarded_for_header", forwarded_for=forwarded_for)
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
            logger.warning("rate_limiter_backend_unavailable", scope=scope)
            if settings.rate_limit_fail_closed:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Authentication is temporarily unavailable. Please try again shortly.",
                )
            return

    return dependency
