---
name: k8s-api-versioned-inspector
description: Guide for inspecting live Kubernetes state from inside a cluster using direct read-only Kubernetes API calls and the generated API reference URL for the exact cluster version. This skill should be used when a DevOps engineer needs grounded cluster evidence for debugging, troubleshooting, or general cluster inspection.
compatibility: Requires execution inside a Kubernetes pod with mounted service account credentials and network access to the Kubernetes API server
metadata:
  author: kilo
  source: project-local
---

# Kubernetes API Versioned Inspector

## Purpose

Use the live Kubernetes API from inside the cluster to answer debugging, troubleshooting, and inspection prompts with observed evidence.

Discover the running Kubernetes version from `/version`, derive the generated API reference URL for that exact major and minor version, and use that URL as the canonical documentation source while reasoning about fields, resources, and endpoints.

Prefer direct API evidence over assumptions. Prefer read and list endpoints. Avoid write, patch, replace, delete, exec, and proxy operations unless the prompt explicitly requires them and policy allows them.

## When To Use

- Use when the prompt depends on current pod, workload, service, storage, RBAC, ingress, node, event, APIService, CRD, or K8sGPT state.
- Use when a DevOps engineer wants live cluster information instead of static or generic advice.
- Use when the answer should align with the generated API docs for the cluster's actual Kubernetes version.
- Skip when the task is only code editing, architecture discussion, or documentation work with no need for live cluster evidence.

## Workflow

1. Confirm that live cluster state matters for the prompt.
2. Verify in-cluster execution by checking `KUBERNETES_SERVICE_HOST` and mounted service account files.
3. Run `scripts/query_k8s_api.py` and let it query `/version` first.
4. Read `references/versioned-api-docs.md` to understand how the docs URL is derived.
5. Read `references/troubleshooting-map.md` to choose the smallest useful set of resources.
6. Use the derived docs URL from the script output as the canonical reference for the live cluster version.
7. Use `--trace service-path`, `--trace workload-path`, `--trace storage-path`, or `--trace owner-chain` when the prompt depends on object relationships rather than a single isolated resource.
8. Use `--summarize-events` to prioritize the highest-signal warning events by object, reason, count, and recency.
9. Use `--diagnose-rollout` for deployment triage when rollout blockers may involve ReplicaSets, Pods, HPAs, PDBs, and warning events together.
10. Use `--log-pod` with `--tail-lines`, `--since-seconds`, `--previous`, and `--log-container` for safe read-only pod log retrieval.
11. Use `--finalizer-report` and the `namespace-debug` bundle for stuck namespace or terminating resource investigations.
12. Use `--discover-api` when CRDs, aggregated APIs, or available resource types are unclear and the live cluster surface must be discovered first.
13. If the version-specific docs URL cannot be derived, fall back to the nearest stable generated API reference and state that limitation.
14. Gather events with the primary resource whenever possible. Events often explain scheduling failures, image pulls, RBAC denials, webhook failures, storage issues, and ingress/controller errors.
15. Treat API failures as evidence. Report `403` as an RBAC boundary, `404` as missing resource or absent CRD/APIService, and connection failures as cluster availability signals.
16. Never expose Secret values. Inspect Secret metadata only.
17. Separate the response into observed evidence, constraints, likely explanation, and next remediation step.

## Helper Script

Use the bundled direct REST client:

` .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py `

It uses the in-cluster service account token and CA bundle, calls the Kubernetes API directly, detects the cluster version from `/version`, returns a `docs_url` field for that exact major.minor version, can summarize warning events, can trace object relationships, can diagnose deployment rollouts, can fetch read-only pod logs, can report finalizers and terminating resources, and can discover the live API surface.

## First-Pass Examples

```bash
python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --resources version nodes namespaces

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --namespace default \
  --resources pods deployments events \
  --selector app=my-app

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --bundle service-connectivity \
  --namespace ingress-nginx

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --bundle storage \
  --namespace monitoring

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --namespace default \
  --name api \
  --diagnose-rollout \
  --trace service-path \
  --trace owner-chain \
  --summarize-events

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --namespace default \
  --log-pod api-6f9c7d78f5-x2abc \
  --log-container api \
  --tail-lines 200 \
  --since-seconds 1800 \
  --previous

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --bundle namespace-debug \
  --namespace stuck-namespace \
  --finalizer-report \
  --summarize-events

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --discover-api \
  --discover-limit 25

python .claude/skills/k8s-api-versioned-inspector/scripts/query_k8s_api.py \
  --raw-path /apis/apiregistration.k8s.io/v1/apiservices
```

## Resource Priorities

- For restart loops or pending workloads, inspect `pods`, `deployments`, `replicasets`, `statefulsets`, `daemonsets`, and `events`.
- For service reachability, inspect `services`, `endpoints`, `endpointslices`, `ingresses`, `networkpolicies`, and `events`.
- For autoscaling or rollout pressure, inspect `deployments`, `horizontalpodautoscalers`, `poddisruptionbudgets`, and `events`.
- For storage issues, inspect `persistentvolumeclaims`, `persistentvolumes`, `storageclasses`, `volumeattachments`, `csinodes`, and `events`.
- For authz issues, inspect `serviceaccounts`, `roles`, `rolebindings`, `clusterroles`, `clusterrolebindings`, and `events`.
- For API health and extension issues, inspect `apiservices`, `customresourcedefinitions`, `namespaces`, `nodes`, and targeted controller workloads.
- For cluster-wide diagnostics, inspect `version`, `nodes`, `namespaces`, `apiservices`, `leases`, and `k8sgpt-results` when present.

## Advanced Capabilities

- Use relationship tracing to correlate `Service -> EndpointSlice -> Pod -> ReplicaSet -> Deployment`, workload ownership chains, and `PVC -> PV -> VolumeAttachment` paths.
- Use event summaries to surface the most likely causative warning events before reading every raw event object.
- Use rollout diagnosis to correlate Deployment status with ReplicaSets, Pods, HPAs, PDBs, and warning events in one output.
- Use pod log retrieval for the smallest possible recent window instead of broad historical logs.
- Use finalizer reporting to identify objects stuck in deletion or blocked by residual finalizers.
- Use API discovery to enumerate live API groups, preferred versions, and available resources before querying CRDs or aggregated APIs.

## Safety Rules

- Keep all operations read-only.
- Avoid broad all-namespace queries when a namespace, resource name, or selector can narrow scope.
- Do not print Secret `data` or `stringData`.
- Prefer dedicated `--log-pod` retrieval over unrestricted raw log paths so log scope stays explicit and bounded.
- Do not mutate workloads, RBAC, CRDs, admission configuration, or storage objects from this skill.

## Reporting Pattern

Structure the final answer in this order:

1. Observed API evidence
2. Permission or visibility constraints
3. Most likely explanation
4. Next remediation step or next API endpoint to inspect

Quote exact resource names, namespaces, conditions, reasons, API groups, and the derived docs URL when available.
