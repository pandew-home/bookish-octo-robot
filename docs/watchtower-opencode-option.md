# Design: OpenCode WatchTower action-plan skill

**Status:** Design only — not implemented.  
**Hand-off:** Implement the package in §2 exactly; treat §5–§8 as normative contracts (tests should lock them).

## 1. Goal

OpenCode skill that answers “what should I fix first?” by merging **K8sGPT Results** + **WatchTower RCAReports** into a **top-3 action plan**.

| Do | Do not |
|----|--------|
| Observe (get/list) | Mutate unless user explicitly asks + permission allows |
| Deterministic merge in a helper | Dump full CRs into the LLM |
| Cap at 3 tabled incidents | Auto multi-cluster scan |
| Degrade if one source is missing | Call an LLM from helpers |

**Inputs:** `results.core.k8sgpt.ai`, RCAReports (apiGroup TBD — confirm), optional Loki `{source="k8sgpt-result"}`.  
**Output:** Markdown action plan (§8).

## 2. Ship this package

```text
.opencode/skills/watchtower-action-plan/
  SKILL.md
  scripts/wt-merge.sh          # required
  scripts/wt-loki-history.sh   # optional
  scripts/wt-context.sh        # optional
  fixtures/
    results.sample.json
    rcareports.sample.json
    merge.expected.json
.opencode/permission-fragments/watchtower-action-plan.json
```

MVP = **one skill + `wt-merge`**. Optional scripts can stub to “unavailable”.

## 3. How it runs

```text
User phrase → OpenCode loads skill → bash wt-merge → (opt) Loki
           → LLM writes plan from compact JSON → stop
```

- **SKILL.md** = prompt only (no execution).  
- **Helpers** = CLI, JSON on stdout, no LLM.  
- **I/O** = OpenCode bash under `opencode.json` permissions.  
- OpenCode ≠ code-server (code-server is just a common host).

Skill discovery: project `.opencode/skills/<name>/` or `~/.config/opencode/skills/<name>/`.  
`name` must match directory: `^[a-z0-9]+(-[a-z0-9]+)*$`.

## 4. SKILL.md

### Frontmatter

```yaml
---
name: watchtower-action-plan
description: >-
  Build a brief Kubernetes action plan from WatchTower RCAReports and K8sGPT
  Results. Use for: action plan, what's broken, cluster RCA, WatchTower plan,
  top incidents, prioritized fixes. Observe-only unless user asks to apply.
---
```

### Body must instruct (in order)

1. Hard rules (§5)  
2. Steps: context → `wt-merge` → optional Loki → emit plan §8 → **stop**  
3. Map user focus → `wt-merge` flags (§6.2)  
4. Pick ≤3 P-items from `candidates` (§7)  
5. A/B solution rules (§7)  
6. Exact plan template (§8)  
7. Data gaps from helper `gaps[]`  
8. Implement only on explicit ask: prefer GitOps edit+diff; `kubectl apply` only if allowed  

## 5. Hard rules

| Rule | Detail |
|------|--------|
| Observe-first | No apply/delete/scale/patch/exec unless user asks + permission allows |
| Helper-first | Always run `wt-merge` before ad-hoc dumps |
| Dual source | Try both CRDs; missing → `gaps`, continue |
| Cap | Max **3** tabled incidents |
| Brief | No full CR JSON, no long runbooks in output |
| Context | Current kube context only unless user asks to switch |

## 6. Helper: `wt-merge` (normative)

### CLI

```bash
wt-merge.sh [--namespace NS] [--workload NS/NAME] [--node NAME] \
  [--since DURATION] [--critical-only] [--limit N] \
  [--results-file PATH] [--rca-file PATH]
```

| Flag | Default | |
|------|---------|---|
| `--since` | `6h` | Drop older |
| `--limit` | `10` | Max candidates out |
| `--critical-only` | off | Drop below `high` |
| `*-file` | live kubectl | Offline/fixture mode |

**Deps:** `kubectl`, `jq` (or equivalent). Read-only.

### Algorithm

1. Load Results + RCAReports (live or files).  
2. One source 403/empty → push `gaps[]`, continue. Both fail → exit `2`.  
3. Normalize each item → common record (below).  
4. Join: same `joinKey` + time within **±15m** → one group.  
5. Dedupe replica/pod noise.  
6. Rank: severity ↓, then recency, then group size.  
7. Print JSON (schema below).  

### Normalized record

```json
{
  "source": "k8sgpt|watchtower",
  "severity": "critical|high|warning|info",
  "joinKey": "namespace/workload|node/<name>",
  "namespace": "",
  "name": "",
  "kind": "",
  "start": "RFC3339",
  "end": "RFC3339",
  "summary": "≤240 chars",
  "ref": { "apiVersion": "", "kind": "", "namespace": "", "name": "" }
}
```

### Severity map (confirm field names on live CRDs)

| Out | WatchTower | K8sGPT |
|-----|------------|--------|
| critical/high | critical/high | error/critical |
| warning | warning/medium | warning |
| info | info/low | info |

**Join fields (confirm):** WatchTower `parentObject` / `affectedWorkloads` / `timeline`; K8sGPT parent kind/name/ns. Make extractors easy to edit.

### Stdout schema

```json
{
  "context": { "kubeContext": "", "cluster": "", "generatedAt": "RFC3339" },
  "gaps": [{ "source": "watchtower|k8sgpt", "code": "empty|forbidden|error", "message": "" }],
  "stats": { "rawK8sgpt": 0, "rawWatchtower": 0, "groups": 0 },
  "candidates": [{
    "id": "c1",
    "joinKey": "checkout/api",
    "severity": "critical",
    "window": { "start": "", "end": "" },
    "sources": ["watchtower", "k8sgpt"],
    "summary": "",
    "members": [{ "source": "", "ref": {}, "summary": "" }]
  }]
}
```

