"""FastAPI entrypoint for the incident-analysis agent.

Alertmanager POSTs firing alerts to /alert. We acknowledge immediately (so
Alertmanager doesn't retry/time out) and process each alert in the background.
"""

import logging

from fastapi import BackgroundTasks, FastAPI

from .analyzer import handle_alert
from .config import settings
from .models import AlertGroup

logging.basicConfig(
    level=settings.log_level.upper(),
    format='{"level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}',
)
logger = logging.getLogger("agent")

app = FastAPI(title="AI Incident Analysis Agent", version="0.1.0")


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


@app.post("/alert")
async def alert(group: AlertGroup, background: BackgroundTasks):
    firing = [a for a in group.alerts if a.status == "firing"]
    logger.info("received %d alerts (%d firing)", len(group.alerts), len(firing))

    for a in firing:
        background.add_task(handle_alert, a)

    return {"received": len(group.alerts), "processing": len(firing)}
