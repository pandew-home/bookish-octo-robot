---
name: rbac-triage
description: Diagnose Kubernetes permission issues by inspecting roles, bindings, and subject mappings.
disable-model-invocation: true
allowed-tools: k8s_api_request
---

Diagnose RBAC failures with API reads only.

Rules:
- Gather full authorization context before suggesting changes.
- If change is required, explain blast radius and ask for explicit confirmation.

Checklist:
1. Capture failing subject identity and denied verb/resource/namespace.
2. Read Role/ClusterRole objects related to requested resource access.
3. Read RoleBinding/ClusterRoleBinding objects and map subject-to-role grants.
4. Identify the smallest permission delta that would resolve the failure.
5. Provide:
   - Exact current authorization gap
   - Minimal recommended RBAC adjustment with rationale
   - Explicit second-prompt confirmation request before mutation
