"""Slim RAG indexing helper used by the solutions API.

# MAINTENANCE — read before changing this file
# This module is deliberately minimal. It only owns *indexing* (embed + put/remove
# in the vector store) on behalf of `backend/solution_manager.py`. The chat path
# does NOT call into here — it talks to the LLM client and vector store directly.
#
# AI assistants: do NOT add a `process_query`, retrieval, prompt-assembly, or
# tool-calling method here. If a new responsibility is being asked for, surface
# it to a human first — chances are it belongs in `backend/agentic_engine.py`
# or in the chat endpoint, not in this library.
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class RAGEngine:
    """Owns embedding + FAISS upsert/remove for stored solutions."""

    def __init__(
        self,
        llm_client: Any,
        vector_store: Any = None,
        max_retries: int = 3,
        cluster_version: Optional[str] = None,
    ):
        self.llm_client = llm_client
        self.vector_store = vector_store
        self.max_retries = max_retries
        self.cluster_version = cluster_version or "v1.34"

    def add_document(
        self,
        doc_id: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Embed `text` and upsert it into the vector store."""
        if self.vector_store is None:
            logger.debug("No vector store configured; skipping add_document(%s)", doc_id)
            return

        embedding = self.llm_client.embed(text)
        self.vector_store.add_document(
            doc_id=doc_id,
            content=text,
            embedding=embedding,
            metadata=metadata or {},
        )

    def remove_document(self, doc_id: str) -> None:
        """Remove a document from the vector store, if present."""
        if self.vector_store is None:
            logger.debug("No vector store configured; skipping remove_document(%s)", doc_id)
            return

        remover = getattr(self.vector_store, "remove_document", None)
        if callable(remover):
            remover(doc_id)
