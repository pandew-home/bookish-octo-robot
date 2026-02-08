# Template and Query Router Mapping Analysis

## Overview

This document analyzes the alignment between prompt templates and query router categories in DevOps Chatbot v2.

## Query Router Categories (9 total)

The query router classifies queries into these categories:

1. **POD_ISSUE** - Pod-related problems (crashes, restarts, failures)
2. **DEPLOYMENT_STATUS** - Deployment, rollout, and scaling issues
3. **SERVICE_NETWORKING** - Service, ingress, DNS, and connectivity issues
4. **NODE_HEALTH** - Node capacity, taints, and kubelet issues
5. **STORAGE** - PVC, volume, and storage class issues
6. **ARGOCD** - GitOps, sync, and ArgoCD application issues
7. **SECURITY** - RBAC, permissions, and security policies
8. **GENERAL_HEALTH** - Overall cluster health queries
9. **KB_SEARCH** - Knowledge base search queries

## Prompt Templates (7 total)

The template system provides these templates:

1. **troubleshooting** - General troubleshooting template
2. **deployment** - Deployment and configuration issues
3. **networking** - Networking and DNS issues
4. **security** - Security and RBAC issues
5. **gitops** - GitOps and ArgoCD issues
6. **analysis** - Cluster state and performance analysis
7. **general** - Miscellaneous queries

## Mapping Analysis

### ✅ Direct Mappings (Good Alignment)

| Query Category | Template | Notes |
|----------------|----------|-------|
| DEPLOYMENT_STATUS | deployment | Perfect match for deployment issues |
| SERVICE_NETWORKING | networking | Perfect match for networking issues |
| SECURITY | security | Perfect match for security/RBAC issues |
| ARGOCD | gitops | Perfect match for GitOps/ArgoCD issues |

### ⚠️ Indirect Mappings (Need Template Selection Logic)

| Query Category | Suggested Template | Reasoning |
|----------------|-------------------|-----------|
| POD_ISSUE | troubleshooting | Pods are the most common troubleshooting target |
| NODE_HEALTH | troubleshooting | Node issues require troubleshooting approach |
| STORAGE | troubleshooting | Storage issues require investigation |
| GENERAL_HEALTH | analysis | Health queries benefit from analysis template |
| KB_SEARCH | general | KB searches are general queries |

### ❌ Missing Templates

No critical gaps identified. The current template set covers all query categories adequately.

## Recommended Template Selection Logic

```python
def select_template(query_category: QueryCategory) -> str:
    """Map query category to appropriate template."""
    
    template_map = {
        # Direct mappings
        QueryCategory.DEPLOYMENT_STATUS: "deployment",
        QueryCategory.SERVICE_NETWORKING: "networking",
        QueryCategory.SECURITY: "security",
        QueryCategory.ARGOCD: "gitops",
        
        # Troubleshooting mappings
        QueryCategory.POD_ISSUE: "troubleshooting",
        QueryCategory.NODE_HEALTH: "troubleshooting",
        QueryCategory.STORAGE: "troubleshooting",
        
        # Analysis/General mappings
        QueryCategory.GENERAL_HEALTH: "analysis",
        QueryCategory.KB_SEARCH: "general",
    }
    
    return template_map.get(query_category, "troubleshooting")
```

## Template Summaries

### 1. Base Template (Applied to All)
**Purpose:** Foundation for all templates
**Key Features:**
- Identifies as "Kubernetes troubleshooting assistant for EKS clusters"
- Emphasizes K8sGPT findings integration
- Requires safety warnings for destructive operations
- Never fabricates resource names or log entries
- Output format: Assessment → Evidence → Fix → Safety → Verification → KB Articles

### 2. Troubleshooting Template
**Purpose:** Root cause analysis and debugging
**Focus:** Step-by-step investigation, kubectl commands, K8sGPT CRDs
**Output:** Issue Assessment → Investigation → Root Cause → Remediation → Verification
**Best For:** POD_ISSUE, NODE_HEALTH, STORAGE

### 3. Deployment Template
**Purpose:** Deployment configuration and rollout issues
**Focus:** Helm, ArgoCD, GitOps, version control
**Output:** Config Assessment → Issues → Changes → Strategy → Verification/Rollback
**Best For:** DEPLOYMENT_STATUS

### 4. Networking Template
**Purpose:** Network connectivity and DNS problems
**Focus:** Service mesh (Istio/Linkerd/Cilium), network policies, ingress
**Output:** Connectivity → DNS Analysis → Service Mesh → Root Cause → Remediation
**Best For:** SERVICE_NETWORKING

### 5. Security Template
**Purpose:** RBAC, permissions, and security policies
**Focus:** Least-privilege, compliance, audit logging
**Output:** Security Assessment → Vulnerabilities → RBAC → Remediation → Monitoring
**Best For:** SECURITY

### 6. GitOps Template
**Purpose:** ArgoCD/Flux sync and drift issues
**Focus:** Sync status, drift detection, reconciliation
**Output:** GitOps State → Sync Analysis → Drift → Remediation → Prevention
**Best For:** ARGOCD

### 7. Analysis Template
**Purpose:** Cluster state and performance analysis
**Focus:** Trends, patterns, optimizations
**Output:** Current State → Trends → Issues → Recommendations → Optimizations
**Best For:** GENERAL_HEALTH

### 8. General Template
**Purpose:** Miscellaneous queries and KB searches
**Focus:** Helpful guidance, clarifying questions
**Output:** Summary → Guidance → Next Steps
**Best For:** KB_SEARCH, unclassified queries

## Integration with Template Engine

The `template_engine.py` already supports all these templates through the `render()` method:

```python
def render(
    self,
    query_category: str,  # Maps to template name
    cluster_context: Dict[str, Any],
    kb_results: List[Dict[str, Any]],
    query: str,
    cluster_name: str,
    k8sgpt_results: Optional[List[Dict[str, Any]]] = None
) -> str
```

## Recommendations

### 1. Add Template Selection Helper
Create a helper function in `template_engine.py` to map query categories to templates:

```python
def get_template_for_category(self, category: QueryCategory) -> str:
    """Get appropriate template name for query category."""
    # Use the mapping logic above
```

### 2. Consider Adding Templates (Optional)
- **storage** template - Dedicated template for PVC/volume issues
- **node** template - Dedicated template for node-specific issues

However, the current "troubleshooting" template handles these well, so this is low priority.

### 3. Template Validation
The current implementation validates that all templates have required fields:
- ✅ system_rules
- ✅ constraints
- ✅ output_format

## Conclusion

**Status:** ✅ Templates are well-aligned with query router categories

**Coverage:** 100% - All query categories have appropriate templates

**Quality:** High - Templates are specific, actionable, and include safety considerations

**Action Items:**
1. Add template selection helper function (5 minutes)
2. Update template engine tests to verify category mapping (10 minutes)
3. Document template selection in API integration guide (5 minutes)

The template system is production-ready and integrates seamlessly with the query router.
