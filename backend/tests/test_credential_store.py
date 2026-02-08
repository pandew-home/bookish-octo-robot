"""
Unit tests for CredentialStore.
"""
import pytest
from datetime import datetime, timedelta
from credential_store import CredentialStore, StoredCredentials
import time
import threading


@pytest.fixture
def credential_store():
    """Create a credential store for testing."""
    return CredentialStore(max_capacity=10, ttl_seconds=2)


@pytest.fixture
def sample_credentials():
    """Create sample credentials for testing."""
    now = datetime.now()
    return StoredCredentials(
        access_key="AKIAIOSFODNN7EXAMPLE",
        secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        session_token="FwoGZXIvYXdzEBQaDH...",
        region="us-east-1",
        user_arn="arn:aws:iam::123456789012:user/test-user",
        account_id="123456789012",
        expires_at=now + timedelta(hours=1),
        created_at=now
    )


class TestCredentialStore:
    """Test cases for CredentialStore."""
    
    def test_store_and_retrieve(self, credential_store, sample_credentials):
        """Test storing and retrieving credentials."""
        session_id = "test-session-123"
        
        # Store credentials
        credential_store.store(session_id, sample_credentials)
        
        # Retrieve credentials
        retrieved = credential_store.get(session_id)
        
        assert retrieved is not None
        assert retrieved.access_key == sample_credentials.access_key
        assert retrieved.user_arn == sample_credentials.user_arn
        assert retrieved.account_id == sample_credentials.account_id
    
    def test_get_nonexistent_session(self, credential_store):
        """Test retrieving credentials for non-existent session."""
        result = credential_store.get("nonexistent-session")
        assert result is None
    
    def test_credential_expiration(self, credential_store, sample_credentials):
        """Test that expired credentials are not returned."""
        session_id = "expiring-session"
        
        # Set credentials to expire in 1 second
        sample_credentials.expires_at = datetime.now() + timedelta(seconds=1)
        credential_store.store(session_id, sample_credentials)
        
        # Should be retrievable immediately
        assert credential_store.get(session_id) is not None
        
        # Wait for expiration
        time.sleep(1.5)
        
        # Should return None after expiration
        assert credential_store.get(session_id) is None
    
    def test_remove_credentials(self, credential_store, sample_credentials):
        """Test removing credentials."""
        session_id = "remove-test"
        
        credential_store.store(session_id, sample_credentials)
        assert credential_store.get(session_id) is not None
        
        # Remove credentials
        result = credential_store.remove(session_id)
        assert result is True
        
        # Should not be retrievable
        assert credential_store.get(session_id) is None
        
        # Removing again should return False
        result = credential_store.remove(session_id)
        assert result is False
    
    def test_cleanup_expired(self, credential_store):
        """Test cleanup of expired credentials."""
        # Create credentials with different expiration times
        now = datetime.now()
        
        for i in range(3):
            creds = StoredCredentials(
                access_key=f"KEY{i}",
                secret_key="secret",
                session_token="token",
                region="us-east-1",
                user_arn=f"arn:aws:iam::123456789012:user/user{i}",
                account_id="123456789012",
                expires_at=now - timedelta(seconds=1),  # Already expired
                created_at=now
            )
            credential_store.store(f"session-{i}", creds)
        
        # Add one non-expired credential
        valid_creds = StoredCredentials(
            access_key="VALID_KEY",
            secret_key="secret",
            session_token="token",
            region="us-east-1",
            user_arn="arn:aws:iam::123456789012:user/valid",
            account_id="123456789012",
            expires_at=now + timedelta(hours=1),
            created_at=now
        )
        credential_store.store("valid-session", valid_creds)
        
        # Cleanup expired
        removed_count = credential_store.cleanup_expired()
        
        assert removed_count == 3
        assert credential_store.get("valid-session") is not None
    
    def test_capacity_limit_eviction(self, credential_store, sample_credentials):
        """Test that oldest expired credentials are evicted when at capacity."""
        # Fill the store to capacity
        for i in range(10):
            creds = StoredCredentials(
                access_key=f"KEY{i}",
                secret_key="secret",
                session_token="token",
                region="us-east-1",
                user_arn=f"arn:aws:iam::123456789012:user/user{i}",
                account_id="123456789012",
                expires_at=datetime.now() + timedelta(hours=1),
                created_at=datetime.now()
            )
            credential_store.store(f"session-{i}", creds)
        
        # Try to add one more (should trigger eviction)
        credential_store.store("session-11", sample_credentials)
        
        # Should have 10 credentials (one was evicted)
        stats = credential_store.get_stats()
        assert stats['total'] == 10
    
    def test_thread_safety(self, credential_store, sample_credentials):
        """Test thread-safe operations."""
        results = []
        
        def store_and_retrieve(session_id):
            credential_store.store(session_id, sample_credentials)
            retrieved = credential_store.get(session_id)
            results.append(retrieved is not None)
        
        # Create multiple threads
        threads = []
        for i in range(10):
            thread = threading.Thread(target=store_and_retrieve, args=(f"thread-{i}",))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        # All operations should succeed
        assert all(results)
        assert len(results) == 10
    
    def test_get_stats(self, credential_store):
        """Test getting store statistics."""
        now = datetime.now()
        
        # Add active credentials
        for i in range(3):
            creds = StoredCredentials(
                access_key=f"KEY{i}",
                secret_key="secret",
                session_token="token",
                region="us-east-1",
                user_arn=f"arn:aws:iam::123456789012:user/user{i}",
                account_id="123456789012",
                expires_at=now + timedelta(hours=1),
                created_at=now
            )
            credential_store.store(f"active-{i}", creds)
        
        # Add expired credentials
        for i in range(2):
            creds = StoredCredentials(
                access_key=f"EXPIRED{i}",
                secret_key="secret",
                session_token="token",
                region="us-east-1",
                user_arn=f"arn:aws:iam::123456789012:user/expired{i}",
                account_id="123456789012",
                expires_at=now - timedelta(seconds=1),
                created_at=now
            )
            credential_store.store(f"expired-{i}", creds)
        
        stats = credential_store.get_stats()
        
        assert stats['total'] == 5
        assert stats['expired'] == 2
        assert stats['active'] == 3
        assert stats['capacity'] == 10
    
    def test_credential_isolation(self, credential_store):
        """Test that credentials for different sessions are isolated."""
        now = datetime.now()
        
        creds1 = StoredCredentials(
            access_key="KEY1",
            secret_key="secret1",
            session_token="token1",
            region="us-east-1",
            user_arn="arn:aws:iam::123456789012:user/user1",
            account_id="123456789012",
            expires_at=now + timedelta(hours=1),
            created_at=now
        )
        
        creds2 = StoredCredentials(
            access_key="KEY2",
            secret_key="secret2",
            session_token="token2",
            region="us-west-2",
            user_arn="arn:aws:iam::987654321098:user/user2",
            account_id="987654321098",
            expires_at=now + timedelta(hours=1),
            created_at=now
        )
        
        credential_store.store("session-1", creds1)
        credential_store.store("session-2", creds2)
        
        # Retrieve and verify isolation
        retrieved1 = credential_store.get("session-1")
        retrieved2 = credential_store.get("session-2")
        
        assert retrieved1.access_key == "KEY1"
        assert retrieved2.access_key == "KEY2"
        assert retrieved1.region == "us-east-1"
        assert retrieved2.region == "us-west-2"
        assert retrieved1.account_id != retrieved2.account_id
