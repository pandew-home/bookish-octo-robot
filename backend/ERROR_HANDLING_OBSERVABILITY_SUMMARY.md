# Error Handling and Observability Implementation Summary

## Overview

This document summarizes the implementation of comprehensive error handling and observability features for the DevOps Chatbot v2.0 backend, completing task 24 from the implementation plan.

## Requirements Addressed

- **17.1**: Comprehensive error logging with severity, timestamp, user ID, and stack trace
- **17.2**: User-friendly error messages without exposing internal details
- **17.3**: AWS API call logging with duration and response status
- **17.4**: LLM API call logging with token counts and latency
- **17.5**: Prometheus metrics for query latency, error rates, and API call counts
- **17.6**: Credential store eviction (already implemented in credential_store.py)
- **17.7**: Kubernetes API retry logic with exponential backoff

## Implementation Details

### 1. Comprehensive Error Logging (Subtask 24.1)

**File**: `utils/error_handler.py`

#### Features Implemented:

1. **`log_error()` function**:
   - Logs errors with severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
   - Includes timestamp in ISO format
   - Captures user ID (or "anonymous" if not provided)
   - Records full stack trace
   - Supports additional context data
   - Integrates with Prometheus metrics

2. **`log_aws_api_call()` function**:
   - Logs AWS API operations with operation name
   - Records duration in milliseconds
   - Captures response status (success, error, throttled)
   - Includes user ID and additional context
   - Records metrics for monitoring

3. **`log_llm_api_call()` function**:
   - Logs LLM API calls with model name
   - Records duration and status
   - Captures token counts (input, output, total)
   - Includes user ID
   - Records metrics for cost tracking

4. **Decorator functions**:
   - `@aws_api_logger(operation)`: Automatically logs AWS API calls
   - `@llm_api_logger(model)`: Automatically logs LLM API calls
   - Support both sync and async functions
   - Automatically extract timing and status information

#### Example Usage:

```python
from utils.error_handler import log_error, log_aws_api_call, aws_api_logger

# Manual logging
try:
    # Some operation
    pass
except Exception as e:
    log_error(e, context="processing query", user_id="user-123")

# Automatic logging with decorator
@aws_api_logger("ListClusters")
async def discover_clusters(creds):
    # AWS API call
    pass
```

### 2. Kubernetes API Retry Logic (Subtask 24.2)

**File**: `utils/error_handler.py`

#### Features Implemented:

