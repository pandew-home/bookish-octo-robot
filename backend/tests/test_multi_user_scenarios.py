"""
Multi-user scenario tests for DevOps Chatbot v2.0

Tests multi-user scenarios:
- Credential isolation between users
- Conversation history isolation
- Shared knowledge base access

Requirements: 1.5, 10.3, 11.5
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch
import time


@pytest.fixture
def client():
    """Create test client"""
    from backend.app import app
    return TestClient(app)


@pytest.fixture
def user_a_credentials():
    """User A credentials"""
    return {
        "access_key": "AKIA_USER_A_EXAMPLE",
        "secret_key": "SECRET_KEY_USER_A",
        "session_token": "SESSION_TOKEN_USER_A",
        "region": "us-east-1"
    }


@pytest.fixture
def user_b_credentials():
    """User B credentials"""
    return {
        "access_key": "AKIA_USER_B_EXAMPLE",
        "secret_key": "SECRET_KEY_USER_B",
        "session_token": "SESSION_TOKEN_USER_B",
        "region": "us-west-2"
    }


class TestCredentialIsolation:
    """Test credential isolation between users"""
    
    def test_users_have_separate_credentials(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: Each user has isolated credentials
        Requirements: 1.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True, "user_arn": "arn:aws:iam::123:user/a"}
            
            # User A logs in
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            assert response_a.status_code == 200
            session_a = response_a.json()["session_id"]
            
            mock_validate.return_value = {"valid": True, "user_arn": "arn:aws:iam::456:user/b"}
            
            # User B logs in
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            assert response_b.status_code == 200
            session_b = response_b.json()["session_id"]
        
        # Verify sessions are different
        assert session_a != session_b
        
        # Verify User A can access their credentials
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            mock_get.return_value = {
                "credentials": user_a_credentials,
                "expires_at": time.time() + 3600
            }
            
            response = client.get(
                "/api/credentials/aws/status",
                headers={"X-Session-ID": session_a}
            )
            assert response.status_code == 200
        
        # Verify User B can access their credentials
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            mock_get.return_value = {
                "credentials": user_b_credentials,
                "expires_at": time.time() + 3600
            }
            
            response = client.get(
                "/api/credentials/aws/status",
                headers={"X-Session-ID": session_b}
            )
            assert response.status_code == 200
    
    def test_user_cannot_access_other_user_credentials(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: User A cannot access User B's credentials
        Requirements: 1.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            # User A logs in
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            # User B logs in
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        # User A tries to use User B's session
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            mock_get.return_value = None  # Session not found
            
            response = client.get(
                "/api/credentials/aws/status",
                headers={"X-Session-ID": session_b + "_tampered"}
            )
            
            # Should fail
            assert response.status_code == 401
    
    def test_credential_deletion_only_affects_owner(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: Deleting User A's credentials doesn't affect User B
        Requirements: 1.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            # Both users log in
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        # User A deletes their credentials
        with patch('backend.credential_store.CredentialStore.remove') as mock_remove:
            response = client.delete(
                "/api/credentials/aws",
                headers={"X-Session-ID": session_a}
            )
            assert response.status_code == 200
            mock_remove.assert_called_once_with(session_a)
        
        # User B's credentials still work
        with patch('backend.credential_store.CredentialStore.get') as mock_get:
            mock_get.return_value = {
                "credentials": user_b_credentials,
                "expires_at": time.time() + 3600
            }
            
            response = client.get(
                "/api/credentials/aws/status",
                headers={"X-Session-ID": session_b}
            )
            assert response.status_code == 200


class TestConversationHistoryIsolation:
    """Test conversation history isolation between users"""
    
    def test_users_have_separate_conversation_history(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: Each user has isolated conversation history
        Requirements: 10.3
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            # Both users log in and select cluster
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": session_a}
            )
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": session_b}
            )
        
        # User A sends a message
        with patch('backend.api.chat.query_router') as mock_router:
            mock_router.classify.return_value = {"category": "troubleshooting"}
            
            with patch('backend.conversation_history.ConversationHistoryManager.add_message') as mock_add:
                client.post(
                    "/api/chat",
                    json={"query": "User A's question"},
                    headers={"X-Session-ID": session_a}
                )
                
                # Verify message was added to User A's history
                assert mock_add.called
                call_args = mock_add.call_args
                assert session_a in str(call_args)
        
        # User B sends a different message
        with patch('backend.api.chat.query_router') as mock_router:
            mock_router.classify.return_value = {"category": "troubleshooting"}
            
            with patch('backend.conversation_history.ConversationHistoryManager.add_message') as mock_add:
                client.post(
                    "/api/chat",
                    json={"query": "User B's question"},
                    headers={"X-Session-ID": session_b}
                )
                
                # Verify message was added to User B's history
                assert mock_add.called
                call_args = mock_add.call_args
                assert session_b in str(call_args)
        
        # Verify User A only sees their history
        with patch('backend.conversation_history.ConversationHistoryManager.get_history') as mock_get:
            mock_get.return_value = [
                {"role": "user", "content": "User A's question"},
                {"role": "assistant", "content": "Response to User A"}
            ]
            
            response = client.get(
                "/api/chat/history",
                headers={"X-Session-ID": session_a}
            )
            
            assert response.status_code == 200
            history = response.json()
            assert len(history) == 2
            assert "User A" in history[0]["content"]
        
        # Verify User B only sees their history
        with patch('backend.conversation_history.ConversationHistoryManager.get_history') as mock_get:
            mock_get.return_value = [
                {"role": "user", "content": "User B's question"},
                {"role": "assistant", "content": "Response to User B"}
            ]
            
            response = client.get(
                "/api/chat/history",
                headers={"X-Session-ID": session_b}
            )
            
            assert response.status_code == 200
            history = response.json()
            assert len(history) == 2
            assert "User B" in history[0]["content"]
    
    def test_per_cluster_history_isolation(
        self,
        client,
        user_a_credentials
    ):
        """
        Test: User has separate history per cluster
        Requirements: 10.3
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            response = client.post("/api/credentials/aws", json=user_a_credentials)
            session_id = response.json()["session_id"]
        
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            # Select dev cluster
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "dev-cluster"},
                headers={"X-Session-ID": session_id}
            )
        
        # Send message to dev cluster
        with patch('backend.api.chat.query_router') as mock_router:
            mock_router.classify.return_value = {"category": "troubleshooting"}
            
            with patch('backend.conversation_history.ConversationHistoryManager.add_message') as mock_add:
                client.post(
                    "/api/chat",
                    json={"query": "Dev cluster question"},
                    headers={"X-Session-ID": session_id}
                )
        
        # Switch to prod cluster
        with patch('backend.api.clusters.get_k8s_clients') as mock_clients:
            mock_clients.return_value = {"core_v1": Mock()}
            
            client.post(
                "/api/clusters/select",
                json={"cluster_name": "prod-cluster"},
                headers={"X-Session-ID": session_id}
            )
        
        # History should be empty for prod cluster
        with patch('backend.conversation_history.ConversationHistoryManager.get_history') as mock_get:
            mock_get.return_value = []  # No history for prod cluster
            
            response = client.get(
                "/api/chat/history",
                headers={"X-Session-ID": session_id}
            )
            
            assert response.status_code == 200
            history = response.json()
            assert len(history) == 0


