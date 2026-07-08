"""Orchestration: turn one firing alert into an emailed root-cause analysis.

Flow:  alert -> "received" email -> collect read-only context -> LLM -> RCA email
"""

import logging

from . import mailer
from .collector import collect_context
from .llm import analyze
from .models import Alert

logger = logging.getLogger("agent.analyzer")


def handle_alert(alert: Alert) -> None:
    name = alert.labels.get("alertname", "unknown")
    logger.info("handling alert: %s", name)

    # 1) immediate notification
    mailer.send_alert_received(alert)

    # 2) gather read-only evidence
    try:
        context = collect_context(alert)
        logger.info("collected context for %s (%d chars)", name, len(context))
    except Exception as exc:  # noqa: BLE001
        logger.error("context collection failed for %s: %s", name, exc)
        context = f"[context collection failed: {exc}]"

    # 3) LLM analysis
    try:
        analysis = analyze(alert, context)
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM analysis failed for %s: %s", name, exc)
        analysis = (
            f"Automated analysis could not be produced ({exc}).\n\n"
            f"Raw evidence collected:\n\n{context}"
        )

    # 4) deliver the analysis
    mailer.send_analysis(alert, analysis)
    logger.info("done handling alert: %s", name)
