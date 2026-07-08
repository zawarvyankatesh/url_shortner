"""Read-only context collector.

Given an alert, gather evidence from the Kubernetes API and Prometheus. This is
deterministic code - the LLM never runs anything here. The agent's Kubernetes
RBAC is read-only (get/list), so nothing in this module can modify the cluster.
"""

import logging

import httpx
from kubernetes import client, config

from .config import settings
from .models import Alert

logger = logging.getLogger("agent.collector")


def _init_k8s() -> None:
    try:
        config.load_incluster_config()
        logger.info("loaded in-cluster kube config")
    except Exception:
        config.load_kube_config()
        logger.info("loaded local kube config")


_init_k8s()
_core = client.CoreV1Api()
_apps = client.AppsV1Api()


def _safe(fn, description: str) -> str:
    """Run a collector call, returning its result or an error note as text."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - we want to report any failure to the LLM
        logger.warning("collector step failed (%s): %s", description, exc)
        return f"[could not collect {description}: {exc}]"


def _pod_summary(namespace: str, pod: str) -> str:
    def _fn() -> str:
        p = _core.read_namespaced_pod(name=pod, namespace=namespace)
        lines = [
            f"name: {p.metadata.name}",
            f"phase: {p.status.phase}",
            f"node: {p.spec.node_name}",
            f"start_time: {p.status.start_time}",
        ]
        for cs in p.status.container_statuses or []:
            lines.append(
                f"container '{cs.name}': ready={cs.ready} restarts={cs.restart_count} image={cs.image}"
            )
            state = cs.state
            if state and state.waiting:
                lines.append(f"  waiting: reason={state.waiting.reason} message={state.waiting.message}")
            if state and state.terminated:
                lines.append(
                    f"  terminated: reason={state.terminated.reason} exit_code={state.terminated.exit_code}"
                )
            last = cs.last_state
            if last and last.terminated:
                lines.append(
                    f"  last_terminated: reason={last.terminated.reason} exit_code={last.terminated.exit_code}"
                )
        # resource requests/limits
        for c in p.spec.containers:
            res = c.resources
            if res:
                lines.append(f"container '{c.name}' resources: requests={res.requests} limits={res.limits}")
        return "\n".join(lines)

    return _safe(_fn, "pod summary")


def _pod_events(namespace: str, pod: str) -> str:
    def _fn() -> str:
        events = _core.list_namespaced_event(
            namespace=namespace, field_selector=f"involvedObject.name={pod}"
        )
        if not events.items:
            return "[no events]"
        rows = []
        for e in sorted(events.items, key=lambda x: x.last_timestamp or x.event_time or 0):
            rows.append(f"{e.last_timestamp} {e.type} {e.reason}: {e.message}")
        return "\n".join(rows[-20:])

    return _safe(_fn, "pod events")


def _pod_logs(namespace: str, pod: str, previous: bool) -> str:
    label = "previous (crashed) container logs" if previous else "current logs"

    def _fn() -> str:
        logs = _core.read_namespaced_pod_log(
            name=pod,
            namespace=namespace,
            tail_lines=settings.log_tail_lines,
            previous=previous,
        )
        return logs.strip() or f"[{label}: empty]"

    return _safe(_fn, label)


def _namespace_pods(namespace: str) -> str:
    def _fn() -> str:
        pods = _core.list_namespaced_pod(namespace=namespace)
        rows = []
        for p in pods.items:
            restarts = sum((cs.restart_count or 0) for cs in (p.status.container_statuses or []))
            ready = all(cs.ready for cs in (p.status.container_statuses or [])) if p.status.container_statuses else False
            rows.append(f"{p.metadata.name}: phase={p.status.phase} ready={ready} restarts={restarts}")
        return "\n".join(rows) or "[no pods]"

    return _safe(_fn, "namespace pod list")


def _prometheus_query(query: str) -> str:
    def _fn() -> str:
        with httpx.Client(timeout=15) as c:
            r = c.get(f"{settings.prometheus_url}/api/v1/query", params={"query": query})
            r.raise_for_status()
            data = r.json().get("data", {}).get("result", [])
            if not data:
                return f"{query} => (no data)"
            out = []
            for series in data[:10]:
                metric = series.get("metric", {})
                value = series.get("value", ["", ""])[1]
                labels = ",".join(f"{k}={v}" for k, v in metric.items() if k != "__name__")
                out.append(f"{query} {{{labels}}} => {value}")
            return "\n".join(out)

    return _safe(_fn, f"prometheus query '{query}'")


def collect_context(alert: Alert) -> str:
    """Return a human-readable evidence bundle for the given alert."""
    labels = alert.labels
    namespace = labels.get("namespace")
    pod = labels.get("pod")
    app = labels.get("app")

    sections: list[str] = []

    if namespace and pod:
        sections.append(f"=== POD SUMMARY ({namespace}/{pod}) ===\n{_pod_summary(namespace, pod)}")
        sections.append(f"=== POD EVENTS ===\n{_pod_events(namespace, pod)}")
        sections.append(f"=== CURRENT LOGS ===\n{_pod_logs(namespace, pod, previous=False)}")
        sections.append(f"=== PREVIOUS (CRASHED) LOGS ===\n{_pod_logs(namespace, pod, previous=True)}")
    elif namespace:
        sections.append(f"=== PODS IN NAMESPACE '{namespace}' ===\n{_namespace_pods(namespace)}")

    # Relevant Prometheus signals (bounded, read-only).
    metric_queries = []
    if app:
        metric_queries.append(f'up{{app="{app}"}}')
    metric_queries.append("redis_up")
    if namespace:
        metric_queries.append(
            f'kube_pod_container_status_restarts_total{{namespace="{namespace}"}}'
        )
    prom = "\n".join(_prometheus_query(q) for q in metric_queries)
    sections.append(f"=== PROMETHEUS SIGNALS ===\n{prom}")

    return "\n\n".join(sections)
