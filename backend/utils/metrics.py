"""
Prometheus metrics for observability.

This module provides Prometheus metrics for monitoring query latency,
error rates, and API call counts.

Requirements: 17.5
"""
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from typing import Optional
import time
from functools import wraps
import logging

logger = logging.getLogger(__name__)

# Query metrics
query_total = Counter(
    'chatbot_queries_total',
    'Total number of chat queries',
    ['status', 'user_id']
)

query_latency = Histogram(
    'chatbot_query_latency_seconds',
    'Query processing latency in seconds',
    ['endpoint'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0]
)

# Error metrics
errors_total = Counter(
    'chatbot_errors_total',
    'Total number of errors',
    ['error_type', 'component']
)

# API call metrics
aws_api_calls_total = Counter(
    'chatbot_aws_api_calls_total',
    'Total number of AWS API calls',
    ['operation', 'status']
)

aws_api_latency = Histogram(
    'chatbot_aws_api_latency_seconds',
    'AWS API call latency in seconds',
    ['operation'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

k8s_api_calls_total = Counter(
    'chatbot_k8s_api_calls_total',
    'Total number of Kubernetes API calls',
    ['operation', 'status']
)

k8s_api_latency = Histogram(
    'chatbot_k8s_api_latency_seconds',
    'Kubernetes API call latency in seconds',
    ['operation'],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

llm_api_calls_total = Counter(
    'chatbot_llm_api_calls_total',
    'Total number of LLM API calls',
    ['model', 'status']
)

llm_api_latency = Histogram(
    'chatbot_llm_api_latency_seconds',
    'LLM API call latency in seconds',
    ['model'],
    buckets=[0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 30.0, 60.0]
)

llm_tokens_total = Counter(
    'chatbot_llm_tokens_total',
    'Total number of LLM tokens consumed',
    ['model', 'token_type']
)

# System metrics
active_sessions = Gauge(
    'chatbot_active_sessions',
    'Number of active user sessions'
)

credential_store_size = Gauge(
    'chatbot_credential_store_size',
    'Number of credentials in store'
)

kb_solutions_total = Gauge(
    'chatbot_kb_solutions_total',
    'Total number of solutions in knowledge base'
)


def track_query_latency(endpoint: str):
    """
    Decorator to track query latency.
    
    Args:
        endpoint: Endpoint name for labeling
        
    Returns:
        Decorator function
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                query_latency.labels(endpoint=endpoint).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                query_latency.labels(endpoint=endpoint).observe(duration)
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def record_query(status: str, user_id: Optional[str] = None):
    """
    Record a query execution.
    
    Args:
        status: Query status ('success', 'error', 'rate_limited')
        user_id: User ID (optional, defaults to 'anonymous')
    """
    query_total.labels(
        status=status,
        user_id=user_id or 'anonymous'
    ).inc()


def record_error(error_type: str, component: str):
    """
    Record an error occurrence.
    
    Args:
        error_type: Type of error (e.g., 'ApiException', 'ClientError')
        component: Component where error occurred (e.g., 'enrichment', 'rag')
    """
    errors_total.labels(
        error_type=error_type,
        component=component
    ).inc()


def record_aws_api_call(operation: str, status: str, duration_seconds: float):
    """
    Record an AWS API call.
    
    Args:
        operation: AWS operation name (e.g., 'ListClusters')
        status: Call status ('success', 'error', 'throttled')
        duration_seconds: Call duration in seconds
    """
    aws_api_calls_total.labels(
        operation=operation,
        status=status
    ).inc()
    
    aws_api_latency.labels(
        operation=operation
    ).observe(duration_seconds)


def record_k8s_api_call(operation: str, status: str, duration_seconds: float):
    """
    Record a Kubernetes API call.
    
    Args:
        operation: K8s operation name (e.g., 'list_pods')
        status: Call status ('success', 'error', 'permission_denied')
        duration_seconds: Call duration in seconds
    """
    k8s_api_calls_total.labels(
        operation=operation,
        status=status
    ).inc()
    
    k8s_api_latency.labels(
        operation=operation
    ).observe(duration_seconds)


def record_llm_api_call(
    model: str,
    status: str,
    duration_seconds: float,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None
):
    """
    Record an LLM API call.
    
    Args:
        model: LLM model name (e.g., 'gpt-3.5-turbo')
        status: Call status ('success', 'error', 'rate_limited')
        duration_seconds: Call duration in seconds
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
    """
    llm_api_calls_total.labels(
        model=model,
        status=status
    ).inc()
    
    llm_api_latency.labels(
        model=model
    ).observe(duration_seconds)
    
    if input_tokens is not None:
        llm_tokens_total.labels(
            model=model,
            token_type='input'
        ).inc(input_tokens)
    
    if output_tokens is not None:
        llm_tokens_total.labels(
            model=model,
            token_type='output'
        ).inc(output_tokens)


def update_active_sessions(count: int):
    """
    Update the active sessions gauge.
    
    Args:
        count: Current number of active sessions
    """
    active_sessions.set(count)


def update_credential_store_size(count: int):
    """
    Update the credential store size gauge.
    
    Args:
        count: Current number of credentials in store
    """
    credential_store_size.set(count)


def update_kb_solutions_total(count: int):
    """
    Update the knowledge base solutions gauge.
    
    Args:
        count: Current number of solutions in KB
    """
    kb_solutions_total.set(count)


def get_metrics() -> tuple[bytes, str]:
    """
    Get Prometheus metrics in text format.
    
    Returns:
        Tuple of (metrics_bytes, content_type)
    """
    return generate_latest(), CONTENT_TYPE_LATEST
