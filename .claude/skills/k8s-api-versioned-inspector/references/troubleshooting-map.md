# Troubleshooting Map

Use this map to choose the smallest useful Kubernetes API surface for a debugging prompt.

## Symptom To Resource Map

| Prompt or symptom | Query first | Also inspect | Key evidence |
| --- | --- | --- | --- |
| Pod restarting, CrashLoopBackOff, ImagePullBackOff | `pods`, `events` | `deployments`, `replicasets`, `k8sgpt-results` | `containerStatuses`, restart counts, waiting reason, probe failures, image pull errors |
| Deployment rollout stalled or partially updated | `deployments`, `replicasets`, `pods`, `events` | `horizontalpodautoscalers`, `poddisruptionbudgets` | unavailable replicas, stale observed generation, waiting reasons, HPA scaling limits, PDB disruption pressure |
| Pod pending or unschedulable | `pods`, `events` | `nodes`, `persistentvolumeclaims`, `resourcequotas`, `limitranges` | `PodScheduled` condition, taints, node pressure, quota denials, PVC pending |
| Deployment stuck or rollout failing | `deployments`, `replicasets`, `events` | `pods`, `horizontalpodautoscalers`, `poddisruptionbudgets` | progressing conditions, replica counts, failed creates, unavailable replicas |
| Service unreachable | `services`, `endpoints`, `endpointslices` | `pods`, `deployments`, `events` | selector mismatch, empty endpoints, targetPort mismatch, not-ready backends |
| Ingress path or host broken | `ingresses`, `services`, `endpointslices`, `events` | `networkpolicies`, ingress controller pods | backend mapping, TLS refs, status load balancer, controller warnings |
| RBAC forbidden | `serviceaccounts`, `roles`, `rolebindings` | `clusterroles`, `clusterrolebindings`, `events` | service account subject mappings, allowed verbs, denied resources |
| Storage mount or claim failure | `persistentvolumeclaims`, `persistentvolumes`, `events` | `storageclasses`, `volumeattachments`, `csinodes`, `csistoragecapacities` | claim phase, access modes, attachment errors, provisioning failures |
| Cluster API extension issue | `apiservices`, `customresourcedefinitions`, `events` | controller workloads for the extension | unavailable APIService, failing webhook or aggregated API |
| Node instability | `nodes`, `events` | affected `pods`, `leases` | Ready condition, pressure signals, taints, lease freshness |
| General cluster overview | `version`, `nodes`, `namespaces` | `apiservices`, `leases`, `k8sgpt-results` | cluster version, unhealthy nodes, terminating namespaces, extension availability |
| Stuck namespace or terminating object | `namespaces`, `events` | `persistentvolumeclaims`, `customresourcedefinitions`, `apiservices` | `metadata.finalizers`, `deletionTimestamp`, blocking child resources |

## Recommended Flags

- Use `--summarize-events` when fetching `events` to get a prioritized warning view.
- Use `--diagnose-rollout` for deployment triage across Deployment, ReplicaSet, Pod, HPA, PDB, and warning event signals.
- Use `--trace service-path` for service-to-pod correlation.
- Use `--trace workload-path` or `--trace owner-chain` for deployment and controller lineage.
- Use `--trace storage-path` for `PVC -> PV -> VolumeAttachment` tracing.
- Use `--log-pod` with `--tail-lines`, `--since-seconds`, and `--previous` for targeted read-only pod log retrieval.
- Use `--finalizer-report` with `--bundle namespace-debug` for stuck namespace investigations.
- Use `--discover-api` before querying unfamiliar CRDs or aggregated APIs.

## Minimal Evidence Standard

Before asserting a root cause, gather at least two of these when available:

- primary resource status or conditions
- one or more relevant warning events
- owner or selector relationship
- corroborating node, storage, or RBAC evidence
- K8sGPT result or API extension health signal

## Safety Constraints

- Prefer namespace-scoped reads.
- Prefer selectors over large full-cluster lists.
- Treat `403` as evidence, not as a generic failure.
- Treat `404` on CRD or APIService paths as a likely absence signal.
- Never reveal Secret values.
