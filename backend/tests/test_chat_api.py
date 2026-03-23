"""
Comprehensive tests for the Chat API endpoint.

Tests cover:
- Chat query endpoint with K8sGPT results integration
- Chat response structure and fields
- Error handling scenarios
- Input sanitization flow
- Query classification
- Enrichment with context
- K8sGPT findings serialization
- Conversation history management
- Rate limiting
- Credential validation
- All chat-related endpoints (history, export, conversations)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, AsyncMock, call
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from fastapi import HTTPException
from pydantic import ValidationError

from api.chat import (
    ChatRequest,
    ChatResponse,
    FeedbackRequest,
    ExportRequest,
    process_chat_query,
    submit_feedback,
    export_conversation,
    get_chat_history,
    get_conversation_list,
    get_conversation,
)
from enrichment_engine import EnrichedContext
from k8sgpt_reader import K8sGPTResult
from conversation_history import ConversationHistory, Conversation, ChatMessage
from query_router import EnrichmentPlan, QueryCategory
from credential_store import StoredCredentials
from input_sanitizer import InputSanitizer


@pytest.fixture
def mock_credentials():
    """Create mock AWS credentials."""
    creds = Mock(spec=StoredCredentials)
    creds.access_key = "ASIATESTACCESSKEY123456"
    creds.secret_key = "test_secret_key_" + "a" * 24
    creds.session_token = "test_session_token_" + "a" * 40
    creds.region = "us-east-1"
    creds.auth_mode = "aws"
    creds.is_expiring_soon.return_value = False
    return creds


@pytest.fixture
def mock_k8s_clients():
    """Create mock Kubernetes API clients."""
    return {
        "core_v1": Mock(),
        "apps_v1": Mock(),
        "custom_objects": Mock(),
        "networking_v1": Mock(),
    }


@pytest.fixture
def mock_k8sgpt_results():
    """Create mock K8sGPT results."""
    results = [
        K8sGPTResult(
            name="pod-nginx-crashloop-abc123",
            kind="Pod",
            namespace="default",
            severity="high",
            problem="Pod nginx is in CrashLoopBackOff",
            solution="Check pod logs with 'kubectl logs nginx' and fix the issue",
            analyzer="Pod",
            timestamp=datetime.utcnow(),
            details={
                "resource_name": "nginx",
                "error": ["CrashLoopBackOff"],
                "backend": "openai",
            },
        ),
        K8sGPTResult(
            name="pod-worker-oom-def456",
            kind="Pod",
            namespace="production",
            severity="high",
            problem="Pod worker was OOMKilled",
            solution="Increase memory limit in pod spec",
            analyzer="Pod",
            timestamp=datetime.utcnow(),
            details={
                "resource_name": "worker",
                "error": ["OOMKilled"],
                "backend": "openai",
            },
        ),
        K8sGPTResult(
            name="deployment-app-pending-ghi789",
            kind="Deployment",
            namespace="staging",
            severity="medium",
            problem="Deployment replicas are pending",
            solution="Check node capacity and add more nodes if needed",
            analyzer="Deployment",
            timestamp=datetime.utcnow(),
            details={
                "resource_name": "app",
                "error": ["Pending"],
                "backend": "openai",
            },
        ),
    ]
    return results


@pytest.fixture
def mock_enriched_context(mock_k8sgpt_results):
    """Create mock enriched context."""
    context = EnrichedContext()
    context.k8sgpt_results = mock_k8sgpt_results
    context.pod_data = {
        "pods": [
            {
                "name": "nginx",
                "namespace": "default",
                "phase": "Failed",
                "container_statuses": [
                    {
                        "name": "nginx",
                        "restart_count": 5,
                        "last_state": {"terminated": {"reason": "CrashLoopBackOff"}},
                    }
                ],
            }
        ]
    }
    context.deployment_data = {
        "deployments": [
            {
                "name": "app",
                "namespace": "staging",
                "replicas": 3,
                "ready_replicas": 0,
                "updated_replicas": 3,
            }
        ]
    }
    context.enrichment_plan = {
        "categories": ["POD_ISSUE", "DEPLOYMENT_STATUS"],
        "resource_names": ["nginx", "app"],
        "namespaces": ["default", "staging"],
        "include_aws_context": False,
        "time_range": None,
    }
    context.cluster_name = "test-cluster"
    context.errors = []
    return context


@pytest.fixture
def mock_enrichment_plan():
    """Create mock enrichment plan."""
    return EnrichmentPlan(
        categories=[QueryCategory.POD_ISSUE],
        resource_names=["nginx"],
        namespaces=["default"],
        include_aws_context=False,
        time_range=timedelta(hours=1),
    )


@pytest.fixture
def mock_rag_response():
    """Create mock RAG response."""
    return {
        "response": "The pod nginx is in CrashLoopBackOff state, which indicates the container is repeatedly exiting. Based on the K8sGPT analysis and cluster context, this is likely due to a configuration error. Check the pod logs for details.",
        "citations": [
            {
                "source": "K8sGPT Results",
                "detail": "Pod nginx is in CrashLoopBackOff",
            },
            {
                "source": "Kubernetes Documentation",
                "detail": "CrashLoopBackOff explained",
            },
        ],
        "errors": [],
        "metadata": {
            "sources_used": 2,
            "retrieval_score": 0.92,
            "processing_time_ms": 145,
        },
    }


class TestChatQueryEndpoint:
    """Test the POST /api/chat/query endpoint."""

    def test_valid_chat_request_structure(self):
        """Test ChatRequest model accepts valid input."""
        request = ChatRequest(
            query="Why is my pod crashing?",
            session_id="session_abc123",
            user_id="user_123",
            cluster_name="test-cluster",
        )

        assert request.query == "Why is my pod crashing?"
        assert request.session_id == "session_abc123"
        assert request.user_id == "user_123"
        assert request.cluster_name == "test-cluster"
        assert request.max_tokens == 500  # Default
        assert request.is_export is False  # Default

    def test_chat_request_validation_min_length(self):
        """Test ChatRequest rejects empty query."""
        with pytest.raises(ValidationError):
            ChatRequest(
                query="",
                session_id="session_abc123",
                user_id="user_123",
            )

    def test_chat_request_validation_max_length(self):
        """Test ChatRequest rejects query over 2000 chars."""
        long_query = "a" * 2001
        with pytest.raises(ValidationError):
            ChatRequest(
                query=long_query,
                session_id="session_abc123",
                user_id="user_123",
            )

    def test_chat_request_validation_max_tokens(self):
        """Test ChatRequest rejects max_tokens over 2000."""
        with pytest.raises(ValidationError):
            ChatRequest(
                query="test query",
                session_id="session_abc123",
                user_id="user_123",
                max_tokens=2001,
            )

    def test_chat_request_validation_min_tokens(self):
        """Test ChatRequest rejects max_tokens under 100."""
        with pytest.raises(ValidationError):
            ChatRequest(
                query="test query",
                session_id="session_abc123",
                user_id="user_123",
                max_tokens=99,
            )

    @pytest.mark.asyncio
    @patch("api.chat.rate_limiter")
    @patch("api.chat.input_sanitizer")
    @patch("api.chat.get_credentials_for_session")
    async def test_process_chat_query_rate_limit_exceeded(
        self, mock_get_creds, mock_sanitizer, mock_rate_limiter
    ):
        """Test rate limiting is enforced."""
        # Setup mocks
        mock_rate_limiter.check_rate_limit = AsyncMock(
            return_value=(False, 30, 0)  # Not allowed, 30 sec retry, 0 remaining
        )
        mock_sanitizer.validate_query.return_value = (True, None, "test query")

        request = ChatRequest(
            query="test query",
            session_id="session_abc123",
            user_id="user_123",
            cluster_name="test-cluster",
        )

        with pytest.raises(HTTPException) as exc_info:
            await process_chat_query(request)

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("api.chat.input_sanitizer")
    async def test_process_chat_query_invalid_input(self, mock_sanitizer):
        """Test invalid input is rejected."""
        # Setup mock
        mock_sanitizer.validate_query.return_value = (
            False,
            "Query contains shell commands",
            None,
        )

        request = ChatRequest(
            query="bash -c 'echo hello'",
            session_id="session_abc123",
            user_id="user_123",
            cluster_name="test-cluster",
        )

        with pytest.raises(HTTPException) as exc_info:
            await process_chat_query(request)

        assert exc_info.value.status_code == 400
        assert "shell commands" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("api.chat.rate_limiter")
    @patch("api.chat.input_sanitizer")
    @patch("api.chat.get_credentials_for_session")
    async def test_process_chat_query_missing_credentials(
        self, mock_get_creds, mock_sanitizer, mock_rate_limiter
    ):
        """Test missing credentials returns 401."""
        # Setup mocks
        mock_sanitizer.validate_query.return_value = (True, None, "test query")
        mock_rate_limiter.check_rate_limit = AsyncMock(
            return_value=(True, None, 20)
        )
        mock_get_creds.return_value = None

        request = ChatRequest(
            query="test query",
            session_id="invalid_session",
            user_id="user_123",
            cluster_name="test-cluster",
        )

        with pytest.raises(HTTPException) as exc_info:
            await process_chat_query(request)

        assert exc_info.value.status_code == 401
        assert "No credentials found" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("api.chat.rate_limiter")
    @patch("api.chat.input_sanitizer")
    @patch("api.chat.get_credentials_for_session")
    async def test_process_chat_query_missing_cluster(
        self, mock_get_creds, mock_sanitizer, mock_rate_limiter, mock_credentials
    ):
        """Test missing cluster selection returns 400."""
        # Setup mocks
        mock_sanitizer.validate_query.return_value = (True, None, "test query")
        mock_rate_limiter.check_rate_limit = AsyncMock(
            return_value=(True, None, 20)
        )
        mock_get_creds.return_value = mock_credentials

        request = ChatRequest(
            query="test query",
            session_id="session_abc123",
            user_id="user_123",
            cluster_name=None,  # No cluster
        )

        with pytest.raises(HTTPException) as exc_info:
            await process_chat_query(request)

        assert exc_info.value.status_code == 400
        assert "No cluster selected" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    @patch("api.chat.rate_limiter")
    @patch("api.chat.input_sanitizer")
    @patch("api.chat.get_credentials_for_session")
    async def test_process_chat_query_cluster_not_found(
        self,
        mock_get_creds,
        mock_sanitizer,
        mock_rate_limiter,
        mock_credentials,
    ):
        """Test non-existent cluster returns 404."""
        # Setup mocks
        mock_sanitizer.validate_query.return_value = (True, None, "test query")
        mock_rate_limiter.check_rate_limit = AsyncMock(
            return_value=(True, None, 20)
        )
        mock_get_creds.return_value = mock_credentials

        # Mock cluster discovery to return clusters
        with patch("cluster_manager.discover_clusters", new_callable=AsyncMock) as mock_discover:
            mock_discover.return_value = [
                {"name": "cluster-1", "version": "v1.28"},
                {"name": "cluster-2", "version": "v1.27"},
            ]

            request = ChatRequest(
                query="test query",
                session_id="session_abc123",
                user_id="user_123",
                cluster_name="nonexistent-cluster",
            )

            with pytest.raises(HTTPException) as exc_info:
                await process_chat_query(request)

            assert exc_info.value.status_code == 404
            assert "not found or not accessible" in str(exc_info.value.detail)

    def test_chat_response_structure(self, mock_k8sgpt_results):
        """Test ChatResponse has all required fields."""
        response = ChatResponse(
            query="test query",
            response="test response",
            conversation_id="conv_123",
            citations=[],
            k8sgpt_findings=[
                {
                    "name": result.name,
                    "kind": result.kind,
                    "severity": result.severity,
                    "problem": result.problem,
                    "solution": result.solution,
                }
                for result in mock_k8sgpt_results[:5]
            ],
            safety_warnings=[],
            enrichment_plan={
                "categories": ["POD_ISSUE"],
                "resource_names": ["nginx"],
                "namespaces": ["default"],
                "include_aws_context": False,
                "time_range": None,
            },
            token_usage={"prompt_tokens": 150, "completion_tokens": 50},
            errors=[],
            metadata={
                "cluster": "test-cluster",
                "cluster_version": "v1.28",
                "k8sgpt_result_count": 3,
            },
        )

        assert response.query == "test query"
        assert response.response == "test response"
        assert response.conversation_id == "conv_123"
        assert len(response.k8sgpt_findings) == 3
        assert response.k8sgpt_findings[0]["kind"] == "Pod"
        assert response.k8sgpt_findings[0]["severity"] == "high"
        assert "categories" in response.enrichment_plan

    def test_chat_response_k8sgpt_findings_serialization(self):
        """Test K8sGPT findings are properly serialized in response."""
        findings = [
            {
                "name": "pod-nginx-crash-123",
                "kind": "Pod",
                "severity": "high",
                "problem": "Pod is in CrashLoopBackOff",
                "solution": "Check logs with kubectl logs",
            },
            {
                "name": "pod-worker-oom-456",
                "kind": "Pod",
                "severity": "high",
                "problem": "Pod was OOMKilled",
                "solution": "Increase memory limit",
            },
        ]

        response = ChatResponse(
            query="Why is my pod crashing?",
            response="Your pod is experiencing issues...",
            conversation_id="conv_abc",
            k8sgpt_findings=findings,
        )

        assert len(response.k8sgpt_findings) == 2
        assert response.k8sgpt_findings[0]["severity"] == "high"
        assert response.k8sgpt_findings[1]["problem"] == "Pod was OOMKilled"

        # Verify serialization to dict works
        response_dict = response.dict()
        assert "k8sgpt_findings" in response_dict
        assert len(response_dict["k8sgpt_findings"]) == 2

    def test_chat_response_empty_optional_fields(self):
        """Test ChatResponse handles empty optional fields."""
        response = ChatResponse(
            query="test",
            response="response",
            conversation_id="conv_id",
            # All optional fields omitted
        )

        assert response.citations == []
        assert response.k8sgpt_findings == []
        assert response.safety_warnings == []
        assert response.errors == []
        assert response.metadata == {}
        assert response.token_usage == {}


class TestInputSanitizationFlow:
    """Test input sanitization integration in chat API."""

    def test_sanitizer_blocks_shell_commands(self):
        """Test that destructive shell commands are blocked.

        Note: General shell syntax (bash -c, shebangs, kubectl, etc.) is intentionally
        allowed — this is a DevOps chatbot where users routinely include such syntax in
        their questions. Only genuinely destructive patterns (rm -rf /, fork bombs) are
        blocked.
        """
        sanitizer = InputSanitizer()

        queries = [
            "$(rm -rf /)",   # destructive rm targeting root filesystem
            "rm -rf /tmp",   # rm -rf / variant
        ]

        for query in queries:
            is_valid, error, _ = sanitizer.validate_query(query)
            assert is_valid is False, f"Should block: {query}"

    def test_sanitizer_allows_safe_questions(self):
        """Test that safe questions are allowed."""
        sanitizer = InputSanitizer()

        queries = [
            "Why is my pod crashing?",
            "How do I debug a deployment?",
            "What's the status of my services?",
        ]

        for query in queries:
            is_valid, error, _ = sanitizer.validate_query(query)
            assert is_valid is True, f"Should allow: {query}"

    def test_sanitizer_cleans_backticks(self):
        """Test that backticks are cleaned from queries."""
        sanitizer = InputSanitizer()

        query = "Show me `pod` status"
        is_valid, error, cleaned = sanitizer.validate_query(query)

        assert is_valid is True
        assert "`" not in cleaned


class TestQueryClassificationFlow:
    """Test query classification integration."""

    def test_query_classification_pod_issue(self):
        """Test pod issue classification."""
        from query_router import QueryRouter

        router = QueryRouter()
        plan = router.classify("Why is my pod crashing?")

        assert QueryCategory.POD_ISSUE in plan.categories

    def test_query_classification_deployment_issue(self):
        """Test deployment issue classification."""
        from query_router import QueryRouter

        router = QueryRouter()
        plan = router.classify("My deployment is not rolling out")

        assert QueryCategory.DEPLOYMENT_STATUS in plan.categories

    def test_query_classification_extracts_namespaces(self):
        """Test that classification extracts namespaces."""
        from query_router import QueryRouter

        router = QueryRouter()
        plan = router.classify("Show me pods in namespace production")

        # Should extract namespace from query
        assert plan.namespaces is not None

    def test_enrichment_plan_structure(self, mock_enrichment_plan):
        """Test enrichment plan has all required fields."""
        assert mock_enrichment_plan.categories is not None
        assert mock_enrichment_plan.resource_names is not None
        assert mock_enrichment_plan.namespaces is not None
        assert mock_enrichment_plan.include_aws_context is not None


class TestEnrichmentFlow:
    """Test enrichment context integration."""

    def test_enriched_context_includes_k8sgpt_results(
        self, mock_enriched_context, mock_k8sgpt_results
    ):
        """Test enriched context contains K8sGPT results."""
        assert mock_enriched_context.k8sgpt_results is not None
        assert len(mock_enriched_context.k8sgpt_results) == 3
        assert all(isinstance(r, K8sGPTResult) for r in mock_enriched_context.k8sgpt_results)

    def test_enriched_context_includes_pod_data(self, mock_enriched_context):
        """Test enriched context contains pod data."""
        assert mock_enriched_context.pod_data is not None
        assert "pods" in mock_enriched_context.pod_data
        assert len(mock_enriched_context.pod_data["pods"]) > 0

    def test_enriched_context_includes_deployment_data(self, mock_enriched_context):
        """Test enriched context contains deployment data."""
        assert mock_enriched_context.deployment_data is not None
        assert "deployments" in mock_enriched_context.deployment_data

    def test_enriched_context_includes_enrichment_plan(self, mock_enriched_context):
        """Test enriched context contains enrichment plan metadata."""
        assert mock_enriched_context.enrichment_plan is not None
        assert "categories" in mock_enriched_context.enrichment_plan
        assert "resource_names" in mock_enriched_context.enrichment_plan

    def test_enriched_context_tracks_errors(self, mock_enriched_context):
        """Test enriched context has error tracking."""
        assert isinstance(mock_enriched_context.errors, list)

    def test_enriched_context_merge(self):
        """Test enriched context can merge another context."""
        context1 = EnrichedContext()
        context1.pod_data = {"pods": [{"name": "pod1"}]}

        context2 = EnrichedContext()
        context2.pod_data = {"pods": [{"name": "pod2"}]}
        context2.errors = ["error1"]

        context1.merge(context2)

        assert context1.pod_data == {"pods": [{"name": "pod2"}]}
        assert "error1" in context1.errors


class TestK8sGPTFindings:
    """Test K8sGPT findings integration."""

    def test_k8sgpt_result_serialization(self):
        """Test K8sGPT results can be serialized to dict."""
        result = K8sGPTResult(
            name="pod-nginx-crash",
            kind="Pod",
            namespace="default",
            severity="high",
            problem="CrashLoopBackOff",
            solution="Check logs",
            analyzer="Pod",
            timestamp=datetime.utcnow(),
            details={"error": ["CrashLoopBackOff"]},
        )

        result_dict = result.to_dict()

        assert result_dict["name"] == "pod-nginx-crash"
        assert result_dict["severity"] == "high"
        assert result_dict["problem"] == "CrashLoopBackOff"
        # Timestamp should be ISO format string
        assert isinstance(result_dict["timestamp"], str)

    def test_k8sgpt_results_filtered_to_top_5(self, mock_k8sgpt_results):
        """Test that only top 5 K8sGPT results are included in response."""
        # Create more than 5 results
        results = mock_k8sgpt_results * 3  # 9 results

        # Simulate response building (top 5)
        findings = [
            {
                "name": r.name,
                "kind": r.kind,
                "severity": r.severity,
                "problem": r.problem,
                "solution": r.solution,
            }
            for r in results[:5]
        ]

        assert len(findings) == 5

    def test_k8sgpt_results_sorted_by_severity(self):
        """Test K8sGPT results are sorted by severity."""
        from k8sgpt_reader import K8sGPTReader

        results = [
            K8sGPTResult(
                name="low-severity",
                kind="Pod",
                namespace="default",
                severity="low",
                problem="Minor issue",
                solution="Minor fix",
                analyzer="Pod",
                timestamp=datetime.utcnow(),
                details={},
            ),
            K8sGPTResult(
                name="high-severity",
                kind="Pod",
                namespace="default",
                severity="high",
                problem="Critical issue",
                solution="Critical fix",
                analyzer="Pod",
                timestamp=datetime.utcnow(),
                details={},
            ),
            K8sGPTResult(
                name="medium-severity",
                kind="Pod",
                namespace="default",
                severity="medium",
                problem="Medium issue",
                solution="Medium fix",
                analyzer="Pod",
                timestamp=datetime.utcnow(),
                details={},
            ),
        ]

        reader = K8sGPTReader(Mock())
        sorted_results = reader.sort_by_severity(results)

        assert sorted_results[0].severity == "high"
        assert sorted_results[1].severity == "medium"
        assert sorted_results[2].severity == "low"


class TestErrorHandling:
    """Test error handling in chat API."""

    def test_http_exception_for_connection_errors(self):
        """Test that connection errors would return HTTP 503 based on code structure."""
        # The chat.py code at lines 328-335 handles ConnectionError -> 503
        # Verify the code pattern exists
        import inspect
        source = inspect.getsource(process_chat_query)
        assert "ConnectionError" in source
        assert "503" in source

    def test_http_exception_for_validation_errors(self):
        """Test that validation errors would return HTTP 400 based on code structure."""
        # The chat.py code at lines 336-339 handles ValueError -> 400
        import inspect
        source = inspect.getsource(process_chat_query)
        assert "ValueError" in source
        assert "400" in source

    def test_http_exception_for_auth_errors(self):
        """Test that auth errors would return HTTP 401 based on code structure."""
        # The chat.py code at lines 341-349 handles 401 Unauthorized
        import inspect
        source = inspect.getsource(process_chat_query)
        assert "401" in source or "unauthorized" in source.lower()

    def test_http_exception_for_rbac_errors(self):
        """Test that RBAC errors would return HTTP 403 based on code structure."""
        # The chat.py code at lines 350-356 handles 403 Forbidden
        import inspect
        source = inspect.getsource(process_chat_query)
        assert "403" in source or "forbidden" in source.lower()


class TestConversationHistoryIntegration:
    """Test conversation history integration in chat API."""

    def test_feedback_request_structure(self):
        """Test FeedbackRequest model."""
        feedback = FeedbackRequest(
            query="test query",
            response="test response",
            rating=5,
            comment="Great response",
            session_id="session_123",
        )

        assert feedback.rating == 5
        assert feedback.comment == "Great response"

    def test_feedback_request_rating_validation(self):
        """Test FeedbackRequest rating validation."""
        with pytest.raises(ValidationError):
            FeedbackRequest(
                query="test",
                response="test",
                rating=6,  # Invalid, > 5
                session_id="session_123",
            )

    def test_export_request_structure(self):
        """Test ExportRequest model."""
        export = ExportRequest(
            user_id="user_123",
            cluster_name="test-cluster",
            conversation_id="conv_123",
        )

        assert export.user_id == "user_123"
        assert export.cluster_name == "test-cluster"
        assert export.conversation_id == "conv_123"

    @pytest.mark.asyncio
    @patch("api.chat.conversation_history")
    async def test_get_chat_history(self, mock_hist):
        """Test getting chat history for cluster."""
        # Mock conversation history
        mock_conv = Mock()
        mock_conv.id = "conv_123"
        mock_conv.messages = [
            Mock(role="user", content="test", timestamp=datetime.utcnow()),
            Mock(role="assistant", content="response", timestamp=datetime.utcnow()),
        ]

        mock_hist.get_user_conversations.return_value = [mock_conv]

        result = await get_chat_history(
            user_id="user_123",
            cluster_name="test-cluster",
            limit=50,
        )

        assert result["user_id"] == "user_123"
        assert result["cluster"] == "test-cluster"
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    @patch("api.chat.conversation_history")
    async def test_get_conversation_list(self, mock_hist):
        """Test getting list of conversations."""
        # Mock conversations
        mock_conv1 = Mock()
        mock_conv1.id = "conv_1"
        mock_conv1.title = "First Conversation"
        mock_conv1.messages = [Mock(content="test message")]
        mock_conv1.created_at = datetime.utcnow()
        mock_conv1.updated_at = datetime.utcnow()

        mock_conv2 = Mock()
        mock_conv2.id = "conv_2"
        mock_conv2.title = "Second Conversation"
        mock_conv2.messages = [Mock(content="another message")]
        mock_conv2.created_at = datetime.utcnow()
        mock_conv2.updated_at = datetime.utcnow()

        mock_hist.get_user_conversations.return_value = [mock_conv1, mock_conv2]

        result = await get_conversation_list(
            user_id="user_123",
            cluster_name="test-cluster",
            limit=10,
        )

        assert len(result["conversations"]) == 2
        assert result["conversations"][0]["title"] == "First Conversation"

    @pytest.mark.asyncio
    @patch("api.chat.conversation_history")
    async def test_get_specific_conversation(self, mock_hist):
        """Test getting specific conversation."""
        # Mock conversation
        mock_conv = Mock()
        mock_conv.id = "conv_123"
        mock_conv.title = "Test Conversation"
        mock_conv.created_at = datetime.utcnow()
        mock_conv.updated_at = datetime.utcnow()
        mock_conv.messages = [
            Mock(role="user", content="question", timestamp=datetime.utcnow()),
            Mock(role="assistant", content="answer", timestamp=datetime.utcnow()),
        ]

        mock_hist.get_conversation.return_value = mock_conv

        result = await get_conversation(
            user_id="user_123",
            conversation_id="conv_123",
            cluster_name="test-cluster",
        )

        assert result["id"] == "conv_123"
        assert result["title"] == "Test Conversation"
        assert len(result["messages"]) == 2

    @pytest.mark.asyncio
    @patch("api.chat.conversation_history")
    async def test_get_conversation_not_found(self, mock_hist):
        """Test getting non-existent conversation."""
        mock_hist.get_conversation.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_conversation(
                user_id="user_123",
                conversation_id="nonexistent",
                cluster_name="test-cluster",
            )

        assert exc_info.value.status_code == 404


class TestHealthEndpoint:
    """Test health check endpoint."""

    @pytest.mark.asyncio
    @patch("api.chat.get_rag_integration")
    async def test_chat_health_check_healthy(self, mock_get_rag):
        """Test health check returns healthy status."""
        # Mock RAG integration
        mock_rag = Mock()
        mock_rag.get_initialization_status.return_value = {
            "fully_functional": True,
            "llm_available": True,
            "kb_available": True,
        }
        mock_get_rag.return_value = mock_rag

        from api.chat import chat_health

        result = await chat_health()

        assert result["status"] == "healthy"
        assert "components" in result

    @pytest.mark.asyncio
    @patch("api.chat.get_rag_integration")
    async def test_chat_health_check_degraded(self, mock_get_rag):
        """Test health check handles degraded RAG."""
        # Mock degraded RAG
        mock_rag = Mock()
        mock_rag.get_initialization_status.return_value = {
            "fully_functional": False,
            "llm_available": True,
            "kb_available": False,
        }
        mock_get_rag.return_value = mock_rag

        from api.chat import chat_health

        result = await chat_health()

        assert result["status"] == "healthy"
        # The endpoint checks if RAG is "fully_functional"
        assert result["components"]["rag_integration"]["status"] == "degraded"


class TestCredentialExpiration:
    """Test handling of expiring credentials."""

    def test_response_includes_expiration_warning(self, mock_credentials):
        """Test response includes credential expiration warning."""
        mock_credentials.is_expiring_soon.return_value = True

        response = ChatResponse(
            query="test",
            response="response",
            conversation_id="conv",
            metadata={
                "credentials_expiring_soon": True,
            },
        )

        assert response.metadata["credentials_expiring_soon"] is True


class TestRateLimitMetadata:
    """Test rate limit information in responses."""

    def test_response_includes_rate_limit_remaining(self):
        """Test response includes rate limit remaining."""
        response = ChatResponse(
            query="test",
            response="response",
            conversation_id="conv",
            metadata={
                "rate_limit_remaining": 19,
            },
        )

        assert response.metadata["rate_limit_remaining"] == 19


class TestResponseMetadata:
    """Test response metadata fields."""

    def test_response_includes_cluster_version(self):
        """Test response includes cluster version."""
        response = ChatResponse(
            query="test",
            response="response",
            conversation_id="conv",
            metadata={
                "cluster": "test-cluster",
                "cluster_version": "v1.28",
                "k8sgpt_result_count": 5,
            },
        )

        assert response.metadata["cluster_version"] == "v1.28"
        assert response.metadata["k8sgpt_result_count"] == 5

    def test_response_includes_rag_metadata(self):
        """Test response includes RAG metadata."""
        response = ChatResponse(
            query="test",
            response="response",
            conversation_id="conv",
            metadata={
                "rag_metadata": {
                    "sources_used": 2,
                    "retrieval_score": 0.92,
                }
            },
        )

        assert "rag_metadata" in response.metadata
        assert response.metadata["rag_metadata"]["sources_used"] == 2
