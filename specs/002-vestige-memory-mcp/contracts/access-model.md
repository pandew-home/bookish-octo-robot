# Contract: Code-enforced cluster access

**Feature**: `002-vestige-memory-mcp` (access-model portion)

## Principle

| Allowed freely | Enforced in code |
|----------------|------------------|
| Natural-language remediation **recommendations** | **Execution** of cluster mutations |
| Suggested kubectl/YAML the **user** may run | Agent tools that call the live API |
| **Identify** Secrets (name, namespace, type, labels, keys names only) | **Read Secret `data` / `stringData`** |

## Authorization stack

1. **User credentials** — session’s Kion/kubeconfig identity against the API server.  
2. **Python kube API wrapper policy** — from Helm `values.yaml` → env (defaults below).

## Default policy (chart defaults)

These are the **product defaults** for every environment unless an overlay explicitly loosens them.

```yaml
kubeApi:
  allowRead: true
  allowMutate: false
  allowedMethods:
    - GET
  allowedSubresources: []      # empty = no extra subresource allowlist (deny rules still apply)
  namespaceMode: any           # any | allowlist | denylist
  namespaces: []
  allowedResources: []         # empty = no resource allowlist (deny rules still apply)
  allowedApiGroups: []         # empty = no group allowlist
  secrets:
    # Secrets may be discovered/identified, never materialised.
    allowIdentify: true        # LIST + metadata-only GET
    allowReadData: false       # block Secret data / stringData in responses
    allowMutate: false         # no create/update/delete of Secrets via wrappers
  deny:
    serviceaccounts: true
    clusterScopedWrites: true
    execSubresource: true
    portforwardSubresource: true
    proxySubresource: true
  dryRunMutations: false
  logDeniedRequests: true
```

### Env mapping (deployment)

| Env | Default |
|-----|---------|
| `KUBE_API_ALLOW_READ` | `true` |
| `KUBE_API_ALLOW_MUTATE` | `false` |
| `KUBE_API_ALLOWED_METHODS` | `GET` |
| `KUBE_API_ALLOWED_SUBRESOURCES` | _(empty)_ |
| `KUBE_API_NAMESPACE_MODE` | `any` |
| `KUBE_API_NAMESPACES` | _(empty)_ |
| `KUBE_API_ALLOWED_RESOURCES` | _(empty)_ |
| `KUBE_API_ALLOWED_API_GROUPS` | _(empty)_ |
| `KUBE_API_SECRETS_ALLOW_IDENTIFY` | `true` |
| `KUBE_API_SECRETS_ALLOW_READ_DATA` | `false` |
| `KUBE_API_SECRETS_ALLOW_MUTATE` | `false` |
| `KUBE_API_DENY_SERVICEACCOUNTS` | `true` |
| `KUBE_API_DENY_CLUSTER_SCOPED_WRITES` | `true` |
| `KUBE_API_DENY_EXEC` | `true` |
| `KUBE_API_DENY_PORTFORWARD` | `true` |
| `KUBE_API_DENY_PROXY` | `true` |
| `KUBE_API_DRY_RUN_MUTATIONS` | `false` |
| `KUBE_API_LOG_DENIED` | `true` |

## Secrets: identify vs read

| Operation | Default | Wrapper behavior |
|-----------|---------|------------------|
| LIST `secrets` | **Allowed** (if read on + creds) | Return name, namespace, type, labels, annotations, `data` **key names only** (or omit `data` and expose `dataKeys: [...]`) |
| GET secret by name | **Metadata only** | Strip `data` and `stringData` before returning to the agent; may include `dataKeys` (key names, not values) |
| GET with raw data | **Denied** | `{ "blocked": true, "reason": "secrets_data_forbidden" }` |
| POST/PUT/PATCH/DELETE secrets | **Denied** | `{ "blocked": true, "reason": "secrets_mutate_forbidden" }` unless `secrets.allowMutate` explicitly true **and** global mutate on |

**Identify** means the agent can answer: “does Secret `X` exist in namespace `Y`?”, “what type is it?”, “which keys are present?” — **not** “what is the password?”.

Implementation note: even if the apiserver returns `data`, the **wrapper MUST redact** before the tool result reaches the LLM.

## Single chokepoint (keep code small)

Policy is **many settings, one gate**:

- Load `KubeApiPolicy` **once** at process start from env (Helm `kubeApi`).
- Every agent cluster call goes through **one** `authorize(request)` then API then `redact(response)`.
- Do **not** re-check policy in prompts, skills, or chat handlers.
- Free-text recommendations never enter this path.

Suggested module split (illustrative): policy load + authorize + redact; wire only into the shared kube API tool entrypoint.

## Evaluation order (wrapper)

1. Method valid?  
2. Read vs mutate (`allowRead` / `allowMutate` + `allowedMethods`).  
3. **Secrets policy** (identify vs data vs mutate).  
4. Other deny rules (SA, exec, cluster-scoped writes, …).  
5. Namespace / resource / API group filters if non-empty.  
6. dryRun if mutate.  
7. Call API with **user credentials** (RBAC final).  
8. **Post-process redaction** for Secrets (and any accidental secret-like fields).

First deny wins → `{ "blocked": true, "reason": "..." }` with no partial apply.

## Prompt contract

**Keep**:

- Use only approved Python Kubernetes API wrappers for cluster I/O.
- Prefer live API evidence; K8sGPT/memory supporting.
- Real resource names; clear structure.

**Remove**:

- Prompt bans on recommendations.
- Verbal multi-step approval as authorization.
- Chat-phrase unlock for mutations.

## Agent tool registry

- Cluster I/O only via wrappers that enforce the policy above.
- Mutate/data denied → structured `{ "blocked": true, "reason": "..." }` — no partial apply, no secret values.

## Tests (required)

| Test | Expect |
|------|--------|
| Default mutate off | POST/PATCH/DELETE blocked |
| Default secrets | LIST/metadata OK; `data` never in tool payload |
| Secret GET | redacted even if apiserver returned data |
| Recommendations | still present in text when mutate off |
| Bad RBAC | surfaced when mutate enabled |

## Non-goals

- Prompt-based prohibition of advice.
- Dual verbal approval as security control.
- Storing Secret values in Vestige memory (scrubber still required).
