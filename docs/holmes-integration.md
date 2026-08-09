# HolmesGPT integration (design draft)

**Status:** Draft for later consideration. Not installed, not wired. Optional future implementation.

How **HolmesGPT** could complement **K8sGPT** and the DevOps Chatbot. Target architecture only—not current runtime behavior.

## Why Holmes (not OpenRCA)

[openrca/orca](https://github.com/openrca/orca) is largely unmaintained (Helm 2-era, stale activity). Prefer a modern, actively supported agent:

| | **K8sGPT** (today) | **HolmesGPT** (planned) |
|--|--------------------|-------------------------|
| Role | Continuous **analyzers** → `Result` CRs | Multi-step **investigation / RCA** agent |
| Project | CNCF Sandbox; operator in-repo | CNCF Sandbox; [HolmesGPT/holmesgpt](https://github.com/HolmesGPT/holmesgpt) |
| Output | Structured findings + short AI solutions | Narrative RCA using live tools (kubectl, Prom, Loki, …) |
| In this repo | Operator, Results, weather, chat context | **Not deployed yet** |

Holmes does **not** replace K8sGPT Results or the chatbot. It is an optional deep-RCA layer.

## Complementary roles

```
Cluster state
    │
    ├─► K8sGPT Operator ──► Result CRs ──► chatbot / weather / Loki (existing)
    │
    └─► HolmesGPT (planned) ──► deep RCA on demand or for critical findings
                                      │
                                      └─► recommendations only (no auto-mutate by default)
```

| Layer | Job |
|-------|-----|
| **K8sGPT** | Find and explain common Kubernetes object issues on a schedule |
| **Holmes** | Investigate *why* (multi-hop, metrics/logs) when deeper RCA is needed |
| **Chatbot** | Session UX, Kion/kubeconfig auth, Vestige, policy-gated tools; may later surface Holmes output |

**There is no built-in “K8sGPT operator calls Holmes” feature.** Composition is application-level (CronJob, chatbot tool, or MCP).

## How K8sGPT and Holmes work together

1. **Side-by-side (minimum)**  
   Both run in-cluster. Humans use Results in Grafana/chatbot and Holmes CLI/API separately.

2. **Results as Holmes input (recommended composition)**  
   A future job or the chatbot packs K8sGPT Result fields (kind, namespace, errors, solution text) into a Holmes `ask` / HealthCheck query for read-only RCA.

3. **K8sGPT MCP (optional)**  
   K8sGPT can expose an MCP server (`k8sgpt serve --mcp`). Holmes can consume MCP servers as tool sources so investigations call analyzers mid-flight. Not configured in this repo today.

4. **Chatbot fusion (optional product path)**  
   Extend the agent the same way as `K8sGPTReader`: load Results always; call Holmes only when the user asks for root cause or a critical path triggers it. Avoid calling Holmes on every chat turn (cost).

## Namespace and GitOps (target)

When installed, keep diagnostic operators in **one namespace**:

| Component | Namespace (target) |
|-----------|--------------------|
| K8sGPT operator + instance | `k8sgpt-operator-system` (already) |
| Holmes Helm release / operator | **same** `k8sgpt-operator-system` |
| Loki / Grafana / Prometheus | `loki` / `monitoring` (unchanged) |
| DevOps chatbot | `devops-chatbot` (unchanged) |

Suggested future Argo layout (not present yet):

- Existing: `00-k8sgpt-operator`, `10-k8sgpt-instance`  
- Future: e.g. `15-holmesgpt` targeting `k8sgpt-operator-system` with pinned chart version  

Install sketch (lab only; adjust to current [Holmes Helm docs](https://holmesgpt.dev/)):

```bash
helm repo add robusta https://robusta-charts.storage.googleapis.com
helm repo update

kubectl -n k8sgpt-operator-system create secret generic holmes-secrets \
  --from-literal=openai-api-key="$OPENROUTER_API_KEY"   # out-of-band; never commit

helm upgrade --install holmesgpt robusta/holmes \
  -n k8sgpt-operator-system \
  -f path/to/values.yaml   # when values exist in-repo
```

- Secrets: out-of-band only (same rule as `k8sgpt-ai-secret` / `devops-chatbot-secrets`).  
- Prefer OpenRouter-compatible models aligned with existing AI ops.  
- Holmes **operator** HealthChecks (if enabled) are alpha upstream; start with API-only and infrequent schedules to control LLM cost.

## Proposed implementation (fleshed out, 2026-08-09 review)

Grounded against current repo state: Argo waves (`00` operator = -3, `10` instance = -2, `50` chatbot = 3), the `helm/alloy-extras` Result→Loki scraper (`source=k8sgpt-result`, every 5 min) and hourly Result GC (24 h retention), and the chatbot tool architecture in `backend/agent_tools.py`.

### Phase 0 — prerequisites

- Separate out-of-band secret `holmes-secrets` (OpenRouter-compatible key); do **not** reuse `k8sgpt-ai-secret` so cost/budget is attributable.
- Review upstream Holmes chart ClusterRole before install: read-only verbs only; no `pods/exec`, `pods/attach`, or remediation toolsets.

### Phase 1 — side-by-side (lab)

New Argo app `argocd/apps/15-holmesgpt.yaml`, sync wave `-1` (after operator/instance, before monitoring), namespace `k8sgpt-operator-system`, upstream `robusta/holmes` chart pinned by version, values inline (repo pattern for upstream charts). API-only — no ingress; access via port-forward/CLI.

Toolsets to enable (all read-only):

| Toolset | Endpoint (this cluster) |
|---------|------------------------|
| kubernetes | in-cluster, read-only |
| prometheus | `http://kube-prometheus-stack-prometheus.monitoring:9090` |
| loki | `http://loki.loki.svc.cluster.local:3100` — includes the existing `source=k8sgpt-result` stream |

### Phase 2 — Results → Holmes composition (CronJob)

Clone the `helm/alloy-extras` scraper pattern: every N hours, select **critical** Results (all Results are <24 h old due to GC), pack kind/namespace/error/fix into a Holmes `ask`/investigate call, push the narrative RCA to Loki as `source=holmes-rca` for Grafana. Infrequent + critical-only keeps LLM spend bounded.

### Phase 3 — chatbot fusion (product change, needs sign-off)

- Requires a new executable tool (e.g. `ask_holmes`) in `backend/agent_tools.py` — that file's maintenance header **forbids adding tools without explicit human sign-off**. A `backend/skills/` drop-in is *not* sufficient: skills return markdown instructions only and cannot call HTTP endpoints.
- Tool contract: input = focus (kind/ns/name or question); call the in-cluster Holmes Service with a hard timeout (60–120 s) and max one call per turn; on failure degrade soft (`holmes_unavailable` in chat metadata, mirroring `memory_degraded`) — never fail the chat turn.
- Policy note: a Holmes call is not a Kubernetes API mutation, so it is not kubeApi-gated; safety depends on Holmes itself being deployed read-only (Phase 0 review).

### Failure modes

| Failure | Behavior |
|---------|----------|
| Holmes pod down | Chat/weather unaffected; Phase 3 tool degrades soft |
| LLM cost spike | No scheduled HealthChecks initially; Phase 2 critical-only + infrequent |
| Chart RBAC too broad | Block promotion until values/fork make it read-only |
| Result GC (24 h) vs CronJob | Query window < retention; Loki keeps history anyway |

### Open questions

- Pin exact chart version and validate values keys against current upstream (sketch is indicative).
- Same OpenRouter account as K8sGPT with a separate key, or separate account/budget?
- Does Holmes output ever feed the weather widget, or stay chat/Grafana-only?

## Security posture (must match constitution)

| Do | Do not |
|----|--------|
| Observe / recommend (read-only tools) | Auto-mutate the cluster without policy + approval |
| Respect RBAC; review Holmes chart ClusterRole before prod | Enable Kubernetes remediation MCP by default |
| Keep chatbot `kubeApi.allowMutate: false` unless deliberately changed | Stack blind auto-remediation from K8sGPT Mutations + Holmes |

**Auto-mutate** means the system *applies* cluster changes (delete pod, scale, patch) without a human/GitOps step. **Not** part of the documented default integration. Posting text to chat/Loki or recommending `kubectl`/Helm steps is observe-only.

## Notifications (related, optional later)

Existing path: Result CRs → scraper/Alloy → Loki → Grafana (see `docs/k8sgpt-setup.md`, `k8sgpt/Alloy/`).

A future single notify pipeline (design only) could:

1. Push **all** Results to Loki every few minutes.  
2. Post a **critical-only** summary to Rocket.Chat (or similar).  
3. Optionally attach Holmes RCA text for those critical items.

Not required to adopt Holmes.

## What exists today vs planned

| Capability | Today | Planned with Holmes |
|------------|--------|---------------------|
| Continuous K8s object scan | Yes (`Result` CRs) | Unchanged |
| Chatbot reads Results | Yes (`K8sGPTReader`) | Unchanged; may show Holmes notes later |
| Weather widget | K8sGPT-driven | Unchanged |
| Deep multi-source RCA agent | Chatbot tools only | Holmes API / HealthChecks |
| Holmes in GitOps | No | Same NS as K8sGPT |
| Auto-remediation | Off by default | Stay off by default |

## References

- HolmesGPT: https://holmesgpt.dev/ · https://github.com/HolmesGPT/holmesgpt  
- K8sGPT (this repo): `docs/k8sgpt-setup.md` · https://docs.k8sgpt.ai/  
- Agent rules: `AGENTS.md` (observe-default, policy-gated mutation)  
- Architecture: `docs/architecture.md`  
- Alternate option: [watchtower-opencode-option.md](watchtower-opencode-option.md)
