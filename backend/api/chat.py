"""Chat API endpoints.

# MAINTENANCE — read before changing this file
# This is the public HTTP surface for the chatbot. AI assistants: do NOT add,
# remove, or rename endpoints, request/response fields, or status codes
# without explicit human review — the frontend is wired to these contracts.
# Keep error handling narrow: rate-limit -> 429, RBAC -> 403, cluster down ->
# 503, anything else -> handle_generic_error.
"""

import logging
from datetime import datetime
from typing import Optional
import re

from fastapi import APIRouter, HTTPException, Query
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, Field

from agentic_engine import AgentEngine
from conversation_history import ConversationHistory
from k8s_client import get_k8s_client
from k8sgpt_reader import K8sGPTReader
from middleware.rate_limiter import rate_limiter
from rag_integration import get_rag_integration
from utils.error_handler import handle_generic_error

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

conversation_history = ConversationHistory()
APPROVAL_RE = re.compile(r"\b(approve|approved|confirm|confirmed)\b", re.IGNORECASE)


class ChatRequest(BaseModel):
    """Chat request model."""

    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    user_id: str = Field(..., description="User ID for conversation history")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID (creates new if not provided)"
    )
    max_tokens: int = Field(
        500, ge=100, le=2000, description="Maximum tokens for response"
    )


def _is_mutation_approval_prompt(query: str) -> bool:
    """Detect explicit user confirmation to allow mutating Kubernetes API calls."""
    if not query:
        return False
    lowered = query.lower()
    if not APPROVAL_RE.search(lowered):
        return False
    return "change" in lowered or "apply" in lowered or "execute" in lowered or "proceed" in lowered


class ChatResponse(BaseModel):
    """Chat response model."""

    query: str
    response: str
    conversation_id: str
    k8sgpt_findings: list = []
    token_usage: dict = {}
    errors: list = []
    metadata: dict = {}


@router.post("/query", response_model=ChatResponse)
async def process_chat_query(request: ChatRequest) -> ChatResponse:
    """Process a chat query through the agentic pipeline."""
    try:
        logger.info("[CHAT_QUERY] user=%s query=%r", request.user_id, request.query[:100])

        allowed, retry_after, remaining = await rate_limiter.check_rate_limit(
            user_id=request.user_id, max_requests=20, window_seconds=60, endpoint="chat"
        )
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )

        k8s_client = get_k8s_client()
        k8s_clients = k8s_client.get_clients()
        cluster_version = k8s_client.get_cluster_version()

        k8sgpt_reader = K8sGPTReader(k8s_clients["custom_objects"])
        k8sgpt_results = await k8sgpt_reader.read_results()
        logger.info("[CHAT_QUERY] %d K8sGPT results", len(k8sgpt_results))

        rag = get_rag_integration()
        kb_results = rag.search_knowledge_base(request.query, top_k=5)
        logger.info("[CHAT_QUERY] %d KB results", len(kb_results))

        agent = AgentEngine(
            llm_client=rag.llm_client,
            k8sgpt_results=k8sgpt_results,
            kb_results=kb_results,
            k8s_clients=k8s_clients,
            kb_search_func=rag.search_knowledge_base,
            cluster_version=cluster_version,
            execution_mode="execute",
            require_human_approval=not _is_mutation_approval_prompt(request.query),
        )
        rag_response = await agent.run(query=request.query)
        logger.info("[CHAT_QUERY] agent done: %d chars", len(rag_response["response"]))

        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = conversation_history.create_conversation(
                user_id=request.user_id, title=request.query[:50]
            )

        conversation_history.save_message(
            user_id=request.user_id,
            conversation_id=conversation_id,
            role="user",
            content=request.query,
        )
        conversation_history.save_message(
            user_id=request.user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=rag_response["response"],
        )

        return ChatResponse(
            query=request.query,
            response=rag_response["response"],
            conversation_id=conversation_id,
            k8sgpt_findings=[
                {
                    "name": r.name,
                    "kind": r.kind,
                    "severity": r.severity,
                    "problem": r.problem,
                    "solution": r.solution,
                }
                for r in k8sgpt_results[:5]
            ],
            token_usage=rag.get_token_usage(),
            errors=rag_response.get("errors", []),
            metadata={
                "k8sgpt_result_count": len(k8sgpt_results),
                "rag_metadata": rag_response.get("metadata", {}),
                "rate_limit_remaining": remaining,
            },
        )

    except HTTPException:
        raise
    except ApiException as e:
        if e.status == 403:
            logger.warning("RBAC forbidden: %s", e)
            raise HTTPException(
                status_code=403,
                detail="Access denied. Check your RBAC permissions.",
                headers={"X-Error-Code": "rbac_forbidden"},
            )
        raise handle_generic_error(
            e,
            context="processing chat query",
            user_message="An error occurred while processing your query. Please try again.",
        )
    except ConnectionError as e:
        logger.error("Cluster connection error: %s", e)
        raise HTTPException(
            status_code=503,
            detail="Cluster not responding. Please verify the cluster is accessible and try again.",
            headers={"X-Error-Code": "cluster_unreachable"},
        )
    except Exception as e:
        logger.error("Error processing chat query: %s", e, exc_info=True)
        raise handle_generic_error(
            e,
            context="processing chat query",
            user_message="An error occurred while processing your query. Please try again.",
        )


