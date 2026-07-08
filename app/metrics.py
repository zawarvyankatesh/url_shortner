"""Prometheus metrics.

These are what Prometheus scrapes from /metrics and what our alerting rules
(and later the AI agent) reason about. Labels are kept low-cardinality on
purpose: we label by route *template* (e.g. "/{short_code}") rather than the
concrete path, otherwise every short code would create a new time series.
"""

from prometheus_client import Counter, Gauge, Histogram

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests processed.",
    ["method", "path", "status"],
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)

urls_created_total = Counter(
    "urls_created_total",
    "Total number of short URLs created.",
)

redirects_total = Counter(
    "redirects_total",
    "Total successful redirects served.",
)

redirect_misses_total = Counter(
    "redirect_misses_total",
    "Total redirect lookups for unknown short codes.",
)

redis_up = Gauge(
    "redis_up",
    "Whether the Redis dependency is reachable (1 = up, 0 = down).",
)
