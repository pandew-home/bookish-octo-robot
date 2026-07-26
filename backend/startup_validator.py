"""
Startup Validator for DevOps Chatbot v2.0

Validates configuration and dependencies on backend startup.
Ensures the application is properly configured before accepting requests.

Requirements: 16.1, 16.2, 16.3, 16.4, 16.5
"""
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def get_data_root() -> Path:
    """Get the root data directory used by startup validation.

    Defaults to /data for cluster deployments, but can be overridden in local
    development using DATA_ROOT.
    """
    return Path(os.getenv("DATA_ROOT", "/data"))


class StartupValidator:
    """
    Validates critical configuration and dependencies on startup.

    Performs checks for:
    - Required environment variables
    - PVC mount and writability
    - Conversation history directory

    Memory is Vestige/noop via MEMORY_BACKEND (not local vector indexes).
    """

    def __init__(self):
        """Initialize startup validator."""
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.validation_complete = False

    def validate(self) -> Tuple[bool, List[str]]:
        """
        Run all startup validation checks.

        Returns:
            Tuple of (is_valid, error_messages)
        """
        logger.info("=" * 80)
        logger.info("Starting startup validation...")
        logger.info("=" * 80)

        self.errors = []
        self.warnings = []

        self._validate_environment_variables()
        self._validate_pvc_mount()
        self._validate_prompt_templates()
        self._log_memory_backend()

        self._log_validation_results()

        self.validation_complete = len(self.errors) == 0
        return self.validation_complete, self.errors

    def _validate_environment_variables(self) -> None:
        """Validate required environment variables are set."""
        logger.info("Checking required environment variables...")

        llm_api_key = (
            os.getenv("LLM_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("ANTHROPIC_API_KEY")
        )

        if not llm_api_key:
            self.errors.append(
                "Missing LLM API key. Set one of: LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY"
            )
            logger.error("✗ LLM API key not found")
        else:
            masked_key = llm_api_key[:8] + "..." if len(llm_api_key) > 8 else "***"
            logger.info(f"✓ LLM API key found: {masked_key}")

        default_region = os.getenv("DEFAULT_REGION")
        if not default_region:
            self.errors.append(
                "Missing DEFAULT_REGION environment variable. Set to AWS region (e.g., us-east-1)"
            )
            logger.error("✗ DEFAULT_REGION not set")
        else:
            logger.info(f"✓ DEFAULT_REGION set: {default_region}")

        llm_provider = os.getenv("LLM_PROVIDER", "openai")
        llm_model = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
        logger.info(f"  LLM_PROVIDER: {llm_provider}")
        logger.info(f"  LLM_MODEL: {llm_model}")

    def _validate_pvc_mount(self) -> None:
        """Validate data directory is mounted and writable."""
        data_path = get_data_root()
        logger.info(f"Checking data directory at {data_path}...")

        if not data_path.exists():
            self.errors.append(
                f"Data directory not mounted: {data_path} does not exist. "
                "Set DATA_ROOT for local development or ensure PVC is mounted in deployment."
            )
            logger.error(f"✗ {data_path} directory not found")
            return

        logger.info(f"✓ {data_path} directory exists")

        if not os.access(data_path, os.W_OK):
            self.errors.append(
                f"Data directory not writable: {data_path} exists but is not writable. "
                "Check volume permissions and security context."
            )
            logger.error(f"✗ {data_path} directory not writable")
            return

        logger.info(f"✓ {data_path} directory is writable")

        test_file = data_path / ".startup_validation_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            logger.info(f"✓ Successfully created and deleted test file in {data_path}")
        except Exception as e:
            self.errors.append(
                f"Data directory write test failed: Cannot write to {data_path}. Error: {str(e)}"
            )
            logger.error(f"✗ Failed to write test file: {e}")
            return

        # Conversation history only; Vestige owns its own PVC/data dir.
        required_dirs = ["conversations"]
        for dir_name in required_dirs:
            dir_path = data_path / dir_name
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"✓ Created directory: {data_path / dir_name}")
                except Exception as e:
                    self.warnings.append(
                        f"Could not create directory {data_path / dir_name}: {str(e)}"
                    )
                    logger.warning(f"⚠ Failed to create {data_path / dir_name}: {e}")
            else:
                logger.info(f"✓ Directory exists: {data_path / dir_name}")

    def _validate_prompt_templates(self) -> None:
        """Prompt templates are no longer used — agentic engine loads system.md."""
        logger.info("Prompt template validation skipped (agentic engine handles prompts)")

    def _log_memory_backend(self) -> None:
        """Log configured memory backend (informational only).

        Default when unset is ``noop``, matching ``memory.get_memory_port``.
        Production charts set ``MEMORY_BACKEND=vestige`` explicitly.
        """
        backend = os.getenv("MEMORY_BACKEND", "noop").lower()
        logger.info(f"  MEMORY_BACKEND: {backend}")
        if backend == "vestige":
            url = os.getenv("VESTIGE_HTTP_URL", "(unset)")
            logger.info(f"  VESTIGE_HTTP_URL: {url}")
        elif backend not in ("noop", "vestige"):
            self.warnings.append(
                f"Unknown MEMORY_BACKEND={backend!r}; expected noop|vestige"
            )

    def _log_validation_results(self) -> None:
        """Log validation results summary."""
        logger.info("=" * 80)
        logger.info("Startup validation complete")
        logger.info("=" * 80)

        if self.errors:
            logger.error(f"✗ Validation FAILED with {len(self.errors)} error(s):")
            for i, error in enumerate(self.errors, 1):
                logger.error(f"  {i}. {error}")
        else:
            logger.info("✓ All critical checks passed")

        if self.warnings:
            logger.warning(f"⚠ {len(self.warnings)} warning(s):")
            for i, warning in enumerate(self.warnings, 1):
                logger.warning(f"  {i}. {warning}")

        logger.info("=" * 80)

    def is_ready(self) -> bool:
        """Check if application is ready to accept requests."""
        return self.validation_complete

    def get_status(self) -> dict:
        """Get detailed validation status."""
        return {
            "validation_complete": self.validation_complete,
            "ready": self.is_ready(),
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": {
                "environment_variables": len(
                    [
                        e
                        for e in self.errors
                        if "environment" in e.lower() or "LLM" in e or "REGION" in e
                    ]
                )
                == 0,
                "pvc_mount": len(
                    [e for e in self.errors if "PVC" in e or "/data" in e or "Data directory" in e]
                )
                == 0,
                "prompt_templates": True,
            },
        }


_validator: Optional[StartupValidator] = None


def get_validator() -> StartupValidator:
    """Get or create global validator instance."""
    global _validator
    if _validator is None:
        _validator = StartupValidator()
    return _validator


def validate_startup() -> Tuple[bool, List[str]]:
    """
    Run startup validation and exit if critical checks fail.
    """
    validator = get_validator()
    is_valid, errors = validator.validate()

    if not is_valid:
        logger.error("=" * 80)
        logger.error("STARTUP VALIDATION FAILED")
        logger.error("=" * 80)
        logger.error("The application cannot start due to configuration errors.")
        logger.error("Please fix the errors above and restart the application.")
        logger.error("=" * 80)
        sys.exit(1)

    return is_valid, errors
