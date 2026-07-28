# KubeApi Permissions Model

**Purpose**: Document the chatbot's Kubernetes API access control layer so deployments can adapt policy for different environments and troubleshoot recurring access issues without code changes.

**Source of truth**: `backend/kube_policy/policy.py`, `backend/kube_policy/authorize.py`, `backend/kube_policy/redact.py`
**Chart wiring**: `chart/values.yaml` → `chart/templates/deployment.yaml` env vars
**Runtime config**: Environment variables loaded via `load_policy_from_env()` in `backend/kube_policy/__init__.py`

---

## 1. Overview

The kubeApi layer is a defense-in-depth policy engine that sits **between** the chatbot agent tools and the Kubernetes API client. It enforces rules on every API call regardless of the pod's RBAC bindings. This means:

- RBAC controls what the **ServiceAccount can technically do**
- KubeApi policy controls what the **chatbot is permitted to request**

The layer is initialized once at app startup (`app.py` startup event) and applies globally to all cluster API calls made through `k8s_api_request` in `backend/agent_tools.py`.

Key properties:
- **Fail-closed**: Deny is the default for mutations, high-risk subresources, and cluster-scoped writes
- **Non-blocking for reads**: Read failures are logged; the agent continues with available context
- **Secret-safe by default**: Secret data is never returned in full; env values in workload specs are redacted
- **Env-driven**: All rules are configured via environment variables set by the Helm chart

---

## 2. Policy Data Model

```python
class KubeApiPolicy:
    allowRead: bool = True
    allowMutate: bool = False
    allowedMethods: List[str] = ["GET"]
    allowedSubresources: List[str] = []
    namespaceMode: str = "any"          # "any" | "allowlist" | "denylist"
    namespaces: List[str] = []
    allowedResources: List[str] = []   # e.g. ["pods", "deployments"]
    allowedApiGroups: List[str] = []  # e.g. ["apps", "v1"]
    secrets: SecretsPolicy
    deny: DenyRules
    dryRunMutations: bool = False
    logDeniedRequests: bool = True
```

### 2.1 SecretsPolicy

| Field | Default | Meaning |
|-------|---------|---------|
| `allowIdentify` | `true` | Can list/get Secret metadata (name, namespace, type) |
| `allowReadData` | `false` | Can read Secret `data` / `stringData` values |
| `allowMutate` | `false` | Can create/update/delete Secrets |

### 2.2 DenyRules

| Field | Default | Blocks |
|-------|---------|--------|
| `serviceaccounts` | `true` | Mutating ServiceAccount resources |
| `clusterScopedWrites` | `true` | POST/PUT/PATCH/DELETE without a namespace |
| `execSubresource` | `true` | `pods/exec` (shell access) |
| `portforwardSubresource` | `true` | `pods/portforward` |
| `proxySubresource` | `true` | `services/proxy` |

Additionally hard-coded denies (not configurable):
- `logs` / `log` subresource (leaks secrets from running pods)
- `attach` subresource

---

## 3. Authorization Evaluation Order

Every request goes through these 7 gates in order. **First deny wins.**

```
1. METHOD VALIDITY
   - Must be GET, POST, PUT, PATCH, or DELETE
   - Unknown methods → deny

2. READ vs MUTATE
   - GET/list/watch → check allowRead
   - Others → check allowMutate AND must be in allowedMethods

3. SECRETS POLICY
   - If resource == "secrets":
     - Read: check allowIdentify
     - Write: check allowMutate + allowMutate

4. DENY RULES
   - serviceaccounts mutate → deny
   - exec/portforward/proxy → deny
   - cluster-scoped write (no namespace + mutate) → deny
   - logs/attach subresource → deny (always)

5. NAMESPACE MODE
   - "any": allow all namespaces
   - "allowlist": namespace must be in list
   - "denylist": namespace must NOT be in list

6. RESOURCE / API GROUP ALLOWLISTS
   - If allowedResources set, resource must match
   - If allowedApiGroups set, group must match

7. SUBRESOURCE ALLOWLIST
   - If allowedSubresources set, subresource must match
```

If all gates pass → **allow**.

---

## 4. Environment Variable Reference

All variables are read at startup. Change requires pod restart.

