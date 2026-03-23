"""
Tests for conversation history API endpoints.

Covers:
- GET /api/chat/history - retrieve messages for a user/cluster
- POST /api/chat/export - export conversation as structured summary
- GET /api/chat/conversations/{user_id} - list conversations
- GET /api/chat/conversations/{user_id}/{conversation_id} - get specific conversation
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient

from api.chat import (
    get_chat_history,
    export_conversation,
    get_conversation_list,
    get_conversation,
    ExportRequest,
)
from conversation_history import ConversationHistory, Conversation, ChatMessage


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_conversation(conv_id: str, user_id: str, messages=None) -> Conversation:
    """Build a Conversation with optional pre-loaded messages."""
    conv = Conversation(conv_id, user_id, title="Test conversation")
    if messages:
        for role, content in messages:
            conv.add_message(role, content)
    return conv


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------

class TestGetChatHistory:
    """Tests for the /api/chat/history endpoint."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_conversations(self):
        """History endpoint returns empty messages list when user has no conversations."""
        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = []

            result = await get_chat_history(
                user_id="user1",
                cluster_name="prod-cluster",
                limit=50
            )

        assert result["messages"] == []
        assert result["total"] == 0
        assert result["cluster"] == "prod-cluster"

    @pytest.mark.asyncio
    async def test_returns_messages_from_all_conversations(self):
        """History aggregates messages from all conversations for the cluster."""
        conv1 = make_conversation("conv-1", "user1", [
            ("user", "What is wrong with my pod?"),
            ("assistant", "The pod is in CrashLoopBackOff"),
        ])
        conv2 = make_conversation("conv-2", "user1", [
            ("user", "How do I scale a deployment?"),
            ("assistant", "Use kubectl scale"),
        ])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = [conv1, conv2]

            result = await get_chat_history(
                user_id="user1",
                cluster_name="prod-cluster",
                limit=50
            )

        assert result["total"] == 4
        assert all(m["cluster"] == "prod-cluster" for m in result["messages"])
        roles = [m["role"] for m in result["messages"]]
        assert "user" in roles
        assert "assistant" in roles

    @pytest.mark.asyncio
    async def test_limit_is_applied(self):
        """History respects the limit parameter."""
        conv = make_conversation("conv-1", "user1", [
            ("user", f"question {i}") for i in range(20)
        ])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = [conv]

            result = await get_chat_history(
                user_id="user1",
                cluster_name="prod-cluster",
                limit=5
            )

        assert result["total"] <= 5

    @pytest.mark.asyncio
    async def test_messages_sorted_by_timestamp(self):
        """Messages are returned sorted by timestamp ascending."""
        conv = make_conversation("conv-1", "user1", [
            ("user", "first"),
            ("assistant", "second"),
            ("user", "third"),
        ])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = [conv]

            result = await get_chat_history(
                user_id="user1",
                cluster_name="prod-cluster",
                limit=50
            )

        timestamps = [m["timestamp"] for m in result["messages"]]
        assert timestamps == sorted(timestamps)

    @pytest.mark.asyncio
    async def test_cluster_isolation(self):
        """History for cluster A does not include messages from cluster B."""
        conv_a = make_conversation("conv-a", "user1", [
            ("user", "prod cluster question"),
        ])

        with patch('api.chat.conversation_history') as mock_history:
            # cluster A returns conv_a; cluster B returns nothing
            def side_effect(user_id, cluster_name):
                return [conv_a] if cluster_name == "cluster-a" else []
            mock_history.get_user_conversations.side_effect = side_effect

            result_a = await get_chat_history("user1", "cluster-a", limit=50)
            result_b = await get_chat_history("user1", "cluster-b", limit=50)

        assert result_a["total"] == 1
        assert result_b["total"] == 0

    @pytest.mark.asyncio
    async def test_includes_conversation_id_in_messages(self):
        """Each message includes the conversation_id it belongs to."""
        conv = make_conversation("my-conv-id", "user1", [
            ("user", "hello"),
        ])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = [conv]

            result = await get_chat_history("user1", "prod", limit=50)

        assert result["messages"][0]["conversation_id"] == "my-conv-id"


# ---------------------------------------------------------------------------
# GET /api/chat/conversations/{user_id}
# ---------------------------------------------------------------------------

