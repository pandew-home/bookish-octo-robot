"""Solution model for knowledge base."""

import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any


class Solution:
    """Represents a solution in the knowledge base."""

    def __init__(
        self,
        problem_description: str,
        resolution_steps: str,
        tags: Optional[List[str]] = None,
        runbook_url: Optional[str] = None,
        automation_script: Optional[str] = None,
        estimated_fix_time_minutes: Optional[int] = None,
        cluster_context: Optional[Dict[str, Any]] = None,
        solution_id: Optional[str] = None,
        created_at: Optional[datetime] = None,
        usage_count: int = 0,
        success_rate: float = 0.0,
    ):
        """Initialize a solution.

        Args:
            problem_description: Description of the problem
            resolution_steps: Steps to resolve the problem
            tags: List of tags for categorization
            runbook_url: Optional URL to runbook
            automation_script: Optional automation script
            estimated_fix_time_minutes: Optional estimated fix time in minutes
            cluster_context: Optional cluster context information
            solution_id: Optional solution ID (generated if not provided)
            created_at: Optional creation timestamp (current time if not provided)
            usage_count: Number of times this solution was used
            success_rate: Success rate of this solution (0.0-1.0)
        """
        self.id = solution_id or str(uuid.uuid4())
        self.problem_description = problem_description
        self.resolution_steps = resolution_steps
        self.tags = tags or []
        self.runbook_url = runbook_url
        self.automation_script = automation_script
        self.estimated_fix_time_minutes = estimated_fix_time_minutes
        self.cluster_context = cluster_context or {}
        self.created_at = created_at or datetime.utcnow()
        self.usage_count = usage_count
        self.success_rate = success_rate

    def to_dict(self) -> Dict[str, Any]:
        """Convert solution to dictionary.

        Returns:
            Dictionary representation of solution
        """
        return {
            "id": self.id,
            "problem_description": self.problem_description,
            "resolution_steps": self.resolution_steps,
            "tags": self.tags,
            "runbook_url": self.runbook_url,
            "automation_script": self.automation_script,
            "estimated_fix_time_minutes": self.estimated_fix_time_minutes,
            "cluster_context": self.cluster_context,
            "created_at": self.created_at.isoformat(),
            "usage_count": self.usage_count,
            "success_rate": self.success_rate,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Solution":
        """Create solution from dictionary.

        Args:
            data: Dictionary representation of solution

        Returns:
            Solution object
        """
        created_at = None
        if "created_at" in data:
            try:
                created_at = datetime.fromisoformat(data["created_at"])
            except (ValueError, TypeError):
                created_at = datetime.utcnow()

        return cls(
            problem_description=data.get("problem_description", ""),
            resolution_steps=data.get("resolution_steps", ""),
            tags=data.get("tags", []),
            runbook_url=data.get("runbook_url"),
            automation_script=data.get("automation_script"),
            estimated_fix_time_minutes=data.get("estimated_fix_time_minutes"),
            cluster_context=data.get("cluster_context", {}),
            solution_id=data.get("id"),
            created_at=created_at,
            usage_count=data.get("usage_count", 0),
            success_rate=data.get("success_rate", 0.0),
        )

    def increment_usage(self) -> None:
        """Increment usage count."""
        self.usage_count += 1

    def update_success_rate(self, success: bool) -> None:
        """Update success rate based on feedback.

        Args:
            success: Whether the solution was successful
        """
        total = self.usage_count + 1
        current_successes = int(self.success_rate * self.usage_count)
        if success:
            current_successes += 1
        self.success_rate = current_successes / total