| Env Var | Maps To | Default | Purpose |
|--------|---------|---------|---------|
| `KUBE_API_ALLOW_READ` | `allowRead` | `true` | Enable all read operations |
| `KUBE_API_ALLOW_MUTATE` | `allowMutate` | `false` | Enable mutation operations |
| `KUBE_API_ALLOWED_METHODS` | `allowedMethods` | `[GET]` | Comma-separated allowed methods |
| `KUBE_API_ALLOWED_SUBRESOURCES` | `allowedSubresources` | `[]` | Comma-separated allowed subresources |
| `KUBE_API_NAMESPACE_MODE` | `namespaceMode` | `any` | `any`, `allowlist`, `denylist` |
| `KUBE_API_NAMESPACES` | `namespaces` | `[]` | Comma-separated namespace list |
| `KUBE_API_ALLOWED_RESOURCES` | `allowedResources` | `[]` | Comma-separated resource names |
| `KUBE_API_ALLOWED_API_GROUPS` | `allowedApiGroups` | `[]` | Comma-separated API groups |
| `KUBE_API_SECRETS_ALLOW_IDENTIFY` | `secrets.allowIdentify` | `true` | Can list Secret metadata |
| `KUBE_API_SECRETS_ALLOW_READ_DATA` | `secrets.allowReadData` | `false` | Can read Secret values |
| `KUBE_API_SECRETS_ALLOW_MUTATE` | `secrets.allowMutate` | `false` | Can modify Secrets |
| `KUBE_API_DENY_SERVICEACCOUNTS` | `deny.serviceaccounts` | `true` | Block SA mutations |
| `KUBE_API_DENY_CLUSTER_SCOPED_WRITES` | `deny.clusterScopedWrites` | `true` | Block cluster-scoped writes |
| `KUBE_API_DENY_EXEC` / `KUBE_API_DENY_EXEC_SUBRESOURCE` | `deny.execSubresource` | `true` | Block pod exec |
| `KUBE_API_DENY_PORTFORWARD` / `..._SUBRESOURCE` | `deny.portforwardSubresource` | `true` | Block port forward |
| `KUBE_API_DENY_PROXY` / `..._SUBRESOURCE` | `deny.proxySubresource` | `true` | Block service proxy |
| `KUBE_API_DRY_RUN_MUTATIONS` | `dryRunMutations` | `false` | Force dry-run for mutations |
| `KUBE_API_LOG_DENIED` | `logDeniedRequests` | `true` | Log denied requests |

---

## 5. Response Redaction

After a request is authorized and executed, the response is filtered through `redact_response()`:

- **Secret resources**: Replace `data` and `stringData` with `dataKeys` (list of key names only)
- **All other resources**: Walk tree and redact container/env values that match secret patterns (password, token, api_key, etc.) with `[REDACTED]`
- **If `allowReadData=true`**: Redaction is skipped entirely

This protects against accidental secret exposure in agent context even if authorization is misconfigured.

---

## 6. Helm Chart Wiring

Add to `chart/values.yaml`:

```yaml
kubeApi:
  allowRead: true
  allowMutate: false
  allowedMethods: ["GET"]
  allowedSubresources: []
  namespaceMode: "any"
  namespaces: []
  allowedResources: []
  allowedApiGroups: []
  secrets:
    allowIdentify: true
    allowReadData: false
    allowMutate: false
  deny:
    serviceaccounts: true
    clusterScopedWrites: true
    execSubresource: true
    portforwardSubresource: true
    proxySubresource: true
  dryRunMutations: false
  logDeniedRequests: true

memory:
  backend: "vestige"
  vestigeHttpUrl: "http://127.0.0.1:3928"
  vestigeAuthSecret: ""
  dataDir: "/data/vestige"
  modelCacheDir: "/data/vestige/model-cache"
```

Then in `chart/templates/deployment.yaml`, wire as env vars:

```yaml
- name: KUBE_API_ALLOW_READ
  value: "{{ .Values.kubeApi.allowRead }}"
- name: KUBE_API_ALLOW_MUTATE
  value: "{{ .Values.kubeApi.allowMutate }}"
# ... etc for all fields
- name: MEMORY_BACKEND
  value: "{{ .Values.memory.backend }}"
- name: VESTIGE_HTTP_URL
  value: "{{ .Values.memory.vestigeHttpUrl }}"
```

---

## 7. Deployment Configuration Profiles

Use these as starting points for cluster overlays (`clusters/<name>/devops-chatbot.values.yaml`).

### 7.1 Staging (JADE) — Default / Recommended

```yaml
kubeApi:
  allowRead: true
  allowMutate: false
  namespaceMode: "any"
  secrets:
    allowReadData: false
  deny:
    execSubresource: true
    clusterScopedWrites: true
```