@router.get("/health")
async def chat_health() -> dict:
    """Component status for the chat pipeline."""
    try:
        rag = get_rag_integration()
        rag_status = rag.get_initialization_status()
        return {
            "status": "healthy",
            "components": {
                "rag_integration": {
                    "status": "healthy" if rag_status["fully_functional"] else "degraded",
                    "details": rag_status,
                },
            },
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return {"status": "unhealthy", "error": str(e)}


@router.get("/history")
async def get_chat_history(
    user_id: str = Query(..., description="User ID"),
    cluster_name: str = Query(..., description="Target cluster name"),
    limit: int = Query(50, ge=1, le=50, description="Maximum number of messages to return"),
) -> dict:
    """Last `limit` messages for the user on the given cluster (per-cluster isolation)."""
    try:
        conversations = conversation_history.get_user_conversations(user_id, cluster_name)

        all_messages = []
        for conv in conversations:
            for msg in conv.messages:
                all_messages.append(
                    {
                        "conversation_id": conv.id,
                        "role": msg.role,
                        "content": msg.content,
                        "timestamp": msg.timestamp,
                        "cluster": cluster_name,
                    }
                )

        all_messages.sort(key=lambda m: m["timestamp"])
        recent_messages = all_messages[-limit:] if len(all_messages) > limit else all_messages

        return {
            "user_id": user_id,
            "cluster": cluster_name,
            "messages": recent_messages,
            "total": len(recent_messages),
            "limit": limit,
        }
    except Exception as e:
        logger.error("Error retrieving chat history: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation history.")


class ExportRequest(BaseModel):
    """Conversation export request model."""

    user_id: str = Field(..., description="User ID")
    cluster_name: str = Field(..., description="Target cluster name")
    conversation_id: Optional[str] = Field(
        None, description="Specific conversation ID to export (optional)"
    )


@router.post("/export")
async def export_conversation(export: ExportRequest) -> dict:
    """Export a conversation (or all the user's conversations on the cluster) as Markdown."""
    try:
        if export.conversation_id:
            conversation = conversation_history.get_conversation(
                export.user_id, export.conversation_id, export.cluster_name
            )
            if not conversation:
                raise HTTPException(
                    status_code=404,
                    detail=f"Conversation {export.conversation_id} not found on cluster {export.cluster_name}",
                )
            conversations = [conversation]
        else:
            conversations = conversation_history.get_user_conversations(
                export.user_id, export.cluster_name
            )

        if not conversations:
            raise HTTPException(
                status_code=404,
                detail=f"No conversations found for export on cluster {export.cluster_name}",
            )

        all_messages = [msg for conv in conversations for msg in conv.messages]
        if not all_messages:
            raise HTTPException(status_code=400, detail="No messages found in conversation(s)")

        export_time = datetime.now().isoformat()
        content = _render_export_markdown(export, all_messages, export_time)

        return {
            "user_id": export.user_id,
            "cluster": export.cluster_name,
            "conversation_id": export.conversation_id,
            "export_format": "markdown",
            "content": content,
            "message_count": len(all_messages),
            "exported_at": export_time,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error exporting conversation: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to export conversation: {str(e)}")


def _render_export_markdown(export: "ExportRequest", messages: list, export_time: str) -> str:
    header = (
        f"# Conversation Export\n\n"
        f"- **User:** {export.user_id}\n"
        f"- **Cluster:** {export.cluster_name}\n"
        f"- **Exported:** {export_time}\n"
        f"- **Messages:** {len(messages)}\n\n---\n\n"
    )
    body_parts = []
    for msg in messages:
        body_parts.append(f"## {msg.role.title()}\n\n{msg.content}\n")
    return header + "\n".join(body_parts)


@router.get("/conversations/{user_id}")
async def get_conversation_list(
    user_id: str,
    cluster_name: Optional[str] = Query(None, description="Optional cluster name to filter conversations"),
    limit: int = Query(10, ge=1, le=50, description="Number of conversations to return"),
) -> dict:
    """List the user's conversations, optionally filtered to one cluster."""
    try:
        conversations = conversation_history.get_user_conversations(user_id, cluster_name)
        conversations = conversations[:limit]

        return {
            "conversations": [
                {
                    "id": conv.id,
                    "title": conv.title,
                    "message_count": len(conv.messages),
                    "created_at": conv.created_at,
                    "updated_at": conv.updated_at,
                    "preview": conv.messages[0].content[:100] if conv.messages else "",
                    "cluster": cluster_name if cluster_name else "unknown",
                }
                for conv in conversations
            ],
            "total": len(conversations),
            "cluster": cluster_name,
        }
    except Exception as e:
        logger.error("Error retrieving conversation list: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation list.")


@router.get("/conversations/{user_id}/{conversation_id}")
async def get_conversation(
    user_id: str,
    conversation_id: str,
    cluster_name: Optional[str] = Query(None, description="Optional cluster name for per-cluster isolation"),
) -> dict:
    """Fetch one conversation with all of its messages."""
    try:
        conversation = conversation_history.get_conversation(user_id, conversation_id, cluster_name)
        if not conversation:
            raise HTTPException(
                status_code=404, detail=f"Conversation {conversation_id} not found"
            )

        return {
            "id": conversation.id,
            "title": conversation.title,
            "created_at": conversation.created_at,
            "updated_at": conversation.updated_at,
            "cluster": cluster_name,
            "messages": [
                {"role": msg.role, "content": msg.content, "timestamp": msg.timestamp}
                for msg in conversation.messages
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error retrieving conversation: %s", e)
        raise HTTPException(status_code=500, detail="Failed to retrieve conversation.")
