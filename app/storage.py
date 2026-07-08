"""Redis storage layer.

The Redis client is created lazily (no socket is opened until the first
command), so the app can start even when Redis is down. That is intentional:
the process comes up, the liveness probe passes, but the readiness probe fails
until Redis is reachable. This produces a realistic "dependency down" scenario
for the incident-analysis agent to diagnose.
"""

import redis.asyncio as redis

from .config import settings
from .metrics import redis_up

URL_KEY_PREFIX = "url:"
STATS_TOTAL_KEY = "stats:total_urls"


class Storage:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    def connect(self) -> None:
        """Instantiate the Redis client (does not open a connection yet)."""
        self._client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True,
            socket_connect_timeout=settings.redis_connect_timeout,
            socket_timeout=settings.redis_connect_timeout,
        )

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Storage.connect() must be called first")
        return self._client

    async def ping(self) -> bool:
        """Return True if Redis responds to PING, updating the redis_up gauge."""
        try:
            await self.client.ping()
            redis_up.set(1)
            return True
        except Exception:
            redis_up.set(0)
            return False

    async def save_url(self, code: str, url: str) -> None:
        await self.client.set(f"{URL_KEY_PREFIX}{code}", url)
        await self.client.incr(STATS_TOTAL_KEY)

    async def get_url(self, code: str) -> str | None:
        return await self.client.get(f"{URL_KEY_PREFIX}{code}")

    async def code_exists(self, code: str) -> bool:
        return bool(await self.client.exists(f"{URL_KEY_PREFIX}{code}"))


storage = Storage()
