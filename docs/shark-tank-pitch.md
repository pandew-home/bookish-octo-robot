# AI Ops Assistant: Cluster Intelligence Without the Noise

*2026 Shark Tank Submission*

---

## The Problem

DevOps engineers spend hours context-switching between Kubernetes dashboards, alert systems, runbooks, and Slack threads to diagnose a single incident. Developers and security teams get too little signal — or signal too late. Existing tools require deep K8s expertise just to ask the right questions.

---

## The Solution

A **minimally invasive AI Ops assistant** that deploys alongside your existing infrastructure and integrates with what you already use — no rip-and-replace.

### Three Layers of Value

---

### 1. DevOps Engineer — Chatbot Interface

Natural-language cluster troubleshooting powered by K8sGPT Operator. Engineers get context-aware, AI-assisted resolution in seconds.

> *[INSERT: screenshot of chat interface and weather widget from Docker Desktop deployment]*

The **weather widget** gives an at-a-glance cluster health signal — Sunny, Cloudy, or Stormy — derived from live K8sGPT findings.

---

### 2. Alerting Teams — Grafana Alloy Integration

K8sGPT findings flow automatically into your existing Grafana/Loki stack via Alloy — no new dashboards required:

```
K8sGPT Operator (k8sgpt-operator-system)
    │ pod logs
    ▼
Grafana Alloy (DaemonSet, monitoring namespace)
    │ loki.source.kubernetes → loki.process → loki.write
    ▼
Loki → Grafana (K8sGPT Results dashboard)

CronJob: k8sgpt-result-cleanup (hourly, 24h retention)
```

Four live Grafana panels included out of the box:
- **K8sGPT Operator Logs** — live stream tagged `source=k8sgpt`
- **Analysis Activity** — requests/min time series
- **HPA & Scaling Issues** — filtered for scaling/replica anomalies
- **All K8sGPT Findings** — full namespace log view (last 1h)

> *[INSERT: screenshot of Grafana K8sGPT dashboard from Docker Desktop deployment]*

---

### 3. Developers & Security — Structured Alerts

K8sGPT analyzes every 2 minutes across these resource types, routing findings to the right team:

```yaml
# k8sgpt/k8sgpt-openrouter-cr.yaml
analysis:
  interval: 2m
filters:
  - Pod
  - Deployment
  - ReplicaSet
  - StatefulSet
  - Node
  - HorizontalPodAutoscaler
  - PersistentVolumeClaim
  - Service
  - Ingress
```

Sensitive cluster data is masked before LLM analysis (`anonymized: true`).

---

## Security by Design

**Operator: strict read-only RBAC — no write access to any workload**

```yaml
# k8sgpt/rbac.yaml (excerpt)
rules:
  - apiGroups: [""]
    resources: [pods, services, nodes, events, ...]
    verbs: [get, list, watch]   # read-only, no create/update/delete

  - apiGroups: ["apps"]
    resources: [deployments, replicasets, statefulsets, daemonsets]
    verbs: [get, list, watch]
```

Secrets access is **namespace-scoped** to a single named secret only:

```yaml
  - apiGroups: [""]
    resources: [secrets]
    verbs: [get, list]
    resourceNames: [k8sgpt-ai-secret]   # no wildcard access
```

**Chatbot: user-owned credentials, zero standing access**
- Authenticates with the engineer's own Kion temporary AWS tokens (ASIA*)
- Backend validates via STS `GetCallerIdentity` — no shared service account
- EKS bearer tokens expire after 60 seconds, regenerated per request
- No persistent cluster credentials stored server-side

**Pod hardening (enforced by Kyverno):**

```yaml
# k8s/deployment.yaml (excerpt)
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
```

---

## Why Minimally Invasive?

- Deploys via ArgoCD/Helm — pure GitOps, no manual cluster changes
- Uses your existing Kion credentials — no new IAM footprint
- Reads cluster state via K8s API — no agents, no sidecars
- Writes to Grafana Alloy — zero new alerting infrastructure
- Operator deployed per monitored cluster; chatbot is a single centralized deployment

---

## Business Impact

- Reduces MTTR for cluster incidents — assisted resolution in the chat, not after 3 Slack threads
- Democratizes cluster observability beyond the K8s expert on the team
- Turns tribal runbook knowledge into a searchable, AI-augmented knowledge base
- Audit-friendly: every query is traceable to a specific user session with ephemeral credentials
- Zero-trust aligned: no standing credentials, no shared accounts, access expires automatically

---

## Current State

Working prototype validated on EKS with Docker Desktop for local demo. Frontend + backend containerized, K8sGPT Operator integration tested, Grafana Alloy pipeline verified end-to-end.

---

## TODO — Before Submitting

- [ ] Add screenshot: chat interface + weather widget (sunny/stormy state)
- [ ] Add screenshot: Grafana dashboard showing K8sGPT findings panels
- [ ] Add any additional sections from the submission form
