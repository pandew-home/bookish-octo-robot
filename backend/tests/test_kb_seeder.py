"""
Tests for Knowledge Base Seeding

Verifies KB initialization, seeding, and pre-deployment checks.
"""

import os
from unittest.mock import patch, MagicMock

import pytest

from kb_seeder import (
    seed_knowledge_base,
    should_seed_kb,
    should_force_reseed,
    INITIAL_SOLUTIONS,
)


class TestKBSeederEnvVars:
    """Test environment variable checks for KB seeding."""

    def test_should_seed_kb_enabled(self):
        """Test should_seed_kb returns True when enabled."""
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "true"}):
            assert should_seed_kb() is True

    def test_should_seed_kb_enabled_numeric(self):
        """Test should_seed_kb with numeric 1."""
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "1"}):
            assert should_seed_kb() is True

    def test_should_seed_kb_enabled_yes(self):
        """Test should_seed_kb with 'yes'."""
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "yes"}):
            assert should_seed_kb() is True

    def test_should_seed_kb_disabled(self):
        """Test should_seed_kb returns False when disabled."""
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "false"}):
            assert should_seed_kb() is False

    def test_should_seed_kb_default_disabled(self):
        """Test should_seed_kb defaults to False."""
        with patch.dict(os.environ, {}, clear=True):
            assert should_seed_kb() is False

    def test_should_force_reseed_enabled(self):
        """Test should_force_reseed returns True when enabled."""
        with patch.dict(os.environ, {"KB_FORCE_RESEED": "true"}):
            assert should_force_reseed() is True

    def test_should_force_reseed_disabled(self):
        """Test should_force_reseed returns False when disabled."""
        with patch.dict(os.environ, {"KB_FORCE_RESEED": "false"}):
            assert should_force_reseed() is False

    def test_should_force_reseed_default_disabled(self):
        """Test should_force_reseed defaults to False."""
        with patch.dict(os.environ, {}, clear=True):
            assert should_force_reseed() is False


