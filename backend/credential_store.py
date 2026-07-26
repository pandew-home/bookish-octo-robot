"""
Credential Store for managing per-user AWS credentials with TTL-based expiration.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional
import logging
import threading

logger = logging.getLogger(__name__)


def scrub_credentials(creds: "StoredCredentials") -> None:
    """Overwrite secret material in-place so residual references cannot leak."""
    creds.access_key = None
    creds.secret_key = None
    creds.session_token = None
    creds.kubeconfig_path = None
    creds.kubeconfig_content = None
    creds.kubeconfig_contexts = None
    creds.selected_context = None
    # Keep non-secret metadata cleared for a full empty session record.
    creds.user_arn = None
    creds.account_id = None
    creds.region = None


@dataclass
class StoredCredentials:
    """Credentials with metadata (supports both AWS and kubeconfig auth)."""
    # Auth mode: "aws" or "kubeconfig"
    auth_mode: str
    expires_at: datetime
    created_at: datetime

    # AWS-specific fields (optional)
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    session_token: Optional[str] = None
    region: Optional[str] = None
    user_arn: Optional[str] = None
    account_id: Optional[str] = None

    # Kubeconfig-specific fields (optional)
    kubeconfig_path: Optional[str] = None
    kubeconfig_content: Optional[str] = None  # Raw YAML content for streaming auth
    kubeconfig_contexts: Optional[Dict[str, str]] = None  # context_name -> cluster_name
    selected_context: Optional[str] = None  # User-selected context

    def is_expiring_soon(self, threshold_seconds: int = 600) -> bool:
        """Check if credentials expire within the given threshold."""
        return (self.expires_at - datetime.now()).total_seconds() <= threshold_seconds

    def scrub(self) -> None:
        """Empty secret and identity fields on this object."""
        scrub_credentials(self)


class CredentialStore:
    """
    Thread-safe in-memory storage for per-user AWS credentials with TTL-based expiration.

    Features:
    - Thread-safe operations using threading.Lock
    - Automatic cleanup of expired credentials (with scrub + optional session hook)
    - Eviction of oldest expired credentials when at capacity
    - TTL of 3600 seconds (1 hour) for all credentials
    """

    def __init__(
        self,
        max_capacity: int = 1000,
        ttl_seconds: int = 3600,
        on_session_removed: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize the credential store.

        Args:
            max_capacity: Maximum number of credential entries to store
            ttl_seconds: Time-to-live for credentials in seconds (default: 3600)
            on_session_removed: Optional callback(session_id) after credentials
                are scrubbed and dropped (logout, expire, evict). Used to tear
                down per-session K8s clients and caches.
        """
        self._store: Dict[str, StoredCredentials] = {}
        self._lock = threading.Lock()
        self._max_capacity = max_capacity
        self._ttl_seconds = ttl_seconds
        self._on_session_removed = on_session_removed
        logger.info(
            f"CredentialStore initialized with capacity={max_capacity}, ttl={ttl_seconds}s"
        )

    def set_on_session_removed(
        self, callback: Optional[Callable[[str], None]]
    ) -> None:
        """Register or replace the session-removed hook (e.g. clear K8s clients)."""
        self._on_session_removed = callback

    def _drop_locked(self, session_id: str) -> bool:
        """Scrub + delete under lock. Caller holds ``self._lock``."""
        creds = self._store.pop(session_id, None)
        if creds is None:
            return False
        scrub_credentials(creds)
        return True

    def _notify_removed(self, session_ids: List[str]) -> None:
        """Invoke session-removed hook outside the lock."""
        if not self._on_session_removed or not session_ids:
            return
        for session_id in session_ids:
            try:
                self._on_session_removed(session_id)
            except Exception as e:
                logger.warning(
                    "on_session_removed failed for %s...: %s",
                    session_id[:8],
                    e,
                )

    def store(self, session_id: str, creds: StoredCredentials) -> None:
        """
        Store credentials for a session with TTL.

        Args:
            session_id: Unique session identifier
            creds: Credentials to store
        """
        notify: List[str] = []
        with self._lock:
            # Check capacity and evict if needed
            if len(self._store) >= self._max_capacity and session_id not in self._store:
                evicted = self._evict_oldest_expired_locked()
                if evicted:
                    notify.append(evicted)

            # Replacing an existing session: scrub old secrets and tear down
            # any session K8s clients bound to the previous credentials.
            if session_id in self._store:
                self._drop_locked(session_id)
                notify.append(session_id)

            # Set expiration time if not already set (allow storing expired creds for testing)
            if creds.expires_at is None:
                creds.expires_at = datetime.now() + timedelta(seconds=self._ttl_seconds)

            self._store[session_id] = creds
            logger.info(
                f"Stored credentials for session {session_id[:8]}... (expires at {creds.expires_at})"
            )
        self._notify_removed(notify)

    def get(self, session_id: str) -> Optional[StoredCredentials]:
        """
        Retrieve credentials for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            StoredCredentials if found and not expired, None otherwise
        """
        notify: List[str] = []
        with self._lock:
            creds = self._store.get(session_id)

            if creds is None:
                logger.debug(f"No credentials found for session {session_id[:8]}...")
                return None

            # Check if expired
            if creds.expires_at <= datetime.now():
                logger.info(f"Credentials expired for session {session_id[:8]}...")
                self._drop_locked(session_id)
                notify.append(session_id)
                creds = None
            else:
                logger.debug(f"Retrieved credentials for session {session_id[:8]}...")

        self._notify_removed(notify)
        return creds

    def cleanup_expired(self) -> int:
        """
        Remove all expired credentials from the store (scrub + session hook).

        Returns:
            Number of credentials removed
        """
        with self._lock:
            now = datetime.now()
            expired_sessions = [
                session_id
                for session_id, creds in self._store.items()
                if creds.expires_at <= now
            ]

            for session_id in expired_sessions:
                self._drop_locked(session_id)

            if expired_sessions:
                logger.info(f"Cleaned up {len(expired_sessions)} expired credential(s)")

        self._notify_removed(expired_sessions)
        return len(expired_sessions)

    def remove(self, session_id: str) -> bool:
        """
        Remove and scrub credentials for a session.

        Args:
            session_id: Unique session identifier

        Returns:
            True if credentials were removed, False if not found
        """
        with self._lock:
            removed = self._drop_locked(session_id)
            if removed:
                logger.info(f"Removed credentials for session {session_id[:8]}...")
        if removed:
            self._notify_removed([session_id])
        return removed

    def _evict_oldest_expired_locked(self) -> Optional[str]:
        """
        Evict one entry under lock. Returns session_id if evicted, else None.
        """
        now = datetime.now()

        expired = [
            (session_id, creds)
            for session_id, creds in self._store.items()
            if creds.expires_at <= now
        ]

        if expired:
            expired.sort(key=lambda x: x[1].expires_at)
            oldest_session_id = expired[0][0]
            self._drop_locked(oldest_session_id)
            logger.info(
                f"Evicted expired credentials for session {oldest_session_id[:8]}..."
            )
            return oldest_session_id

        if self._store:
            oldest_session_id = min(
                self._store.items(), key=lambda x: x[1].created_at
            )[0]
            self._drop_locked(oldest_session_id)
            logger.warning(
                f"Evicted oldest credentials for session {oldest_session_id[:8]}... "
                "(capacity limit reached)"
            )
            return oldest_session_id
        return None

    def get_stats(self) -> Dict[str, int]:
        """
        Get statistics about the credential store.

        Returns:
            Dictionary with stats (total, expired, active)
        """
        with self._lock:
            now = datetime.now()
            total = len(self._store)
            expired = sum(
                1 for creds in self._store.values() if creds.expires_at <= now
            )
            active = total - expired

            return {
                "total": total,
                "expired": expired,
                "active": active,
                "capacity": self._max_capacity,
            }
