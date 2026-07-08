"""FastAPI URL shortener.

Endpoints:
    POST /shorten          create a short code for a URL
    GET  /{short_code}     redirect to the original URL
    GET  /healthz          liveness  (process is up)
    GET  /readyz           readiness (Redis is reachable)
    GET  /metrics          Prometheus metrics
    GET  /                 service info

Design notes for the wider project:
- Liveness vs readiness are separated so Kubernetes can tell "the process is
  alive" apart from "the app can actually serve traffic". Killing the wrong one
  is a classic outage cause the agent should be able to explain.
- All request metrics are recorded in middleware using the matched route
  template to keep Prometheus cardinality bounded.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel, HttpUrl

from .config import settings
from .metrics import (
    http_request_duration_seconds,
    http_requests_total,
    redirect_misses_total,
    redirects_total,
    urls_created_total,
)
from .shortener import generate_code
from .storage import storage

logging.basicConfig(
    level=settings.log_level.upper(),
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger(settings.app_name)

RESERVED_PATHS = {"", "shorten", "healthz", "readyz", "metrics", "docs", "redoc", "openapi.json"}


class ShortenRequest(BaseModel):
    url: HttpUrl


class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str


@asynccontextmanager
async def _lifespan(app: FastAPI):
    storage.connect()
    logger.info("started app=%s redis=%s:%s", settings.app_name, settings.redis_host, settings.redis_port)
    yield
    await storage.close()
    logger.info("shutdown complete")


app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=_lifespan)


@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)

    http_requests_total.labels(request.method, path, response.status_code).inc()
    http_request_duration_seconds.labels(request.method, path).observe(duration)
    return response


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": app.version}


@app.get("/healthz")
async def healthz():
    """Liveness: the process is running. Must not depend on Redis."""
    return {"status": "ok"}


@app.get("/readyz")
async def readyz():
    """Readiness: we can actually serve traffic, i.e. Redis is reachable."""
    if await storage.ping():
        return {"status": "ready"}
    return JSONResponse(status_code=503, content={"status": "not ready", "reason": "redis unreachable"})


@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/shorten", response_model=ShortenResponse, status_code=201)
async def shorten(body: ShortenRequest):
    if not await storage.ping():
        raise HTTPException(status_code=503, detail="storage unavailable")

    code = None
    for _ in range(settings.max_code_generation_attempts):
        candidate = generate_code(settings.short_code_length)
        if not await storage.code_exists(candidate):
            code = candidate
            break
    if code is None:
        raise HTTPException(status_code=500, detail="could not allocate a unique short code")

    original_url = str(body.url)
    await storage.save_url(code, original_url)
    urls_created_total.inc()
    logger.info("created code=%s", code)

    return ShortenResponse(
        short_code=code,
        short_url=f"{settings.base_url.rstrip('/')}/{code}",
        original_url=original_url,
    )


@app.get("/{short_code}")
async def redirect(short_code: str):
    if short_code in RESERVED_PATHS:
        raise HTTPException(status_code=404, detail="not found")

    if not await storage.ping():
        raise HTTPException(status_code=503, detail="storage unavailable")

    url = await storage.get_url(short_code)
    if url is None:
        redirect_misses_total.inc()
        raise HTTPException(status_code=404, detail="short code not found")

    redirects_total.inc()
    return RedirectResponse(url=url, status_code=307)
