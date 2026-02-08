# RAG Integration Error Handling

## Overview

The RAG integration includes comprehensive error handling at every layer to ensure graceful degradation and user-friendly error messages.

## Error Handling Layers

### 1. LLM Client Initialization

**Errors Handled:**
- **ImportError**: Missing LLM client library
  - Message: "LLM client library not available. Please install the required package for {provider}."
  - Action: Raises ValueError with installation instructions

- **Authentication Error**: Invalid API key
  - Message: "Invalid API key for {provider}. Please check your API key configuration."
  - Action: Raises ValueError with environment variable instructions

- **Generic Errors**: Other initialization failures
  - Message: "Failed to initialize LLM client: {error}"
  - Action: Raises ValueError with error details

**Example:**
```python
try:
    client = OpenAIClient(api_key=api_key, model=model)
except Exception as e:
    if "api_key" in str(e).lower():
        raise ValueError("Invalid API key. Set OPENAI_API_KEY environment variable.")
```

### 2. Knowledge Base Initialization

**Errors Handled:**
- **FileNotFoundError**: KB path doesn't exist
  - Action: Returns None, logs warning, continues without KB

- **PermissionError**: No access to KB directory
  - Action: Returns None, logs warning, continues without KB

- **Generic Errors**: Other KB initialization failures
  - Action: Returns None, logs warning, continues without KB

**Graceful Degradation:**
- System continues to function without knowledge base
- Queries are processed using only cluster context
- No semantic search available, but basic Q&A still works

### 3. Vector Store Initialization

**Errors Handled:**
- **ImportError**: FAISS library not available
  - Action: Returns None, logs warning, continues without vector store

- **Embedding Errors**: Individual document embedding failures
  - Action: Skips failed document, continues with others
  - Logs warning for each failure

- **Generic Errors**: Other vector store failures
  - Action: Returns None, logs warning, continues without vector store

**Graceful Degradation:**
- System continues without semantic search
- Knowledge base documents not indexed
- Queries processed with cluster context only

**Example:**
```python
for doc in documents:
    try:
        embedding = self.llm_client.embed(doc.get('content', ''))
        vector_store.add(embedding=embedding, metadata=doc)
    except Exception as e:
        logger.warning(f"Failed to embed document {doc.get('id')}: {e}")
        continue  # Skip this document, continue with others
```

### 4. Query Processing

**Errors Handled:**
- **Rate Limit Errors**: LLM API rate limiting
  - Message: "The LLM service is currently rate-limited. Please wait a moment and try again."
  - Returns structured error response

- **Timeout Errors**: Request timeouts
  - Message: "The request timed out. The cluster may be slow to respond. Please try again."
  - Returns structured error response

- **Authentication Errors**: API key issues during query
  - Message: "There's an issue with the LLM API authentication. Please contact your administrator."
  - Returns structured error response

- **Connection Errors**: Network connectivity issues
  - Message: "Unable to connect to the LLM service. Please check your network connection."
  - Returns structured error response

- **Generic Errors**: Other processing failures
  - Message: "Please try rephrasing your question or contact support if the issue persists."
  - Returns structured error response

**Error Response Structure:**
```python
{
    'query': query,
    'response': user_friendly_message,
    'citations': [],
    'errors': [
        {
            'type': 'rag_processing',
            'message': technical_error_message,
            'severity': 'error'
        }
    ],
    'metadata': {'error_handled': True}
}
```

### 5. Knowledge Base Search

**Errors Handled:**
- **No Vector Store**: Vector store not initialized
  - Action: Returns empty list, logs warning

- **Embedding Errors**: Query embedding failures
  - Action: Returns empty list, logs error

- **Search Errors**: Vector store search failures
  - Action: Returns empty list, logs error

**Graceful Degradation:**
- Returns empty results rather than failing
- Allows query processing to continue
- User gets response without KB context

## Error Severity Levels

### Critical (Raises Exception)
- LLM client initialization failures
- Invalid API keys
- Missing required libraries

