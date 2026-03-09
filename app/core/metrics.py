from __future__ import annotations

from collections import defaultdict
from time import time
from typing import Any

from prometheus_client import Counter, Histogram

APP_STARTED_AT = time()

REQUEST_COUNT = Counter(
    "smart_auth_http_requests_total",
    "Total HTTP requests handled by the API",
    ["method", "path", "status"],
)

REQUEST_DURATION = Histogram(
    "smart_auth_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

REQUEST_EXCEPTIONS = Counter(
    "smart_auth_http_exceptions_total",
    "Unhandled HTTP exceptions raised by the API",
    ["method", "path", "exception_type"],
)


def get_http_metrics_snapshot() -> dict[str, Any]:
    requests_by_status: dict[str, int] = defaultdict(int)
    requests_by_route: dict[str, int] = defaultdict(int)
    total_requests = 0
    duration_sum = 0.0
    duration_count = 0
    exception_count = 0

    for metric in REQUEST_COUNT.collect():
        for sample in metric.samples:
            if sample.name != "smart_auth_http_requests_total":
                continue
            value = int(sample.value)
            total_requests += value
            status = sample.labels.get("status", "unknown")
            path = sample.labels.get("path", "unknown")
            requests_by_status[status] += value
            requests_by_route[path] += value

    for metric in REQUEST_DURATION.collect():
        for sample in metric.samples:
            if sample.name == "smart_auth_http_request_duration_seconds_sum":
                duration_sum += float(sample.value)
            elif sample.name == "smart_auth_http_request_duration_seconds_count":
                duration_count += int(sample.value)

    for metric in REQUEST_EXCEPTIONS.collect():
        for sample in metric.samples:
            if sample.name != "smart_auth_http_exceptions_total":
                continue
            exception_count += int(sample.value)

    success_responses = sum(count for status, count in requests_by_status.items() if status.startswith("2"))
    client_error_responses = sum(count for status, count in requests_by_status.items() if status.startswith("4"))
    server_error_responses = sum(count for status, count in requests_by_status.items() if status.startswith("5"))
    average_latency_ms = round((duration_sum / duration_count) * 1000, 2) if duration_count else 0.0
    top_routes = [
        {"path": path, "requests": count}
        for path, count in sorted(requests_by_route.items(), key=lambda item: item[1], reverse=True)[:6]
    ]

    return {
        "total_requests": total_requests,
        "success_responses": success_responses,
        "client_error_responses": client_error_responses,
        "server_error_responses": server_error_responses,
        "exception_count": exception_count,
        "average_latency_ms": average_latency_ms,
        "top_routes": top_routes,
    }
