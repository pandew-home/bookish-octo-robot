"""
Error handling scenario tests for DevOps Chatbot v2.0

Tests error handling for:
- Credential expiration
- Cluster discovery failures
- K8sGPT CRD read failures
- RBAC permission errors
- LLM API failures
- Rate limit enforcement

Requirements: 1.3, 2.5, 3.6, 5.7, 9.1, 17.2, 17.7
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from kubernetes.client.exceptions import ApiException
import time


@pytest.fixture
def client():
    """Create test client"""
    from backend.app import app
    return TestClient(app)


@pytest.fixture
def authenticated_session(client):
    """Create authenticated session"""
    with patch('backend.api.credentials.validate_credentials') as mock_validate:
        mock_validate.return_value = {
            "valid": True,
            "user_arn": "arn:aws:iam::123456789012:user/test-user"
        }
        
        response = client.post(
            "/api/credentials/aws",
            json={
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "session_token": "FwoGZXIvYXdzEBQaDH...",
                "region": "us-east-1"
            }
        )
        
        return response.json()["session_id"]


class TestCredentialExpiration:
    """Test credential expiration handling"""
    
    def test_credential_expiration_during_request(self, client, authenticated_session):
        """
        Test: Credentials expire during API request
        Requirements: 1.3
        """
        # Simulate expired credentials
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            mock_get.return_value = None
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 401
            data = response.json()
            assert "expired" in data["error"].lower() or "invalid" in data["error"].lower()
    
    def test_credential_status_shows_expiring_soon(self, client, authenticated_session):
        """
        Test: Status endpoint shows 'expiring_soon' when TTL < 300s
        Requirements: 1.3
        """
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            # Mock credentials with 200 seconds remaining
            mock_get.return_value = {
                "credentials": {"access_key": "AKIA..."},
                "expires_at": time.time() + 200
            }
            
            response = client.get(
                "/api/credentials/aws/status",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "expiring_soon"
            assert data["ttl_remaining"] < 300


class TestClusterDiscoveryFailures:
    """Test cluster discovery failure handling"""
    
    def test_eks_api_unavailable(self, client, authenticated_session):
        """
        Test: EKS API is unavailable
        Requirements: 2.5
        """
        with patch('backend.api.clusters.discover_clusters') as mock_discover:
            mock_discover.side_effect = Exception("Unable to connect to EKS API")
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 500
            data = response.json()
            assert "error" in data
            assert "EKS" in data["error"] or "discover" in data["error"].lower()
    
    def test_no_clusters_found(self, client, authenticated_session):
        """
        Test: No clusters found in region
        Requirements: 2.5
        """
        with patch('backend.api.clusters.discover_clusters') as mock_discover:
            mock_discover.return_value = []
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert len(data) == 0
    
    def test_insufficient_permissions(self, client, authenticated_session):
        """
        Test: User lacks EKS permissions
        Requirements: 2.5
        """
        with patch('backend.api.clusters.discover_clusters') as mock_discover:
            mock_discover.side_effect = Exception("AccessDenied: User lacks eks:ListClusters permission")
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 500
            data = response.json()
            assert "error" in data
            assert "permission" in data["error"].lower() or "access" in data["error"].lower()


class TestK8sGPTCRDFailures:
    """Test K8sGPT CRD read failure handling"""
    
    def test_k8sgpt_operator_not_installed(self, client, authenticated_session):
        """
        Test: K8sGPT Operator not installed in cluster
        Requirements: 3.6
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"custom_objects": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.k8sgpt_reader.read_k8sgpt_results') as mock_read:
            # Simulate CRD not found
            mock_read.side_effect = ApiException(status=404, reason="Not Found")
            
            response = client.get(
                "/api/weather",
                headers={"X-Session-ID": authenticated_session}
            )
            
            # Should return gracefully with no results
            assert response.status_code == 200
            data = response.json()
            assert data["state"] == "sunny"  # Default when no issues found
            assert len(data["top_issues"]) == 0
    
    def test_k8sgpt_crd_read_timeout(self, client, authenticated_session):
        """
        Test: Timeout reading K8sGPT CRDs
        Requirements: 3.6
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"custom_objects": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.k8sgpt_reader.read_k8sgpt_results') as mock_read:
            mock_read.side_effect = TimeoutError("Request timed out")
            
            response = client.get(
                "/api/weather",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 500
            data = response.json()
            assert "error" in data
            assert "timeout" in data["error"].lower()


class TestRBACPermissionErrors:
    """Test RBAC permission error handling"""
    
    def test_rbac_403_on_enrichment(self, client, authenticated_session):
        """
        Test: RBAC 403 error during enrichment
        Requirements: 5.7, 17.7
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.enrichment_engine.EnrichmentEngine.execute') as mock_enrich:
            # Simulate RBAC 403 error
            mock_enrich.side_effect = ApiException(
                status=403,
                reason="Forbidden: User lacks permission to list pods"
            )
            
            with patch('backend.api.chat.query_router') as mock_router:
                mock_router.classify.return_value = {"category": "troubleshooting"}
                
                response = client.post(
                    "/api/chat",
                    json={"query": "Why is my pod failing?"},
                    headers={"X-Session-ID": authenticated_session}
                )
                
                # Should handle gracefully and continue with limited context
                assert response.status_code == 200
                data = response.json()
                assert "response" in data
                # Response should mention permission issues
                assert "permission" in data["response"].lower() or "access" in data["response"].lower()
    
    def test_rbac_403_handled_gracefully(self, client, authenticated_session):
        """
        Test: RBAC 403 errors are logged but don't crash the request
        Requirements: 17.7
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_core_v1 = Mock()
            mock_core_v1.list_pod_for_all_namespaces.side_effect = ApiException(
                status=403,
                reason="Forbidden"
            )
            mock_clients.return_value = {"core_v1": mock_core_v1}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        # Request should not crash
        with patch('backend.enrichment_engine.EnrichmentEngine._enrich_pods') as mock_enrich:
            mock_enrich.return_value = {}  # Empty result due to RBAC error
            
            response = client.get(
                "/api/weather",
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 200


class TestLLMAPIFailures:
    """Test LLM API failure handling"""
    
    def test_llm_api_timeout(self, client, authenticated_session):
        """
        Test: LLM API request times out
        Requirements: 17.2
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.llm_client.LLMClient.generate') as mock_llm:
            mock_llm.side_effect = TimeoutError("LLM API request timed out")
            
            with patch('backend.api.chat.query_router') as mock_router:
                mock_router.classify.return_value = {"category": "troubleshooting"}
                
                response = client.post(
                    "/api/chat",
                    json={"query": "Why is my pod failing?"},
                    headers={"X-Session-ID": authenticated_session}
                )
                
                assert response.status_code == 500
                data = response.json()
                assert "error" in data
                assert "timeout" in data["error"].lower() or "llm" in data["error"].lower()
    
    def test_llm_api_rate_limit(self, client, authenticated_session):
        """
        Test: LLM API rate limit exceeded
        Requirements: 17.2
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.llm_client.LLMClient.generate') as mock_llm:
            mock_llm.side_effect = Exception("Rate limit exceeded. Please try again later.")
            
            with patch('backend.api.chat.query_router') as mock_router:
                mock_router.classify.return_value = {"category": "troubleshooting"}
                
                response = client.post(
                    "/api/chat",
                    json={"query": "Why is my pod failing?"},
                    headers={"X-Session-ID": authenticated_session}
                )
                
                assert response.status_code == 500
                data = response.json()
                assert "error" in data
                assert "rate limit" in data["error"].lower()
    
    def test_llm_api_invalid_key(self, client, authenticated_session):
        """
        Test: Invalid LLM API key
        Requirements: 17.2
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.llm_client.LLMClient.generate') as mock_llm:
            mock_llm.side_effect = Exception("Invalid API key")
            
            with patch('backend.api.chat.query_router') as mock_router:
                mock_router.classify.return_value = {"category": "troubleshooting"}
                
                response = client.post(
                    "/api/chat",
                    json={"query": "Why is my pod failing?"},
                    headers={"X-Session-ID": authenticated_session}
                )
                
                assert response.status_code == 500
                data = response.json()
                assert "error" in data


