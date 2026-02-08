"""
End-to-end integration tests for DevOps Chatbot v2.0

Tests complete flows:
- Authentication flow (Kion creds → cluster discovery → selection)
- Chat flow (query → enrichment → RAG → LLM → response)
- Weather monitoring flow (polling → CRD reading → calculation → display)
- Solution submission flow (chat → save to KB → retrieval)
- Cluster switching flow (select new cluster → token regeneration → history switch)

Requirements: 1.1, 1.2, 2.1, 2.3, 3.1, 3.2, 7.1, 11.2, 13.1, 13.3
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import json
from datetime import datetime, timedelta


@pytest.fixture
def client():
    """Create test client"""
    from backend.app import app
    return TestClient(app)


@pytest.fixture
def mock_aws_credentials():
    """Mock AWS credentials"""
    return {
        "access_key": "AKIAIOSFODNN7EXAMPLE",
        "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "session_token": "FwoGZXIvYXdzEBQaDH...",
        "region": "us-east-1"
    }


@pytest.fixture
def mock_cluster_list():
    """Mock cluster list"""
    return [
        {
            "name": "dev-cluster",
            "endpoint": "https://ABC123.gr7.us-east-1.eks.amazonaws.com",
            "version": "1.28",
            "status": "ACTIVE",
            "region": "us-east-1",
            "ca_data": "LS0tLS1CRUdJTi..."
        },
        {
            "name": "prod-cluster",
            "endpoint": "https://XYZ789.gr7.us-east-1.eks.amazonaws.com",
            "version": "1.28",
            "status": "ACTIVE",
            "region": "us-east-1",
            "ca_data": "LS0tLS1CRUdJTi..."
        }
    ]


class TestAuthenticationFlow:
    """Test complete authentication flow"""
    
    @patch('backend.api.credentials.validate_credentials')
    def test_complete_auth_flow(self, mock_validate, client, mock_aws_credentials):
        """
        Test: Login → Cluster Discovery → Selection
        Requirements: 1.1, 1.2, 2.1, 2.3
        """
        # Mock credential validation
        mock_validate.return_value = {
            "valid": True,
            "user_arn": "arn:aws:iam::123456789012:user/test-user",
            "account_id": "123456789012"
        }
        
        # Step 1: Submit credentials
        response = client.post("/api/credentials/aws", json=mock_aws_credentials)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "session_id" in data
        
        session_id = data["session_id"]
        
        # Step 2: Check credential status
        response = client.get(
            "/api/credentials/aws/status",
            headers={"X-Session-ID": session_id}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "active"
        assert data["ttl_remaining"] > 0
        
        # Step 3: Discover clusters (mocked)
        with patch('backend.api.clusters.discover_clusters') as mock_discover:
            mock_discover.return_value = [
                {"name": "dev-cluster", "region": "us-east-1"},
                {"name": "prod-cluster", "region": "us-east-1"}
            ]
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": session_id}
            )
            assert response.status_code == 200
            clusters = response.json()
            assert len(clusters) >= 1
            assert "name" in clusters[0]
        
        # Step 4: Select cluster (mocked)
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {
                "core_v1": Mock(),
                "apps_v1": Mock()
            }
            
            response = client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": session_id}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["cluster_name"] == "dev-cluster"


class TestChatFlow:
    """Test complete chat flow"""
    
    @patch('backend.api.chat.query_router')
    @patch('backend.api.chat.enrichment_engine')
    @patch('backend.api.chat.rag_integration')
    @patch('backend.api.chat.llm_client')
    def test_complete_chat_flow(
        self,
        mock_llm,
        mock_rag,
        mock_enrichment,
        mock_router,
        client,
        mock_aws_credentials
    ):
        """
        Test: Query → Enrichment → RAG → LLM → Response
        Requirements: 7.1, 11.2
        """
        # Setup mocks
        mock_router.classify.return_value = {
            "category": "troubleshooting",
            "confidence": 0.95
        }
        
        mock_enrichment.execute.return_value = {
            "pods": [{"name": "test-pod", "status": "Running"}],
            "events": []
        }
        
        mock_rag.search.return_value = [
            {
                "title": "Pod Troubleshooting Guide",
                "content": "Check pod logs...",
                "score": 0.85
            }
        ]
        
        mock_llm.generate.return_value = {
            "response": "The pod is running normally. Check logs for details.",
            "citations": ["Pod Troubleshooting Guide"]
        }
        
        # Setup session with credentials
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "user_arn": "arn:aws:iam::123456789012:user/test-user"
            }
            
            response = client.post("/api/credentials/aws", json=mock_aws_credentials)
            session_id = response.json()["session_id"]
        
        # Select cluster
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": session_id}
            )
        
        # Send chat query
        response = client.post(
            "/api/chat",
            json={"query": "Why is my pod failing?"},
            headers={"X-Session-ID": session_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "response" in data
        assert "citations" in data
        
        # Verify mocks were called
        mock_router.classify.assert_called_once()
        mock_enrichment.execute.assert_called_once()
        mock_rag.search.assert_called_once()
        mock_llm.generate.assert_called_once()


class TestWeatherMonitoring:
    """Test weather monitoring flow"""
    
    @patch('backend.api.weather.read_k8sgpt_results')
    @patch('backend.api.weather.calculate_weather_state')
    def test_weather_monitoring_flow(
        self,
        mock_calculate,
        mock_read_results,
        client,
        mock_aws_credentials
    ):
        """
        Test: Polling → CRD Reading → Calculation → Display
        Requirements: 3.1, 3.2
        """
        # Mock K8sGPT results
        mock_read_results.return_value = [
            {
                "name": "pod-issue-1",
                "severity": "warning",
                "problem": "Pod has high memory usage",
                "solution": "Increase memory limits"
            },
            {
                "name": "deployment-issue-1",
                "severity": "error",
                "problem": "Deployment has 0 ready replicas",
                "solution": "Check pod logs"
            }
        ]
        
        # Mock weather calculation
        mock_calculate.return_value = {
            "state": "rainy",
            "severity_counts": {"error": 1, "warning": 1},
            "top_issues": mock_read_results.return_value[:5]
        }
        
        # Setup session
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            response = client.post("/api/credentials/aws", json=mock_aws_credentials)
            session_id = response.json()["session_id"]
        
        # Select cluster
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": session_id}
            )
        
        # Get weather
        response = client.get(
            "/api/weather",
            headers={"X-Session-ID": session_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "rainy"
        assert "severity_counts" in data
        assert "top_issues" in data
        assert len(data["top_issues"]) <= 5


class TestSolutionSubmission:
    """Test solution submission and retrieval flow"""
    
    @patch('backend.api.solutions.solution_manager')
    @patch('backend.api.solutions.rag_integration')
    def test_solution_submission_flow(
        self,
        mock_rag,
        mock_solution_manager,
        client,
        mock_aws_credentials
    ):
        """
        Test: Chat → Save to KB → Retrieval
        Requirements: 11.2
        """
        # Setup session
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            response = client.post("/api/credentials/aws", json=mock_aws_credentials)
            session_id = response.json()["session_id"]
        
        # Submit solution
        solution_data = {
            "title": "Fix Pod CrashLoopBackOff",
            "description": "Increase memory limits to resolve OOMKilled errors",
            "tags": ["pods", "memory", "troubleshooting"],
            "conversation_id": "conv-123"
        }
        
        mock_solution_manager.add_solution.return_value = {
            "id": "sol-123",
            "status": "success"
        }
        
        response = client.post(
            "/api/solutions",
            json=solution_data,
            headers={"X-Session-ID": session_id}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "id" in data
        
        # Search for solution
        mock_rag.search.return_value = [
            {
                "id": "sol-123",
                "title": "Fix Pod CrashLoopBackOff",
                "score": 0.95
            }
        ]
        
        response = client.get(
            "/api/kb/search",
            params={"query": "pod memory crash"},
            headers={"X-Session-ID": session_id}
        )
        
        assert response.status_code == 200
        results = response.json()
        assert len(results) > 0
        assert results[0]["title"] == "Fix Pod CrashLoopBackOff"


class TestClusterSwitching:
    """Test cluster switching flow"""
    
    @patch('backend.api.clusters.get_k8s_clients')
    @patch('backend.api.clusters.conversation_history')
    def test_cluster_switching_flow(
        self,
        mock_history,
        mock_clients,
        client,
        mock_aws_credentials,
        mock_cluster_list
    ):
        """
        Test: Select New Cluster → Token Regeneration → History Switch
        Requirements: 13.1, 13.3
        """
        # Setup session
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            response = client.post("/api/credentials/aws", json=mock_aws_credentials)
            session_id = response.json()["session_id"]
        
        # Select first cluster
        mock_clients.return_value = {"core_v1": Mock()}
        
        response = client.post(
            "/api/clusters/select",
            json={"cluster_name": "dev-cluster"},
            headers={"X-Session-ID": session_id}
        )
        assert response.status_code == 200
        
        # Send a message to create history
        with patch('backend.api.chat.query_router') as mock_router:
            mock_router.classify.return_value = {"category": "troubleshooting"}
            
            client.post(
                "/api/chat",
                json={"query": "Test query for dev"},
                headers={"X-Session-ID": session_id}
            )
        
        # Switch to second cluster
        response = client.post(
            "/api/clusters/select",
            json={"cluster_name": "prod-cluster"},
            headers={"X-Session-ID": session_id}
        )
        assert response.status_code == 200
        
        # Verify new token was generated (mock was called again)
        assert mock_clients.call_count >= 2
        
        # Verify history switched
        mock_history.switch_cluster.assert_called_with(
            session_id=session_id,
            cluster_name="prod-cluster"
        )
        
        # Get history for new cluster (should be empty)
        mock_history.get_history.return_value = []
        
        response = client.get(
            "/api/chat/history",
            headers={"X-Session-ID": session_id}
        )
        assert response.status_code == 200
        history = response.json()
        assert len(history) == 0  # New cluster has no history


class TestErrorHandling:
    """Test error handling in integration flows"""
    
    def test_invalid_credentials(self, client):
        """Test handling of invalid credentials"""
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": False, "error": "Invalid credentials"}
            
            response = client.post(
                "/api/credentials/aws",
                json={
                    "access_key": "INVALID",
                    "secret_key": "INVALID",
                    "session_token": "INVALID",
                    "region": "us-east-1"
                }
            )
            
            assert response.status_code == 401
            data = response.json()
            assert "error" in data
    
    def test_cluster_discovery_failure(self, client, mock_aws_credentials):
        """Test handling of cluster discovery failures"""
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            response = client.post("/api/credentials/aws", json=mock_aws_credentials)
            session_id = response.json()["session_id"]
        
        with patch('backend.api.clusters.discover_clusters') as mock_discover:
            mock_discover.side_effect = Exception("EKS API error")
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": session_id}
            )
            
            assert response.status_code == 500
            data = response.json()
            assert "error" in data
    
    def test_expired_credentials(self, client, mock_aws_credentials):
        """Test handling of expired credentials"""
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            response = client.post("/api/credentials/aws", json=mock_aws_credentials)
            session_id = response.json()["session_id"]
        
        # Simulate credential expiration
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            mock_get.return_value = None
            
            response = client.get(
                "/api/clusters",
                headers={"X-Session-ID": session_id}
            )
            
            assert response.status_code == 401
            data = response.json()
            assert "expired" in data.get("error", "").lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
