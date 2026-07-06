---
name: workload-triage
description: Investigate workload failures (pods/deployments/statefulsets) using Kubernetes API evidence.
disable-model-invocation: true
allowed-tools: k8s_api_request
---

Perform workload troubleshooting with Kubernetes API calls only.

Rules:
- Read first, then diagnose.
- No mutating actions unless explicitly confirmed by user in a follow-up prompt.

Checklist:
1. List failing pods in relevant namespaces.
2. Inspect affected deployment/statefulset/daemonset status.
3. Pull related warning events.
4. Correlate restarts, probe failures, image pull errors, scheduling failures, and OOM patterns.
5. Produce:
   - Live State Assessment
   - Root Cause Hypothesis
   - Recommended Change with explicit rationale and risk
   - Confirmation request if mutation is needed
