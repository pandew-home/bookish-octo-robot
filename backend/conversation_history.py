"""Conversation history management with per-cluster isolation for v2."""

import json
import uuid
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional


class ChatMessage:
    """Individual chat message."""

    def __init__(self, role: str, content: str, timestamp: Optional[str] = None):
        """Initialize chat message.

        Args:
            role: Message role ("user" or "assistant")
            content: Message content
            timestamp: Optional timestamp (defaults to current time)
        """
        self.role = role
        self.content = content
        self.timestamp = timestamp or datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "content": self.content,
            "timestamp": self.timestamp
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ChatMessage":
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data.get("timestamp")
        )


class Conversation:
    """Individual conversation with messages."""

    def __init__(self, conversation_id: str, user_id: str, title: str = ""):
        """Initialize conversation.

        Args:
            conversation_id: Unique conversation ID
            user_id: User ID who owns the conversation
            title: Optional conversation title
        """
        self.id = conversation_id
        self.user_id = user_id
        self.title = title or f"Conversation {conversation_id[:8]}"
        self.messages: List[ChatMessage] = []
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.updated_at = self.created_at

    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation.

        Args:
            role: Message role ("user" or "assistant")
            content: Message content
        """
        message = ChatMessage(role, content)
        self.messages.append(message)
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "messages": [msg.to_dict() for msg in self.messages],
            "created_at": self.created_at,
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Conversation":
        """Create from dictionary."""
        conversation = cls(
            conversation_id=data["id"],
            user_id=data["user_id"],
            title=data.get("title", "")
        )
        conversation.created_at = data.get("created_at", conversation.created_at)
        conversation.updated_at = data.get("updated_at", conversation.updated_at)
        conversation.messages = [
            ChatMessage.from_dict(msg_data)
            for msg_data in data.get("messages", [])
        ]
        return conversation


class ConversationHistory:
    """Manage conversation history with 10 conversation limit per user per cluster.
    
    Requirements: 10.1, 10.2, 10.3, 10.4
    """

    def __init__(self, data_dir: Optional[str] = None):
        """Initialize conversation history manager.

        Args:
            data_dir: Directory to store conversation files (defaults to /data/conversations or temp)
        """
        if data_dir is None:
            # Default to /data/conversations (PVC mount) or fallback to temp
            data_dir = os.environ.get("CONVERSATIONS_PATH", "/data/conversations")
        
        self.data_dir = Path(data_dir)
        try:
            # Try to create the configured directory
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            # Fallback to temp directory
            fallback_base = Path(tempfile.gettempdir())
            self.data_dir = fallback_base / "conversations"
            self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.max_conversations = 10

    def _get_user_dir(self, user_id: str, cluster_name: Optional[str] = None) -> Path:
        """Get user's conversation directory.

        Args:
            user_id: User ID
            cluster_name: Optional cluster name for per-cluster isolation

        Returns:
            Path to user's conversation directory
        """
        if cluster_name:
            # Per-cluster isolation: store conversations in user_id/cluster_name/
            user_dir = self.data_dir / user_id / cluster_name
        else:
            # Legacy: store in user_id/ (for backward compatibility)
            user_dir = self.data_dir / user_id
        
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir

    def _get_conversation_file(self, user_id: str, conversation_id: str, cluster_name: Optional[str] = None) -> Path:
        """Get path to conversation file.

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            cluster_name: Optional cluster name for per-cluster isolation

        Returns:
            Path to conversation file
        """
        return self._get_user_dir(user_id, cluster_name) / f"{conversation_id}.json"

    def create_conversation(self, user_id: str, title: str = "", cluster_name: Optional[str] = None) -> str:
        """Create new conversation for user.

        Args:
            user_id: User ID
            title: Optional conversation title
            cluster_name: Optional cluster name for per-cluster isolation

        Returns:
            New conversation ID
        """
        conversation_id = str(uuid.uuid4())
        conversation = Conversation(conversation_id, user_id, title)

        # Save conversation
        self._save_conversation(conversation, cluster_name)

        # Cleanup old conversations if needed
        self.cleanup_old_conversations(user_id, cluster_name)

        return conversation_id

    def save_message(self, user_id: str, conversation_id: str, role: str, content: str, cluster_name: Optional[str] = None) -> None:
        """Save message to conversation.

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            role: Message role ("user" or "assistant")
            content: Message content
            cluster_name: Optional cluster name for per-cluster isolation
        """
        conversation = self.get_conversation(user_id, conversation_id, cluster_name)
        if not conversation:
            # Create new conversation if it doesn't exist
            conversation = Conversation(conversation_id, user_id)

        conversation.add_message(role, content)
        self._save_conversation(conversation, cluster_name)

    def get_conversation(self, user_id: str, conversation_id: str, cluster_name: Optional[str] = None) -> Optional[Conversation]:
        """Get conversation by ID.

        Args:
            user_id: User ID
            conversation_id: Conversation ID
            cluster_name: Optional cluster name for per-cluster isolation

        Returns:
            Conversation object or None if not found
        """
        conversation_file = self._get_conversation_file(user_id, conversation_id, cluster_name)
        if not conversation_file.exists():
            return None

        try:
            with open(conversation_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return Conversation.from_dict(data)
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Error loading conversation {conversation_id}: {e}")
            return None

    def get_user_conversations(self, user_id: str, cluster_name: Optional[str] = None) -> List[Conversation]:
        """Get up to 10 most recent conversations for user.

        Args:
            user_id: User ID
            cluster_name: Optional cluster name for per-cluster isolation

        Returns:
            List of conversations sorted by updated_at (most recent first)
        """
        user_dir = self._get_user_dir(user_id, cluster_name)

        # Sort files once by mtime to avoid re-reading everything
        conversation_files = sorted(
            user_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        conversations: List[Conversation] = []

        for conversation_file in conversation_files[: self.max_conversations]:
            try:
                with open(conversation_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                conversation = Conversation.from_dict(data)
                conversations.append(conversation)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Error loading conversation {conversation_file.name}: {e}")
                continue

        return conversations

    def cleanup_old_conversations(self, user_id: str, cluster_name: Optional[str] = None) -> None:
        """Delete conversations beyond the limit of 10.

        Args:
            user_id: User ID
            cluster_name: Optional cluster name for per-cluster isolation
        """
        user_dir = self._get_user_dir(user_id, cluster_name)
        conversation_files = sorted(
            user_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if len(conversation_files) > self.max_conversations:
            for conversation_file in conversation_files[self.max_conversations:]:
                try:
                    conversation_file.unlink()
                except OSError as e:
                    print(f"Error deleting conversation {conversation_file.stem}: {e}")

    def _save_conversation(self, conversation: Conversation, cluster_name: Optional[str] = None) -> None:
        """Save conversation to file.

        Args:
            conversation: Conversation to save
            cluster_name: Optional cluster name for per-cluster isolation
        """
        conversation_file = self._get_conversation_file(conversation.user_id, conversation.id, cluster_name)

        try:
            with open(conversation_file, 'w', encoding='utf-8') as f:
                json.dump(conversation.to_dict(), f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Error saving conversation {conversation.id}: {e}")
            raise
