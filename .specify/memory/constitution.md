# k8sgpt DevOps Troubleshooting Platform — Constitution

> Core principles and invariants that govern this platform's development and operation.

## Meta

- **Project**: k8sgpt-based DevOps Troubleshooting Platform
- **Last Updated**: 2026-03-29
- **Version**: 1.0.0

## Purpose

This platform provides intelligent Kubernetes cluster troubleshooting through k8sgpt-powered analysis. The k8sgpt operator continuously analyzes clusters and produces Result CRDs, which power both a Grafana dashboard and an in-cluster troubleshooting chatbot. The system is fundamentally **read-only** — it observes, analyzes, and recommends, but never modifies the cluster.

## Core Principles

### 1. Read-Only Product Safety (NON-NEGOTIABLE)

**Invariant**: The k8sgpt operator and chatbot NEVER modify the cluster under any circumstances.

This platform is an **observational diagnostic tool**. Both the operator running on the cluster and the chatbot interface are designed exclusively for reading and analyzing cluster state. No component in this system has write access to Kubernetes resources.

**Enforcement**:
- All Kubernetes ServiceAccounts receive only read verbs (`get`, `list`, `watch`) in deployed manifests
- Chatbot backend has no `create`, `update`, `patch`, or `delete` permissions in cluster RBAC
- LLM prompts explicitly instruct the model to never suggest kubectl commands that modify resources
- Every new feature must include a verification step confirming it adds no write operations

**Rationale**: DevOps engineers rely on this tool to diagnose production issues. A tool that modifies the cluster could cause outages or data loss. Trust is paramount — users must be confident the system will not make changes.

### 2. Explainability

**Invariant**: Every AI-generated recommendation must include reasoning that helps the engineer understand the problem before acting.

When the system surfaces an issue or suggests a fix, it must answer:
- **Why was this flagged?** — The specific analysis that led to the finding
- **What is the evidence?** — The relevant cluster state, events, or metrics
- **What would fixing it involve?** — Not just a command, but the meaning behind it

**Enforcement**:
- Prompt templates require explanation sections in all recommendations
- K8sGPT Result CRDs include `details` field with contextual information
- Response parser validates that explanations are present before returning results

**Rationale**: DevOps engineers cannot safely act on recommendations they don't understand. The goal is to transfer knowledge, not create dependency on a black box.

### 3. Operator as Source of Truth

**Invariant**: The Grafana dashboard and chatbot derive from identical analyzed data and must remain in sync.

Both surfaces consume the same k8sgpt Result CRDs. The operator produces analysis results once; the dashboard renders them for visual inspection, and the chatbot reads them for conversational access. There is no separate pipeline or data transformation between them.

**Enforcement**:
- No feature that displays information in one surface but not the other
- Both surfaces use the same Result CRD schema and filters
- Integration tests verify parity between dashboard queries and chatbot responses

**Rationale**: Inconsistency between diagnostic surfaces erodes trust. An engineer might notice an issue in the dashboard and ask the chatbot about it — they expect the same answer.

### 4. DevOps-First UX

**Invariant**: The interface prioritizes information density, keyboard navigation, and minimal clicks to action.

DevOps engineers are power users who need fast access to relevant data. The system optimizes for:
- Dense, scannable information displays
- Keyboard shortcuts for common actions
- Time-to-resolution over visual polish
- Contextual actions without deep navigation

**Enforcement**:
- UI components must support keyboard navigation
- No unnecessary modal dialogs or multi-step wizards for common tasks
- Search and filter available without clicking
- Mobile-responsive is secondary to desktop keyboard-driven workflows

**Rationale**: Engineers using this tool are often responding to incidents under time pressure. Every extra click or page load costs time during a critical period.

### 5. Reliability Over Completeness

**Invariant**: The system prefers accurate, actionable findings over comprehensive coverage with potential false positives.

Noise destroys trust faster than missing occasional edge cases. A false positive about a non-existent problem wastes engineer time and trains users to ignore alerts. The platform宁可漏报 (prefer to miss) than to cry wolf.

**Enforcement**:
- k8sgpt analyzers are configured with conservative thresholds
- Confidence scores below threshold are not surfaced in the dashboard or chatbot
- Regular review of top issues to identify and suppress spurious patterns
- Users can filter by severity, not just view all results

**Rationale**: An engineer who ignores a tool because it cries wolf too often will miss real issues when they occur.

### 6. Development Access for Testing

**Invariant**: Development and test environments provide full read-write access for agents to deploy, test, and validate changes. Production enforces read-only access via RBAC.

The development lifecycle requires the ability to:
- Deploy updated operator versions
- Modify Result CRDs to test rendering
- Create/destroy test workloads
- Validate RBAC configurations

Production environments remain strictly read-only, enforced by:
- ClusterRole with read-only verbs only
- No ServiceAccount with write permissions in production namespaces
- Audit logging of all API access

**Enforcement**:
- Separate Helm values files for dev/staging vs. production
- RBAC manifests use environment-specific namespaces
- CI/CD pipelines validate production manifests have no write verbs

**Rationale**: Agents need full access to test their changes. Production must be safe to observe but impossible to modify through the platform.

### 7. Observability

**Invariant**: Every query and analysis is logged with sufficient context to reconstruct what happened and enable trending.

