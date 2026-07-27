"""Prometheus metrics.

These are what Prometheus scrapes from /metrics and what our alerting rules
(and later the AI agent) reason about. Labels are kept low-cardinality on
purpose: we label by route *template* (e.g. "/{short_code}") rather than the
concrete path, otherwise every short code would create a new time series.
"""

# Counter = only goes up; Gauge = up/down; Histogram = buckets values (latency).
from prometheus_client import Counter, Gauge, Histogram

# Counter: total requests, sliced by method/route/status (set in the middleware).
http_requests_total = Counter(
    "http_requests_total", # name of the metric
    "Total HTTP requests processed.",  # this is like description of variable, when we hit /metrics it will show as #help: Total HTTP requests processed.
    ["method", "path", "status"],  # labels
) # converting to prometheus format

# Histogram: request latency in seconds, bucketed (for p95/p99 etc.).
http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "path"],
)

# Counter: how many short URLs we've created (bumped in /shorten).
urls_created_total = Counter(
    "urls_created_total",
    "Total number of short URLs created.",
)

# Counter: successful redirects served (bumped in /{short_code}).
redirects_total = Counter(
    "redirects_total",
    "Total successful redirects served.",
)

# Counter: lookups for codes that don't exist (bumped on a 404 redirect).
redirect_misses_total = Counter(
    "redirect_misses_total",
    "Total redirect lookups for unknown short codes.",
)

# Gauge: our custom dependency signal - 1=up, 0=down. Set by storage.ping();
# used by /readyz and the RedisDown alert rule.
redis_up = Gauge(
    "redis_up",
    "Whether the Redis dependency is reachable (1 = up, 0 = down).",
)
