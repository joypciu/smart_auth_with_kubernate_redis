from __future__ import annotations

from time import time
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query

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


@router.get("/prometheus-query")
async def prometheus_query(
    query: str = Query(..., min_length=1, max_length=512),
    start: float | None = None,
    end: float | None = None,
    step: str = Query(default="30s", max_length=16),
) -> dict[str, Any]:
    """Proxy Prometheus query_range to avoid browser CORS issues."""
    now = time()
    _end = end if end is not None else now
    _start = start if start is not None else now - 3600

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "http://prometheus:9090/api/v1/query_range",
                params={"query": query, "start": _start, "end": _end, "step": step},
                timeout=10.0,
            )
        return resp.json()
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail=f"Prometheus unreachable: {exc}") from exc