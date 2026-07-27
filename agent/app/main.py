"""FastAPI entrypoint for the incident-analysis agent.

Alertmanager POSTs firing alerts to /alert. We acknowledge immediately (so
Alertmanager doesn't retry/time out) and process each alert in the background.
"""

import logging

from fastapi import BackgroundTasks, FastAPI

# The full pipeline for one alert (mail -> collect -> LLM -> mail) lives here.
from .analyzer import handle_alert
from .config import settings
# The shape of the JSON Alertmanager POSTs to us.
from .models import AlertGroup

# Configure JSON logs at the level from config, then get our named logger.
logging.basicConfig(
    level=settings.log_level.upper(),
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("agent")

# The web server object; uvicorn runs this ("app.main:app").
app = FastAPI(title="AI Incident Analysis Agent", version="0.1.0")


# Liveness probe: K8s hits this to check the process is alive.
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# The webhook Alertmanager calls. FastAPI validates the body into AlertGroup.
@app.post("/alert")
async def alert(group: AlertGroup, background: BackgroundTasks):
    # We only act on alerts that are currently firing (ignore "resolved").
    firing = [a for a in group.alerts if a.status == "firing"]
    logger.info("received %d alerts (%d firing)", len(group.alerts), len(firing))

    # Hand each alert to a background task so we can reply instantly (no timeout).
    for a in firing:
        background.add_task(handle_alert, a)

    # Immediate 200 ack; the real work continues in the background.
    return {"received": len(group.alerts), "processing": len(firing)}
