from __future__ import annotations

from time import time
from typing import Any

from fastapi import APIRouter

from app.core.config import settings
from app.core.metrics import APP_STARTED_AT, get_http_metrics_snapshot

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/overview")
async def system_overview() -> dict[str, Any]:
    metrics = get_http_metrics_snapshot()

    return {
        "service": {
            "name": settings.app_name,
            "status": "healthy",
            "environment": settings.app_env,
            "version": "0.1.0",
            "debug": settings.debug,
            "uptime_seconds": max(0, int(time() - APP_STARTED_AT)),
            "api_prefix": settings.api_v1_prefix,
        },
        "security": {
            "access_token_expire_minutes": settings.access_token_expire_minutes,
            "refresh_token_expire_days": settings.refresh_token_expire_days,
            "rate_limit_auth_requests": settings.rate_limit_auth_requests,
            "rate_limit_auth_window_seconds": settings.rate_limit_auth_window_seconds,
            "cors_origins": settings.cors_origins,
        },
        "oauth": {
            "google_configured": bool(settings.google_client_id and settings.google_client_secret),
            "github_configured": bool(settings.github_client_id and settings.github_client_secret),
        },
        "links": {
            "docs": "/docs",
            "health": f"{settings.api_v1_prefix}/health",
            "metrics": "/metrics",
            "prometheus": settings.prometheus_public_url,
            "grafana": settings.grafana_public_url,
        },
        "traffic": metrics,
    }