### Exit codes

| Code | |
|------|---|
| 0 | OK (may include `gaps`) |
| 2 | Both sources failed/empty |
| 3 | Missing kubectl/deps |
| 4 | Bad flags |

### Optional helpers

- `wt-context.sh` → `{ kubeContext, namespace, server }`  
- `wt-loki-history.sh --namespace --name [--window 6h]` → `{ count, first, last, status: ok|unavailable }` — never fail the plan  

### Focus → flags

| User says | Flags |
|-----------|--------|
| (default) | `--limit 10` |
| namespace X | `--namespace X` |
| workload ns/name | `--workload ns/name` |
| node N | `--node N` |
| critical only | `--critical-only` |
| last 2h | `--since 2h` |

## 7. LLM selection rules (from `candidates`)

| If | Then |
|----|------|
| Any critical/high | Table only those (max 3); rest → Deferred |
| None | Up to 3 warnings; info deferred unless nothing else |
| | Do not re-split helper groups |

**A/B table** (one per P-item): Solution | Probability (H/M/L) | Rollback | Cluster-wide impact of **fix** (L/M/H + clause). Prefer GitOps wording.

| Best vs alt | Show |
|-------------|------|
| H+H, H+M, M+M | A and B |
| H+L, M+L, or one fix | **A only** |

No weak filler B. **A** = preferred when both shown.  
**Execution order:** preferred row only, P1→P3.

## 8. Action plan template

```markdown
# Action plan — <context> — <UTC>

## Situation
2–3 sentences. Sources: WatchTower | K8sGPT | both. Note top k of n / deferred.

## P1 — <title> — <severity>
- **Window:** <start> → <end> (±15m)
- **Sources:** both | WatchTower | K8sGPT
- **Root cause (best effort):** ≤2 sentences
- **History (Loki):** optional

| Solution | Probability | Rollback | Cluster-wide impact of fix |
|----------|-------------|---------|----------------------------|
| **A —** … | H\|M\|L | … | L/M/H: … |

**Prefer:** A   ← or A/B note; omit Prefer if A-only single row

## P2 — …
## P3 — …

## Execution order
1. P1 — <preferred>
2. P2 — …
3. P3 — …

## Deferred
- …

## Data gaps
- …
```

## 9. Permissions fragment (intent)

Merge into platform `opencode.json`. Match DSL to the image’s OpenCode version.

```json
{
  "permission": {
    "skill": { "watchtower-action-plan": "allow" },
    "bash": {
      "**/wt-merge.sh*": "allow",
      "**/wt-loki-history.sh*": "allow",
      "**/wt-context.sh*": "allow",
      "kubectl get *": "allow",
      "kubectl api-resources *": "allow",
      "kubectl config current-context": "allow",
      "kubectl config get-contexts": "allow",
      "curl *loki*": "ask",
      "aws *": "ask",
      "kion *": "ask",
      "kubectl apply *": "deny",
      "kubectl delete *": "deny",
      "kubectl patch *": "deny",
      "kubectl scale *": "deny",
      "kubectl exec *": "deny"
    }
  }
}
```

## 10. Cluster RBAC (IDE identity)

```yaml
# ClusterRole rca-reader — get/list only; CONFIRM apiGroup
rules:
  - apiGroups: ["core.k8sgpt.ai"]
    resources: ["results"]
    verbs: ["get", "list"]
  - apiGroups: ["rca.watchtower.dev"]
    resources: ["rcareports"]
    verbs: ["get", "list"]
```

## 11. Platform prereqs (not this package)

- K8sGPT Results available  
- WatchTower with **`reports.write: true`** (else WatchTower half empty)  
- Prefer `reports.retentionDays: 7` on controller  
- WatchTower chart today lives in a **personal** JADE repo — mirror before prod GitOps  

Rocket.Chat = WatchTower’s job, not this skill.

## 12. Tests

| Test | Pass if |
|------|---------|
| Helper unit | fixtures → `merge.expected.json` (join, ±15m, severity, gaps) |
| Flags | `--namespace` / `--critical-only` / `--since` filter |
| Exit 2 | both sources empty |
| Golden plan (manual/eval) | frozen candidates → ≤3 tables, A/B rules, no CR dumps |
| RBAC | get/list OK; patch Deployment denied |
| Permissions | apply denied; skill loads |
| Degrade | empty WatchTower → K8sGPT-only + Data gaps |

## 13. Out of scope

Holmes, chatbot product changes, auto-remediation, scheduled runs, owning WatchTower controller/chart, multi-cluster fan-out.

## 14. Blocked until confirmed

1. RCAReport **apiGroup/version**, severity enums, join field paths  
2. OpenCode **permission DSL** for the binary in your image  
3. Install path: ops git `.opencode/skills/` vs image `~/.config/opencode/skills/`

## 15. Implement checklist

- [ ] Confirm CRD schema  
- [ ] `wt-merge.sh` + fixtures + unit tests  
- [ ] Optional `wt-context` / `wt-loki-history`  
- [ ] `SKILL.md` from §4–§8  
- [ ] Permission fragment  
- [ ] Seed into OpenCode host (git and/or image)  
- [ ] Lab run with both CRDs + golden plan review  
- [ ] (Platform, separate) WatchTower `reports.write` + RBAC bind  

## Refs

- OpenCode skills: https://opencode.ai/docs · https://github.com/anomalyco/opencode  
- K8sGPT here: [k8sgpt-setup.md](k8sgpt-setup.md)  
- WatchTower (internal): `internal/jup/ept/personal/danis-repo/watchtowerrca`  
