---
name: networking-triage
description: Investigate service, endpoints, ingress, and network-policy issues via Kubernetes APIs.
disable-model-invocation: true
allowed-tools: k8s_api_request
---

Perform Kubernetes networking diagnostics using API reads.

Rules:
- Use API evidence only.
- No mutation without explicit second-prompt user confirmation.

Checklist:
1. Read Services and Endpoints for impacted app paths.
2. Read Ingress resources, hosts, backends, and status addresses.
3. Read warning Events for ingress controller/service endpoints.
4. Read NetworkPolicies in affected namespaces and identify blocked traffic patterns.
5. Report:
   - Live routing/data-plane findings
   - Most likely networking fault domain
   - Recommended change and why it is needed
   - Explicit confirmation request before any mutation
