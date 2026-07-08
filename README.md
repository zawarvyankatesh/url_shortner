# URL Shortener

A small, production-shaped FastAPI URL shortener backed by Redis. It is the
sample workload for an AI incident-analysis project: it exposes Prometheus
metrics and clean liveness/readiness probes, and is easy to break in realistic
ways (dependency down, OOM, bad config) so an AI agent can later investigate
those failures on Kubernetes.

## Features

- `POST /shorten` — create a short code for a URL
- `GET /{short_code}` — 307 redirect to the original URL
- `GET /healthz` — liveness (process up; independent of Redis)
- `GET /readyz` — readiness (returns 503 when Redis is unreachable)
- `GET /metrics` — Prometheus metrics
- Multi-stage Dockerfile, runs as non-root

## Tech stack

- Python 3.12, FastAPI, Uvicorn
- Redis (via `redis.asyncio`)
- `prometheus-client` for metrics
- `pydantic-settings` for env-based config

## Run locally

```bash
# 1. start Redis (Docker)
make redis

# 2. install deps and run
make dev
make run
```

Then:

```bash
curl -X POST localhost:8000/shorten -H 'content-type: application/json' \
  -d '{"url":"https://example.com/some/long/path"}'
# -> {"short_code":"Ab3xK9p","short_url":"http://localhost:8000/Ab3xK9p", ...}

curl -i localhost:8000/Ab3xK9p        # 307 redirect
curl localhost:8000/readyz            # readiness
curl localhost:8000/metrics           # prometheus metrics
```

## Test

```bash
make dev
make test
```

Tests use `fakeredis`, so no running Redis is required.

## Docker

```bash
make docker-build          # builds url-shortener:local
make docker-run            # needs a reachable Redis (see .env)
```

Your CI pipeline builds this `Dockerfile` on push and publishes the image to
Docker Hub.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable            | Default                 | Description                          |
| ------------------- | ----------------------- | ------------------------------------ |
| `REDIS_HOST`        | `localhost`             | Redis host                           |
| `REDIS_PORT`        | `6379`                  | Redis port                           |
| `REDIS_PASSWORD`    | _(unset)_               | Redis password (optional)            |
| `BASE_URL`          | `http://localhost:8000` | Base URL used in the short link      |
| `SHORT_CODE_LENGTH` | `7`                     | Length of generated short codes      |
| `LOG_LEVEL`         | `INFO`                  | Log level                            |

## Project roadmap

1. **This repo** — the app + Docker image (done).
2. Deploy to Kubernetes (kind → EKS) with Redis.
3. Add Prometheus + Alertmanager monitoring and alert rules.
4. Add the read-only AI incident-analysis agent that investigates alerts and
   emails a root-cause summary.
