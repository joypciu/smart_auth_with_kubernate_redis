from __future__ import annotations

from time import perf_counter
from uuid import uuid4

import structlog
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.core.metrics import REQUEST_COUNT, REQUEST_DURATION, REQUEST_EXCEPTIONS


def _route_path(request: Request) -> str:
    route = request.scope.get("route")
    if route is not None and getattr(route, "path", None):
        return route.path
    return request.url.path


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get("x-request-id", str(uuid4()))
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        logger = structlog.get_logger("app.request")
        start_time = perf_counter()
        response: Response | None = None

        try:
            response = await call_next(request)
            return response
        except Exception as error:
            route_path = _route_path(request)
            if route_path != "/metrics":
                REQUEST_EXCEPTIONS.labels(
                    method=request.method,
                    path=route_path,
                    exception_type=error.__class__.__name__,
                ).inc()
            logger.exception("request_failed")
            raise
        finally:
            route_path = _route_path(request)
            status_code = response.status_code if response is not None else 500
            duration_seconds = perf_counter() - start_time

            if route_path != "/metrics":
                REQUEST_COUNT.labels(
                    method=request.method,
                    path=route_path,
                    status=str(status_code),
                ).inc()
                REQUEST_DURATION.labels(
                    method=request.method,
                    path=route_path,
                ).observe(duration_seconds)

            if response is not None:
                response.headers["X-Request-ID"] = request_id

            logger.info(
                "request_completed",
                status_code=status_code,
                duration_ms=round(duration_seconds * 1000, 2),
                route=route_path,
            )
            structlog.contextvars.clear_contextvars()