**Rationale**: These prevent the system from functioning at all

### Warning (Logs and Continues)
- Knowledge base initialization failures
- Vector store initialization failures
- Individual document embedding failures
- Knowledge base search failures

**Rationale**: System can still function without these features

### Error (Returns Error Response)
- Query processing failures
- LLM API errors during query
- Rate limiting
- Timeouts

**Rationale**: User should know the query failed but system remains operational

## User-Friendly Error Messages

### Principles
1. **No technical jargon**: Avoid stack traces, error codes
2. **Actionable**: Tell user what to do next
3. **Contextual**: Explain what went wrong in user terms
4. **Helpful**: Provide suggestions for resolution

### Examples

**Bad:**
```
Error: openai.error.RateLimitError: Rate limit reached for default-gpt-3.5-turbo
```

**Good:**
```
The LLM service is currently rate-limited. Please wait a moment and try again.
```

**Bad:**
```
Exception: Connection refused [Errno 111]
```

**Good:**
```
Unable to connect to the LLM service. Please check your network connection.
```

## Testing Coverage

### Error Scenarios Tested (30+ tests)
1. LLM client import errors
2. LLM client API key errors
3. Knowledge base file not found
4. Knowledge base permission denied
5. Vector store import errors
6. Individual document embedding failures
7. Query processing rate limit errors
8. Query processing timeout errors
9. Query processing authentication errors
10. Query processing connection errors
11. Knowledge base search errors

### Test Strategy
- Mock external dependencies (OpenAI, FAISS, KB)
- Simulate various error conditions
- Verify graceful degradation
- Verify user-friendly error messages
- Verify error logging

## Logging Strategy

### Log Levels

**ERROR**: Critical failures that prevent operation
```python
logger.error(f"Failed to initialize LLM client: {e}")
```

**WARNING**: Non-critical failures with graceful degradation
```python
logger.warning(f"Failed to initialize knowledge base: {e}")
```

**INFO**: Normal operational messages
```python
logger.info(f"RAG integration initialized with {llm_provider}/{llm_model}")
```

**DEBUG**: Detailed diagnostic information
```python
logger.debug("No AWS context retrieved")
```

### What Gets Logged

**Always Logged:**
- Initialization success/failure
- Query processing errors
- API errors (rate limits, timeouts)
- Configuration issues

**Never Logged:**
- API keys or credentials
- User query content (privacy)
- Full error responses (may contain sensitive data)

## Integration with Centralized Error Handler

The RAG integration complements the centralized error handler:

**Centralized Handler** (`utils/error_handler.py`):
- Handles AWS errors
- Handles Kubernetes API errors
- Converts to HTTP exceptions

**RAG Integration** (`rag_integration.py`):
- Handles LLM API errors
- Handles knowledge base errors
- Handles vector store errors
- Returns structured error responses

**Together**: Provide comprehensive error coverage across all system components

## Future Enhancements

### 1. Retry Logic
Add exponential backoff for transient errors:
```python
@retry(max_attempts=3, backoff=exponential)
def process_query(...):
    # Query processing
```

### 2. Circuit Breaker
Prevent cascading failures:
```python
if error_rate > threshold:
    return cached_response or fallback_response
```

### 3. Error Metrics
Track error rates for monitoring:
```python
error_counter.inc(labels={'error_type': 'rate_limit'})
```

### 4. User Feedback
Allow users to report unhelpful errors:
```python
response['metadata']['feedback_url'] = '/api/feedback'
```

## Summary

✅ **Comprehensive Coverage**: All error scenarios handled
✅ **Graceful Degradation**: System continues with reduced functionality
✅ **User-Friendly Messages**: Clear, actionable error messages
✅ **Extensive Testing**: 30+ error scenario tests
✅ **Proper Logging**: Appropriate log levels and content
✅ **Privacy Conscious**: No sensitive data in logs
✅ **Production Ready**: Robust error handling for real-world use