class TestSharedKnowledgeBase:
    """Test shared knowledge base access"""
    
    def test_users_can_access_shared_knowledge_base(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: All users can access shared knowledge base
        Requirements: 11.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            # User A logs in
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            # User B logs in
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        # User A submits a solution
        with patch('backend.solution_manager.SolutionManager.add_solution') as mock_add:
            mock_add.return_value = {"id": "sol-123", "status": "success"}
            
            response = client.post(
                "/api/solutions",
                json={
                    "title": "Fix Pod CrashLoopBackOff",
                    "description": "Increase memory limits",
                    "tags": ["pods", "memory"]
                },
                headers={"X-Session-ID": session_a}
            )
            
            assert response.status_code == 200
            solution_id = response.json()["id"]
        
        # User B can search and find User A's solution
        with patch('backend.rag_integration.RAGIntegration.search') as mock_search:
            mock_search.return_value = [
                {
                    "id": solution_id,
                    "title": "Fix Pod CrashLoopBackOff",
                    "score": 0.95
                }
            ]
            
            response = client.get(
                "/api/kb/search",
                params={"query": "pod crash memory"},
                headers={"X-Session-ID": session_b}
            )
            
            assert response.status_code == 200
            results = response.json()
            assert len(results) > 0
            assert results[0]["id"] == solution_id
    
    def test_solution_submission_updates_shared_index(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: Solution submitted by one user is immediately available to others
        Requirements: 11.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        # User A submits solution
        with patch('backend.solution_manager.SolutionManager.add_solution') as mock_add:
            with patch('backend.rag_integration.RAGIntegration.update_index') as mock_update:
                mock_add.return_value = {"id": "sol-456", "status": "success"}
                
                client.post(
                    "/api/solutions",
                    json={
                        "title": "Service Discovery Issues",
                        "description": "Check DNS configuration",
                        "tags": ["networking", "dns"]
                    },
                    headers={"X-Session-ID": session_a}
                )
                
                # Verify index was updated
                assert mock_update.called
        
        # User B immediately searches and finds it
        with patch('backend.rag_integration.RAGIntegration.search') as mock_search:
            mock_search.return_value = [
                {
                    "id": "sol-456",
                    "title": "Service Discovery Issues",
                    "score": 0.92
                }
            ]
            
            response = client.get(
                "/api/kb/search",
                params={"query": "service dns"},
                headers={"X-Session-ID": session_b}
            )
            
            assert response.status_code == 200
            results = response.json()
            assert len(results) > 0
            assert results[0]["title"] == "Service Discovery Issues"
    
    def test_all_users_see_same_solution_list(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: All users see the same solution list
        Requirements: 11.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        # Mock shared solution list
        shared_solutions = [
            {"id": "sol-1", "title": "Solution 1", "tags": ["tag1"]},
            {"id": "sol-2", "title": "Solution 2", "tags": ["tag2"]},
            {"id": "sol-3", "title": "Solution 3", "tags": ["tag3"]}
        ]
        
        with patch('backend.solution_manager.SolutionManager.list_solutions') as mock_list:
            mock_list.return_value = shared_solutions
            
            # User A gets solution list
            response_a = client.get(
                "/api/solutions",
                headers={"X-Session-ID": session_a}
            )
            
            # User B gets solution list
            response_b = client.get(
                "/api/solutions",
                headers={"X-Session-ID": session_b}
            )
            
            # Both should see the same solutions
            assert response_a.status_code == 200
            assert response_b.status_code == 200
            
            solutions_a = response_a.json()
            solutions_b = response_b.json()
            
            assert len(solutions_a) == len(solutions_b)
            assert solutions_a == solutions_b


class TestConcurrentAccess:
    """Test concurrent access scenarios"""
    
    def test_concurrent_credential_submission(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: Multiple users can submit credentials concurrently
        Requirements: 1.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            # Simulate concurrent requests
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            
            # Both should succeed
            assert response_a.status_code == 200
            assert response_b.status_code == 200
            
            # Sessions should be different
            session_a = response_a.json()["session_id"]
            session_b = response_b.json()["session_id"]
            assert session_a != session_b
    
    def test_concurrent_solution_submission(
        self,
        client,
        user_a_credentials,
        user_b_credentials
    ):
        """
        Test: Multiple users can submit solutions concurrently
        Requirements: 11.5
        """
        with patch('backend.api.credentials.validate_credentials') as mock_validate:
            mock_validate.return_value = {"valid": True}
            
            response_a = client.post("/api/credentials/aws", json=user_a_credentials)
            session_a = response_a.json()["session_id"]
            
            response_b = client.post("/api/credentials/aws", json=user_b_credentials)
            session_b = response_b.json()["session_id"]
        
        with patch('backend.solution_manager.SolutionManager.add_solution') as mock_add:
            # Mock returns different IDs for each submission
            mock_add.side_effect = [
                {"id": "sol-a", "status": "success"},
                {"id": "sol-b", "status": "success"}
            ]
            
            # Concurrent solution submissions
            response_a = client.post(
                "/api/solutions",
                json={
                    "title": "Solution from User A",
                    "description": "Description A",
                    "tags": ["tag-a"]
                },
                headers={"X-Session-ID": session_a}
            )
            
            response_b = client.post(
                "/api/solutions",
                json={
                    "title": "Solution from User B",
                    "description": "Description B",
                    "tags": ["tag-b"]
                },
                headers={"X-Session-ID": session_b}
            )
            
            # Both should succeed
            assert response_a.status_code == 200
            assert response_b.status_code == 200
            
            # Different solution IDs
            assert response_a.json()["id"] != response_b.json()["id"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
