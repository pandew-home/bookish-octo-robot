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
from typing import Tuple, List, Optional

logger = logging.getLogger(__name__)


class StartupValidator:
    """
    Validates critical configuration and dependencies on startup.
    
    Performs checks for:
    - Required environment variables
    - PVC mount and writability
    - Prompt template loading
    - FAISS index initialization
    
    If any critical check fails, logs detailed errors and exits with non-zero code.
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
            - is_valid: True if all critical checks pass
            - error_messages: List of error messages (empty if valid)
        """
        logger.info("=" * 80)
        logger.info("Starting startup validation...")
        logger.info("=" * 80)
        
        # Reset state
        self.errors = []
        self.warnings = []
        
        # Run validation checks
        self._validate_environment_variables()
        self._validate_pvc_mount()
        self._validate_prompt_templates()
        self._validate_faiss_index()
        
        # Log results
        self._log_validation_results()
        
        # Mark validation as complete
        self.validation_complete = len(self.errors) == 0
        
        return self.validation_complete, self.errors
    
    def _validate_environment_variables(self) -> None:
        """
        Validate required environment variables are set.
        
        Required variables:
        - LLM_API_KEY or OPENAI_API_KEY or ANTHROPIC_API_KEY: API key for LLM provider
        - DEFAULT_REGION: Default AWS region for operations
        """
        logger.info("Checking required environment variables...")
        
        # Check LLM API key (multiple possible names)
        llm_api_key = (
            os.getenv('LLM_API_KEY') or 
            os.getenv('OPENAI_API_KEY') or 
            os.getenv('ANTHROPIC_API_KEY')
        )
        
        if not llm_api_key:
            self.errors.append(
                "Missing LLM API key. Set one of: LLM_API_KEY, OPENAI_API_KEY, or ANTHROPIC_API_KEY"
            )
            logger.error("✗ LLM API key not found")
        else:
            # Mask the key for logging
            masked_key = llm_api_key[:8] + "..." if len(llm_api_key) > 8 else "***"
            logger.info(f"✓ LLM API key found: {masked_key}")
        
        # Check DEFAULT_REGION
        default_region = os.getenv('DEFAULT_REGION')
        if not default_region:
            self.errors.append(
                "Missing DEFAULT_REGION environment variable. Set to AWS region (e.g., us-east-1)"
            )
            logger.error("✗ DEFAULT_REGION not set")
        else:
            logger.info(f"✓ DEFAULT_REGION set: {default_region}")
        
        # Check optional but recommended variables
        llm_provider = os.getenv('LLM_PROVIDER', 'openai')
        llm_model = os.getenv('LLM_MODEL', 'gpt-3.5-turbo')
        logger.info(f"  LLM_PROVIDER: {llm_provider}")
        logger.info(f"  LLM_MODEL: {llm_model}")
    
    def _validate_pvc_mount(self) -> None:
        """
        Validate PVC is mounted at /data and writable.
        
        Checks:
        - /data directory exists
        - /data is writable
        - Can create test file
        """
        logger.info("Checking PVC mount at /data...")
        
        data_path = Path("/data")
        
        # Check if directory exists
        if not data_path.exists():
            self.errors.append(
                "PVC not mounted: /data directory does not exist. "
                "Ensure PVC is mounted at /data in deployment manifest."
            )
            logger.error("✗ /data directory not found")
            return
        
        logger.info("✓ /data directory exists")
        
        # Check if directory is writable
        if not os.access(data_path, os.W_OK):
            self.errors.append(
                "PVC not writable: /data directory exists but is not writable. "
                "Check volume permissions and security context."
            )
            logger.error("✗ /data directory not writable")
            return
        
        logger.info("✓ /data directory is writable")
        
        # Try to create a test file
        test_file = data_path / ".startup_validation_test"
        try:
            test_file.write_text("test")
            test_file.unlink()
            logger.info("✓ Successfully created and deleted test file in /data")
        except Exception as e:
            self.errors.append(
                f"PVC write test failed: Cannot write to /data directory. Error: {str(e)}"
            )
            logger.error(f"✗ Failed to write test file: {e}")
            return
        
        # Check for required subdirectories and create if missing
        required_dirs = [
            "knowledge_base",
            "knowledge_base/templates",
            "faiss_index",
            "conversations"
        ]
        
        for dir_name in required_dirs:
            dir_path = data_path / dir_name
            if not dir_path.exists():
                try:
                    dir_path.mkdir(parents=True, exist_ok=True)
                    logger.info(f"✓ Created directory: /data/{dir_name}")
                except Exception as e:
                    self.warnings.append(
                        f"Could not create directory /data/{dir_name}: {str(e)}"
                    )
                    logger.warning(f"⚠ Failed to create /data/{dir_name}: {e}")
            else:
                logger.info(f"✓ Directory exists: /data/{dir_name}")
    
    def _validate_prompt_templates(self) -> None:
        """
        Validate prompt templates can be loaded.
        
        Checks:
        - Template directory exists
        - Required templates are present
        - Templates can be loaded and parsed
        """
        logger.info("Checking prompt templates...")
        
        templates_path = Path("/data/knowledge_base/templates")
        
        # Check if templates directory exists
        if not templates_path.exists():
            self.warnings.append(
                f"Templates directory not found: {templates_path}. "
                "Templates will be loaded from default location."
            )
            logger.warning(f"⚠ Templates directory not found: {templates_path}")
            # This is a warning, not an error - templates can be loaded from defaults
            return
        
        logger.info(f"✓ Templates directory exists: {templates_path}")
        
        # Try to load templates using TemplateEngine
        try:
            from template_engine import TemplateEngine
            
            template_engine = TemplateEngine(str(templates_path))
            is_valid, error_msg = template_engine.validate_templates()
            
            if not is_valid:
                self.warnings.append(
                    f"Template validation failed: {error_msg}. "
                    "Will attempt to use default templates."
                )
                logger.warning(f"⚠ Template validation failed: {error_msg}")
            else:
                logger.info("✓ All required templates loaded and validated")
                
        except Exception as e:
            self.warnings.append(
                f"Could not validate templates: {str(e)}. "
                "Will attempt to use default templates."
            )
            logger.warning(f"⚠ Template validation error: {e}")
    
    def _validate_faiss_index(self) -> None:
        """
        Validate FAISS index exists or can be created.
        
        Checks:
        - FAISS index directory exists
        - Can initialize FAISS index
        - If index doesn't exist, can create new one
        """
        logger.info("Checking FAISS index...")
        
        faiss_path = Path("/data/faiss_index")
        
        # Check if FAISS directory exists
        if not faiss_path.exists():
            try:
                faiss_path.mkdir(parents=True, exist_ok=True)
                logger.info(f"✓ Created FAISS index directory: {faiss_path}")
            except Exception as e:
                self.errors.append(
                    f"Cannot create FAISS index directory: {str(e)}"
                )
                logger.error(f"✗ Failed to create FAISS directory: {e}")
                return
        
        logger.info(f"✓ FAISS index directory exists: {faiss_path}")
        
        # Check if index file exists
        index_file = faiss_path / "index.faiss"
        metadata_file = faiss_path / "metadata.json"
        
        if index_file.exists() and metadata_file.exists():
            logger.info("✓ Existing FAISS index found")
            
            # Try to load the index to verify it's valid
            try:
                import faiss
                import json
                
                # Load index
                index = faiss.read_index(str(index_file))
                logger.info(f"✓ FAISS index loaded successfully ({index.ntotal} vectors)")
                
                # Load metadata
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)
                logger.info(f"✓ FAISS metadata loaded ({len(metadata)} entries)")
                
            except ImportError:
                self.warnings.append(
                    "FAISS library not installed. Semantic search will be unavailable. "
                    "Install with: pip install faiss-cpu"
                )
                logger.warning("⚠ FAISS library not available")
            except Exception as e:
                self.warnings.append(
                    f"Could not load existing FAISS index: {str(e)}. "
                    "A new index will be created on first use."
                )
                logger.warning(f"⚠ Failed to load FAISS index: {e}")
        else:
            logger.info("ℹ No existing FAISS index found - will be created on first use")
            
            # Verify we can create a new index
            try:
                import faiss
                
                # Create a small test index
                test_index = faiss.IndexFlatL2(128)  # Small dimension for test
                test_file = faiss_path / ".test_index"
                faiss.write_index(test_index, str(test_file))
                test_file.unlink()
                
                logger.info("✓ FAISS index can be created successfully")
                
            except ImportError:
                self.warnings.append(
                    "FAISS library not installed. Semantic search will be unavailable. "
                    "Install with: pip install faiss-cpu"
                )
                logger.warning("⚠ FAISS library not available")
            except Exception as e:
                self.warnings.append(
                    f"Could not create test FAISS index: {str(e)}. "
                    "Semantic search may not work properly."
                )
                logger.warning(f"⚠ Failed to create test FAISS index: {e}")
    
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
        """
        Check if application is ready to accept requests.
        
        Returns:
            True if validation completed successfully
        """
        return self.validation_complete
    
    def get_status(self) -> dict:
        """
        Get detailed validation status.
        
        Returns:
            Dictionary with validation status and details
        """
        return {
            "validation_complete": self.validation_complete,
            "ready": self.is_ready(),
            "errors": self.errors,
            "warnings": self.warnings,
            "checks": {
                "environment_variables": len([e for e in self.errors if "environment" in e.lower() or "LLM" in e or "REGION" in e]) == 0,
                "pvc_mount": len([e for e in self.errors if "PVC" in e or "/data" in e]) == 0,
                "prompt_templates": len([e for e in self.errors if "template" in e.lower()]) == 0,
                "faiss_index": len([e for e in self.errors if "FAISS" in e]) == 0
            }
        }


# Global validator instance
_validator: Optional[StartupValidator] = None


def get_validator() -> StartupValidator:
    """
    Get or create global validator instance.
    
    Returns:
        StartupValidator instance
    """
    global _validator
    
    if _validator is None:
        _validator = StartupValidator()
    
    return _validator


def validate_startup() -> Tuple[bool, List[str]]:
    """
    Run startup validation and exit if critical checks fail.
    
    This function should be called during application startup.
    If validation fails, it will log errors and exit with code 1.
    
    Returns:
        Tuple of (is_valid, error_messages)
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
