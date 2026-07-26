"""
Centralized error handling with user-friendly messages and comprehensive logging.

Requirements: 17.1, 17.2, 17.3, 17.4, 17.5, 17.7
"""
from typing import Optional, Dict, Any, Callable, TypeVar, Awaitable, cast, TypedDict, List
from fastapi import HTTPException
from botocore.exceptions import ClientError, BotoCoreError
from kubernetes.client.exceptions import ApiException
import logging
import traceback
import time
from functools import wraps
from datetime import datetime
import asyncio

logger = logging.getLogger(__name__)

T = TypeVar('T')

# Stable machine codes shared with the frontend
AUTH_REQUIRED = "auth_required"
RBAC_FORBIDDEN = "rbac_forbidden"
CLUSTER_UNREACHABLE = "cluster_unreachable"
RATE_LIMITED = "rate_limited"
VALIDATION_ERROR = "validation_error"
TIMEOUT = "timeout"
INTERNAL_ERROR = "internal_error"
AGENT_STOP = "agent_stop"
AGENT_ERROR = "agent_error"


class ErrorInfo(TypedDict):
    message: str
    status: int


def _current_request_id() -> str:
    try:
        from middleware.request_id import get_request_id

        return get_request_id()
    except Exception:
        return "unknown"


def error_envelope(
    *,
    code: str,
    message: str,
    details: Any = None,
    recoverable: bool = True,
    request_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Standard API error body (plus detail mirror for legacy clients)."""
    rid = request_id or _current_request_id()
    body: Dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "details": details,
            "request_id": rid,
            "recoverable": recoverable,
        },
        "detail": message,
    }
    return body


def api_error(
    code: str,
    message: str,
    status_code: int = 500,
    *,
    details: Any = None,
    recoverable: Optional[bool] = None,
    headers: Optional[Dict[str, str]] = None,
) -> HTTPException:
    """Build an HTTPException with the standard envelope."""
    if recoverable is None:
        recoverable = status_code != 401
    rid = _current_request_id()
    hdrs = {"X-Error-Code": code, "X-Request-Id": rid}
    if headers:
        hdrs.update(headers)
    return HTTPException(
        status_code=status_code,
        detail=error_envelope(
            code=code,
            message=message,
            details=details,
            recoverable=recoverable,
            request_id=rid,
        ),
        headers=hdrs,
    )


def normalize_agent_errors(raw_errors: List[Any]) -> List[Dict[str, str]]:
    """Turn free-text agent errors into structured objects for the UI."""
    out: List[Dict[str, str]] = []
    for item in raw_errors or []:
        if isinstance(item, dict) and item.get("message"):
            out.append(
                {
                    "code": str(item.get("code") or AGENT_ERROR),
                    "message": str(item["message"]),
                    "severity": str(item.get("severity") or "warning"),
                }
            )
            continue
        text = str(item)
        code = AGENT_STOP if "Stop condition" in text else AGENT_ERROR
        severity = "warning" if code == AGENT_STOP else "error"
        out.append({"code": code, "message": text, "severity": severity})
    return out

# Import metrics (lazy import to avoid circular dependencies)
_metrics = None

def _get_metrics():
    """Lazy import of metrics module."""
    global _metrics
    if _metrics is None:
        try:
            from utils import metrics as _metrics_module
            _metrics = _metrics_module
        except ImportError:
            logger.warning("Metrics module not available")
            _metrics = None
    return _metrics


class UserFriendlyError(Exception):
    """Base exception for user-friendly errors."""
    
    def __init__(self, message: str, details: Optional[str] = None, status_code: int = 500):
        self.message = message
        self.details = details
        self.status_code = status_code
        super().__init__(self.message)


def log_error(
    error: Exception,
    context: str = "",
    user_id: Optional[str] = None,
    severity: str = "ERROR",
    additional_data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log errors with comprehensive information.
    
    Logs errors with severity, timestamp, user ID, stack trace, and additional context.
    Also records error metrics for Prometheus.
    
    Requirements: 17.1, 17.5
    
    Args:
        error: The exception that occurred
        context: Description of what operation failed
        user_id: User ID if available (for tracking user-specific errors)
        severity: Log severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        additional_data: Additional context data to log
    """
    timestamp = datetime.utcnow().isoformat()
    error_type = type(error).__name__
    error_message = str(error)
    stack_trace = traceback.format_exc()
    request_id = _current_request_id()

    log_data = {
        "timestamp": timestamp,
        "severity": severity,
        "error_type": error_type,
        "error_message": error_message,
        "context": context,
        "user_id": user_id or "anonymous",
        "request_id": request_id,
        "stack_trace": stack_trace,
    }

    if additional_data:
        log_data.update(additional_data)

    log_method = getattr(logger, severity.lower(), logger.error)
    log_method(
        f"request_id={request_id} Error in {context}: {error_type} - {error_message} | "
        f"User: {user_id or 'anonymous'}",
        extra=log_data,
    )
    
    # Record error metric
    metrics = _get_metrics()
    if metrics:
        component = additional_data.get('error_category', 'unknown') if additional_data else 'unknown'
        metrics.record_error(error_type, component)


def log_aws_api_call(
    operation: str,
    duration_ms: float,
    status: str,
    user_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log AWS API calls with duration and response status.
    
    Also records metrics for Prometheus monitoring.
    
    Requirements: 17.3, 17.5
    
    Args:
        operation: AWS operation name (e.g., "ListClusters", "DescribeCluster")
        duration_ms: Duration of the API call in milliseconds
        status: Response status ("success", "error", "throttled")
        user_id: User ID if available
        additional_data: Additional context data (region, cluster name, etc.)
    """
    timestamp = datetime.utcnow().isoformat()
    
    log_data = {
        "timestamp": timestamp,
        "operation": operation,
        "duration_ms": duration_ms,
        "status": status,
        "user_id": user_id or "anonymous",
        "api_type": "aws"
    }
    
    if additional_data:
        log_data.update(additional_data)
    
    logger.info(
        f"AWS API call: {operation} | "
        f"Duration: {duration_ms:.2f}ms | "
        f"Status: {status} | "
        f"User: {user_id or 'anonymous'}",
        extra=log_data
    )
    
    # Record metric
    metrics = _get_metrics()
    if metrics:
        metrics.record_aws_api_call(operation, status, duration_ms / 1000.0)


def log_llm_api_call(
    model: str,
    duration_ms: float,
    status: str,
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    user_id: Optional[str] = None,
    additional_data: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log LLM API calls with token counts and latency.
    
    Also records metrics for Prometheus monitoring.
    
    Requirements: 17.4, 17.5
    
    Args:
        model: LLM model name (e.g., "gpt-3.5-turbo", "claude-sonnet")
        duration_ms: Duration of the API call in milliseconds
        status: Response status ("success", "error", "rate_limited")
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        total_tokens: Total tokens (input + output)
        user_id: User ID if available
        additional_data: Additional context data
    """
    timestamp = datetime.utcnow().isoformat()
    
    log_data = {
        "timestamp": timestamp,
        "model": model,
        "duration_ms": duration_ms,
        "status": status,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "user_id": user_id or "anonymous",
        "api_type": "llm"
    }
    
    if additional_data:
        log_data.update(additional_data)
    
    logger.info(
        f"LLM API call: {model} | "
        f"Duration: {duration_ms:.2f}ms | "
        f"Status: {status} | "
        f"Tokens: {total_tokens or 'N/A'} (in: {input_tokens or 'N/A'}, out: {output_tokens or 'N/A'}) | "
        f"User: {user_id or 'anonymous'}",
        extra=log_data
    )
    
    # Record metric
    metrics = _get_metrics()
    if metrics:
        metrics.record_llm_api_call(
            model, status, duration_ms / 1000.0,
            input_tokens, output_tokens
        )


def aws_api_logger(operation: str):
    """
    Decorator to automatically log AWS API calls with duration and status.
    
    Requirements: 17.3
    
    Args:
        operation: AWS operation name
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            user_id = kwargs.get('user_id')
            status = "success"
            
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                log_aws_api_call(operation, duration_ms, status, user_id)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            user_id = kwargs.get('user_id')
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                status = "error"
                raise
            finally:
                duration_ms = (time.time() - start_time) * 1000
                log_aws_api_call(operation, duration_ms, status, user_id)
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def llm_api_logger(model: str):
    """
    Decorator to automatically log LLM API calls with token counts and latency.
    
    Requirements: 17.4
    
    Args:
        model: LLM model name
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            user_id = kwargs.get('user_id')
            status = "success"
            
            try:
                result = await func(*args, **kwargs)
                
                # Extract token counts from result if available
                input_tokens = None
                output_tokens = None
                total_tokens = None
                
                if isinstance(result, dict):
                    usage = result.get('usage', {})
                    input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens')
                    output_tokens = usage.get('output_tokens') or usage.get('completion_tokens')
                    total_tokens = usage.get('total_tokens')
                
                duration_ms = (time.time() - start_time) * 1000
                log_llm_api_call(
                    model, duration_ms, status,
                    input_tokens, output_tokens, total_tokens,
                    user_id
                )
                
                return result
            except Exception as e:
                status = "error"
                duration_ms = (time.time() - start_time) * 1000
                log_llm_api_call(model, duration_ms, status, user_id=user_id)
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            user_id = kwargs.get('user_id')
            status = "success"
            
            try:
                result = func(*args, **kwargs)
                
                # Extract token counts from result if available
                input_tokens = None
                output_tokens = None
                total_tokens = None
                
                if isinstance(result, dict):
                    usage = result.get('usage', {})
                    input_tokens = usage.get('input_tokens') or usage.get('prompt_tokens')
                    output_tokens = usage.get('output_tokens') or usage.get('completion_tokens')
                    total_tokens = usage.get('total_tokens')
                
                duration_ms = (time.time() - start_time) * 1000
                log_llm_api_call(
                    model, duration_ms, status,
                    input_tokens, output_tokens, total_tokens,
                    user_id
                )
                
                return result
            except Exception as e:
                status = "error"
                duration_ms = (time.time() - start_time) * 1000
                log_llm_api_call(model, duration_ms, status, user_id=user_id)
                raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


def retry_with_exponential_backoff(
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None
):
    """
    Decorator to retry functions with exponential backoff.
    
    Implements exponential backoff retry logic for handling transient failures,
    particularly for Kubernetes API connection failures.
    
    Requirements: 17.7
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        max_delay: Maximum delay in seconds between retries
        exponential_base: Base for exponential backoff calculation
        exceptions: Tuple of exception types to catch and retry
        on_retry: Optional callback function called on each retry
        
    Returns:
        Decorator function
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception: Optional[BaseException] = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    return await cast(Awaitable[T], result)
                except exceptions as e:
                    last_exception = e
                    
                    # Don't retry on RBAC 403 errors - these won't be fixed by retrying
                    if isinstance(e, ApiException) and e.status == 403:
                        logger.warning(f"RBAC permission denied (403) - not retrying: {e}")
                        raise
                    
                    # Don't retry on authentication errors
                    if isinstance(e, ApiException) and e.status == 401:
                        logger.warning(f"Authentication failed (401) - not retrying: {e}")
                        raise
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {type(e).__name__} - {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        if on_retry:
                            on_retry(attempt, e, delay)
                        
                        await asyncio.sleep(delay)
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        logger.error(
                            f"All {max_retries} retry attempts failed for {func.__name__}. "
                            f"Last error: {type(e).__name__} - {e}"
                        )
            
            # If we get here, all retries failed
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry failed without an exception")
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs) -> T:
            delay = initial_delay
            last_exception: Optional[BaseException] = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    
                    # Don't retry on RBAC 403 errors - these won't be fixed by retrying
                    if isinstance(e, ApiException) and e.status == 403:
                        logger.warning(f"RBAC permission denied (403) - not retrying: {e}")
                        raise
                    
                    # Don't retry on authentication errors
                    if isinstance(e, ApiException) and e.status == 401:
                        logger.warning(f"Authentication failed (401) - not retrying: {e}")
                        raise
                    
                    if attempt < max_retries:
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_retries} failed: {type(e).__name__} - {e}. "
                            f"Retrying in {delay:.2f}s..."
                        )
                        
                        if on_retry:
                            on_retry(attempt, e, delay)
                        
                        time.sleep(delay)
                        delay = min(delay * exponential_base, max_delay)
                    else:
                        logger.error(
                            f"All {max_retries} retry attempts failed for {func.__name__}. "
                            f"Last error: {type(e).__name__} - {e}"
                        )
            
            # If we get here, all retries failed
            if last_exception is not None:
                raise last_exception
            raise RuntimeError("Retry failed without an exception")
        
        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return cast(Callable[..., T], async_wrapper)
        return cast(Callable[..., T], sync_wrapper)
    
    return decorator


def k8s_api_retry(max_retries: int = 3, initial_delay: float = 1.0):
    """
    Specialized retry decorator for Kubernetes API calls.
    
    Retries on connection failures and transient errors, but not on
    RBAC 403 errors or authentication failures.
    
    Requirements: 17.7
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds before first retry
        
    Returns:
        Decorator function
    """
    return retry_with_exponential_backoff(
        max_retries=max_retries,
        initial_delay=initial_delay,
        max_delay=30.0,
        exponential_base=2.0,
        exceptions=(ApiException, ConnectionError, TimeoutError, OSError)
    )


def handle_aws_error(
    error: Exception,
    context: str = "",
    user_id: Optional[str] = None
) -> HTTPException:
    """
    Convert AWS/boto3 errors into user-friendly HTTP exceptions.
    
    Logs errors with comprehensive information including severity, timestamp,
    user ID, and stack trace.
    
    Requirements: 17.1, 17.2, 17.3
    
    Args:
        error: The AWS error
        context: Additional context about what operation failed
        user_id: User ID if available
        
    Returns:
        HTTPException with user-friendly message
    """
    # Log the error with comprehensive information
    log_error(error, context, user_id, severity="ERROR", additional_data={
        "error_category": "aws",
        "operation": context
    })
    
    if isinstance(error, ClientError):
        error_code = error.response.get('Error', {}).get('Code', 'Unknown')
        error_message = error.response.get('Error', {}).get('Message', str(error))
        
        # Map AWS error codes to user-friendly messages
        error_map: Dict[str, ErrorInfo] = {
            'InvalidClientTokenId': {
                'message': 'Invalid AWS access key. Please check your Kion credentials and try again.',
                'status': 401
            },
            'SignatureDoesNotMatch': {
                'message': 'Invalid AWS secret key. Please verify your Kion credentials.',
                'status': 401
            },
            'ExpiredToken': {
                'message': 'Your AWS session token has expired. Please get new credentials from Kion.',
                'status': 401
            },
            'AccessDenied': {
                'message': f'Access denied. Your AWS credentials do not have permission to {context}.',
                'status': 403
            },
            'UnauthorizedOperation': {
                'message': f'Unauthorized operation. You do not have permission to {context}.',
                'status': 403
            },
            'ResourceNotFoundException': {
                'message': f'Resource not found. The {context} you requested does not exist.',
                'status': 404
            },
            'ClusterNotFoundException': {
                'message': 'EKS cluster not found. It may have been deleted or you may not have access.',
                'status': 404
            },
            'ThrottlingException': {
                'message': 'Too many requests to AWS. Please wait a moment and try again.',
                'status': 429
            },
            'RequestLimitExceeded': {
                'message': 'AWS request limit exceeded. Please wait a moment and try again.',
                'status': 429
            }
        }
        
        error_info: ErrorInfo = error_map.get(error_code, {
            'message': f'AWS error: {error_message}',
            'status': 500
        })
        st = error_info["status"]
        code = (
            AUTH_REQUIRED if st == 401 else
            RBAC_FORBIDDEN if st == 403 else
            RATE_LIMITED if st == 429 else
            INTERNAL_ERROR
        )
        return api_error(code, error_info["message"], st, recoverable=st != 401)

    if isinstance(error, BotoCoreError):
        return api_error(
            INTERNAL_ERROR,
            "AWS connection error. Please check your network connection and try again.",
            500,
        )

    return api_error(
        INTERNAL_ERROR,
        f"An unexpected error occurred while {context}. Please try again.",
        500,
    )


def handle_k8s_error(
    error: Exception,
    context: str = "",
    user_id: Optional[str] = None
) -> HTTPException:
    """
    Convert Kubernetes API errors into user-friendly HTTP exceptions.
    
    Logs errors with comprehensive information including severity, timestamp,
    user ID, and stack trace.
    
    Requirements: 17.1, 17.2
    
    Args:
        error: The Kubernetes error
        context: Additional context about what operation failed
        user_id: User ID if available
        
    Returns:
        HTTPException with user-friendly message
    """
    # Log the error with comprehensive information
    log_error(error, context, user_id, severity="ERROR", additional_data={
        "error_category": "kubernetes",
        "operation": context
    })
    
    if isinstance(error, ApiException):
        status_code = error.status
        reason = error.reason
        
        # Map K8s error codes to user-friendly messages
        if status_code == 401:
            message = 'Kubernetes authentication failed. Your session may have expired. Please re-authenticate.'
            http_status = 401
        elif status_code == 403:
            message = f'Permission denied. You do not have access to {context} in this cluster.'
            http_status = 403
        elif status_code == 404:
            message = f'Resource not found. The {context} does not exist in this cluster.'
            http_status = 404
        elif status_code == 409:
            message = f'Conflict. The {context} already exists or is in an incompatible state.'
            http_status = 409
        elif status_code == 429:
            message = 'Too many requests to Kubernetes API. Please wait a moment and try again.'
            http_status = 429
        elif status_code >= 500:
            message = f'Kubernetes API error. The cluster may be experiencing issues. Please try again later.'
            http_status = 503
        else:
            message = f'Kubernetes error: {reason}'
            http_status = 500
        
        code = RBAC_FORBIDDEN if http_status == 403 else (
            AUTH_REQUIRED if http_status == 401 else (
                CLUSTER_UNREACHABLE if http_status == 503 else (
                    RATE_LIMITED if http_status == 429 else INTERNAL_ERROR
                )
            )
        )
        return api_error(
            code,
            message,
            http_status,
            recoverable=http_status != 401,
        )

    return api_error(
        INTERNAL_ERROR,
        f"An unexpected error occurred while {context}. Please try again.",
        500,
    )


def handle_generic_error(
    error: Exception,
    context: str = "",
    user_message: Optional[str] = None,
    user_id: Optional[str] = None,
) -> HTTPException:
    """
    Convert generic errors into user-friendly HTTP exceptions.
    """
    log_error(
        error,
        context,
        user_id,
        severity="ERROR",
        additional_data={"error_category": "generic", "operation": context},
    )

    if user_message:
        message = user_message
    else:
        message = (
            f"An error occurred while {context}. Please try again or contact "
            "support if the issue persists."
        )

    return api_error(INTERNAL_ERROR, message, 500, recoverable=True)


def create_error_response(
    message: str,
    details: Optional[str] = None,
    error_code: Optional[str] = None,
    suggestions: Optional[list] = None
) -> Dict[str, Any]:
    """
    Create a structured error response for the frontend.
    
    Args:
        message: User-friendly error message
        details: Additional technical details (optional)
        error_code: Machine-readable error code (optional)
        suggestions: List of suggested actions (optional)
        
    Returns:
        Structured error response dictionary
    """
    response = {
        'error': True,
        'message': message
    }
    
    if details:
        response['details'] = details
    
    if error_code:
        response['error_code'] = error_code
    
    if suggestions:
        response['suggestions'] = suggestions
    
    return response


# Common error messages
ERROR_MESSAGES = {
    'credentials_expired': {
        'message': 'Your session has expired. Please log in again with your Kion credentials.',
        'suggestions': [
            'Click the login button to re-authenticate',
            'Get fresh credentials from Kion',
            'Ensure your Kion session is still active'
        ]
    },
    'no_cluster_selected': {
        'message': 'No cluster selected. Please select a cluster from the dropdown.',
        'suggestions': [
            'Use the cluster selector at the top of the page',
            'Ensure you have access to at least one EKS cluster'
        ]
    },
    'cluster_unreachable': {
        'message': 'Unable to connect to the selected cluster. The cluster may be down or unreachable.',
        'suggestions': [
            'Check if the cluster is running in AWS console',
            'Verify your network connection',
            'Try selecting a different cluster',
            'Contact your cluster administrator'
        ]
    },
    'permission_denied': {
        'message': 'Permission denied. You do not have access to perform this operation.',
        'suggestions': [
            'Verify your IAM permissions in AWS',
            'Check your Kubernetes RBAC permissions',
            'Contact your administrator to request access'
        ]
    },
    'rate_limit_exceeded': {
        'message': 'Too many requests. Please wait a moment before trying again.',
        'suggestions': [
            'Wait 30-60 seconds before retrying',
            'Reduce the frequency of your requests'
        ]
    },
    'invalid_input': {
        'message': 'Invalid input. Please check your request and try again.',
        'suggestions': [
            'Verify all required fields are filled',
            'Check for any validation errors',
            'Ensure input formats are correct'
        ]
    }
}


def get_error_message(error_key: str) -> Dict[str, Any]:
    """
    Get a predefined error message by key.
    
    Args:
        error_key: Key for the error message
        
    Returns:
        Error message dictionary
    """
    return ERROR_MESSAGES.get(error_key, {
        'message': 'An unexpected error occurred. Please try again.',
        'suggestions': ['Refresh the page', 'Contact support if the issue persists']
    })
