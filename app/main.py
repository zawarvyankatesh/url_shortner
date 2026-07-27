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
from contextlib import asynccontextmanager  # used to build the startup/shutdown lifespan

# FastAPI core + response types we return from handlers.
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
# Helpers to render metrics in the exact text format Prometheus expects.
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
# BaseModel = request/response schemas; HttpUrl = auto-validates URLs.
from pydantic import BaseModel, HttpUrl

# this is like import from config.py file which has all the settings/ config of application
from .config import settings
# this is like import from metrics.py file which has all the metrics of application . this metrics will be used to collect metrics of application for prometheus to scrape and store in its database
from .metrics import (
    http_request_duration_seconds,
    http_requests_total,
    redirect_misses_total,
    redirects_total,
    urls_created_total,
)
# this is like import from shortener.py file which has all the logic of generating short code for the original url
from .shortener import generate_code
# this is like import from storage.py file which has all the logic of storing the original url and short code in the database. this file is responsible to communicate with the redis db, get, set, ping in redis.
from .storage import storage

#Configure logging globally (once, at startup)
logging.basicConfig(
    #Set minimum level from config (INFO by default), normalized with .upper()
    level=settings.log_level.upper(),
    #Format each line as JSON for machine-parseable structured logging
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
#Create a named logger (app_name) so logs are attributed to this component
logger = logging.getLogger(settings.app_name)

#setup for low cardinality paths, except this paths all are stored in prometheus as short_code
RESERVED_PATHS = {"", "shorten", "healthz", "readyz", "metrics", "docs", "redoc", "openapi.json"}

#fast api feature 
# Input model: the JSON body of POST /shorten. HttpUrl rejects bad URLs with 422.
class ShortenRequest(BaseModel):
    url: HttpUrl


# Output model: the JSON we send back (guarantees the response shape).
class ShortenResponse(BaseModel):
    short_code: str
    short_url: str
    original_url: str


# Startup/shutdown hook: code before `yield` runs once at boot, code after at exit.
@asynccontextmanager
async def _lifespan(app: FastAPI):
    storage.connect()   # create the Redis client at startup (no socket opened yet)
    logger.info("started app=%s redis=%s:%s", settings.app_name, settings.redis_host, settings.redis_port)
    yield               # <-- app serves requests while paused here
    await storage.close()   # clean up the Redis connection on shutdown
    logger.info("shutdown complete")


# The web server object; uvicorn runs this. lifespan wires in the hook above.
app = FastAPI(title="URL Shortener", version="0.1.0", lifespan=_lifespan)

# this below code is most imp. every http req goes from here and call_next proccess the req ahead
@app.middleware("http")
async def record_metrics(request: Request, call_next):
    start = time.perf_counter()            # start the timer
    response = await call_next(request)    # run the actual endpoint
    duration = time.perf_counter() - start # how long it took

    # Use the route TEMPLATE (e.g. "/{short_code}") not the real path, to keep
    # Prometheus cardinality low (one series per route, not per short code).
    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)

    # Record one count + one latency observation for this request.
    http_requests_total.labels(request.method, path, response.status_code).inc()
    http_request_duration_seconds.labels(request.method, path).observe(duration)
    return response


# Simple info endpoint at the root URL.
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


# The endpoint Prometheus scrapes: dumps all metrics in its text format.
@app.get("/metrics")
async def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Create a short code for a URL. body is validated against ShortenRequest.
@app.post("/shorten", response_model=ShortenResponse, status_code=201)
async def shorten(body: ShortenRequest):
    # Can't store anything if Redis is down -> 503.
    if not await storage.ping():
        raise HTTPException(status_code=503, detail="storage unavailable")

    # Generate a code and retry until we find one not already used (avoid collisions).
    code = None
    for _ in range(settings.max_code_generation_attempts):
        candidate = generate_code(settings.short_code_length)
        if not await storage.code_exists(candidate):
            code = candidate
            break
    # Extremely unlikely, but if every attempt collided, fail clearly.
    if code is None:
        raise HTTPException(status_code=500, detail="could not allocate a unique short code")

    # Save the mapping in Redis and bump the "urls created" counter.
    original_url = str(body.url)
    await storage.save_url(code, original_url)
    urls_created_total.inc()
    logger.info("created code=%s", code)

    # Return the short code + full short URL as JSON.
    return ShortenResponse(
        short_code=code,
        short_url=f"{settings.base_url.rstrip('/')}/{code}",
        original_url=original_url,
    )


# Look up a short code and redirect to the original URL. Must be the LAST route
# (it matches any single path segment).
@app.get("/{short_code}")
async def redirect(short_code: str):
    # Don't treat our own endpoints (/healthz, /metrics...) as short codes.
    if short_code in RESERVED_PATHS:
        raise HTTPException(status_code=404, detail="not found")

    if not await storage.ping():
        raise HTTPException(status_code=503, detail="storage unavailable")

    # Fetch the original URL; count a miss + 404 if the code is unknown.
    url = await storage.get_url(short_code)
    if url is None:
        redirect_misses_total.inc()
        raise HTTPException(status_code=404, detail="short code not found")

    # Found it: 307 redirect to the original URL.
    redirects_total.inc()
    return RedirectResponse(url=url, status_code=307)
