"""Pydantic models for the Alertmanager webhook payload.

Only the fields we use are modelled; extras are ignored.
"""

from pydantic import BaseModel, ConfigDict


class Alert(BaseModel):
    model_config = ConfigDict(extra="ignore")

    status: str = "firing"
    labels: dict[str, str] = {}
    annotations: dict[str, str] = {}
    startsAt: str | None = None
    endsAt: str | None = None
    generatorURL: str | None = None


class AlertGroup(BaseModel):
    model_config = ConfigDict(extra="ignore")

    version: str | None = None
    status: str | None = None
    receiver: str | None = None
    groupLabels: dict[str, str] = {}
    commonLabels: dict[str, str] = {}
    commonAnnotations: dict[str, str] = {}
    alerts: list[Alert] = []
