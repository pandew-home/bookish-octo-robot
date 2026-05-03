---
name: k8s-check
description: Read-only Kubernetes API health check using live cluster state with optional namespace scope.
disable-model-invocation: true
allowed-tools: k8s_api_request
---

You are performing a comprehensive Kubernetes health check in READ/VIEW mode only.

This skill is strictly non-mutating:
- Allowed: inspect/list/read operations only
- Not allowed: create, apply, patch, replace, edit, delete, rollout restart, scale, cordon, drain, exec

Collect all data first, then analyze and report findings clearly.

## Arguments
- `$ARGUMENTS` — optional namespace to scope the check (e.g. `production`, `staging`). If omitted, check all namespaces.

## Namespace scope

Set namespace scope based on `$ARGUMENTS`:
- If provided: use that namespace for namespaced resources.
- If empty: query cluster-wide where supported, otherwise iterate namespaced resources.

## API-first behavior

Use Kubernetes API semantics as the source of truth (resource `kind`, `apiVersion`, `metadata`, `spec`, `status`).
If API version context is needed, use the cluster version-specific reference URL provided by the caller.

---

## Step 1 — Collect data (run in parallel where possible)

### Pods
- API calls:
	- `GET /api/v1/namespaces/{ns}/pods` (or cluster-wide pod list where supported)
	- Filter non-running pods from `.status.phase`

### Deployments
- API calls:
	- `GET /apis/apps/v1/namespaces/{ns}/deployments`
	- Compare desired vs ready/available from `.spec.replicas` and `.status.*`

### Events (warnings only)
- API calls:
	- `GET /api/v1/namespaces/{ns}/events`
	- Keep only warning events and sort by timestamp

### Ingress
- API calls:
	- `GET /apis/networking.k8s.io/v1/namespaces/{ns}/ingresses`

### Nodes (always cluster-wide)
- API calls:
	- `GET /api/v1/nodes`
	- Optional metrics API where available (e.g. `metrics.k8s.io`)

### Resource pressure
- API calls:
	- Optional metrics API for pod CPU/memory (if installed)

### Output bounding (required)

Limit returned output to keep responses manageable:
- At most 50 objects per resource list in the report
- At most 10 warning events in the summary
- At most 50 log lines per pod
- Truncate long text fields to 2000 characters

---

## Step 2 — Drill into unhealthy pods

For any pod that is:
- Not in `Running` or `Succeeded` phase
- In `Running` phase but with restarts > 5
- In `CrashLoopBackOff`, `OOMKilled`, `Error`, `Pending`, `ImagePullBackOff`

Fetch pod details and related events via API:
- `GET /api/v1/namespaces/{ns}/pods/{name}`
- `GET /api/v1/namespaces/{ns}/events?fieldSelector=involvedObject.name={name}`
- If supported by your tool implementation, retrieve pod/container logs using API-backed log access

For pending pods, pay attention to `Events` section in describe output — it often reveals scheduling failures (resource limits, node selectors, taints).

Do not run any mutating follow-up commands.

---

## Step 3 — Analyze and report

Structure your report in this order:

### Cluster Nodes
- Node count, status, any NotReady nodes
- Resource pressure (CPU/memory from metrics API when available)

### Deployments
- List all deployments with: desired / ready / available replicas
- Flag any deployment where ready < desired
- Note any deployments with recent rollout activity

### Pod Health Summary
- Total pods by phase (Running / Pending / Failed / Succeeded)
- List any pods with issues — include: name, namespace, phase, restart count, age
- For each unhealthy pod: summarize the log tail and describe events

### Events (Warnings)
- List the 10 most recent warning events
- Group by reason if multiple events share the same cause

### Ingress
- List all ingress rules: name, namespace, host(s), backend service(s), address
- Flag any ingress with no assigned address (not yet provisioned)

### Overall Health
End with a single verdict:

- **HEALTHY** — all pods running, no warnings, deployments fully available
- **DEGRADED** — some issues but cluster is operational (list them)
- **CRITICAL** — pods crashing, nodes not ready, or deployments unavailable (list them with urgency)

Include recommended next steps for any issues found.

When recommending next steps, separate them into:
- Read-only verification steps
- Optional remediation suggestions (clearly marked as not executed by this skill)

Never propose shell commands in this skill output; use Kubernetes API operations and resource/version terminology.
