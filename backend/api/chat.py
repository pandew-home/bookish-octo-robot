"""
Chat API endpoint for DevOps Chatbot v2.

Integrates all components:
- Query routing and classification
- Cluster context enrichment
- RAG-powered response generation
- Conversation history management
- K8sGPT Result integration
"""
import logging
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
import asyncio

from api.credentials import get_credentials_for_session
from cluster_manager import get_k8s_clients
from query_router import QueryRouter
from enrichment_engine import EnrichmentEngine
from rag_integration import get_rag_integration
from k8sgpt_reader import K8sGPTReader
from conversation_history import ConversationHistory
from input_sanitizer import InputSanitizer
from middleware.rate_limiter import rate_limiter
from response_parser import ResponseParser
from utils.error_handler import handle_generic_error, create_error_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# Initialize shared components
conversation_history = ConversationHistory()
input_sanitizer = InputSanitizer()
response_parser = ResponseParser()


class ChatRequest(BaseModel):
    """Chat request model."""
    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    session_id: str = Field(..., description="Session ID for credential lookup")
    user_id: str = Field(..., description="User ID for conversation history")
    conversation_id: Optional[str] = Field(None, description="Conversation ID (creates new if not provided)")
    cluster_name: Optional[str] = Field(None, description="Target cluster name")
    max_tokens: int = Field(500, ge=100, le=2000, description="Maximum tokens for response")
    is_export: bool = Field(False, description="Whether this is for export (uses more tokens)")


class ChatResponse(BaseModel):
    """Chat response model."""
    query: str
    response: str
    conversation_id: str
    citations: list = []
    k8sgpt_findings: list = []
    safety_warnings: list = []
    enrichment_plan: dict = {}
    token_usage: dict = {}
    errors: list = []
    metadata: dict = {}


