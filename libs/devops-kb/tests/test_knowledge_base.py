"""Tests for knowledge base."""

import tempfile
from datetime import datetime, timedelta

import pytest

from devops_kb.knowledge_base import KnowledgeBase
from devops_kb.solution import Solution


@pytest.fixture
def temp_kb_path():
    """Create temporary knowledge base path."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


def test_add_and_get_solution(temp_kb_path):
    """Test adding and retrieving a solution."""
    kb = KnowledgeBase(temp_kb_path)

    solution = Solution(
        problem_description="Pod failing with ImagePullBackOff",
        resolution_steps="Check pull secret and registry credentials",
        tags=["pod", "image", "registry"],
    )

    solution_id = kb.add_solution(solution)
    assert solution_id == solution.id

    retrieved = kb.get_solution(solution_id)
    assert retrieved is not None
    assert retrieved.problem_description == solution.problem_description
    assert retrieved.resolution_steps == solution.resolution_steps


def test_get_all_solutions(temp_kb_path):
    """Test retrieving all solutions."""
    kb = KnowledgeBase(temp_kb_path)

    solutions = [
        Solution("Problem 1", "Resolution 1", tags=["tag1"]),
        Solution("Problem 2", "Resolution 2", tags=["tag2"]),
        Solution("Problem 3", "Resolution 3", tags=["tag3"]),
    ]

    for solution in solutions:
        kb.add_solution(solution)

    all_solutions = kb.get_all_solutions()
    assert len(all_solutions) == 3


def test_add_and_get_snapshot(temp_kb_path):
    """Test adding and retrieving a snapshot."""
    kb = KnowledgeBase(temp_kb_path)

    snapshot_data = {
        "id": "snap-123",
        "timestamp": datetime.utcnow().isoformat(),
        "cluster_name": "prod-cluster",
        "metrics": {
            "pod_failures": 2,
            "cpu_usage": 45.0,
            "memory_usage": 60.0,
        },
    }

    snapshot_id = kb.add_snapshot(snapshot_data)
    assert snapshot_id == "snap-123"

    retrieved = kb.get_snapshot(snapshot_id)
    assert retrieved is not None
    assert retrieved["cluster_name"] == "prod-cluster"


def test_get_snapshots_by_namespace(temp_kb_path):
    """Test retrieving snapshots by namespace."""
    kb = KnowledgeBase(temp_kb_path)

    snapshots = [
        {
            "id": "snap-1",
            "timestamp": datetime.utcnow().isoformat(),
            "namespace": "default",
            "metrics": {},
        },
        {
            "id": "snap-2",
            "timestamp": datetime.utcnow().isoformat(),
            "namespace": "kube-system",
            "metrics": {},
        },
        {
            "id": "snap-3",
            "timestamp": datetime.utcnow().isoformat(),
            "namespace": "default",
            "metrics": {},
        },
    ]

    for snapshot in snapshots:
        kb.add_snapshot(snapshot)

    default_snapshots = kb.get_snapshots_by_namespace("default")
    assert len(default_snapshots) == 2


def test_get_snapshots_by_timerange(temp_kb_path):
    """Test retrieving snapshots by time range."""
    kb = KnowledgeBase(temp_kb_path)

    now = datetime.utcnow()
    past = now - timedelta(hours=2)
    future = now + timedelta(hours=2)

    snapshots = [
        {
            "id": "snap-1",
            "timestamp": (now - timedelta(hours=1)).isoformat(),
            "metrics": {},
        },
        {
            "id": "snap-2",
            "timestamp": (now - timedelta(hours=3)).isoformat(),
            "metrics": {},
        },
        {
            "id": "snap-3",
            "timestamp": (now + timedelta(hours=1)).isoformat(),
            "metrics": {},
        },
    ]

    for snapshot in snapshots:
        kb.add_snapshot(snapshot)

    in_range = kb.get_snapshots_by_timerange(past, future)
    assert len(in_range) == 2


def test_find_healthy_baseline(temp_kb_path):
    """Test finding healthy baseline snapshot."""
    kb = KnowledgeBase(temp_kb_path)

    snapshots = [
        {
            "id": "snap-1",
            "timestamp": (datetime.utcnow() - timedelta(hours=2)).isoformat(),
            "metrics": {
                "pod_failures": 5,
                "critical_events": 2,
                "unhealthy_nodes": 0,
            },
        },
        {
            "id": "snap-2",
            "timestamp": (datetime.utcnow() - timedelta(hours=1)).isoformat(),
            "metrics": {
                "pod_failures": 0,
                "critical_events": 0,
                "unhealthy_nodes": 0,
            },
        },
        {
            "id": "snap-3",
            "timestamp": datetime.utcnow().isoformat(),
            "metrics": {
                "pod_failures": 3,
                "critical_events": 1,
                "unhealthy_nodes": 0,
            },
        },
    ]

    for snapshot in snapshots:
        kb.add_snapshot(snapshot)

    baseline = kb.find_healthy_baseline()
    assert baseline is not None
    assert baseline["id"] == "snap-2"


def test_delete_solution(temp_kb_path):
    """Test deleting a solution."""
    kb = KnowledgeBase(temp_kb_path)

    solution = Solution("Problem", "Resolution")
    solution_id = kb.add_solution(solution)

    assert kb.get_solution(solution_id) is not None
    assert kb.delete_solution(solution_id)
    assert kb.get_solution(solution_id) is None


def test_delete_snapshot(temp_kb_path):
    """Test deleting a snapshot."""
    kb = KnowledgeBase(temp_kb_path)

    snapshot_data = {
        "id": "snap-123",
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": {},
    }

    kb.add_snapshot(snapshot_data)
    assert kb.get_snapshot("snap-123") is not None
    assert kb.delete_snapshot("snap-123")
    assert kb.get_snapshot("snap-123") is None


def test_kb_stats(temp_kb_path):
    """Test knowledge base statistics."""
    kb = KnowledgeBase(temp_kb_path)

    solution = Solution("Problem", "Resolution")
    kb.add_solution(solution)

    snapshot_data = {
        "id": "snap-1",
        "timestamp": datetime.utcnow().isoformat(),
        "metrics": {},
    }
    kb.add_snapshot(snapshot_data)

    stats = kb.get_kb_stats()
    assert stats["total_solutions"] == 1
    assert stats["total_snapshots"] == 1
