import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.storage import storage


@pytest.fixture
def client():
    with TestClient(app) as c:
        # Replace the real (lazy) Redis client with an in-memory fake so tests
        # need no running Redis.
        storage._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        yield c


def test_healthz_is_independent_of_redis(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_ok_when_redis_up(client):
    resp = client.get("/readyz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_shorten_then_redirect_roundtrip(client):
    resp = client.post("/shorten", json={"url": "https://example.com/some/long/path"})
    assert resp.status_code == 201
    body = resp.json()
    code = body["short_code"]
    assert body["original_url"] == "https://example.com/some/long/path"

    resp = client.get(f"/{code}", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "https://example.com/some/long/path"


def test_shorten_rejects_invalid_url(client):
    resp = client.post("/shorten", json={"url": "not-a-url"})
    assert resp.status_code == 422


def test_unknown_code_returns_404(client):
    resp = client.get("/doesnotexist", follow_redirects=False)
    assert resp.status_code == 404


def test_metrics_endpoint_exposes_prometheus(client):
    client.post("/shorten", json={"url": "https://example.com"})
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "urls_created_total" in resp.text