class TestGetConversationList:
    """Tests for the conversation list endpoint."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_conversations(self):
        """Returns empty list when user has no conversations."""
        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = []

            result = await get_conversation_list(
                user_id="user1",
                cluster_name="prod",
                limit=10
            )

        assert result["conversations"] == []
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_conversation_metadata(self):
        """Each conversation entry has expected metadata fields."""
        conv = make_conversation("conv-1", "user1", [
            ("user", "What is wrong with nginx?"),
            ("assistant", "Check pod logs"),
        ])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = [conv]

            result = await get_conversation_list("user1", "prod", 10)

        assert result["total"] == 1
        entry = result["conversations"][0]
        assert entry["id"] == "conv-1"
        assert entry["message_count"] == 2
        assert "created_at" in entry
        assert "updated_at" in entry
        assert "preview" in entry

    @pytest.mark.asyncio
    async def test_limit_is_applied(self):
        """Conversation list respects limit."""
        convs = [make_conversation(f"conv-{i}", "user1") for i in range(15)]

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = convs

            result = await get_conversation_list("user1", "prod", limit=5)

        assert result["total"] <= 5

    @pytest.mark.asyncio
    async def test_preview_is_first_message_truncated(self):
        """Preview field contains the beginning of the first message."""
        long_content = "A" * 200
        conv = make_conversation("conv-1", "user1", [("user", long_content)])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = [conv]

            result = await get_conversation_list("user1", "prod", 10)

        preview = result["conversations"][0]["preview"]
        assert len(preview) <= 100


# ---------------------------------------------------------------------------
# GET /api/chat/conversations/{user_id}/{conversation_id}
# ---------------------------------------------------------------------------

class TestGetConversation:
    """Tests for the single conversation endpoint."""

    @pytest.mark.asyncio
    async def test_returns_conversation_with_messages(self):
        """Returns conversation data with all messages."""
        conv = make_conversation("conv-abc", "user1", [
            ("user", "pod is crashing"),
            ("assistant", "check logs"),
        ])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_conversation.return_value = conv

            result = await get_conversation(
                user_id="user1",
                conversation_id="conv-abc",
                cluster_name="prod"
            )

        assert result["id"] == "conv-abc"
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "user"
        assert result["messages"][0]["content"] == "pod is crashing"

    @pytest.mark.asyncio
    async def test_returns_404_when_not_found(self):
        """Returns 404 when conversation does not exist."""
        from fastapi import HTTPException

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_conversation.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await get_conversation("user1", "nonexistent-id", "prod")

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_messages_include_timestamp(self):
        """Each message includes a timestamp."""
        conv = make_conversation("conv-1", "user1", [("user", "hello")])

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_conversation.return_value = conv

            result = await get_conversation("user1", "conv-1", "prod")

        assert "timestamp" in result["messages"][0]


# ---------------------------------------------------------------------------
# POST /api/chat/export
# ---------------------------------------------------------------------------

class TestExportConversation:
    """Tests for the conversation export endpoint."""

    @pytest.mark.asyncio
    async def test_export_returns_structured_summary(self):
        """Export returns a structured summary dict."""
        conv = make_conversation("conv-1", "user1", [
            ("user", "My nginx pod is crashing"),
            ("assistant", "The pod is in CrashLoopBackOff due to missing config"),
        ])

        mock_rag = Mock()
        mock_rag.process_query.return_value = {
            'response': 'problem: nginx crash\ninvestigation: checked logs\nroot cause: missing config\nsolution: add config map\nverification: pod is running',
            'citations': [],
            'errors': [],
            'metadata': {}
        }

        with patch('api.chat.conversation_history') as mock_history, \
             patch('api.chat.get_rag_integration', return_value=mock_rag):
            mock_history.get_user_conversations.return_value = [conv]

            export_req = ExportRequest(
                user_id="user1",
                cluster_name="prod"
            )
            result = await export_conversation(export_req)

        # Export should have a response (the summary)
        assert result is not None
        assert "cluster" in result or "response" in result or "summary" in result

    @pytest.mark.asyncio
    async def test_export_raises_400_when_no_conversations(self):
        """Export raises 400 when no conversations exist for the cluster."""
        from fastapi import HTTPException

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_user_conversations.return_value = []

            with pytest.raises(HTTPException) as exc_info:
                await export_conversation(ExportRequest(
                    user_id="user1",
                    cluster_name="prod"
                ))

        assert exc_info.value.status_code in (400, 404)

    @pytest.mark.asyncio
    async def test_export_specific_conversation_not_found_raises_404(self):
        """Export raises 404 when specific conversation_id not found."""
        from fastapi import HTTPException

        with patch('api.chat.conversation_history') as mock_history:
            mock_history.get_conversation.return_value = None

            with pytest.raises(HTTPException) as exc_info:
                await export_conversation(ExportRequest(
                    user_id="user1",
                    cluster_name="prod",
                    conversation_id="nonexistent-id"
                ))

        assert exc_info.value.status_code == 404