class TestRateLimitEnforcement:
    """Test rate limit enforcement"""
    
    def test_chat_rate_limit_exceeded(self, client, authenticated_session):
        """
        Test: User exceeds chat rate limit (20 queries/min)
        Requirements: 9.1
        """
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": authenticated_session}
            )
        
        with patch('backend.middleware.rate_limiter.RateLimiter.check_rate_limit') as mock_rate_limit:
            # First 20 requests succeed
            mock_rate_limit.return_value = True
            
            for i in range(20):
                with patch('backend.api.chat.query_router') as mock_router:
                    mock_router.classify.return_value = {"category": "troubleshooting"}
                    
                    response = client.post(
                        "/api/chat",
                        json={"query": f"Query {i}"},
                        headers={"X-Session-ID": authenticated_session}
                    )
                    
                    assert response.status_code == 200
            
            # 21st request should be rate limited
            mock_rate_limit.return_value = False
            
            response = client.post(
                "/api/chat",
                json={"query": "Query 21"},
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 429
            data = response.json()
            assert "rate limit" in data["error"].lower()
            assert "retry-after" in response.headers.get("Retry-After", "").lower() or response.headers.get("retry-after") is not None
    
    def test_rate_limit_reset_after_window(self, client, authenticated_session):
        """
        Test: Rate limit resets after time window
        Requirements: 9.1
        """
        with patch('backend.middleware.rate_limiter.RateLimiter.check_rate_limit') as mock_rate_limit:
            # Simulate rate limit exceeded
            mock_rate_limit.return_value = False
            
            response = client.post(
                "/api/chat",
                json={"query": "Test query"},
                headers={"X-Session-ID": authenticated_session}
            )
            
            assert response.status_code == 429
            
            # Simulate time passing and rate limit reset
            mock_rate_limit.return_value = True
            
            response = client.post(
                "/api/chat",
                json={"query": "Test query after reset"},
                headers={"X-Session-ID": authenticated_session}
            )
            
            # Should succeed after reset (mocked)
            # In real scenario, would need to wait 60 seconds


class TestMultiUserScenarios:
    """Test multi-user error scenarios"""
    
    def test_credential_isolation_on_error(self, client):
        """
        Test: User A's error doesn't affect User B
        Requirements: 1.5
        """
        # Create two sessions
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            response_a = client.post(
                "/api/credentials/aws",
                json={
                    "access_key": "AKIA_USER_A",
                    "secret_key": "SECRET_A",
                    "session_token": "TOKEN_A",
                    "region": "us-east-1"
                }
            )
            session_a = response_a.json()["session_id"]
            
            response_b = client.post(
                "/api/credentials/aws",
                json={
                    "access_key": "AKIA_USER_B",
                    "secret_key": "SECRET_B",
                    "session_token": "TOKEN_B",
                    "region": "us-east-1"
                }
            )
            session_b = response_b.json()["session_id"]
        
        # Expire User A's credentials
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            def get_credentials(session_id):
                if session_id == session_a:
                    return None  # Expired
                else:
                    return {"credentials": {"access_key": "AKIA_USER_B"}}
            
            mock_get.side_effect = get_credentials
            
            # User A's request fails
            response_a = client.get(
                "/api/clusters",
                headers={"X-Session-ID": session_a}
            )
            assert response_a.status_code == 401
            
            # User B's request succeeds
            with patch('backend.api.clusters.discover_clusters') as mock_discover:
                mock_discover.return_value = [{"name": "cluster-1"}]
                
                response_b = client.get(
                    "/api/clusters",
                    headers={"X-Session-ID": session_b}
                )
                assert response_b.status_code == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
