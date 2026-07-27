"""Orchestration: turn one firing alert into an emailed root-cause analysis.

Flow:  alert -> "received" email -> collect read-only context -> LLM -> RCA email
"""

import logging

# The three building blocks this file wires together in order.
from . import mailer                      # sends the two emails
from .collector import collect_context    # gathers read-only evidence
from .llm import analyze                  # asks the LLM for the RCA
from .models import Alert

logger = logging.getLogger("agent.analyzer")


# Runs in the background for ONE alert. This is the whole pipeline.
def handle_alert(alert: Alert) -> None:
    # Alert name (e.g. "RedisDown") used for logs/subjects.
    name = alert.labels.get("alertname", "unknown")
    logger.info("handling alert: %s", name)

    # 1) Tell on-call immediately that we're investigating.
    mailer.send_alert_received(alert)

    # 2) Gather read-only evidence (pod status, events, logs, metrics).
    #    If it fails, keep going with an error note instead of crashing.
    try:
        context = collect_context(alert)
        logger.info("collected context for %s (%d chars)", name, len(context))
    except Exception as exc:  # noqa: BLE001
        logger.error("context collection failed for %s: %s", name, exc)
        context = f"[context collection failed: {exc}]"

    # 3) Ask the LLM to reason over that evidence.
    #    If the LLM fails, fall back to emailing the raw evidence.
    try:
        analysis = analyze(alert, context)
    except Exception as exc:  # noqa: BLE001
        logger.error("LLM analysis failed for %s: %s", name, exc)
        analysis = (
            f"Automated analysis could not be produced ({exc}).\n\n"
            f"Raw evidence collected:\n\n{context}"
        )

    # 4) Email the final root-cause analysis.
    mailer.send_analysis(alert, analysis)
    logger.info("done handling alert: %s", name)
