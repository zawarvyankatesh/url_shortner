# AI Incident Analysis Agent

A read-only Kubernetes incident-analysis agent. Alertmanager POSTs firing alerts
to it; for each alert it:

1. emails an immediate "alert received" notification,
2. gathers **read-only** evidence (pod status, events, current + previous logs,
   Prometheus signals),
3. asks an LLM (Azure OpenAI-compatible proxy) for a root-cause analysis, and
4. emails the analysis.

## Safety model

- **Read-only Kubernetes RBAC** (`get`/`list` only; no write, no exec, no Secrets).
  The LLM has no tools and no cluster access - it only reasons over text.
- Suggested remediations are **for human review** and are never executed.
- Log/event text is treated as untrusted data, not instructions.

## Layout

```
agent/
  app/
    main.py        FastAPI webhook (/alert, /healthz)
    analyzer.py    orchestration: alert -> mail -> collect -> llm -> mail
    collector.py   read-only K8s + Prometheus context gathering
    llm.py         Azure OpenAI proxy client + RCA prompt
    mailer.py      SMTP emails (received + analysis)
    config.py      env-based settings
    models.py      Alertmanager payload models
  Dockerfile
  requirements.txt
```

## Build & push the image

```bash
cd agent
docker build -t vyankateshzawar/incident-agent:latest .
docker push vyankateshzawar/incident-agent:latest
```

## Deploy

```bash
# 1) create the secret (never commit real secrets)
kubectl create secret generic incident-agent-secrets -n ai-agent \
  --from-literal=LLM_API_KEY='<rotated-key>' \
  --from-literal=SMTP_PASSWORD=''

# 2) apply manifests (namespace, RBAC, config, deployment)
kubectl apply -f ../k8s/agent/

# 3) re-apply the updated Alertmanager config (now points at this agent)
kubectl apply -f ../k8s/monitoring/06-alertmanager-config.yaml
kubectl rollout restart deployment/alertmanager -n monitoring
```

## Configuration

Non-secret config is in `k8s/agent/02-configmap.yaml`; fill in `SMTP_HOST`
(your internal relay) so email can be sent.
