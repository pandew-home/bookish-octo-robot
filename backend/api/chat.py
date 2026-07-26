"""Chat API endpoints.

# MAINTENANCE — read before changing this file
# This is the public HTTP surface for the chatbot. AI assistants: do NOT add,
# remove, or rename endpoints, request/response fields, or status codes
# without explicit human review — the frontend is wired to these contracts.
# Keep error handling narrow: rate-limit -> 429, RBAC -> 403, cluster down ->
# 503, anything else -> handle_generic_error.
"""

import logging
import os
import re
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query
from kubernetes.client.exceptions import ApiException
from pydantic import BaseModel, Field

from agentic_engine import AgentEngine
from conversation_history import ConversationHistory
from k8sgpt_reader import K8sGPTReader
from memory import MemoryUnavailableError, get_memory_port
from memory.policy import is_durable_turn
from memory.scrub import contains_high_risk_secret, scrub as scrub_text
from kube_policy import get_policy
from middleware.rate_limiter import rate_limiter
from middleware.request_id import get_request_id
from rag_integration import get_rag_integration
from utils.error_handler import (
    AUTH_REQUIRED,
    CLUSTER_UNREACHABLE,
    RATE_LIMITED,
    RBAC_FORBIDDEN,
    api_error,
    handle_generic_error,
    normalize_agent_errors,
)

# Soft code for "select a cluster before chat tools" (not a hard auth failure).
CLUSTER_REQUIRED = "cluster_required"


def _get_session_cluster_context(session_id: str):
    """Return (k8s_clients, selected_cluster) for the authenticated session.

    Lazy-imports api.clusters to avoid hard dependency cycles and to keep unit
    tests free of botocore when they only patch this helper.
    """
    from api.clusters import get_k8s_clients_for_session, get_selected_cluster

    return get_k8s_clients_for_session(session_id), get_selected_cluster(session_id)

logger = logging.getLogger(__name__)

_BULLET_RE = re.compile(r"^\s*(?:[-*]\s+|\d+\.\s+)(.*)", re.MULTILINE)


def _build_ingest_content(
    *,
    cluster_name: str,
    user_query: str,
    assistant_response: str,
) -> str:
    """Build structured content for Vestige smart_ingest."""
    bullets = _BULLET_RE.findall(assistant_response)
    remediation = "\n".join(f"- {b.strip()}" for b in bullets[:10]) if bullets else "(no structured remediation found)"
    diagnosis = assistant_response[:500] if len(assistant_response) > 500 else assistant_response
    return (
        f"cluster: {cluster_name}\n"
        f"problem: {user_query}\n"
        f"diagnosis: {diagnosis}\n"
        f"remediation: {remediation}\n"
        f"source: devops-chatbot-auto"
    )


def _format_memory_summary(recall_hits: list) -> str:
    """Format recall hits with per-hit and total length caps."""
    parts: list[str] = []
    total = 0
    for h in recall_hits:
        content = h.content[:500]
        part = f"- {content}" + (f" (score={h.score})" if h.score else "")
        if total + len(part) > 2000:
            remaining = 2000 - total - len("\n")
            if remaining > 10:
                parts.append(part[:remaining])
            break
        parts.append(part)
        total += len(part) + len("\n")
    return "\n".join(parts)


router = APIRouter(prefix="/api/chat", tags=["chat"])

conversation_history = ConversationHistory()


class ChatRequest(BaseModel):
    """Chat request model."""

    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    user_id: str = Field(..., description="User ID for conversation history")
    conversation_id: Optional[str] = Field(
        None, description="Conversation ID (creates new if not provided)"
    )
    cluster_name: Optional[str] = Field(
        None, description="Selected cluster name (per-cluster history + memory scope)"
    )
    session_id: Optional[str] = Field(
        None, description="Legacy body session id (prefer cookie/header)"
    )
    max_tokens: int = Field(
        500, ge=100, le=2000, description="Maximum tokens for response"
    )


class ChatResponse(BaseModel):
    """Chat response model."""

    query: str
    response: str
    conversation_id: str
    k8sgpt_findings: list = []
    token_usage: dict = {}
    errors: list = []
    metadata: dict = {}


