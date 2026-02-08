"""Solution validation and submission management."""

import logging
from typing import Tuple, Optional, List
from datetime import datetime

from devops_kb.solution import Solution
from devops_kb.knowledge_base import KnowledgeBase
from devops_rag.rag_engine import RAGEngine

logger = logging.getLogger(__name__)


class SolutionManager:
    """Manage solution validation, submission, and indexing."""

    def __init__(self, knowledge_base: KnowledgeBase, rag_engine: RAGEngine):
        """Initialize solution manager.

        Args:
            knowledge_base: KnowledgeBase instance for storage
            rag_engine: RAGEngine instance for embedding generation and indexing
        """
        self.knowledge_base = knowledge_base
        self.rag_engine = rag_engine

    def validate_solution(
        self,
        title: str,
        description: str,
        tags: List[str]
    ) -> Tuple[bool, Optional[str]]:
        """Validate solution fields before submission.

        Args:
            title: Solution title
            description: Solution description/resolution steps
            tags: List of tags for categorization

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if solution is valid, False otherwise
            - error_message: None if valid, descriptive error if invalid
        """
        # Validate title
        if not title or not title.strip():
            return False, "Solution title is required and cannot be empty."

        if len(title.strip()) < 5:
            return False, "Solution title must be at least 5 characters long."

        if len(title) > 200:
            return False, f"Solution title is too long ({len(title)} characters). Please limit to 200 characters."

        # Validate description
        if not description or not description.strip():
            return False, "Solution description is required and cannot be empty."

        if len(description.strip()) < 20:
            return False, "Solution description must be at least 20 characters long."

        if len(description) > 10000:
            return False, f"Solution description is too long ({len(description)} characters). Please limit to 10000 characters."

        # Validate tags
        if not tags or len(tags) == 0:
            return False, "At least one tag is required for categorization."

        if len(tags) > 10:
            return False, f"Too many tags ({len(tags)}). Please limit to 10 tags."

        # Validate individual tags
        for tag in tags:
            if not tag or not tag.strip():
                return False, "Tags cannot be empty."

            if len(tag) > 50:
                return False, f"Tag '{tag}' is too long. Please limit tags to 50 characters."

        return True, None

    def submit_solution(
        self,
        title: str,
        description: str,
        tags: List[str],
        runbook_url: Optional[str] = None,
        automation_script: Optional[str] = None,
        estimated_fix_time_minutes: Optional[int] = None,
        cluster_context: Optional[dict] = None,
        user_id: Optional[str] = None
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """Submit a new solution to the knowledge base.

        This method:
        1. Validates the solution fields
        2. Creates a Solution object
        3. Generates embeddings for the solution
        4. Stores the solution in the knowledge base
        5. Updates the FAISS index immediately

        Args:
            title: Solution title
            description: Solution description/resolution steps
            tags: List of tags for categorization
            runbook_url: Optional URL to runbook
            automation_script: Optional automation script
            estimated_fix_time_minutes: Optional estimated fix time
            cluster_context: Optional cluster context information
            user_id: Optional user ID who submitted the solution

        Returns:
            Tuple of (success, error_message, solution_id)
            - success: True if submission succeeded, False otherwise
            - error_message: None if successful, descriptive error if failed
            - solution_id: Solution ID if successful, None otherwise
        """
        # Validate solution fields
        is_valid, error_message = self.validate_solution(title, description, tags)
        if not is_valid:
            logger.warning(f"Solution validation failed: {error_message}")
            return False, error_message, None

        try:
            # Create Solution object
            solution = Solution(
                problem_description=title,
                resolution_steps=description,
                tags=tags,
                runbook_url=runbook_url,
                automation_script=automation_script,
                estimated_fix_time_minutes=estimated_fix_time_minutes,
                cluster_context=cluster_context or {},
                created_at=datetime.utcnow()
            )

            # Store solution in knowledge base
            solution_id = self.knowledge_base.add_solution(solution)
            logger.info(f"Solution {solution_id} stored in knowledge base")

            # Generate embeddings and update FAISS index
            # Combine title and description for embedding
            solution_text = f"{title}\n\n{description}"
            self.rag_engine.add_document(
                doc_id=solution_id,
                text=solution_text,
                metadata={
                    "type": "solution",
                    "tags": tags,
                    "created_at": solution.created_at.isoformat(),
                    "user_id": user_id or "unknown"
                }
            )
            logger.info(f"Solution {solution_id} indexed in FAISS")

            return True, None, solution_id

        except Exception as e:
            error_msg = f"Failed to submit solution: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg, None

    def get_solution(self, solution_id: str) -> Optional[Solution]:
        """Retrieve a solution by ID.

        Args:
            solution_id: Solution ID to retrieve

        Returns:
            Solution object or None if not found
        """
        try:
            return self.knowledge_base.get_solution(solution_id)
        except Exception as e:
            logger.error(f"Failed to retrieve solution {solution_id}: {e}")
            return None

    def get_all_solutions(self, tags: Optional[List[str]] = None) -> List[Solution]:
        """Retrieve all solutions, optionally filtered by tags.

        Args:
            tags: Optional list of tags to filter by

        Returns:
            List of Solution objects
        """
        try:
            solutions = self.knowledge_base.get_all_solutions()

            # Filter by tags if provided
            if tags:
                solutions = [
                    s for s in solutions
                    if any(tag in s.tags for tag in tags)
                ]

            return solutions
        except Exception as e:
            logger.error(f"Failed to retrieve solutions: {e}")
            return []

    def delete_solution(self, solution_id: str) -> Tuple[bool, Optional[str]]:
        """Delete a solution from the knowledge base.

        Args:
            solution_id: Solution ID to delete

        Returns:
            Tuple of (success, error_message)
        """
        try:
            # Delete from knowledge base
            deleted = self.knowledge_base.delete_solution(solution_id)

            if not deleted:
                return False, f"Solution {solution_id} not found"

            # Remove from FAISS index
            self.rag_engine.remove_document(solution_id)
            logger.info(f"Solution {solution_id} deleted from knowledge base and index")

            return True, None

        except Exception as e:
            error_msg = f"Failed to delete solution {solution_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            return False, error_msg
