"""Vector store for semantic search."""

from typing import List, Dict, Any, Optional


class VectorStore:
    """Vector store for semantic search using FAISS or similar."""

    def __init__(self, dimension: int = 384):
        """Initialize vector store.

        Args:
            dimension: Embedding dimension
        """
        self.dimension = dimension
        self.documents: List[Dict[str, Any]] = []
        self.embeddings: List[List[float]] = []

        try:
            import faiss
            self.faiss = faiss
            self.index = faiss.IndexFlatL2(dimension)
        except ImportError:
            self.faiss = None
            self.index = None

    def add_document(self, doc_id: str, content: str, embedding: List[float], metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add document to vector store.

        Args:
            doc_id: Document ID
            content: Document content
            embedding: Document embedding vector
            metadata: Optional metadata dictionary
        """
        if len(embedding) != self.dimension:
            raise ValueError(f"Embedding dimension {len(embedding)} does not match store dimension {self.dimension}")

        doc = {
            "id": doc_id,
            "content": content,
            "metadata": metadata or {},
        }

        self.documents.append(doc)
        self.embeddings.append(embedding)

        if self.index:
            import numpy as np
            self.index.add(np.array([embedding], dtype=np.float32))

    def search(self, query_embedding: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Search for similar documents.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of top results to return

        Returns:
            List of similar documents with scores
        """
        if len(query_embedding) != self.dimension:
            raise ValueError(f"Query embedding dimension {len(query_embedding)} does not match store dimension {self.dimension}")

        if not self.documents:
            return []

        if self.index:
            import numpy as np
            distances, indices = self.index.search(
                np.array([query_embedding], dtype=np.float32),
                min(top_k, len(self.documents)),
            )

            results = []
            for idx, distance in zip(indices[0], distances[0]):
                if idx < len(self.documents):
                    doc = self.documents[idx].copy()
                    doc["score"] = float(distance)
                    results.append(doc)
            return results
        else:
            # Fallback: simple cosine similarity
            import math

            def cosine_similarity(a: List[float], b: List[float]) -> float:
                dot_product = sum(x * y for x, y in zip(a, b))
                magnitude_a = math.sqrt(sum(x * x for x in a))
                magnitude_b = math.sqrt(sum(x * x for x in b))
                if magnitude_a == 0 or magnitude_b == 0:
                    return 0
                return dot_product / (magnitude_a * magnitude_b)

            scores = [
                (i, cosine_similarity(query_embedding, emb))
                for i, emb in enumerate(self.embeddings)
            ]
            scores.sort(key=lambda x: x[1], reverse=True)

            results = []
            for idx, score in scores[:top_k]:
                doc = self.documents[idx].copy()
                doc["score"] = score
                results.append(doc)
            return results

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document dictionary or None if not found
        """
        for doc in self.documents:
            if doc["id"] == doc_id:
                return doc
        return None

    def delete_document(self, doc_id: str) -> bool:
        """Delete document by ID.

        Args:
            doc_id: Document ID

        Returns:
            True if deleted, False if not found
        """
        for i, doc in enumerate(self.documents):
            if doc["id"] == doc_id:
                self.documents.pop(i)
                self.embeddings.pop(i)
                # Note: FAISS index doesn't support deletion, would need to rebuild
                return True
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get vector store statistics.

        Returns:
            Statistics dictionary
        """
        return {
            "total_documents": len(self.documents),
            "dimension": self.dimension,
            "has_faiss": self.faiss is not None,
        }
