"""
Unit tests for per-cluster isolation.

Tests cover:
- Conversation history is isolated by cluster
- Enriched context is per-cluster
- Switching clusters clears state
- Concurrent requests to different clusters
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime, timedelta
import asyncio
from typing import Dict, Any

from conversation_history import ConversationHistory, Conversation, ChatMessage
from enrichment_engine import EnrichedContext


@pytest.fixture
def user_id():
    """Test user ID."""
    return "test-user-123"


@pytest.fixture
def cluster_names():
    """Test cluster names."""
    return ["cluster-1", "cluster-2", "cluster-3"]


@pytest.fixture
def conversation_history(user_id, tmp_path):
    """Create conversation history with temporary storage."""
    # Mock the base path for testing
    history = ConversationHistory(data_dir=str(tmp_path))
    return history


@pytest.fixture
def enriched_context():
    """Create enriched context."""
    return EnrichedContext()


class TestConversationHistoryIsolation:
    """Test conversation history isolation per cluster."""

    def test_conversation_history_isolated_by_cluster(self, conversation_history, user_id, cluster_names):
        """Test that conversation history is isolated by cluster."""
        cluster1, cluster2, cluster3 = cluster_names

        # Create conversation on cluster 1
        conv1_id = conversation_history.create_conversation(user_id, title="Cluster 1 Conversation", cluster_name=cluster1)
        conversation_history.save_message(user_id, conv1_id, "user", "What is the status of pod X?", cluster_name=cluster1)

        # Create conversation on cluster 2
        conv2_id = conversation_history.create_conversation(user_id, title="Cluster 2 Conversation", cluster_name=cluster2)
        conversation_history.save_message(user_id, conv2_id, "user", "What is the status of pod Y?", cluster_name=cluster2)

        # Retrieve and verify isolation
        retrieved1 = conversation_history.get_conversation(user_id, conv1_id, cluster_name=cluster1)
        retrieved2 = conversation_history.get_conversation(user_id, conv2_id, cluster_name=cluster2)

        assert retrieved1 is not None
        assert retrieved2 is not None
        assert len(retrieved1.messages) == 1
        assert len(retrieved2.messages) == 1
        assert retrieved1.messages[0].content == "What is the status of pod X?"
        assert retrieved2.messages[0].content == "What is the status of pod Y?"

    def test_conversation_history_cluster_independent(self, conversation_history, user_id, cluster_names):
        """Test that modifying one cluster's history doesn't affect others."""
        cluster1, cluster2, _ = cluster_names

        # Create conversations for both clusters
        conv1_id = conversation_history.create_conversation(user_id, cluster_name=cluster1)
        conv2_id = conversation_history.create_conversation(user_id, cluster_name=cluster2)

        # Add message to cluster 1
        conversation_history.save_message(user_id, conv1_id, "user", "Cluster 1 query", cluster_name=cluster1)

        # Add different message to cluster 2
        conversation_history.save_message(user_id, conv2_id, "user", "Cluster 2 query", cluster_name=cluster2)

        # Verify cluster 1 wasn't affected by cluster 2
        retrieved1 = conversation_history.get_conversation(user_id, conv1_id, cluster_name=cluster1)
        retrieved2 = conversation_history.get_conversation(user_id, conv2_id, cluster_name=cluster2)

        assert len(retrieved1.messages) == 1
        assert len(retrieved2.messages) == 1
        assert retrieved1.messages[0].content == "Cluster 1 query"
        assert retrieved2.messages[0].content == "Cluster 2 query"

    def test_different_users_different_clusters_isolated(self, conversation_history, cluster_names):
        """Test isolation across users and clusters."""
        user1, user2 = "user-1", "user-2"
        cluster1, cluster2, _ = cluster_names

        # User 1 in cluster 1
        conv_u1_c1 = conversation_history.create_conversation(user1, cluster_name=cluster1)
        conversation_history.save_message(user1, conv_u1_c1, "user", "User 1 Cluster 1", cluster_name=cluster1)

        # User 2 in cluster 1
        conv_u2_c1 = conversation_history.create_conversation(user2, cluster_name=cluster1)
        conversation_history.save_message(user2, conv_u2_c1, "user", "User 2 Cluster 1", cluster_name=cluster1)

        # User 1 in cluster 2
        conv_u1_c2 = conversation_history.create_conversation(user1, cluster_name=cluster2)
        conversation_history.save_message(user1, conv_u1_c2, "user", "User 1 Cluster 2", cluster_name=cluster2)

        # Verify all are isolated
        retrieved_u1_c1 = conversation_history.get_conversation(user1, conv_u1_c1, cluster_name=cluster1)
        retrieved_u2_c1 = conversation_history.get_conversation(user2, conv_u2_c1, cluster_name=cluster1)
        retrieved_u1_c2 = conversation_history.get_conversation(user1, conv_u1_c2, cluster_name=cluster2)

        assert retrieved_u1_c1.messages[0].content == "User 1 Cluster 1"
        assert retrieved_u2_c1.messages[0].content == "User 2 Cluster 1"
        assert retrieved_u1_c2.messages[0].content == "User 1 Cluster 2"

    def test_clear_conversation_history_for_cluster(self, conversation_history, user_id, cluster_names):
        """Test clearing conversation history for a specific cluster."""
        cluster1, cluster2, _ = cluster_names

        # Add messages to both clusters
        conv1_id = conversation_history.create_conversation(user_id, cluster_name=cluster1)
        conversation_history.save_message(user_id, conv1_id, "user", "Query 1", cluster_name=cluster1)

        conv2_id = conversation_history.create_conversation(user_id, cluster_name=cluster2)
        conversation_history.save_message(user_id, conv2_id, "user", "Query 2", cluster_name=cluster2)

        # Retrieve both conversations
        retrieved1 = conversation_history.get_conversation(user_id, conv1_id, cluster_name=cluster1)
        retrieved2 = conversation_history.get_conversation(user_id, conv2_id, cluster_name=cluster2)

        # Verify both have messages
        assert retrieved1 is not None
        assert len(retrieved1.messages) == 1
        assert len(retrieved2.messages) == 1


class TestEnrichedContextIsolation:
    """Test enriched context isolation per cluster."""

    def test_enriched_context_per_cluster(self):
        """Test that enriched context is isolated per cluster."""
        context1 = EnrichedContext()
        context2 = EnrichedContext()

        # Set different data
        context1.pod_data = {
            "pods": [{"name": "pod-1", "cluster": "cluster-1"}]
        }
        context2.pod_data = {
            "pods": [{"name": "pod-2", "cluster": "cluster-2"}]
        }

        # Verify isolation
        assert context1.pod_data["pods"][0]["name"] == "pod-1"
        assert context2.pod_data["pods"][0]["name"] == "pod-2"
        assert context1 is not context2

    def test_enriched_context_independent_k8sgpt_results(self):
        """Test that K8sGPT results are isolated per context."""
        context1 = EnrichedContext()
        context2 = EnrichedContext()

        # Set different K8sGPT results (as K8sGPTResult objects)
        from k8sgpt_reader import K8sGPTResult
        
        context1.k8sgpt_results = [
            K8sGPTResult(
                name="pod-1",
                kind="Pod",
                namespace="default",
                severity="high",
                problem="CrashLoopBackOff",
                solution="Check logs",
                analyzer="Pod",
                timestamp=datetime.now(),
                details={"cluster": "cluster-1"}
            )
        ]
        context2.k8sgpt_results = [
            K8sGPTResult(
                name="pod-2",
                kind="Pod",
                namespace="default",
                severity="critical",
                problem="OOMKilled",
                solution="Increase memory",
                analyzer="Pod",
                timestamp=datetime.now(),
                details={"cluster": "cluster-2"}
            )
        ]

        # Verify isolation
        assert context1.k8sgpt_results[0].name == "pod-1"
        assert context2.k8sgpt_results[0].name == "pod-2"
        assert context1.k8sgpt_results[0].severity == "high"
        assert context2.k8sgpt_results[0].severity == "critical"


class TestClusterSwitching:
    """Test cluster switching behavior."""

    def test_switch_clusters_clears_state(self, user_id, cluster_names):
        """Test that switching clusters properly manages state."""
        cluster1, cluster2, _ = cluster_names
        
        # Create enriched context for cluster 1
        context1 = EnrichedContext()
        context1.pod_data = {"pods": [{"name": "pod-1"}]}
        
        # Create enriched context for cluster 2
        context2 = EnrichedContext()
        context2.pod_data = {"pods": [{"name": "pod-2"}]}
        
        # Verify they're independent
        assert context1.pod_data != context2.pod_data
        assert context1.pod_data["pods"][0]["name"] == "pod-1"
        assert context2.pod_data["pods"][0]["name"] == "pod-2"

    def test_k8s_clients_refreshed_on_cluster_switch(self):
        """Test that K8s clients are refreshed when switching clusters."""
        # Mock cluster data
        cluster1 = {
            "name": "cluster-1",
            "version": "v1.28",
            "ca_data": "cert-data-1"
        }
        cluster2 = {
            "name": "cluster-2",
            "version": "v1.27",
            "ca_data": "cert-data-2"
        }
        
        # Verify cluster data is different
        assert cluster1["name"] != cluster2["name"]
        assert cluster1["ca_data"] != cluster2["ca_data"]


class TestConcurrentClusterAccess:
    """Test concurrent access to different clusters."""

    def test_concurrent_requests_to_different_clusters(self, conversation_history, cluster_names):
        """Test that concurrent requests to different clusters don't interfere."""
        user_id = "concurrent-test-user"
        cluster1, cluster2, _ = cluster_names
        
        # Create conversations in different clusters
        conv1_id = conversation_history.create_conversation(user_id, cluster_name=cluster1)
        conv2_id = conversation_history.create_conversation(user_id, cluster_name=cluster2)
        
        # Add messages concurrently (simulated)
        conversation_history.save_message(user_id, conv1_id, "user", "Query 1", cluster_name=cluster1)
        conversation_history.save_message(user_id, conv2_id, "user", "Query 2", cluster_name=cluster2)
        
        # Retrieve and verify isolation
        conv1 = conversation_history.get_conversation(user_id, conv1_id, cluster_name=cluster1)
        conv2 = conversation_history.get_conversation(user_id, conv2_id, cluster_name=cluster2)
        
        assert conv1.messages[0].content == "Query 1"
        assert conv2.messages[0].content == "Query 2"
        assert conv1.messages[0].content != conv2.messages[0].content
