"""
Pre-Deployment Knowledge Base Checks

These tests verify KB configuration and readiness before deploying to production.
Run with: pytest tests/test_kb_predeploy.py -v

Requirements:
- KB seeding is properly configured
- KB can be initialized
- Initial solutions are available
- No missing dependencies
"""

import os
import sys
import tempfile
import shutil
from pathlib import Path
import pytest

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), "..", "..", "libs", "devops-kb", "src")
)


class TestKBPreDeploymentChecks:
    """Pre-deployment checks for Knowledge Base configuration."""

    def test_kb_seeder_module_exists(self):
        """Test that KB seeder module can be imported."""
        try:
            from kb_seeder import (
                seed_knowledge_base,
                should_seed_kb,
                should_force_reseed,
                INITIAL_SOLUTIONS,
            )

            assert callable(seed_knowledge_base)
            assert callable(should_seed_kb)
            assert callable(should_force_reseed)
            assert isinstance(INITIAL_SOLUTIONS, list)
        except ImportError as e:
            pytest.fail(f"Failed to import KB seeder module: {e}")

    def test_kb_library_available(self):
        """Test that KB library is available."""
        try:
            from devops_kb.knowledge_base import KnowledgeBase
            from devops_kb.solution import Solution

            assert KnowledgeBase is not None
            assert Solution is not None
        except ImportError as e:
            pytest.fail(f"Failed to import KB library: {e}")

    def test_initial_solutions_valid(self):
        """Test that initial solutions are valid and complete."""
        from kb_seeder import INITIAL_SOLUTIONS

        assert len(INITIAL_SOLUTIONS) > 0, "No initial solutions defined"

        for i, solution in enumerate(INITIAL_SOLUTIONS):
            assert "title" in solution, f"Solution {i} missing 'title'"
            assert "description" in solution, f"Solution {i} missing 'description'"
            assert "tags" in solution, f"Solution {i} missing 'tags'"

            assert solution["title"], f"Solution {i} has empty title"
            assert solution["description"], f"Solution {i} has empty description"
            assert solution["tags"], f"Solution {i} has empty tags list"
            assert isinstance(solution["tags"], list), f"Solution {i} tags not a list"

    def test_kb_can_be_initialized(self):
        """Test that KB can be initialized in temp directory."""
        temp_dir = tempfile.mkdtemp(prefix="kb_test_")
        try:
            from devops_kb.knowledge_base import KnowledgeBase

            kb = KnowledgeBase(temp_dir)
            assert kb is not None
            assert hasattr(kb, "add_solution")
            assert hasattr(kb, "get_all_solutions")
        except Exception as e:
            pytest.fail(f"Failed to initialize KB: {e}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_kb_seeding_can_run(self):
        """Test that KB seeding function can execute successfully."""
        from kb_seeder import seed_knowledge_base
        from devops_kb.knowledge_base import KnowledgeBase

        temp_dir = tempfile.mkdtemp(prefix="kb_seed_test_")
        try:
            kb = KnowledgeBase(temp_dir)
            result = seed_knowledge_base(kb)
            assert isinstance(result, bool)
            assert result is True, "KB seeding failed"
        except Exception as e:
            pytest.fail(f"KB seeding execution failed: {e}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_kb_env_vars_properly_used(self):
        """Test that KB seeding environment variables are being used."""
        import kb_seeder

        # Test that functions exist and are callable
        assert hasattr(kb_seeder, "should_seed_kb")
        assert hasattr(kb_seeder, "should_force_reseed")

        # Test default behavior (when not set)
        os.environ.pop("KB_SEEDING_ENABLED", None)
        os.environ.pop("KB_FORCE_RESEED", None)

        result_seed = kb_seeder.should_seed_kb()
        result_force = kb_seeder.should_force_reseed()

        assert result_seed is False, "Default should_seed_kb should be False"
        assert result_force is False, "Default should_force_reseed should be False"

    def test_deployment_yaml_has_kb_seeding_enabled(self):
        """Test that deployment.yaml has KB seeding enabled."""
        deployment_file = (
            Path(__file__).parent.parent.parent / "k8s" / "deployment.yaml"
        )

        assert deployment_file.exists(), f"Deployment file not found: {deployment_file}"

        with open(deployment_file) as f:
            content = f.read()

        assert (
            "KB_SEEDING_ENABLED" in content
        ), "KB_SEEDING_ENABLED not in deployment.yaml"
        assert "KB_FORCE_RESEED" in content, "KB_FORCE_RESEED not in deployment.yaml"

    def test_pvc_yaml_configured(self):
        """Test that PVC is properly configured for KB storage."""
        pvc_file = Path(__file__).parent.parent.parent / "k8s" / "pvc.yaml"

        assert pvc_file.exists(), f"PVC file not found: {pvc_file}"

        with open(pvc_file) as f:
            content = f.read()

        assert "devops-chatbot-pvc" in content, "PVC name not found"
        assert (
            "25Gi" in content or "storage" in content.lower()
        ), "Storage size not configured"

    def test_solution_schema_valid(self):
        """Test that solution data matches expected schema."""
        from kb_seeder import INITIAL_SOLUTIONS

        required_fields = {"title", "description", "tags"}
        min_title_length = 5
        min_description_length = 20

        for solution in INITIAL_SOLUTIONS:
            # Check required fields
            assert required_fields.issubset(
                solution.keys()
            ), f"Solution missing required fields: {solution.get('title', 'UNKNOWN')}"

            # Check field types
            assert isinstance(
                solution["title"], str
            ), f"Title not string for: {solution}"
            assert isinstance(
                solution["description"], str
            ), f"Description not string for: {solution}"
            assert isinstance(solution["tags"], list), f"Tags not list for: {solution}"

            # Check field lengths
            assert (
                len(solution["title"]) >= min_title_length
            ), f"Title too short: {solution['title']}"
            assert (
                len(solution["description"]) >= min_description_length
            ), f"Description too short for: {solution.get('title')}"

            # Check tags are non-empty strings
            for tag in solution["tags"]:
                assert isinstance(
                    tag, str
                ), f"Tag not string in: {solution.get('title')}"
                assert tag, f"Empty tag in: {solution.get('title')}"

    def test_rag_integration_imports_seeder(self):
        """Test that RAG integration imports KB seeder."""
        try:
            with open(Path(__file__).parent.parent / "rag_integration.py", "r") as f:
                content = f.read()

            assert (
                "kb_seeder" in content or "seed_knowledge_base" in content
            ), "RAG integration does not import KB seeder"
        except Exception as e:
            pytest.fail(f"Failed to check RAG integration: {e}")

    def test_startup_integration_ready(self):
        """Test that startup integration is ready for KB seeding."""
        try:
            from app import startup_event

            assert startup_event is not None
        except Exception as e:
            pytest.fail(f"Failed to import startup event: {e}")


class TestKBPreDeploymentIntegration:
    """Integration tests for pre-deployment KB checks."""

    def test_kb_seeding_workflow(self):
        """Test complete KB seeding workflow."""
        from kb_seeder import seed_knowledge_base
        from devops_kb.knowledge_base import KnowledgeBase

        temp_dir = tempfile.mkdtemp(prefix="kb_workflow_test_")
        try:
            # Create KB
            kb = KnowledgeBase(temp_dir)

            # Seed with initial solutions
            result = seed_knowledge_base(kb)
            assert result is True

            # Verify solutions were added
            solutions = kb.get_all_solutions()
            assert len(solutions) > 0

            # Verify can't re-seed without force
            result = seed_knowledge_base(kb, force_reseed=False)
            assert result is True  # Still succeeds but doesn't add duplicates

            # Verify force reseed works
            result = seed_knowledge_base(kb, force_reseed=True)
            assert result is True

        except Exception as e:
            pytest.fail(f"KB seeding workflow failed: {e}")
        finally:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)

    def test_all_predeploy_requirements(self):
        """Test all pre-deployment requirements are met."""
        checks = {
            "KB seeder module": False,
            "KB library": False,
            "Initial solutions": False,
            "Deployment config": False,
            "PVC config": False,
        }

        try:
            from kb_seeder import INITIAL_SOLUTIONS

            checks["KB seeder module"] = True
        except ImportError:
            pass

        try:
            import devops_kb.knowledge_base  # noqa: F401

            checks["KB library"] = True
        except ImportError:
            pass

        try:
            from kb_seeder import INITIAL_SOLUTIONS

            checks["Initial solutions"] = len(INITIAL_SOLUTIONS) > 0
        except ImportError:
            pass

        deployment_file = (
            Path(__file__).parent.parent.parent / "k8s" / "deployment.yaml"
        )
        checks["Deployment config"] = deployment_file.exists()

        pvc_file = Path(__file__).parent.parent.parent / "k8s" / "pvc.yaml"
        checks["PVC config"] = pvc_file.exists()

        failed_checks = [name for name, passed in checks.items() if not passed]
        assert not failed_checks, f"Pre-deployment checks failed: {failed_checks}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