Use case: Chatbot can diagnose any namespace, cannot mutate, cannot read secrets.

### 7.2 Development / Debug — Relaxed

```yaml
kubeApi:
  allowRead: true
  allowMutate: true
  allowedMethods: ["GET", "POST", "PUT", "PATCH", "DELETE"]
  dryRunMutations: true
  namespaceMode: "allowlist"
  namespaces: ["devops-chatbot", "default"]
  secrets:
    allowReadData: false
  deny:
    execSubresource: true
    clusterScopedWrites: true
```

Use case: Developers need to apply fixes via chatbot, but mutations are dry-run and scoped to specific namespaces.

### 7.3 Restricted / High-Security

```yaml
kubeApi:
  allowRead: true
  allowMutate: false
  namespaceMode: "allowlist"
  namespaces: ["bookish-octo-robot"]
  allowedResources: ["pods", "services", "configmaps", "deployments"]
  allowedApiGroups: ["v1", "apps"]
  secrets:
    allowIdentify: false
  deny:
    serviceaccounts: true
    clusterScopedWrites: true
    execSubresource: true
```

Use case: Chatbot can only inspect specific resources in its own namespace. Cannot see Secret names at all.

### 7.4 Diagnostic-Only (Read-only, specific resources)

```yaml
kubeApi:
  allowRead: true
  allowMutate: false
  allowedResources: ["pods", "nodes", "events", "k8sgpt/results"]
  allowedApiGroups: ["v1", "k8sgpt.io"]
  namespaceMode: "any"
```

Use case: Chatbot is purely for monitoring and K8sGPT result interpretation.

---

## 8. Common Problems and Fixes

### "Chatbot can read pods but not deployments"
**Cause**: `allowedResources` or `allowedApiGroups` is restricting access.
**Fix**: Add `deployments` to `allowedResources` and `apps` to `allowedApiGroups`, or clear both lists for unrestricted reads.

### "Chatbot can list Secrets but not read values — good, but now it can't diagnose secret-related issues"
**Expected**: This is correct behavior. The chatbot can say "Secret X exists in namespace Y" but not show its contents. For diagnosis, direct the user to check the secret manually or use Vault access.

### "Mutations are always dry-run"
**Cause**: `KUBE_API_DRY_RUN_MUTATIONS=true` or `allowMutate=false`.
**Fix**: Set `dryRunMutations: false` and `allowMutate: true` with explicit `allowedMethods` including POST/PATCH.

### "Chatbot can't access resources in namespace Z"
**Cause**: `namespaceMode: allowlist` with Z missing.
**Fix**: Add Z to `namespaces` list, or switch to `any`.

### "Denial logs are noisy"
**Fix**: Set `KUBE_API_LOG_DENIED=false` to suppress logging of expected denies.

### "Vestige memory is not available, chatbot works but has no history"
**Cause**: `MEMORY_BACKEND=noop` or Vestige not running.
**Fix**: Set `MEMORY_BACKEND=vestige` and ensure the Vestige sidecar is running on port 3928 with the correct auth token.

---

## 9. Integration Checklist

Before enabling in production:

- [ ] Chart values include `kubeApi` and `memory` blocks
- [ ] Deployment env vars are wired correctly
- [ ] Init container creates `/data/vestige` with correct ownership
- [ ] PVC includes `/data/vestige` mount
- [ ] `readOnlyRootFilesystem: true` still works (Vestige writes only to `/data` and `/tmp`)
- [ ] RBAC is tightened separately (T025) — do not rely on kubeApi alone
- [ ] `KUBE_API_LOG_DENIED` is configured for your observability needs
- [ ] Smoke test confirms chatbot can still diagnose and chat works without memory if degraded

---

## 10. File References

| File | Line | Purpose |
|------|------|---------|
| `backend/kube_policy/policy.py` | 29-43 | Policy dataclass definition |
| `backend/kube_policy/policy.py` | 60-101 | Env loader with defaults |
| `backend/kube_policy/authorize.py` | 53-150 | Authorization evaluation engine |
| `backend/kube_policy/redact.py` | 77-115 | Response redaction logic |
| `backend/kube_policy/__init__.py` | — | Singleton init/get/close |
| `backend/agent_tools.py` | — | Integration point (`_authorize_or_deny`) |
| `backend/app.py` | — | Startup initialization call |
| `chart/values.yaml` | — | Helm configuration source |
| `chart/templates/deployment.yaml` | — | Env var wiring |