def require_chat_session(
    x_session_id: Optional[str] = Header(None),
    session_id_cookie: Optional[str] = Cookie(None, alias="session_id"),
) -> str:
    """Require session header/cookie and valid stored credentials."""
    session_id = x_session_id or session_id_cookie
    if not session_id:
        raise api_error(
            AUTH_REQUIRED,
            "Session ID required. Please log in again.",
            401,
            recoverable=False,
        )
    # Import lazily so unit tests can patch without loading boto3 at import time.
    from api.credentials import get_credentials_for_session

    get_credentials_for_session(session_id)
    return session_id


@router.post("/query", response_model=ChatResponse)
async def process_chat_query(
    request: ChatRequest,
    session_id: str = Depends(require_chat_session),
) -> ChatResponse:
    """Process a chat query through the agentic pipeline (authenticated session required)."""
    try:

        cluster_name = (
            (request.cluster_name or "").strip()
            or os.environ.get("CLUSTER_NAME")
            or os.environ.get("IN_CLUSTER_EKS_CLUSTER_NAME")
            or os.environ.get("EKS_CLUSTER_NAME")
            or "unknown"
        )

        logger.info(
            "[CHAT_QUERY] session=%s user=%s cluster=%s query=%r",
            session_id[:8],
            request.user_id,
            cluster_name,
            request.query[:100],
        )

        allowed, retry_after, remaining = await rate_limiter.check_rate_limit(
            user_id=request.user_id, max_requests=20, window_seconds=60, endpoint="chat"
        )
        if not allowed:
            raise api_error(
                RATE_LIMITED,
                f"Rate limit exceeded. Try again in {retry_after} seconds.",
                429,
                recoverable=True,
                headers={"Retry-After": str(retry_after)},
            )

        # Live diagnostics use the user's session clients (Kion/EKS or kubeconfig),
        # not the pod ServiceAccount. SA is limited to K8sGPT Result CRDs.
        try:
            k8s_clients, selected_cluster = _get_session_cluster_context(session_id)
        except HTTPException as exc:
            if exc.status_code == 400:
                raise api_error(
                    CLUSTER_REQUIRED,
                    "Select a cluster before chatting so diagnostics use your "
                    "credentials (not the chatbot service account).",
                    400,
                    recoverable=True,
                ) from exc
            raise

        if selected_cluster.get("name"):
            cluster_name = selected_cluster["name"]
        cluster_version = (
            selected_cluster.get("version")
            or selected_cluster.get("kubernetes_version")
            or "unknown"
        )

        # K8sGPT Result CRDs: same selected-cluster session clients as live tools
        # (user RBAC). Do not use host pod SA here — multi-cluster would mix evidence.
        k8sgpt_results = []
        try:
            custom_api = k8s_clients.get("custom_objects")
            if custom_api is not None:
                k8sgpt_reader = K8sGPTReader(custom_api)
                k8sgpt_results = await k8sgpt_reader.read_results()
                logger.info(
                    "[CHAT_QUERY] %d K8sGPT results (session cluster)",
                    len(k8sgpt_results),
                )
        except Exception as exc:
            # Operator absent / RBAC deny on Results — non-fatal; live tools still work.
            logger.warning(
                "[CHAT_QUERY] K8sGPT Result read failed (continuing): %s",
                exc,
            )

        rag = get_rag_integration()

        memory_summary = ""
        memory_degraded = False
        recall_hits = []
        try:
            memory_port = get_memory_port()
            # Institutional memory: shared across users for this cluster's
            # findings (not per-user isolation). See specs data-model Scoping.
            recall_hits = await memory_port.recall(
                query=request.query,
                top_k=5,
                metadata={"cluster": cluster_name},
            )
            if recall_hits:
                memory_summary = _format_memory_summary(recall_hits)
            logger.info("[CHAT_QUERY] %d memory recall hits", len(recall_hits))
        except (MemoryUnavailableError, Exception) as exc:
            memory_degraded = True
            logger.warning("[CHAT_QUERY] memory recall failed, continuing degraded: %s", exc)

        agent = AgentEngine(
            llm_client=rag.llm_client,
            k8sgpt_results=k8sgpt_results,
            k8s_clients=k8s_clients,
            cluster_version=cluster_version,
            memory_summary=memory_summary,
            kube_policy=get_policy(),
        )
        rag_response = await agent.run(query=request.query)
        logger.info("[CHAT_QUERY] agent done: %d chars", len(rag_response["response"]))

        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = conversation_history.create_conversation(
                user_id=request.user_id,
                title=request.query[:50],
                cluster_name=cluster_name,
            )

        conversation_history.save_message(
            user_id=request.user_id,
            conversation_id=conversation_id,
            role="user",
            content=request.query,
            cluster_name=cluster_name,
        )
        conversation_history.save_message(
            user_id=request.user_id,
            conversation_id=conversation_id,
            role="assistant",
            content=rag_response["response"],
            cluster_name=cluster_name,
        )

        memory_ingested = False
        memory_ingest_status = "skipped"
        assistant_response = rag_response["response"]
        if is_durable_turn(request.query, assistant_response):
            try:
                # Refuse ingest when original text has high-risk secrets
                if contains_high_risk_secret(request.query) or contains_high_risk_secret(
                    assistant_response
                ):
                    memory_ingest_status = "unsafe"
                    logger.info("[CHAT_QUERY] auto-ingest skipped: high-risk secret in turn")
                else:
                    scrubbed_query = scrub_text(request.query)
                    scrubbed_response = scrub_text(assistant_response)
                    ingest_content = _build_ingest_content(
                        cluster_name=cluster_name,
                        user_query=scrubbed_query,
                        assistant_response=scrubbed_response,
                    )
                    ingest_port = get_memory_port()
                    result = await ingest_port.ingest(
                        content=ingest_content,
                        metadata={
                            "cluster": cluster_name,
                            "source": "devops-chatbot-auto",
                        },
                    )
                    memory_ingested = result.ok
                    memory_ingest_status = result.status or (
                        "stored" if result.ok else "failed"
                    )
                    logger.info(
                        "[CHAT_QUERY] auto-ingest %s: %s", memory_ingest_status, result
                    )
            except (MemoryUnavailableError, Exception) as exc:
                memory_ingested = False
                memory_ingest_status = "failed"
                logger.warning("[CHAT_QUERY] auto-ingest failed (non-blocking): %s", exc)

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
            errors=normalize_agent_errors(rag_response.get("errors", [])),
            metadata={
                "k8sgpt_result_count": len(k8sgpt_results),
                "rag_metadata": rag_response.get("metadata", {}),
                "rate_limit_remaining": remaining,
                "memory_degraded": memory_degraded,
                "memory_hits": len(recall_hits),
                "memory_ingested": memory_ingested,
                "memory_ingest_status": memory_ingest_status,
                "request_id": get_request_id(),
            },
        )

    except HTTPException:
        raise
    except ApiException as e:
        if e.status == 403:
            logger.warning("RBAC forbidden: %s", e)
            raise api_error(
                RBAC_FORBIDDEN,
                "Access denied. Check your RBAC permissions. You can rephrase "
                "or ask for a read-only diagnosis.",
                403,
                recoverable=True,
            )
        raise handle_generic_error(
            e,
            context="processing chat query",
            user_message=(
                "An error occurred while processing your query. "
                "Your chat is still here—try again or rephrase."
            ),
        )
    except ConnectionError as e:
        logger.error("Cluster connection error: %s", e)
        raise api_error(
            CLUSTER_UNREACHABLE,
            "Cluster not responding. Please verify the cluster is accessible, "
            "then continue this chat with a narrower question.",
            503,
            recoverable=True,
        )
    except Exception as e:
        logger.error("Error processing chat query: %s", e, exc_info=True)
        raise handle_generic_error(
            e,
            context="processing chat query",
            user_message=(
                "An error occurred while processing your query. "
                "Your earlier messages are still here—try again or rephrase."
            ),
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
    session_id: str = Depends(require_chat_session),
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
async def export_conversation(
    export: ExportRequest,
    session_id: str = Depends(require_chat_session),
) -> dict:
    """Export a conversation (or all the user's conversations on the cluster) as Markdown."""
    _ = session_id  # authz only — history is keyed by client user_id (pre-existing)
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
    session_id: str = Depends(require_chat_session),
) -> dict:
    """List the user's conversations, optionally filtered to one cluster."""
    _ = session_id
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
    session_id: str = Depends(require_chat_session),
) -> dict:
    """Fetch one conversation with all of its messages."""
    _ = session_id
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