The system maintains:
- Full audit trail of chatbot queries and responses
- Timestamps and metadata for all Result CRDs
- Historical data for identifying patterns over time
- Query logs that include enrichment context (what data was available to the LLM)

**Enforcement**:
- All API endpoints log requests with session ID, timestamp, and query
- Result CRDs include creation timestamp and analyzer version
- Conversation history stored with cluster context
- Metrics exported for monitoring query patterns

**Rationale**: When diagnosing a cluster issue, engineers need to know what the system observed at the time. Historical context prevents repeating investigations.

### 8. Testability

**Invariant**: All components support deterministic testing with mock Kubernetes clusters and controlled test data.

The platform must be testable without a real cluster:
- Unit tests use mocked Kubernetes clients returning fixture data
- Integration tests use kind clusters or mocked API servers
- Test data is committed to the repository for reproducibility
- K8sGPT Result CRDs have fixture files representing common failure modes

**Enforcement**:
- All Kubernetes API calls go through abstraction layers that can be mocked
- Test fixtures cover: healthy cluster, CrashLoopBackOff, OOMKilled, Pending PVC, failing Ingress, etc.
- CI runs tests against mock data without requiring cluster access

**Rationale**: Deterministic tests with known inputs ensure the system behaves correctly before deployment. Tests that require real clusters are slow, flaky, and hard to reproduce.

## Architectural Decisions

### Read-Only Chatbot Backend

**Status**: Accepted
**Context**: The chatbot backend runs in the same cluster it monitors. If it had write permissions, a bug or compromise could modify production resources.
**Consequences**: 
- Positive: No risk of accidental or malicious cluster modification
- Negative: Cannot auto-remediate issues (this is by design)

### Decoupled Operator from Chatbot

**Status**: Accepted
**Context**: K8sGPT runs in each monitored cluster to analyze locally without cross-cluster authentication complexity.
**Consequences**:
- Positive: Each cluster's operator is self-contained; chatbot doesn't need cluster credentials for analysis
- Negative: Must deploy/manage operator per cluster (mitigated by ArgoCD)

### Result CRDs as Single Source of Truth

**Status**: Accepted
**Context**: Both dashboard and chatbot derive from the same k8sgpt analysis results.
**Consequences**:
- Positive: Single source of truth ensures consistency
- Negative: Dashboard and chatbot tied to k8sgpt Result schema

### RAG-Powered Knowledge Base

**Status**: Accepted
**Context**: Engineers accumulate tribal knowledge that should be searchable alongside live analysis.
**Consequences**:
- Positive: Historical solutions are easily rediscovered
- Negative: Adds complexity; KB seeding required for new deployments

## Non-Negotiable Rules

1. **Never deploy write permissions** to production clusters via this platform's manifests
2. **Never include kubectl apply/delete/edit commands** in AI recommendations
3. **Never log credentials or secrets** — only session IDs and timestamps
4. **Never skip explainability** — every finding must include reasoning
5. **Never cache false positives** — suspicious results are logged but not surfaced

## Enforcement Mechanisms

| Principle | Code Enforcement | Test Enforcement |
|-----------|-------------------|------------------|
| Read-Only Safety | RBAC manifests use only `get`, `list`, `watch` | Integration tests verify no write API calls |
| Explainability | Prompt templates require explanation fields | Response parser validates explanation presence |
| Operator as Source | Both surfaces consume same CRD types | Parity tests compare dashboard vs. chatbot data |
| DevOps-First UX | Keyboard navigation in all components | Accessibility tests verify shortcuts |
| Reliability | Confidence thresholds in config | Tests with known false positive data |
| Dev Access | Separate prod/dev manifests | CI validates prod manifests are read-only |
| Observability | Structured logging middleware | Log format validation tests |
| Testability | Mockable Kubernetes clients | Deterministic test suite with fixtures |

## Exceptions

### Dev/Test Cluster Access

**Exception**: Development and test clusters may have elevated permissions for testing purposes.
**Rationale**: Agents need write access to validate changes during development.
**Constraint**: This exception does not apply to any cluster labeled `environment=production`.

### Emergency Debug Mode

**Exception**: In extreme diagnostic scenarios, a separate debug namespace may be granted temporary write access for load testing or chaos engineering.
**Rationale**: Some issues require reproducing failures under load.
**Constraint**: Debug namespace is isolated from production workloads and access expires automatically.

## Review Process

This constitution is reviewed:
- **On every major feature addition**: New features must be evaluated against all principles
- **Quarterly**: Full review of principles for continued relevance
- **On incident**: Any incident that violated a principle triggers immediate review

Changes require:
1. Proposed update with rationale
2. Review for consistency with existing principles
3. Sign-off from platform lead
4. Documentation of changes in git history

## Appendix: k8sgpt Result CRD Schema Reference

The platform operates on the following Result CRD structure (enforced by the operator):

```yaml
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: <resource>-<kind>-<hash>
  namespace: <namespace>
  creationTimestamp: <timestamp>
spec:
  kind: <Pod|Deployment|Service|...>
  name: <resource-name>
  namespace: <namespace>
  error: <error-type>           # e.g., CrashLoopBackOff, OOMKilled
  details: <explanation>        # AI-generated reasoning (REQUIRED)
  severity: <critical|major|minor|unknown>
  sink: <target-ref>           # Where results are delivered
```
