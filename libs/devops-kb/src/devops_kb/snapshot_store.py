"""Snapshot storage and retrieval."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


class SnapshotStore:
    """Store and retrieve cluster snapshots as JSON files."""

    def __init__(self, snapshots_path: str = "/data/knowledge-base/snapshots"):
        """Initialize snapshot store.

        Args:
            snapshots_path: Path to store snapshots
        """
        self.snapshots_path = Path(snapshots_path)
        self.snapshots_path.mkdir(parents=True, exist_ok=True)

    def add_snapshot(self, snapshot_data: Dict[str, Any]) -> str:
        """Add a snapshot to storage.

        Args:
            snapshot_data: Snapshot data dictionary

        Returns:
            Snapshot ID
        """
        snapshot_id = snapshot_data.get("id") or str(uuid.uuid4())
        snapshot_data["id"] = snapshot_id

        # Ensure timestamp is set
        if "timestamp" not in snapshot_data:
            snapshot_data["timestamp"] = datetime.utcnow().isoformat()

        snapshot_file = self.snapshots_path / f"{snapshot_id}.json"
        with open(snapshot_file, "w") as f:
            json.dump(snapshot_data, f, indent=2, default=str)

        return snapshot_id

    def get_snapshot(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a snapshot by ID.

        Args:
            snapshot_id: Snapshot ID to retrieve

        Returns:
            Snapshot data dictionary or None if not found
        """
        snapshot_file = self.snapshots_path / f"{snapshot_id}.json"
        if not snapshot_file.exists():
            return None

        with open(snapshot_file, "r") as f:
            return json.load(f)

    def delete_snapshot(self, snapshot_id: str) -> bool:
        """Delete a snapshot.

        Args:
            snapshot_id: Snapshot ID to delete

        Returns:
            True if deleted, False if not found
        """
        snapshot_file = self.snapshots_path / f"{snapshot_id}.json"
        if snapshot_file.exists():
            snapshot_file.unlink()
            return True
        return False

    def get_all_snapshots(self) -> List[Dict[str, Any]]:
        """Retrieve all snapshots.

        Returns:
            List of snapshot data dictionaries
        """
        snapshots = []
        for snapshot_file in self.snapshots_path.glob("*.json"):
            with open(snapshot_file, "r") as f:
                snapshots.append(json.load(f))
        return snapshots
