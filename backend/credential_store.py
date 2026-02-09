"""
Credential Store for managing per-user AWS credentials with TTL-based expiration.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, Dict
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class StoredCredentials:
    """AWS credentials with metadata."""
    access_key: str
    secret_key: str
    session_token: str
    region: str
    user_arn: str
    account_id: str
    expires_at: datetime
    created_at: datetime

    def is_expiring_soon(self, threshold_seconds: int = 600) -> bool:
        """Check if credentials expire within the given threshold."""
        return (self.expires_at - datetime.now()).total_seconds() <= threshold_seconds


class CredentialStore:
    """
    Thread-safe in-memory storage for per-user AWS credentials with TTL-based expiration.
    
    Features:
    - Thread-safe operations using threading.Lock
    - Automatic cleanup of expired credentials
    - Eviction of oldest expired credentials when at capacity
    - TTL of 3600 seconds (1 hour) for all credentials
    """
    
    def __init__(self, max_capacity: int = 1000, ttl_seconds: int = 3600):
        """
        Initialize the credential store.
        
        Args:
            max_capacity: Maximum number of credential entries to store
            ttl_seconds: Time-to-live for credentials in seconds (default: 3600)
        """
        self._store: Dict[str, StoredCredentials] = {}
        self._lock = threading.Lock()
        self._max_capacity = max_capacity
        self._ttl_seconds = ttl_seconds
        logger.info(f"CredentialStore initialized with capacity={max_capacity}, ttl={ttl_seconds}s")
    
    def store(self, session_id: str, creds: StoredCredentials) -> None:
        """
        Store credentials for a session with TTL.
        
        Args:
            session_id: Unique session identifier
            creds: Credentials to store
        """
        with self._lock:
            # Check capacity and evict if needed
            if len(self._store) >= self._max_capacity and session_id not in self._store:
                self._evict_oldest_expired()
            
            # Set expiration time if not already set (allow storing expired creds for testing)
            if creds.expires_at is None:
                creds.expires_at = datetime.now() + timedelta(seconds=self._ttl_seconds)
            
            self._store[session_id] = creds
            logger.info(f"Stored credentials for session {session_id[:8]}... (expires at {creds.expires_at})")
    
    def get(self, session_id: str) -> Optional[StoredCredentials]:
        """
        Retrieve credentials for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            StoredCredentials if found and not expired, None otherwise
        """
        with self._lock:
            creds = self._store.get(session_id)
            
            if creds is None:
                logger.debug(f"No credentials found for session {session_id[:8]}...")
                return None
            
            # Check if expired
            if creds.expires_at <= datetime.now():
                logger.info(f"Credentials expired for session {session_id[:8]}...")
                del self._store[session_id]
                return None
            
            logger.debug(f"Retrieved credentials for session {session_id[:8]}...")
            return creds
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired credentials from the store.
        
        Returns:
            Number of credentials removed
        """
        with self._lock:
            now = datetime.now()
            expired_sessions = [
                session_id for session_id, creds in self._store.items()
                if creds.expires_at <= now
            ]
            
            for session_id in expired_sessions:
                del self._store[session_id]
            
            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired credential(s)")
            
            return len(expired_sessions)
    
    def remove(self, session_id: str) -> bool:
        """
        Remove credentials for a session.
        
        Args:
            session_id: Unique session identifier
            
        Returns:
            True if credentials were removed, False if not found
        """
        with self._lock:
            if session_id in self._store:
                del self._store[session_id]
                logger.info(f"Removed credentials for session {session_id[:8]}...")
                return True
            return False
    
    def _evict_oldest_expired(self) -> None:
        """
        Evict the oldest expired credentials. If no expired credentials exist,
        evict the oldest credential regardless of expiration.
        
        This is called when the store is at capacity.
        """
        now = datetime.now()
        
        # First try to find expired credentials
        expired = [
            (session_id, creds) for session_id, creds in self._store.items()
            if creds.expires_at <= now
        ]
        
        if expired:
            # Sort by expiration time and remove the oldest
            expired.sort(key=lambda x: x[1].expires_at)
            oldest_session_id = expired[0][0]
            del self._store[oldest_session_id]
            logger.info(f"Evicted expired credentials for session {oldest_session_id[:8]}...")
        else:
            # No expired credentials, evict the oldest by creation time
            if self._store:
                oldest_session_id = min(
                    self._store.items(),
                    key=lambda x: x[1].created_at
                )[0]
                del self._store[oldest_session_id]
                logger.warning(f"Evicted oldest credentials for session {oldest_session_id[:8]}... (capacity limit reached)")
    
    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about the credential store.
        
        Returns:
            Dictionary with stats (total, expired, active)
        """
        with self._lock:
            now = datetime.now()
            total = len(self._store)
            expired = sum(1 for creds in self._store.values() if creds.expires_at <= now)
            active = total - expired
            
            return {
                "total": total,
                "expired": expired,
                "active": active,
                "capacity": self._max_capacity
            }
