"""
Unit tests for conversation history per-cluster isolation.
"""
import pytest
import tempfile
import shutil
from pathlib import Path

from conversation_history import ConversationHistory, Conversation


@pytest.fixture
def temp_dir():
    """Create temporary directory for testing."""
    temp_path = tempfile.mkdtemp()
    yield temp_path
    shutil.rmtree(temp_path)


@pytest.fixture
def conv_history(temp_dir):
    """Create ConversationHistory instance with temp directory."""
    return ConversationHistory(data_dir=temp_dir)


class TestPerClusterIsolation:
    """Test per-cluster conversation history isolation."""
    
    def test_conversations_isolated_by_cluster(self, conv_history):
        """Test that conversations are isolated per cluster."""
        user_id = "user-123"
        cluster1 = "dev-cluster"
        cluster2 = "prod-cluster"
        
        # Create conversation on cluster1
        conv_id1 = conv_history.create_conversation(user_id, "Dev Issue", cluster1)
        conv_history.save_message(user_id, conv_id1, "user", "Dev question", cluster1)
        conv_history.save_message(user_id, conv_id1, "assistant", "Dev answer", cluster1)
        
        # Create conversation on cluster2
        conv_id2 = conv_history.create_conversation(user_id, "Prod Issue", cluster2)
        conv_history.save_message(user_id, conv_id2, "user", "Prod question", cluster2)
        conv_history.save_message(user_id, conv_id2, "assistant", "Prod answer", cluster2)
        
        # Get conversations for cluster1
        cluster1_convs = conv_history.get_user_conversations(user_id, cluster1)
        assert len(cluster1_convs) == 1
        assert cluster1_convs[0].id == conv_id1
        assert cluster1_convs[0].messages[0].content == "Dev question"
        
        # Get conversations for cluster2
        cluster2_convs = conv_history.get_user_conversations(user_id, cluster2)
        assert len(cluster2_convs) == 1
        assert cluster2_convs[0].id == conv_id2
        assert cluster2_convs[0].messages[0].content == "Prod question"
        
        # Verify they are different
        assert cluster1_convs[0].id != cluster2_convs[0].id
    
    def test_switching_clusters_switches_history(self, conv_history):
        """Test that switching clusters switches conversation history."""
        user_id = "user-456"
        cluster1 = "staging-cluster"
        cluster2 = "production-cluster"
        
        # Add messages to cluster1
        conv_id1 = conv_history.create_conversation(user_id, "Staging", cluster1)
        conv_history.save_message(user_id, conv_id1, "user", "Staging msg 1", cluster1)
        conv_history.save_message(user_id, conv_id1, "assistant", "Staging response 1", cluster1)
        
        # Add messages to cluster2
        conv_id2 = conv_history.create_conversation(user_id, "Production", cluster2)
        conv_history.save_message(user_id, conv_id2, "user", "Prod msg 1", cluster2)
        conv_history.save_message(user_id, conv_id2, "assistant", "Prod response 1", cluster2)
        
        # Switch to cluster1 - should only see cluster1 history
        cluster1_history = conv_history.get_user_conversations(user_id, cluster1)
        assert len(cluster1_history) == 1
        assert "Staging" in cluster1_history[0].title
        
        # Switch to cluster2 - should only see cluster2 history
        cluster2_history = conv_history.get_user_conversations(user_id, cluster2)
        assert len(cluster2_history) == 1
        assert "Production" in cluster2_history[0].title
    
    def test_conversation_limit_per_cluster(self, conv_history):
        """Test that conversation limit is enforced per cluster."""
        user_id = "user-789"
        cluster = "test-cluster"
        
        # Create 12 conversations (exceeds limit of 10)
        conv_ids = []
        for i in range(12):
            conv_id = conv_history.create_conversation(user_id, f"Conv {i}", cluster)
            conv_history.save_message(user_id, conv_id, "user", f"Message {i}", cluster)
            conv_ids.append(conv_id)
        
        # Should only have 10 most recent conversations
        conversations = conv_history.get_user_conversations(user_id, cluster)
        assert len(conversations) == 10
        
        # Oldest 2 should be deleted
        remaining_ids = [conv.id for conv in conversations]
        assert conv_ids[0] not in remaining_ids  # Oldest
        assert conv_ids[1] not in remaining_ids  # Second oldest
        assert conv_ids[-1] in remaining_ids  # Most recent
    
    def test_get_conversation_with_cluster_name(self, conv_history):
        """Test getting a specific conversation with cluster name."""
        user_id = "user-abc"
        cluster = "my-cluster"
        
        # Create conversation
        conv_id = conv_history.create_conversation(user_id, "Test", cluster)
        conv_history.save_message(user_id, conv_id, "user", "Hello", cluster)
        
        # Get conversation with cluster name
        conversation = conv_history.get_conversation(user_id, conv_id, cluster)
        assert conversation is not None
        assert conversation.id == conv_id
        assert len(conversation.messages) == 1
        
        # Try to get from different cluster - should not find it
        conversation_wrong_cluster = conv_history.get_conversation(user_id, conv_id, "other-cluster")
        assert conversation_wrong_cluster is None
    
    def test_backward_compatibility_no_cluster(self, conv_history):
        """Test backward compatibility when no cluster name is provided."""
        user_id = "user-legacy"
        
        # Create conversation without cluster name (legacy behavior)
        conv_id = conv_history.create_conversation(user_id, "Legacy")
        conv_history.save_message(user_id, conv_id, "user", "Legacy message")
        
        # Should be retrievable without cluster name
        conversation = conv_history.get_conversation(user_id, conv_id)
        assert conversation is not None
        assert conversation.id == conv_id
        
        # Should also appear in user conversations without cluster filter
        conversations = conv_history.get_user_conversations(user_id)
        assert len(conversations) == 1
        assert conversations[0].id == conv_id
    
    def test_directory_structure_per_cluster(self, conv_history, temp_dir):
        """Test that conversations are stored in cluster-specific directories."""
        user_id = "user-xyz"
        cluster1 = "cluster-a"
        cluster2 = "cluster-b"
        
        # Create conversations on different clusters
        conv_id1 = conv_history.create_conversation(user_id, "Cluster A", cluster1)
        conv_id2 = conv_history.create_conversation(user_id, "Cluster B", cluster2)
        
        # Verify directory structure
        temp_path = Path(temp_dir)
        
        # Cluster 1 directory should exist
        cluster1_dir = temp_path / user_id / cluster1
        assert cluster1_dir.exists()
        assert (cluster1_dir / f"{conv_id1}.json").exists()
        
        # Cluster 2 directory should exist
        cluster2_dir = temp_path / user_id / cluster2
        assert cluster2_dir.exists()
        assert (cluster2_dir / f"{conv_id2}.json").exists()
        
        # Conversations should not be in each other's directories
        assert not (cluster1_dir / f"{conv_id2}.json").exists()
        assert not (cluster2_dir / f"{conv_id1}.json").exists()