@router.post("/query", response_model=ChatResponse)
async def process_chat_query(request: ChatRequest) -> ChatResponse:
    """
    Process a chat query with full RAG pipeline.
    
    Flow:
    1. Validate input and check rate limits
    2. Validate credentials and cluster selection
    3. Read K8sGPT Result CRDs
    4. Route and classify query
    5. Enrich with cluster context
    6. Retrieve KB results via RAG
    7. Render prompt with template engine
    8. Generate response with LLM
    9. Parse response for safety warnings
    10. Save conversation to history
    11. Return formatted response
    
    Args:
        request: Chat request with query and session info
        
    Returns:
        ChatResponse with answer and metadata
        
    Raises:
        HTTPException: If credentials invalid, cluster not selected, or processing fails
    """
    try:
        logger.info(f"Processing chat query for session {request.session_id[:8]}...")
        
        # Step 1: Validate input
        is_valid, error_msg = input_sanitizer.validate_query(request.query)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Check rate limits
        allowed, retry_after, remaining = await rate_limiter.check_rate_limit(
            user_id=request.user_id,
            max_requests=20,
            window_seconds=60,
            endpoint="chat"
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)}
            )
        
        # Step 2: Validate credentials
        creds = get_credentials_for_session(request.session_id)
        if not creds:
            raise HTTPException(
                status_code=401,
                detail="No credentials found. Please authenticate first."
            )
        
        # Check if credentials are expiring soon
        if creds.is_expiring_soon():
            logger.warning(f"Credentials expiring soon for session {request.session_id[:8]}")
        
        # Step 3: Validate cluster selection
        if not request.cluster_name:
            raise HTTPException(
                status_code=400,
                detail="No cluster selected. Please select a cluster first."
            )
        
        # Get K8s clients for target cluster (delegate based on auth_mode)
        from api.clusters import _discover_kubeconfig_clusters, _get_kubeconfig_k8s_clients
        
        if creds.auth_mode == "kubeconfig":
            clusters = _discover_kubeconfig_clusters(creds)
        else:
            from cluster_manager import discover_clusters
            clusters = await discover_clusters(creds)
        
        target_cluster = None
        for cluster in clusters:
            if cluster['name'] == request.cluster_name:
                target_cluster = cluster
                break
        
        if not target_cluster:
            raise HTTPException(
                status_code=404,
                detail=f"Cluster '{request.cluster_name}' not found or not accessible"
            )
        
        # Create K8s clients based on auth mode
        if creds.auth_mode == "kubeconfig":
            k8s_clients = _get_kubeconfig_k8s_clients(creds, target_cluster)
        else:
            k8s_clients = get_k8s_clients(creds, target_cluster)
        
        try:
            # Step 4: Read K8sGPT Result CRDs
            k8sgpt_reader = K8sGPTReader(k8s_clients['custom_objects'])
            k8sgpt_results = await k8sgpt_reader.read_results()
            logger.info(f"Found {len(k8sgpt_results)} K8sGPT results")
            
            # Step 5: Route and classify query
            query_router = QueryRouter()
            enrichment_plan = query_router.classify(request.query)
            
            logger.info(f"Query classified: {[c.value for c in enrichment_plan.categories]}")
            
            # Step 6: Enrich with cluster context
            enrichment_engine = EnrichmentEngine(k8s_clients, creds)
            enriched_context = await enrichment_engine.execute(enrichment_plan)
            
            logger.info(f"Context enriched with {len(enriched_context.errors)} error(s)")
            
            # Step 7: Generate response with RAG
            rag = get_rag_integration(
                llm_provider="openai",  # TODO: Make configurable
                api_key=None,  # Uses environment variable
                cluster_version=target_cluster.get('version', 'v1.28')
            )
            
            # Add K8sGPT results to enriched context
            enriched_context.k8sgpt_results = k8sgpt_results
            
            rag_response = rag.process_query(
                query=request.query,
                enriched_context=enriched_context,
                max_tokens=request.max_tokens,
                is_export=request.is_export
            )
            
            # Step 8: Parse response for safety warnings
            parsed_response = response_parser.parse(rag_response['response'])
            
            # Step 9: Save conversation to history
            conversation_id = request.conversation_id
            if not conversation_id:
                conversation_id = conversation_history.create_conversation(
                    user_id=request.user_id,
                    title=request.query[:50],  # Use first 50 chars as title
                    cluster_name=request.cluster_name  # Per-cluster isolation
                )
            
            # Save user message
            conversation_history.save_message(
                user_id=request.user_id,
                conversation_id=conversation_id,
                role="user",
                content=request.query,
                cluster_name=request.cluster_name  # Per-cluster isolation
            )
            
            # Save assistant message
            conversation_history.save_message(
                user_id=request.user_id,
                conversation_id=conversation_id,
                role="assistant",
                content=rag_response['response'],
                cluster_name=request.cluster_name  # Per-cluster isolation
            )
            
            # Step 10: Build response
            response = ChatResponse(
                query=request.query,
                response=rag_response['response'],
                conversation_id=conversation_id,
                citations=rag_response.get('citations', []),
                k8sgpt_findings=[
                    {
                        'name': r.get('name'),
                        'kind': r.get('kind'),
                        'severity': r.get('severity'),
                        'problem': r.get('problem'),
                        'solution': r.get('solution')
                    }
                    for r in k8sgpt_results[:5]  # Top 5 findings
                ],
                safety_warnings=parsed_response.safety_notices,
                enrichment_plan={
                    'categories': [c.value for c in enrichment_plan.categories],
                    'resource_names': enrichment_plan.resource_names,
                    'namespaces': enrichment_plan.namespaces,
                    'include_aws_context': enrichment_plan.include_aws_context,
                    'time_range': str(enrichment_plan.time_range) if enrichment_plan.time_range else None
                },
                token_usage=rag.get_token_usage(),
                errors=enriched_context.errors + rag_response.get('errors', []),
                metadata={
                    'cluster': request.cluster_name,
                    'cluster_version': target_cluster.get('version'),
                    'k8sgpt_result_count': len(k8sgpt_results),
                    'rag_metadata': rag_response.get('metadata', {}),
                    'credentials_expiring_soon': creds.is_expiring_soon(),
                    'rate_limit_remaining': remaining
                }
            )
            
            logger.info(f"Query processed successfully: {len(response.response)} chars")
            return response
            
        finally:
            # Cleanup K8s clients (only for AWS mode which uses temp files)
            if creds.auth_mode == "aws":
                from cluster_manager import cleanup_k8s_clients
                cleanup_k8s_clients(k8s_clients)
    
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except ConnectionError as e:
        # Cluster unreachable
        logger.error(f"Cluster connection error: {e}")
        raise HTTPException(
            status_code=503,
            detail="Cluster not responding. Please verify the cluster is accessible and try again.",
            headers={"X-Error-Code": "cluster_unreachable"}
        )
    except ValueError as e:
        # Input validation errors
        logger.warning(f"Validation error: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Check for Kubernetes API auth errors
        error_str = str(e).lower()
        if '401' in error_str or 'unauthorized' in error_str:
            logger.warning(f"Auth error: {e}")
            raise HTTPException(
                status_code=401,
                detail="Authentication failed. Please re-authenticate.",
                headers={"X-Error-Code": "cluster_auth_failed"}
            )
        if '403' in error_str or 'forbidden' in error_str:
            logger.warning(f"RBAC error: {e}")
            raise HTTPException(
                status_code=403,
                detail="Access denied. Check your RBAC permissions.",
                headers={"X-Error-Code": "rbac_forbidden"}
            )
        # Unexpected errors
        logger.error(f"Error processing chat query: {e}", exc_info=True)
        raise handle_generic_error(
            e,
            context="processing chat query",
            user_message="An error occurred while processing your query. Please try again."
        )


@router.get("/health")
async def chat_health() -> dict:
    """
    Check chat API health and component status.
    
    Returns:
        Health status of all components
    """
    try:
        # Check RAG integration status
        rag = get_rag_integration()
        rag_status = rag.get_initialization_status()
        
        return {
            'status': 'healthy',
            'components': {
                'query_router': {'status': 'healthy'},
                'enrichment_engine': {'status': 'healthy'},
                'rag_integration': {
                    'status': 'healthy' if rag_status['fully_functional'] else 'degraded',
                    'details': rag_status
                }
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            'status': 'unhealthy',
            'error': str(e)
        }


class FeedbackRequest(BaseModel):
    """Feedback submission model."""
    query: str
    response: str
    rating: int = Field(..., ge=1, le=5)
    comment: Optional[str] = None
    session_id: str


@router.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest
) -> dict:
    """
    Submit feedback on a chat response.
    
    Args:
        query: Original query
        response: Response that was provided
        rating: Rating from 1-5
        comment: Optional feedback comment
        session_id: Session ID
        
    Returns:
        Confirmation message
    """
    try:
        logger.info(f"Feedback received: rating={feedback.rating}, session={feedback.session_id[:8]}")

        # TODO: Store feedback in database or logging system
        # For now, just log it
        logger.info(f"Query: {feedback.query[:100]}...")
        logger.info(f"Response: {feedback.response[:100]}...")
        logger.info(f"Rating: {feedback.rating}/5")
        if feedback.comment:
            logger.info(f"Comment: {feedback.comment}")
        
        return {
            'status': 'success',
            'message': 'Thank you for your feedback!'
        }
    except Exception as e:
        logger.error(f"Error submitting feedback: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to submit feedback. Please try again."
        )


@router.get("/history")
async def get_chat_history(
    user_id: str = Query(..., description="User ID"),
    cluster_name: str = Query(..., description="Target cluster name"),
    limit: int = Query(50, ge=1, le=50, description="Maximum number of messages to return")
) -> dict:
    """
    Get conversation history for user and selected cluster.
    
    Returns the last N messages (default 50) for the user's conversation
    on the specified cluster. This is used to provide context for follow-up
    questions in the chat interface.
    
    Conversation history is isolated per cluster - switching clusters
    automatically switches to that cluster's conversation history.
    
    Requirements: 10.1, 10.4, 13.3
    
    Args:
        user_id: User ID
        cluster_name: Target cluster name
        limit: Maximum number of messages to return (default 50)
        
    Returns:
        List of messages with metadata
    """
    try:
        logger.info(f"Retrieving chat history for user {user_id} on cluster {cluster_name}")
        
        # Get conversations for the user on this specific cluster
        conversations = conversation_history.get_user_conversations(user_id, cluster_name)
        
        all_messages = []
        for conv in conversations:
            for msg in conv.messages:
                all_messages.append({
                    'conversation_id': conv.id,
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.timestamp,
                    'cluster': cluster_name
                })
        
        # Sort by timestamp (most recent last) and limit
        all_messages.sort(key=lambda m: m['timestamp'])
        recent_messages = all_messages[-limit:] if len(all_messages) > limit else all_messages
        
        logger.info(f"Retrieved {len(recent_messages)} messages for user {user_id} on cluster {cluster_name}")
        
        return {
            'user_id': user_id,
            'cluster': cluster_name,
            'messages': recent_messages,
            'total': len(recent_messages),
            'limit': limit
        }
    except Exception as e:
        logger.error(f"Error retrieving chat history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversation history."
        )


class ExportRequest(BaseModel):
    """Conversation export request model."""
    user_id: str = Field(..., description="User ID")
    cluster_name: str = Field(..., description="Target cluster name")
    conversation_id: Optional[str] = Field(None, description="Specific conversation ID to export (optional)")


@router.post("/export")
async def export_conversation(export: ExportRequest
) -> dict:
    """
    Generate LLM summary of conversation and export as markdown.
    
    Creates a structured markdown export with:
    - Problem: What issue was the user trying to solve?
    - Investigation: What steps were taken to diagnose?
    - Root Cause: What was identified as the underlying issue?
    - Solution: What fix was applied?
    - Verification: How was the fix confirmed?
    
    Exports are per-cluster - only conversations from the specified cluster are included.
    
    Requirements: 10.6, 13.3
    
    Args:
        user_id: User ID
        cluster_name: Target cluster name
        conversation_id: Optional specific conversation to export
        
    Returns:
        Markdown-formatted conversation summary
    """
    try:
        logger.info(f"Exporting conversation for user {export.user_id} on cluster {export.cluster_name}")

        # Get conversation(s) to export from the specific cluster
        if export.conversation_id:
            conversation = conversation_history.get_conversation(export.user_id, export.conversation_id, export.cluster_name)
            if not conversation:
                raise HTTPException(
                    status_code=404,
                    detail=f"Conversation {export.conversation_id} not found on cluster {export.cluster_name}"
                )
            conversations = [conversation]
        else:
            # Get all recent conversations for the user on this cluster
            conversations = conversation_history.get_user_conversations(export.user_id, export.cluster_name)
        
        if not conversations:
            raise HTTPException(
                status_code=404,
                detail=f"No conversations found for export on cluster {export.cluster_name}"
            )
        
        # Collect all messages from conversations
        all_messages = []
        for conv in conversations:
            all_messages.extend(conv.messages)
        
        if not all_messages:
            raise HTTPException(
                status_code=400,
                detail="No messages found in conversation(s)"
            )
        
        # Build structured markdown export
        from datetime import datetime
        export_time = datetime.now().isoformat()
        
        # Extract problem (first user message)
        problem = ""
        for msg in all_messages:
            if msg.role == "user":
                problem = msg.content
                break
        
        # Extract investigation steps (user questions)
        investigation_steps = []
        for msg in all_messages:
            if msg.role == "user":
                investigation_steps.append(msg.content)
        
        # Extract solutions (assistant responses)
        solutions = []
        for msg in all_messages:
            if msg.role == "assistant":
                solutions.append(msg.content)
        
        # Build markdown export with structured sections
        markdown_export = f"""# Conversation Export

**User:** {user_id}
**Cluster:** {cluster_name}
**Exported:** {export_time}
**Messages:** {len(all_messages)}

---

## Problem

{problem if problem else "No problem statement found"}

---

## Investigation

"""
        
        for i, step in enumerate(investigation_steps, 1):
            markdown_export += f"{i}. {step}\n\n"
        
        markdown_export += """---

## Root Cause

Based on the conversation, the root cause was identified through the diagnostic steps above.

---

## Solution

"""
        
        for i, solution in enumerate(solutions, 1):
            markdown_export += f"### Response {i}\n\n{solution}\n\n"
        
        markdown_export += """---

## Verification

To verify the solution:
1. Check the cluster status
2. Monitor for recurring issues
3. Review logs and metrics

---

## Full Conversation

"""
        
        # Append full conversation for reference
        for i, msg in enumerate(all_messages, 1):
            role_label = "👤 User" if msg.role == "user" else "🤖 Assistant"
            markdown_export += f"\n### Message {i} - {role_label}\n\n{msg.content}\n"
        
        logger.info(f"Generated export with {len(markdown_export)} characters")
        
        return {
            'user_id': user_id,
            'cluster': cluster_name,
            'conversation_id': conversation_id,
            'export_format': 'markdown',
            'content': markdown_export,
            'message_count': len(all_messages),
            'exported_at': export_time
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error exporting conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to export conversation: {str(e)}"
        )


@router.get("/conversations/{user_id}")
async def get_conversation_list(
    user_id: str,
    cluster_name: Optional[str] = Query(None, description="Optional cluster name to filter conversations"),
    limit: int = Query(10, ge=1, le=50, description="Number of conversations to return")
) -> dict:
    """
    Get list of conversations for a user.
    
    If cluster_name is provided, returns conversations for that specific cluster.
    Otherwise, returns all conversations across all clusters.
    
    Args:
        user_id: User ID
        cluster_name: Optional cluster name to filter by
        limit: Maximum number of conversations to return
        
    Returns:
        List of conversations with metadata
    """
    try:
        conversations = conversation_history.get_user_conversations(user_id, cluster_name)
        
        # Limit results
        conversations = conversations[:limit]
        
        return {
            'conversations': [
                {
                    'id': conv.id,
                    'title': conv.title,
                    'message_count': len(conv.messages),
                    'created_at': conv.created_at,
                    'updated_at': conv.updated_at,
                    'preview': conv.messages[0].content[:100] if conv.messages else "",
                    'cluster': cluster_name if cluster_name else 'unknown'
                }
                for conv in conversations
            ],
            'total': len(conversations),
            'cluster': cluster_name
        }
    except Exception as e:
        logger.error(f"Error retrieving conversation list: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversation list."
        )


@router.get("/conversations/{user_id}/{conversation_id}")
async def get_conversation(
    user_id: str,
    conversation_id: str,
    cluster_name: Optional[str] = Query(None, description="Optional cluster name for per-cluster isolation")
) -> dict:
    """
    Get a specific conversation with all messages.
    
    Args:
        user_id: User ID
        conversation_id: Conversation ID
        cluster_name: Optional cluster name for per-cluster isolation
        
    Returns:
        Conversation with all messages
    """
    try:
        conversation = conversation_history.get_conversation(user_id, conversation_id, cluster_name)
        
        if not conversation:
            raise HTTPException(
                status_code=404,
                detail=f"Conversation {conversation_id} not found"
            )
        
        return {
            'id': conversation.id,
            'title': conversation.title,
            'created_at': conversation.created_at,
            'updated_at': conversation.updated_at,
            'cluster': cluster_name,
            'messages': [
                {
                    'role': msg.role,
                    'content': msg.content,
                    'timestamp': msg.timestamp
                }
                for msg in conversation.messages
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving conversation: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to retrieve conversation."
        )
