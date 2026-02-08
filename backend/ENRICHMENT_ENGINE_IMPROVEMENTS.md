# Enrichment Engine Improvements

## Issues Identified and Fixed

### 1. Missing KB_SEARCH Category Handling ✅

**Problem**: The `QueryCategory.KB_SEARCH` was defined in the query router but not handled in the enrichment engine.

**Solution**: Added explicit handling for KB_SEARCH category:
```python
elif category == QueryCategory.KB_SEARCH:
    # KB_SEARCH doesn't need cluster enrichment, just K8sGPT results
    logger.info("KB_SEARCH category - skipping cluster enrichment")
```

**Rationale**: Knowledge base searches don't need live cluster data - they search historical documentation and solutions. Only K8sGPT results are relevant.

### 2. No Default/Fallback Enrichment ✅

**Problem**: If no categories matched or an unknown category was provided, the engine would return an empty context with no useful data.

**Solution**: Added default enrichment fallback:
```python
# If no enrichment tasks were created (e.g., only KB_SEARCH), add default enrichment
if not tasks and QueryCategory.KB_SEARCH not in plan.categories:
    logger.info("No specific enrichment tasks - adding default cluster context")
    tasks.append(self._enrich_general_health(plan))
```

**Rationale**: Always provide some cluster context unless it's explicitly a KB-only search. This ensures the LLM has basic cluster information even for vague queries.

### 3. Inconsistent Namespace Handling ✅

**Problem**: Every enrichment method had duplicate code for getting the namespace:
```python
namespace = plan.namespaces[0] if plan.namespaces else 'default'
```

**Solution**: Created a helper method for consistent namespace handling:
```python
def _get_namespace(self, plan: EnrichmentPlan) -> str:
    """
    Get namespace from plan or return default.
    
    Args:
        plan: Enrichment plan
        
    Returns:
        Namespace string
    """
    return plan.namespaces[0] if plan.namespaces else 'default'
```

**Benefits**:
- DRY (Don't Repeat Yourself) principle
- Single source of truth for namespace logic
- Easier to modify default behavior in the future
- More testable

**Updated Methods**:
- `_enrich_pods()`
- `_enrich_deployments()`
- `_enrich_services()`
- `_enrich_storage()`
- `_enrich_security()`
- `_enrich_general_health()`

## Additional Improvements to Consider

### 1. Metrics Enrichment (Future Enhancement)

**What**: Add metrics-server data for CPU/memory usage
```python
async def _enrich_metrics(self, plan: EnrichmentPlan) -> Dict[str, Any]:
    """Enrich with metrics-server data if available."""
    try:
        # Get pod metrics
        metrics = custom_metrics.list_namespaced_custom_object(
            group="metrics.k8s.io",
            version="v1beta1",
            namespace=namespace,
            plural="pods"
        )
        # Format and return
    except ApiException as e:
        if e.status == 404:
            return {'error': 'Metrics server not installed'}
```

**When to add**: When users frequently ask about resource usage

### 2. ConfigMap/Secret Enrichment (Future Enhancement)

**What**: Add ConfigMap and Secret metadata (not values) enrichment
```python
async def _enrich_config(self, plan: EnrichmentPlan) -> Dict[str, Any]:
    """Enrich with ConfigMap and Secret metadata."""
    # Get ConfigMaps
    configmaps = core_v1.list_namespaced_config_map(namespace)
    # Get Secrets (metadata only, not data)
    secrets = core_v1.list_namespaced_secret(namespace)
```

**When to add**: When users ask about configuration issues

### 3. Event Aggregation (Future Enhancement)

**What**: Aggregate all events across resources for timeline view
```python
async def _enrich_events_timeline(self, plan: EnrichmentPlan) -> Dict[str, Any]:
    """Create timeline of all events in namespace."""
    events = core_v1.list_namespaced_event(namespace, limit=100)
    # Sort by timestamp
    # Group by resource
    # Return timeline
```

**When to add**: When users ask "what happened in the last hour?"

### 4. StatefulSet/DaemonSet Enrichment (Future Enhancement)

**What**: Add enrichment for StatefulSets and DaemonSets
```python
async def _enrich_statefulsets(self, plan: EnrichmentPlan) -> Dict[str, Any]:
    """Enrich with StatefulSet data."""
    statefulsets = apps_v1.list_namespaced_stateful_set(namespace)
    # Format similar to deployments
```

**When to add**: When users have StatefulSet-heavy workloads

### 5. HPA (Horizontal Pod Autoscaler) Enrichment (Future Enhancement)

**What**: Add HPA status and metrics
```python
async def _enrich_hpa(self, plan: EnrichmentPlan) -> Dict[str, Any]:
    """Enrich with HPA data."""
    hpas = autoscaling_v1.list_namespaced_horizontal_pod_autoscaler(namespace)
    # Include current/desired replicas, metrics
```

**When to add**: When users ask about scaling issues

### 6. Job/CronJob Enrichment (Future Enhancement)

**What**: Add Job and CronJob status
```python
async def _enrich_jobs(self, plan: EnrichmentPlan) -> Dict[str, Any]:
    """Enrich with Job and CronJob data."""
    jobs = batch_v1.list_namespaced_job(namespace)
    cronjobs = batch_v1.list_namespaced_cron_job(namespace)
    # Include success/failure counts, last run times
```

**When to add**: When users have batch workloads

## Testing Additions

Added 5 new tests for the improvements:

1. **test_kb_search_category_skips_enrichment**: Verifies KB_SEARCH doesn't trigger cluster enrichment
2. **test_empty_categories_adds_default_enrichment**: Verifies fallback to general health
3. **test_get_namespace_with_plan_namespace**: Tests namespace extraction from plan
4. **test_get_namespace_defaults_to_default**: Tests default namespace fallback
5. **test_get_namespace_uses_first_namespace**: Tests multiple namespace handling

**Total Tests**: 45+ (up from 40+)

## Impact Summary

### Code Quality
- **Reduced duplication**: 6 methods now use shared `_get_namespace()` helper
- **Better error handling**: KB_SEARCH category explicitly handled
- **Improved robustness**: Default enrichment ensures useful data always returned

### User Experience
- **More consistent**: All queries get some cluster context
- **Better KB searches**: KB_SEARCH category properly handled without unnecessary API calls
- **Clearer intent**: Logging shows when default enrichment is used

### Maintainability
- **Easier to modify**: Namespace logic in one place
- **More testable**: Helper method can be tested independently
- **Better documentation**: Clear rationale for each improvement

## Recommendations

### Short Term (Now)
- ✅ KB_SEARCH handling - **DONE**
- ✅ Default enrichment fallback - **DONE**
- ✅ Namespace helper method - **DONE**

### Medium Term (Next Sprint)
- Consider adding metrics enrichment if metrics-server is commonly available
- Add ConfigMap/Secret metadata enrichment for configuration debugging
- Add event timeline aggregation for "what happened" queries

### Long Term (Future)
- Add StatefulSet/DaemonSet enrichment based on usage patterns
- Add HPA enrichment for scaling-related queries
- Add Job/CronJob enrichment for batch workload debugging

## Migration Notes

**Breaking Changes**: None - all changes are backward compatible

**API Changes**: None - public interface unchanged

**Configuration Changes**: None required

**Testing**: All existing tests pass + 5 new tests added
