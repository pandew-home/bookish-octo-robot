"""Knowledge base management for storing and retrieving solutions and snapshots."""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any

from devops_kb.solution import Solution
from devops_kb.snapshot_store import SnapshotStore


class KnowledgeBase:
    """Manage knowledge base storage including solutions and snapshots."""

    def __init__(self, base_path: str = "/data/knowledge-base"):
        """Initialize knowledge base.

        Args:
            base_path: Base path for knowledge base storage
        """
        self.base_path = Path(base_path)
        self.solutions_path = self.base_path / "solutions"
        self.snapshots_path = self.base_path / "snapshots"
        self.templates_path = self.base_path / "templates"

        # Create directories if they don't exist
        self.solutions_path.mkdir(parents=True, exist_ok=True)
        self.snapshots_path.mkdir(parents=True, exist_ok=True)
        self.templates_path.mkdir(parents=True, exist_ok=True)

        self.snapshot_store = SnapshotStore(str(self.snapshots_path))

    def add_solution(self, solution: Solution) -> str:
        """Add a solution to the knowledge base.

        Args:
            solution: Solution object to add

        Returns:
            Solution ID
        """
        solution_file = self.solutions_path / f"{solution.id}.json"
        with open(solution_file, "w") as f:
            json.dump(solution.to_dict(), f, indent=2, default=str)
        return solution.id

    def get_solution(self, solution_id: str) -> Optional[Solution]:
        """Retrieve a solution by ID.

        Args:
            solution_id: Solution ID to retrieve

        Returns:
            Solution object or None if not found
        """
        solution_file = self.solutions_path / f"{solution_id}.json"
        if not solution_file.exists():
            return None

        with open(solution_file, "r") as f:
            data = json.load(f)
        return Solution.from_dict(data)

    def get_all_solutions(self) -> List[Solution]:
        """Retrieve all solutions from the knowledge base.

        Returns:
            List of Solution objects
        """
        solutions = []
        for solution_file in self.solutions_path.glob("*.json"):
            with open(solution_file, "r") as f:
                data = json.load(f)
            solutions.append(Solution.from_dict(data))
        return solutions

    def add_snapshot(self, snapshot_data: Dict[str, Any]) -> str:
        """Add a snapshot to the knowledge base.

        Args:
            snapshot_data: Snapshot data dictionary

        Returns:
            Snapshot ID
        """
        return self.snapshot_store.add_snapshot(snapshot_data)

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a snapshot by ID.

        Args:
            snapshot_id: Snapshot ID to retrieve

        Returns:
            Snapshot data dictionary or None if not found
        """
        return self.snapshot_store.get_snapshot(snapshot_id)

    def get_snapshots_by_namespace(self, namespace: str) -> List[Dict[str, Any]]:
        """Retrieve all snapshots for a specific namespace.

        Args:
            namespace: Kubernetes namespace

        Returns:
            List of snapshot data dictionaries
        """
        snapshots = []
        for snapshot_file in self.snapshots_path.glob("*.json"):
            with open(snapshot_file, "r") as f:
                data = json.load(f)
            if data.get("namespace") == namespace:
                snapshots.append(data)
        return snapshots

    def get_snapshots_by_timerange(
        self, start_time: datetime, end_time: datetime
    ) -> List[Dict[str, Any]]:
        """Retrieve snapshots within a time range.

        Args:
            start_time: Start time for range
            end_time: End time for range

        Returns:
            List of snapshot data dictionaries within the time range
        """
        snapshots = []
        for snapshot_file in self.snapshots_path.glob("*.json"):
            with open(snapshot_file, "r") as f:
                data = json.load(f)
            timestamp_str = data.get("timestamp")
            if timestamp_str:
                try:
                    timestamp = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                    if start_time <= timestamp <= end_time:
                        snapshots.append(data)
                except ValueError:
                    pass
        return snapshots

    def find_healthy_baseline(self) -> Optional[Dict[str, Any]]:
        """Find the most recent healthy baseline snapshot.

        A healthy baseline is a snapshot with no critical issues.

        Returns:
            Snapshot data dictionary or None if no healthy baseline found
        """
        snapshots = []
        for snapshot_file in self.snapshots_path.glob("*.json"):
            with open(snapshot_file, "r") as f:
                data = json.load(f)
            snapshots.append(data)

        # Sort by timestamp descending (most recent first)
        snapshots.sort(
            key=lambda x: x.get("timestamp", ""),
            reverse=True,
        )

        # Find first healthy snapshot (no critical issues)
        for snapshot in snapshots:
            metrics = snapshot.get("metrics", {})
            # Check if snapshot is healthy (no critical issues)
            if (
                metrics.get("pod_failures", 0) == 0
                and metrics.get("critical_events", 0) == 0
                and metrics.get("unhealthy_nodes", 0) == 0
            ):
                return snapshot

        return None

    def delete_solution(self, solution_id: str) -> bool:
        """Delete a solution from the knowledge base.

        Args:
            solution_id: Solution ID to delete

        Returns:
            True if deleted, False if not found
        """
        solution_file = self.solutions_path / f"{solution_id}.json"
        if solution_file.exists():
            solution_file.unlink()
            return True
        return False

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot from the knowledge base.

        Args:
            snapshot_id: Snapshot ID to delete

        Returns:
            True if deleted, False if not found
        """
        return self.snapshot_store.delete_snapshot(snapshot_id)

    def get_kb_stats(self) -> Dict[str, Any]:
        """Get knowledge base statistics.

        Returns:
            Dictionary with KB statistics
        """
        solutions = self.get_all_solutions()
        snapshots = list(self.snapshots_path.glob("*.json"))

        return {
            "total_solutions": len(solutions),
            "total_snapshots": len(snapshots),
            "solutions_path": str(self.solutions_path),
            "snapshots_path": str(self.snapshots_path),
        }
