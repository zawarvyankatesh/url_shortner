"""Read-only context collector.

Given an alert, gather evidence from the Kubernetes API and Prometheus. This is
deterministic code - the LLM never runs anything here. The agent's Kubernetes
RBAC is read-only (get/list), so nothing in this module can modify the cluster.
"""

import logging

import httpx                                # plain HTTP client (used for Prometheus)
from kubernetes import client, config       # official Kubernetes API client

from .config import settings
from .models import Alert

logger = logging.getLogger("agent.collector")


# Authenticate to the Kubernetes API. This is "who am I", not "what can I do"
# (permissions are enforced separately by RBAC = get/list only).
def _init_k8s() -> None:
    try:
        # Inside the cluster: use the pod's mounted ServiceAccount token.
        config.load_incluster_config()
        logger.info("loaded in-cluster kube config")
    except Exception:
        # On a laptop: fall back to ~/.kube/config so the same code runs locally.
        config.load_kube_config()
        logger.info("loaded local kube config")


_init_k8s()
_core = client.CoreV1Api()   # core objects: pods, logs, events, nodes
_apps = client.AppsV1Api()   # apps objects: deployments, replicasets (reserved for later)


# Wrapper so one failing step becomes a text note instead of crashing the whole
# collection. We always want to hand the LLM whatever evidence we could gather.
def _safe(fn, description: str) -> str:
    """Run a collector call, returning its result or an error note as text."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001 - we want to report any failure to the LLM
        logger.warning("collector step failed (%s): %s", description, exc)
        return f"[could not collect {description}: {exc}]"


# Read ONE pod and summarize its health (like "kubectl describe pod", trimmed).
def _pod_summary(namespace: str, pod: str) -> str:
    def _fn() -> str:
        # GET the pod object from the API.
        p = _core.read_namespaced_pod(name=pod, namespace=namespace)
        # Top-level facts: phase, which node, when it started.
        lines = [
            f"name: {p.metadata.name}",
            f"phase: {p.status.phase}",
            f"node: {p.spec.node_name}",
            f"start_time: {p.status.start_time}",
        ]
        # Per-container health - the most useful signals for an incident.
        for cs in p.status.container_statuses or []:
            lines.append(
                f"container '{cs.name}': ready={cs.ready} restarts={cs.restart_count} image={cs.image}"
            )
            state = cs.state
            # Why a container is stuck now (e.g. ImagePullBackOff, CrashLoopBackOff).
            if state and state.waiting:
                lines.append(f"  waiting: reason={state.waiting.reason} message={state.waiting.message}")
            # Why it exited now (e.g. OOMKilled, exit code).
            if state and state.terminated:
                lines.append(
                    f"  terminated: reason={state.terminated.reason} exit_code={state.terminated.exit_code}"
                )
            # Why it died LAST time - key for crash loops (current may be empty).
            last = cs.last_state
            if last and last.terminated:
                lines.append(
                    f"  last_terminated: reason={last.terminated.reason} exit_code={last.terminated.exit_code}"
                )
        # Requests/limits - needed to reason about OOM (was the memory limit too low?).
        for c in p.spec.containers:
            res = c.resources
            if res:
                lines.append(f"container '{c.name}' resources: requests={res.requests} limits={res.limits}")
        return "\n".join(lines)

    return _safe(_fn, "pod summary")


# Kubernetes events for this pod - the timeline K8s narrates (Scheduled, Pulling, BackOff...).
def _pod_events(namespace: str, pod: str) -> str:
    def _fn() -> str:
        # field_selector filters server-side to events about THIS pod only.
        events = _core.list_namespaced_event(
            namespace=namespace, field_selector=f"involvedObject.name={pod}"
        )
        if not events.items:
            return "[no events]"
        rows = []
        # Sort oldest -> newest so the story reads in order.
        for e in sorted(events.items, key=lambda x: x.last_timestamp or x.event_time or 0):
            rows.append(f"{e.last_timestamp} {e.type} {e.reason}: {e.message}")
        # Keep only the most recent 20 to bound size.
        return "\n".join(rows[-20:])

    return _safe(_fn, "pod events")


# Container logs (like "kubectl logs"). previous=True gets the CRASHED container's logs.
def _pod_logs(namespace: str, pod: str, previous: bool) -> str:
    label = "previous (crashed) container logs" if previous else "current logs"

    def _fn() -> str:
        logs = _core.read_namespaced_pod_log(
            name=pod,
            namespace=namespace,
            tail_lines=settings.log_tail_lines,   # cap lines to protect LLM token cost
            previous=previous,                    # False = live container, True = last crashed one
        )
        return logs.strip() or f"[{label}: empty]"

    return _safe(_fn, label)


# Fallback when the alert names a namespace but no specific pod: list all pods.
def _namespace_pods(namespace: str) -> str:
    def _fn() -> str:
        pods = _core.list_namespaced_pod(namespace=namespace)
        rows = []
        for p in pods.items:
            # One-line health summary per pod: total restarts + all-containers-ready.
            restarts = sum((cs.restart_count or 0) for cs in (p.status.container_statuses or []))
            ready = all(cs.ready for cs in (p.status.container_statuses or [])) if p.status.container_statuses else False
            rows.append(f"{p.metadata.name}: phase={p.status.phase} ready={ready} restarts={restarts}")
        return "\n".join(rows) or "[no pods]"

    return _safe(_fn, "namespace pod list")


# Ask Prometheus a single PromQL query over HTTP (NOT the K8s API - no RBAC needed).
def _prometheus_query(query: str) -> str:
    def _fn() -> str:
        with httpx.Client(timeout=15) as c:
            # Prometheus's instant-query endpoint, reached by Service DNS.
            r = c.get(f"{settings.prometheus_url}/api/v1/query", params={"query": query})
            r.raise_for_status()   # turn an HTTP error into an exception _safe can catch
            # Dig the time-series results out of Prometheus's JSON envelope.
            data = r.json().get("data", {}).get("result", [])
            if not data:
                return f"{query} => (no data)"
            out = []
            # Flatten up to 10 series into readable "query {labels} => value" lines.
            for series in data[:10]:
                metric = series.get("metric", {})
                value = series.get("value", ["", ""])[1]
                labels = ",".join(f"{k}={v}" for k, v in metric.items() if k != "__name__")
                out.append(f"{query} {{{labels}}} => {value}")
            return "\n".join(out)

    return _safe(_fn, f"prometheus query '{query}'")


# The public entry point. analyzer.py calls this with the alert; it decides what
# to gather (based on the alert's labels) and returns one big text evidence bundle.
def collect_context(alert: Alert) -> str:
    """Return a human-readable evidence bundle for the given alert."""
    # The alert labels tell us WHAT to investigate.
    labels = alert.labels
    namespace = labels.get("namespace")
    pod = labels.get("pod")
    app = labels.get("app")

    sections: list[str] = []

    # Case A: we know the exact pod -> deep dive it.
    if namespace and pod:
        sections.append(f"=== POD SUMMARY ({namespace}/{pod}) ===\n{_pod_summary(namespace, pod)}")
        sections.append(f"=== POD EVENTS ===\n{_pod_events(namespace, pod)}")
        sections.append(f"=== CURRENT LOGS ===\n{_pod_logs(namespace, pod, previous=False)}")
        sections.append(f"=== PREVIOUS (CRASHED) LOGS ===\n{_pod_logs(namespace, pod, previous=True)}")
    # Case B: only a namespace -> list its pods for a broad view.
    elif namespace:
        sections.append(f"=== PODS IN NAMESPACE '{namespace}' ===\n{_namespace_pods(namespace)}")

    # Always add a few relevant Prometheus signals (bounded, read-only).
    metric_queries = []
    if app:
        metric_queries.append(f'up{{app="{app}"}}')            # is the app being scraped / alive?
    metric_queries.append("redis_up")                          # our custom dependency metric
    if namespace:
        metric_queries.append(
            f'kube_pod_container_status_restarts_total{{namespace="{namespace}"}}'  # restart counts
        )
    prom = "\n".join(_prometheus_query(q) for q in metric_queries)
    sections.append(f"=== PROMETHEUS SIGNALS ===\n{prom}")

    # Join all sections into the single text blob handed to the LLM.
    return "\n\n".join(sections)
