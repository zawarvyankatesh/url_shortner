"""Redis storage layer.

The Redis client is created lazily (no socket is opened until the first
command), so the app can start even when Redis is down. That is intentional:
the process comes up, the liveness probe passes, but the readiness probe fails
until Redis is reachable. This produces a realistic "dependency down" scenario
for the incident-analysis agent to diagnose.
"""

import redis.asyncio as redis  # async Redis client (non-blocking calls)

from .config import settings
from .metrics import redis_up

# Key prefixes keep our data namespaced inside Redis.
URL_KEY_PREFIX = "url:"            # e.g. "url:aB3xK9p" -> the original URL
STATS_TOTAL_KEY = "stats:total_urls"


# Wraps all Redis access so the rest of the app never touches Redis directly.
class Storage:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None   # not connected until connect()

    def connect(self) -> None:
        """Instantiate the Redis client (does not open a connection yet)."""
        # Lazy: this just builds the client object; the socket opens on first command.
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,                          # return str, not bytes
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_connect_timeout,
        )

    async def close(self) -> None:
        # Cleanly shut the connection on app shutdown.
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        # Guard: fail loudly if we forgot to call connect() first.
        if self._client is None:
            raise RuntimeError("Storage.connect() must be called first")
        return self._client

    async def ping(self) -> bool:
        """Return True if Redis responds to PING, updating the redis_up gauge."""
        # This both checks health AND updates the metric used by /readyz and alerts.
        try:
            await self.client.ping()
            redis_up.set(1)   # gauge -> 1 (up)
            return True
        except Exception:
            redis_up.set(0)   # gauge -> 0 (down)
            return False

    async def save_url(self, code: str, url: str) -> None:
        # Store the mapping and increment the total-URLs counter in Redis.
        await self.client.set(f"{URL_KEY_PREFIX}{code}", url)
        await self.client.incr(STATS_TOTAL_KEY)

    async def get_url(self, code: str) -> str | None:
        # Look up the original URL for a code (None if missing).
        return await self.client.get(f"{URL_KEY_PREFIX}{code}")

    async def code_exists(self, code: str) -> bool:
        # Used by /shorten to avoid reusing an existing code.
        return bool(await self.client.exists(f"{URL_KEY_PREFIX}{code}"))


# One shared Storage instance the whole app imports.
storage = Storage()
 
