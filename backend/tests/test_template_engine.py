"""Tests for template engine."""

import pytest
from template_engine import TemplateEngine


class TestTemplateEngine:
    """Test suite for TemplateEngine."""

    @pytest.fixture
    def engine(self, tmp_path):
        """Create template engine with temp directory."""
        return TemplateEngine(templates_path=str(tmp_path / "templates"))

    def test_render_basic_prompt(self, engine):
        """Test rendering a basic prompt."""
        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query="Why is my pod failing?",
            cluster_name="test-cluster"
        )

        assert "System Rules:" in result
        assert "Cluster: test-cluster" in result
        assert "Why is my pod failing?" in result
        assert "Output Format:" in result

    def test_render_with_k8sgpt_results(self, engine):
        """Test rendering with K8sGPT findings."""
        k8sgpt_results = [
            {
                "severity": "critical",
                "kind": "Pod",
                "name": "failing-pod",
                "problem": "CrashLoopBackOff",
                "solution": "Check container logs"
            }
        ]

        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query="Why is my pod failing?",
            cluster_name="test-cluster",
            k8sgpt_results=k8sgpt_results
        )

        assert "K8sGPT Findings:" in result
        assert "[CRITICAL]" in result
        assert "Pod/failing-pod" in result
        assert "CrashLoopBackOff" in result

    def test_render_with_cluster_context(self, engine):
        """Test rendering with enriched cluster context."""
        cluster_context = {
            "pods": [
                {"name": "pod-1", "status": "Running"},
                {"name": "pod-2", "status": "Failed"}
            ],
            "events": [
                {"type": "Warning", "message": "Failed to pull image"}
            ]
        }

        result = engine.render(
            query_category="troubleshooting",
            cluster_context=cluster_context,
            kb_results=[],
            query="Check pod status",
            cluster_name="test-cluster"
        )

        assert "Cluster Context:" in result
        assert "Pods:" in result
        assert "pod-1" in result

    def test_render_with_kb_results(self, engine):
        """Test rendering with knowledge base results."""
        kb_results = [
            {
                "title": "Fixing CrashLoopBackOff",
                "content": "Check container logs and resource limits",
                "similarity_score": 0.85,
                "tags": ["pods", "troubleshooting"]
            }
        ]

        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=kb_results,
            query="Pod keeps crashing",
            cluster_name="test-cluster"
        )

        assert "Relevant Knowledge Base Articles:" in result
        assert "Fixing CrashLoopBackOff" in result
        assert "relevance: 0.85" in result

    def test_render_all_categories(self, engine):
        """Test rendering for all template categories."""
        categories = [
            "troubleshooting",
            "deployment",
            "networking",
            "security",
            "gitops",
            "general"
        ]

        for category in categories:
            result = engine.render(
                query_category=category,
                cluster_context={},
                kb_results=[],
                query="Test query",
                cluster_name="test-cluster"
            )

            assert "System Rules:" in result
            assert "Cluster: test-cluster" in result

    def test_format_k8sgpt_results_limits_to_five(self, engine):
        """Test that K8sGPT results are limited to top 5."""
        k8sgpt_results = [
            {"severity": "critical", "kind": "Pod", "name": f"pod-{i}", "problem": "Issue", "solution": "Fix"}
            for i in range(10)
        ]

        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query="Test",
            cluster_name="test-cluster",
            k8sgpt_results=k8sgpt_results
        )

        # Should only include 5 results
        assert result.count("[CRITICAL]") == 5

    def test_format_cluster_context_limits_items(self, engine):
        """Test that cluster context items are limited to 10 per category."""
        cluster_context = {
            "pods": [{"name": f"pod-{i}"} for i in range(20)]
        }

        result = engine.render(
            query_category="troubleshooting",
            cluster_context=cluster_context,
            kb_results=[],
            query="Test",
            cluster_name="test-cluster"
        )

        # Should only include 10 pods
        assert result.count("pod-") == 10

    def test_validate_templates_success(self, engine):
        """Test template validation succeeds for default templates."""
        is_valid, error = engine.validate_templates()
        assert is_valid is True
        assert error is None

    def test_render_with_empty_k8sgpt_results(self, engine):
        """Test rendering with empty K8sGPT results."""
        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query="Test",
            cluster_name="test-cluster",
            k8sgpt_results=[]
        )

        assert "K8sGPT Findings:" not in result

    def test_render_with_empty_cluster_context(self, engine):
        """Test rendering with empty cluster context."""
        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query="Test",
            cluster_name="test-cluster"
        )

        assert "No additional cluster context available" in result

    def test_render_with_empty_kb_results(self, engine):
        """Test rendering with empty KB results."""
        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query="Test",
            cluster_name="test-cluster"
        )

        assert "No relevant knowledge base articles found" in result

    def test_format_kb_results_truncates_content(self, engine):
        """Test that KB content is truncated to 200 characters."""
        kb_results = [
            {
                "title": "Long Article",
                "content": "A" * 500,  # 500 characters
                "similarity_score": 0.9,
                "tags": []
            }
        ]

        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=kb_results,
            query="Test",
            cluster_name="test-cluster"
        )

        # Content should be truncated with "..."
        assert "A" * 200 + "..." in result
        assert "A" * 201 not in result

    def test_render_with_complex_cluster_context(self, engine):
        """Test rendering with nested cluster context."""
        cluster_context = {
            "deployment_info": {
                "name": "my-deployment",
                "replicas": 3,
                "ready": 2
            },
            "events": [
                "Warning: Failed to pull image",
                "Normal: Started container"
            ]
        }

        result = engine.render(
            query_category="deployment",
            cluster_context=cluster_context,
            kb_results=[],
            query="Check deployment",
            cluster_name="test-cluster"
        )

        assert "Deployment Info:" in result
        assert "name: my-deployment" in result
        assert "Events:" in result

    def test_render_preserves_query_text(self, engine):
        """Test that user query is preserved exactly in prompt."""
        query = "Why is my pod in CrashLoopBackOff state?"

        result = engine.render(
            query_category="troubleshooting",
            cluster_context={},
            kb_results=[],
            query=query,
            cluster_name="test-cluster"
        )

        assert query in result

    def test_get_template_for_category(self, engine):
        """Test template selection for query categories."""
        from template_engine import QueryCategory
        
        # Test direct mappings
        assert engine.get_template_for_category(QueryCategory.DEPLOYMENT_STATUS) == "deployment"
        assert engine.get_template_for_category(QueryCategory.SERVICE_NETWORKING) == "networking"
        assert engine.get_template_for_category(QueryCategory.SECURITY) == "security"
        assert engine.get_template_for_category(QueryCategory.ARGOCD) == "gitops"
        
        # Test troubleshooting mappings
        assert engine.get_template_for_category(QueryCategory.POD_ISSUE) == "troubleshooting"
        assert engine.get_template_for_category(QueryCategory.NODE_HEALTH) == "troubleshooting"
        assert engine.get_template_for_category(QueryCategory.STORAGE) == "troubleshooting"
        
        # Test analysis/general mappings
        assert engine.get_template_for_category(QueryCategory.GENERAL_HEALTH) == "analysis"
        assert engine.get_template_for_category(QueryCategory.KB_SEARCH) == "general"

    def test_render_includes_all_sections(self, engine):
        """Test that rendered prompt includes all required sections."""
        result = engine.render(
            query_category="troubleshooting",
            cluster_context={"pods": []},
            kb_results=[{"title": "Test", "content": "Content", "similarity_score": 0.8, "tags": []}],
            query="Test query",
            cluster_name="test-cluster",
            k8sgpt_results=[{"severity": "warning", "kind": "Pod", "name": "test", "problem": "Issue", "solution": "Fix"}]
        )

        # Check all major sections are present
        assert "System Rules:" in result
        assert "Constraints:" in result
        assert "Output Format:" in result
        assert "Cluster:" in result
        assert "K8sGPT Findings:" in result
        assert "Cluster Context:" in result
        assert "Relevant Knowledge Base Articles:" in result
        assert "User Query:" in result
