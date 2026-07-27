"""Pydantic models for the Alertmanager webhook payload.

Only the fields we use are modelled; extras are ignored.
"""

from pydantic import BaseModel, ConfigDict


# One single alert (one row in the JSON Alertmanager sends us).
class Alert(BaseModel):
    # Ignore any extra fields Alertmanager sends that we don't model here.
    model_config = ConfigDict(extra="ignore")

    status: str = "firing"              # "firing" or "resolved"
    labels: dict[str, str] = {}         # who/what: alertname, severity, namespace, pod, app
    annotations: dict[str, str] = {}    # human text: summary, description
    startsAt: str | None = None         # when it started firing
    endsAt: str | None = None           # when it resolved (if any)
    generatorURL: str | None = None     # link back to the Prometheus expression


# The whole webhook payload: Alertmanager batches many alerts into one POST.
class AlertGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str | None = None
    status: str | None = None
    receiver: str | None = None
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}
    alerts: list[Alert] = []            # the list of alerts we actually loop over