1. **`retry_with_exponential_backoff()` decorator**:
   - Configurable max retries (default: 3)
   - Exponential backoff with configurable base (default: 2.0)
   - Maximum delay cap to prevent excessive waiting
   - Selective retry - does NOT retry on:
     - RBAC 403 errors (permission issues won't be fixed by retrying)
     - Authentication 401 errors (credentials need to be refreshed)
   - Supports both sync and async functions
   - Optional callback on each retry attempt

2. **`k8s_api_retry()` decorator**:
   - Specialized wrapper for Kubernetes API calls
   - Retries on connection failures, timeouts, and transient errors
   - Does not retry on permission or authentication errors
   - Default configuration optimized for K8s API

#### Example Usage:

```python
from utils.error_handler import k8s_api_retry

@k8s_api_retry(max_retries=3, initial_delay=1.0)
async def read_k8sgpt_results(custom_api, namespace):
    # Kubernetes API call with automatic retry
    return custom_api.list_namespaced_custom_object(...)
```

#### Integration Points:

- **k8sgpt_reader.py**: Added `@k8s_api_retry` to `read_results()` method
- **enrichment_engine.py**: Imported retry decorator for future use
- **cluster_manager.py**: Imported retry decorator for future use

### 3. Prometheus Metrics (Subtask 24.3)

**File**: `utils/metrics.py`

#### Metrics Implemented:

1. **Query Metrics**:
   - `chatbot_queries_total`: Counter for total queries (labeled by status, user_id)
   - `chatbot_query_latency_seconds`: Histogram for query processing time

2. **Error Metrics**:
   - `chatbot_errors_total`: Counter for errors (labeled by error_type, component)

3. **AWS API Metrics**:
   - `chatbot_aws_api_calls_total`: Counter for AWS API calls (labeled by operation, status)
   - `chatbot_aws_api_latency_seconds`: Histogram for AWS API latency

4. **Kubernetes API Metrics**:
   - `chatbot_k8s_api_calls_total`: Counter for K8s API calls (labeled by operation, status)
   - `chatbot_k8s_api_latency_seconds`: Histogram for K8s API latency

5. **LLM API Metrics**:
   - `chatbot_llm_api_calls_total`: Counter for LLM API calls (labeled by model, status)
   - `chatbot_llm_api_latency_seconds`: Histogram for LLM API latency
   - `chatbot_llm_tokens_total`: Counter for token consumption (labeled by model, token_type)

6. **System Metrics**:
   - `chatbot_active_sessions`: Gauge for active user sessions
   - `chatbot_credential_store_size`: Gauge for credentials in store
   - `chatbot_kb_solutions_total`: Gauge for solutions in knowledge base

#### Metrics Endpoint:

**File**: `app.py`

Added `/metrics` endpoint that exposes Prometheus metrics in standard text format:

```python
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    metrics_data, content_type = get_metrics()
    return Response(content=metrics_data, media_type=content_type)
```

#### Helper Functions:

```python
from utils.metrics import (
    record_query,
    record_error,
    record_aws_api_call,
    record_k8s_api_call,
    record_llm_api_call,
    update_active_sessions,
    update_credential_store_size,
    update_kb_solutions_total
)

# Record a query
record_query(status="success", user_id="user-123")

# Record an error
record_error(error_type="ValueError", component="enrichment")

# Record API calls
record_aws_api_call("ListClusters", "success", 0.5)
record_k8s_api_call("list_pods", "success", 0.3)
record_llm_api_call("gpt-3.5-turbo", "success", 2.5, 100, 50)

# Update gauges
update_active_sessions(42)
update_credential_store_size(15)
update_kb_solutions_total(128)
```

### 4. Enhanced Error Handlers

**File**: `utils/error_handler.py`

Updated existing error handlers to use comprehensive logging:

1. **`handle_aws_error()`**:
   - Now accepts optional `user_id` parameter
   - Calls `log_error()` with full context
   - Returns user-friendly messages without internal details

2. **`handle_k8s_error()`**:
   - Now accepts optional `user_id` parameter
   - Calls `log_error()` with full context
   - Returns user-friendly messages without internal details

3. **`handle_generic_error()`**:
   - Now accepts optional `user_id` parameter
   - Calls `log_error()` with full context
   - Returns user-friendly messages without internal details

## Testing

### Test Files:

1. **`tests/test_error_handler.py`**: Existing tests (23 tests) - all passing
2. **`tests/test_observability.py`**: New comprehensive tests (16 tests) - all passing

### Test Coverage:

- Comprehensive error logging with all required fields
- AWS API call logging with duration and status
- LLM API call logging with token counts
- Retry logic with exponential backoff
- Retry logic correctly skips RBAC 403 and auth 401 errors
- Prometheus metrics recording
- Metrics endpoint returns correct format
- User-friendly error messages without internal details

### Running Tests:

```bash
# Run all error handler tests
pytest tests/test_error_handler.py -v

# Run observability tests
pytest tests/test_observability.py -v

# Run all tests
pytest tests/ -v
```

## Dependencies Added

**File**: `requirements.txt`

```
prometheus-client==0.19.0
```

## Integration with Existing Code

The error handling and observability features integrate seamlessly with existing code:

1. **Logging functions** can be called from any module
2. **Retry decorators** can be applied to any function that makes K8s API calls
3. **Metrics functions** are integrated into error logging automatically
4. **Error handlers** maintain backward compatibility while adding new features

## Monitoring and Alerting

With the Prometheus metrics endpoint at `/metrics`, you can:

1. **Set up Prometheus scraping**:
   ```yaml
   scrape_configs:
     - job_name: 'devops-chatbot'
       static_configs:
         - targets: ['chatbot-backend:8000']
   ```

2. **Create Grafana dashboards** for:
   - Query latency percentiles (p50, p95, p99)
   - Error rates by component
   - AWS/K8s/LLM API call rates and latencies
   - Token consumption trends
   - Active sessions and system health

3. **Set up alerts** for:
   - High error rates
   - Slow query processing
   - API failures
   - High token consumption

## Best Practices

1. **Always include user_id** when logging errors or API calls for better traceability
2. **Use decorators** for automatic logging of API calls
3. **Apply retry logic** to transient failures, but not to permission/auth errors
4. **Monitor metrics** regularly to identify performance issues and cost trends
5. **Set up alerts** for critical error conditions

## Future Enhancements

Potential improvements for future iterations:

1. Structured logging with JSON format for better parsing
2. Distributed tracing with OpenTelemetry
3. Custom metrics for business-specific KPIs
4. Automated alerting rules
5. Log aggregation with ELK stack or CloudWatch
6. Performance profiling integration

## Conclusion

The error handling and observability implementation provides:

- ✅ Comprehensive error logging with all required fields
- ✅ User-friendly error messages
- ✅ AWS and LLM API call logging
- ✅ Kubernetes API retry logic with exponential backoff
- ✅ Prometheus metrics for monitoring
- ✅ Full test coverage
- ✅ Backward compatibility with existing code

All requirements (17.1-17.7) have been successfully implemented and tested.