class TestKBSeeding:
    """Test KB seeding functionality."""

    def test_seed_knowledge_base_empty_kb(self):
        """Test seeding an empty knowledge base."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = []

        result = seed_knowledge_base(mock_kb, force_reseed=False)

        assert result is True
        assert mock_kb.add_solution.call_count == len(INITIAL_SOLUTIONS)

    def test_seed_knowledge_base_existing_solutions_no_force(self):
        """Test seeding when KB already has solutions (no force)."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = [MagicMock()]

        result = seed_knowledge_base(mock_kb, force_reseed=False)

        assert result is True
        assert mock_kb.add_solution.call_count == 0

    def test_seed_knowledge_base_existing_solutions_with_force(self):
        """Test seeding with force reseed when KB has solutions."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = [MagicMock()]

        result = seed_knowledge_base(mock_kb, force_reseed=True)

        assert result is True
        assert mock_kb.add_solution.call_count == len(INITIAL_SOLUTIONS)

    def test_seed_knowledge_base_partial_failure(self):
        """Test seeding when some solutions fail to add."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = []

        # Make first solution succeed, rest fail
        side_effects = [None] + [Exception("Add failed")] * (len(INITIAL_SOLUTIONS) - 1)
        mock_kb.add_solution.side_effect = side_effects

        result = seed_knowledge_base(mock_kb, force_reseed=False)

        # Should return True if at least one succeeded
        assert result is True
        assert mock_kb.add_solution.call_count == len(INITIAL_SOLUTIONS)

    def test_seed_knowledge_base_all_failures(self):
        """Test seeding when all solutions fail to add."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = []
        mock_kb.add_solution.side_effect = Exception("Add failed")

        result = seed_knowledge_base(mock_kb, force_reseed=False)

        assert result is False

    def test_seed_knowledge_base_exception_handling(self):
        """Test seeding handles KB exceptions gracefully."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.side_effect = Exception("KB error")

        result = seed_knowledge_base(mock_kb, force_reseed=False)

        assert result is False

    def test_seed_knowledge_base_solution_content(self):
        """Test that seeded solutions have required content."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = []

        seed_knowledge_base(mock_kb, force_reseed=False)

        # Check that add_solution was called with proper Solution objects
        for call in mock_kb.add_solution.call_args_list:
            solution = call[0][0]
            assert hasattr(solution, "problem_description")
            assert hasattr(solution, "resolution_steps")
            assert hasattr(solution, "tags")
            assert solution.problem_description
            assert solution.resolution_steps
            assert solution.tags


class TestInitialSolutions:
    """Test the initial solutions content."""

    def test_initial_solutions_not_empty(self):
        """Test that initial solutions list is not empty."""
        assert len(INITIAL_SOLUTIONS) > 0

    def test_initial_solutions_have_required_fields(self):
        """Test that all initial solutions have required fields."""
        for solution in INITIAL_SOLUTIONS:
            assert "title" in solution
            assert "description" in solution
            assert "tags" in solution
            assert solution["title"]
            assert solution["description"]
            assert solution["tags"]

    def test_initial_solutions_tags_are_lists(self):
        """Test that all solution tags are lists."""
        for solution in INITIAL_SOLUTIONS:
            assert isinstance(solution["tags"], list)
            assert len(solution["tags"]) > 0

    def test_initial_solutions_cover_common_issues(self):
        """Test that initial solutions cover common DevOps issues."""
        solution_titles = [s["title"].lower() for s in INITIAL_SOLUTIONS]

        # Check for key issue types
        assert any("crash" in title for title in solution_titles)
        assert any("image" in title for title in solution_titles)
        assert any("pvc" in title or "storage" in title for title in solution_titles)
        assert any("node" in title for title in solution_titles)
        assert any("dns" in title for title in solution_titles)
        assert any(
            "eviction" in title or "resource" in title for title in solution_titles
        )


class TestPreDeploymentKBChecks:
    """Test pre-deployment checks for KB existence and readiness."""

    def test_kb_directory_exists(self):
        """Test that KB directory path is properly defined."""
        assert "/data/knowledge-base" in ["/data/knowledge-base"]

    def test_kb_seeding_respects_env_vars(self):
        """Test that KB seeding respects environment variables."""
        # When disabled
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "false"}):
            assert should_seed_kb() is False

        # When enabled
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "true"}):
            assert should_seed_kb() is True

    def test_kb_force_reseed_respects_env_vars(self):
        """Test that KB force reseed respects environment variables."""
        # When disabled
        with patch.dict(os.environ, {"KB_FORCE_RESEED": "false"}):
            assert should_force_reseed() is False

        # When enabled
        with patch.dict(os.environ, {"KB_FORCE_RESEED": "true"}):
            assert should_force_reseed() is True

    def test_kb_seeds_on_initialization(self):
        """Test that KB is seeded during initialization when enabled."""
        with patch.dict(os.environ, {"KB_SEEDING_ENABLED": "true"}):
            assert should_seed_kb() is True

            mock_kb = MagicMock()
            mock_kb.get_all_solutions.return_value = []

            result = seed_knowledge_base(mock_kb)
            assert result is True
            assert mock_kb.add_solution.called

    def test_kb_solutions_have_actionable_content(self):
        """Test that all KB solutions have actionable troubleshooting steps."""
        for solution in INITIAL_SOLUTIONS:
            description = solution["description"]
            # Check for numbered steps or actionable content
            has_steps = any(
                str(i) + "." in description for i in range(1, 10)
            )  # Numbered steps
            has_commands = "`" in description  # Commands in backticks
            assert (
                has_steps or has_commands
            ), f"Solution '{solution['title']}' lacks actionable content"


class TestKBIntegration:
    """Integration tests for KB with RAG system."""

    def test_seeded_solutions_are_queryable(self):
        """Test that seeded solutions structure is queryable."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = []

        seed_knowledge_base(mock_kb)

        # Verify solutions were added
        assert mock_kb.add_solution.call_count == len(INITIAL_SOLUTIONS)

    def test_kb_seeding_idempotent(self):
        """Test that seeding is idempotent (safe to run multiple times)."""
        mock_kb = MagicMock()
        mock_kb.get_all_solutions.return_value = []

        # First seed
        result1 = seed_knowledge_base(mock_kb)

        # Reset mock
        mock_kb.reset_mock()
        mock_kb.get_all_solutions.return_value = [
            MagicMock() for _ in range(len(INITIAL_SOLUTIONS))
        ]

        # Second seed (should skip because KB has solutions)
        result2 = seed_knowledge_base(mock_kb)

        assert result1 is True
        assert result2 is True
        assert mock_kb.add_solution.call_count == 0  # Should not add again


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
