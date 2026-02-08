"""Tests for response parser."""

import pytest
from response_parser import ResponseParser, ParsedResponse


class TestResponseParser:
    """Test suite for ResponseParser."""

    @pytest.fixture
    def parser(self):
        """Create response parser."""
        return ResponseParser()

    def test_parse_basic_response(self, parser):
        """Test parsing a basic response."""
        response = "This is a basic response with no special content."
        
        parsed = parser.parse(response)
        
        assert parsed.content == response
        assert len(parsed.commands) == 0
        assert parsed.has_unsafe_commands is False

    def test_extract_commands_from_code_blocks(self, parser):
        """Test extracting commands from code blocks."""
        response = """
Here's how to check pod status:

```bash
kubectl get pods -n default
kubectl describe pod my-pod
```
"""
        
        parsed = parser.parse(response)
        
        assert len(parsed.commands) >= 2
        assert any("kubectl get pods" in cmd for cmd in parsed.commands)

    def test_extract_inline_commands(self, parser):
        """Test extracting inline commands."""
        response = "Run `kubectl get pods` to check pod status."
        
        parsed = parser.parse(response)
        
        assert len(parsed.commands) >= 1
        assert any("kubectl get pods" in cmd for cmd in parsed.commands)

    def test_detect_unsafe_delete_command(self, parser):
        """Test detecting unsafe delete commands."""
        response = """
To fix this, run:

```bash
kubectl delete namespace production
```
"""
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True
        assert len(parsed.safety_notices) > 0

    def test_detect_unsafe_rm_command(self, parser):
        """Test detecting unsafe rm -rf commands."""
        response = "Run `rm -rf /data/*` to clean up."
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True

    def test_detect_unsafe_drop_database(self, parser):
        """Test detecting unsafe database drop commands."""
        response = "Execute `DROP DATABASE production` to remove it."
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True

    def test_safe_commands_not_flagged(self, parser):
        """Test that safe commands are not flagged as unsafe."""
        response = """
Check the status:

```bash
kubectl get pods
kubectl logs my-pod
kubectl describe deployment my-app
```
"""
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is False
        assert len(parsed.safety_notices) == 0

    def test_extract_recommendations(self, parser):
        """Test extracting recommendations from response."""
        response = """
Recommended Actions:
1. Check pod logs for errors
2. Verify resource limits
3. Review deployment configuration
"""
        
        parsed = parser.parse(response)
        
        assert len(parsed.recommendations) >= 3

    def test_extract_warnings(self, parser):
        """Test extracting warnings from response."""
        response = """
Warning: This operation will affect production traffic.

⚠️ Make sure to backup your data first.
"""
        
        parsed = parser.parse(response)
        
        assert len(parsed.warnings) >= 1

    def test_extract_kb_citations(self, parser):
        """Test extracting KB citations."""
        kb_results = [
            {"title": "Fixing CrashLoopBackOff", "content": "..."},
            {"title": "Pod Networking Issues", "content": "..."}
        ]
        
        response = "As mentioned in Fixing CrashLoopBackOff, you should check container logs."
        
        parsed = parser.parse(response, kb_results=kb_results)
        
        assert len(parsed.kb_citations) >= 1
        assert "Fixing CrashLoopBackOff" in parsed.kb_citations

    def test_extract_k8sgpt_references(self, parser):
        """Test extracting K8sGPT references."""
        response = """
According to K8sGPT: The pod is in CrashLoopBackOff state due to missing environment variables.
"""
        
        parsed = parser.parse(response)
        
        assert len(parsed.k8sgpt_references) >= 1

    def test_add_safety_warnings_to_response(self, parser):
        """Test adding safety warnings to response."""
        response = "Run `kubectl delete namespace prod` to clean up."
        
        parsed = parser.parse(response)
        enhanced = parser.add_safety_warnings_to_response(parsed)
        
        assert "SAFETY WARNING" in enhanced
        assert "---" in enhanced
        assert response in enhanced

    def test_format_response_with_metadata(self, parser):
        """Test formatting response with metadata."""
        response = """
Recommended Actions:
1. Check logs
2. Verify config

```bash
kubectl get pods
```
"""
        
        parsed = parser.parse(response)
        formatted = parser.format_response_with_metadata(parsed)
        
        assert "content" in formatted
        assert "recommendations" in formatted
        assert "commands" in formatted
        assert "metadata" in formatted
        assert formatted["metadata"]["command_count"] >= 1

    def test_command_deduplication(self, parser):
        """Test that duplicate commands are removed."""
        response = """
```bash
kubectl get pods
kubectl get pods
```
"""
        
        parsed = parser.parse(response)
        
        # Should only have one instance of the command
        assert len(parsed.commands) == 1

    def test_filter_short_commands(self, parser):
        """Test that very short commands are filtered out."""
        response = "Run `ls` or `cd` to navigate."
        
        parsed = parser.parse(response)
        
        # Very short commands should be filtered
        assert len(parsed.commands) == 0

    def test_multiple_unsafe_patterns(self, parser):
        """Test detecting multiple unsafe patterns."""
        response = """
```bash
kubectl delete namespace prod
rm -rf /data
DROP DATABASE users
```
"""
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True
        assert len(parsed.safety_notices) >= 3

    def test_recommendation_limit(self, parser):
        """Test that recommendations are limited to 10."""
        response = "Recommendations:\n" + "\n".join([f"{i}. Action {i}" for i in range(1, 20)])
        
        parsed = parser.parse(response)
        
        assert len(parsed.recommendations) <= 10

    def test_warning_limit(self, parser):
        """Test that warnings are limited to 5."""
        response = "\n\n".join([f"Warning: Issue {i}" for i in range(1, 10)])
        
        parsed = parser.parse(response)
        
        assert len(parsed.warnings) <= 5

    def test_k8sgpt_reference_limit(self, parser):
        """Test that K8sGPT references are limited to 5."""
        response = "\n\n".join([f"K8sGPT finding: Issue {i}" for i in range(1, 10)])
        
        parsed = parser.parse(response)
        
        assert len(parsed.k8sgpt_references) <= 5

    def test_parse_empty_response(self, parser):
        """Test parsing an empty response."""
        parsed = parser.parse("")
        
        assert parsed.content == ""
        assert len(parsed.commands) == 0
        assert len(parsed.recommendations) == 0
        assert parsed.has_unsafe_commands is False

    def test_parse_response_with_all_components(self, parser):
        """Test parsing a response with all components."""
        kb_results = [{"title": "Test Article", "content": "..."}]
        
        response = """
According to K8sGPT: Pod is failing.

Recommended Actions:
1. Check logs
2. Verify config

Warning: This will affect production.

```bash
kubectl get pods
```

See Test Article for more details.
"""
        
        parsed = parser.parse(response, kb_results=kb_results)
        
        assert len(parsed.commands) >= 1
        assert len(parsed.recommendations) >= 2
        assert len(parsed.warnings) >= 1
        assert len(parsed.kb_citations) >= 1
        assert len(parsed.k8sgpt_references) >= 1

    def test_safety_notice_content(self, parser):
        """Test that safety notices contain helpful information."""
        response = "Run `kubectl delete namespace prod` to clean up."
        
        parsed = parser.parse(response)
        
        assert len(parsed.safety_notices) > 0
        notice = parsed.safety_notices[0]
        assert "SAFETY WARNING" in notice
        assert "destructive" in notice.lower()
        assert "backup" in notice.lower()

    def test_argocd_delete_detected_as_unsafe(self, parser):
        """Test that ArgoCD delete commands are detected as unsafe."""
        response = "Run `argocd app delete my-app` to remove it."
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True

    def test_helm_uninstall_detected_as_unsafe(self, parser):
        """Test that Helm uninstall commands are detected as unsafe."""
        response = "Run `helm uninstall my-release` to remove it."
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True

    def test_pvc_delete_detected_as_unsafe(self, parser):
        """Test that PVC delete commands are detected as unsafe."""
        response = "Run `kubectl delete pvc data-volume` to clean up."
        
        parsed = parser.parse(response)
        
        assert parsed.has_unsafe_commands is True
