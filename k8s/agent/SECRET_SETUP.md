# Agent Secret setup

The agent needs a Secret named `incident-agent-secrets` in the `ai-agent`
namespace. Create it **imperatively** so real secrets never land in git and are
never overwritten by `kubectl apply -f k8s/agent/`.

> IMPORTANT: Do NOT put the Secret in a YAML file inside this folder. Anything
> here is applied by `kubectl apply -f k8s/agent/` and would overwrite your real
> key with a placeholder.

Create (or update) the Secret:

```bash
kubectl delete secret incident-agent-secrets -n ai-agent --ignore-not-found

kubectl create secret generic incident-agent-secrets -n ai-agent \
  --from-literal=LLM_API_KEY='<your-working-llm-token>' \
  --from-literal=SMTP_PASSWORD=''
```

Then roll the agent so it picks up the new value:

```bash
kubectl rollout restart deployment/incident-agent -n ai-agent
```

Verify:

```bash
kubectl exec -n ai-agent deploy/incident-agent -- printenv LLM_API_KEY
```
