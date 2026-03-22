"""
Input validation and sanitization for user queries.
"""

import re
from typing import Tuple, Optional, Dict, List
import logging

logger = logging.getLogger(__name__)


class InputSanitizer:
    """
    Validate and sanitize user inputs to prevent code injection and ensure safety.

    This class implements comprehensive input validation including:
    - Length validation (1-2000 characters)
    - SQL injection detection
    - Shell command injection detection
    - Code execution pattern detection
    - Credential access attempt detection
    """

    # Unsafe patterns that should be blocked
    UNSAFE_PATTERNS = [
        # Shell commands and execution
        r"#!/bin/(bash|sh)",  # Shebang
        r"\$\([^)]+\)",  # Command substitution $(...)
        r"\b(bash|sh|zsh|fish|ksh|csh|tcsh)\s+-c",  # Shell with -c flag
        r"\b(eval|exec|system|subprocess|popen)\s*\(",  # Code execution functions
        r"\b(kubectl|docker|helm|aws|gcloud|az)\s+(delete|remove|destroy)",  # Destructive commands
        # Code injection
        r"import\s+os",  # OS module import
        r"import\s+subprocess",  # Subprocess import
        r"from\s+os\s+import",  # OS imports
        r"__import__\s*\(",  # Dynamic imports
        r"compile\s*\(",  # Code compilation
        # SQL injection
        r"('\s*OR\s+'1'\s*=\s*'1)",  # Classic SQL injection
        r"(;\s*DROP\s+TABLE)",  # DROP TABLE
        r"(;\s*DELETE\s+FROM)",  # DELETE FROM
        r"(UNION\s+SELECT)",  # UNION SELECT
        # Credential access
        r"/etc/passwd",  # Password file
        r"/etc/shadow",  # Shadow file
        r"\.aws/credentials",  # AWS credentials
        r"\.kube/config",  # Kubeconfig
        r"AKIAIO[A-Z0-9]{14}",  # AWS access key pattern
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----",  # Private keys
        # Dockerfile commands (prevent container escape attempts)
        r"\bFROM\s+",
        r"\bRUN\s+",
        r"\bCMD\s+",
        r"\bENTRYPOINT\s+",
        # Module/package management
        r"\b(pip|npm|yarn|gem|cargo)\s+install",
        r"\brequire\s*\(",  # Node.js require
    ]

    # Compile patterns for efficiency
    _compiled_patterns = [
        re.compile(pattern, re.IGNORECASE) for pattern in UNSAFE_PATTERNS
    ]

    # Patterns to sanitize in logs (replace with [REDACTED])
    SENSITIVE_PATTERNS = [
        r"AKIA[0-9A-Z]{16}",  # AWS access keys
        r"[A-Za-z0-9+/]{40}",  # AWS secret keys (base64-like)
        r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",  # JWT tokens
        r"ghp_[A-Za-z0-9]{36}",  # GitHub personal access tokens
        r"sk-[A-Za-z0-9]{48}",  # OpenAI API keys
    ]

    _sensitive_compiled = [re.compile(pattern) for pattern in SENSITIVE_PATTERNS]

    def validate_query(self, query: str) -> Tuple[bool, Optional[str], str]:
        """
        Validate a user query for safety and correctness.

        Args:
            query: User query string

        Returns:
            Tuple of (is_valid, error_message, cleaned_query)
            - is_valid: True if query is safe, False otherwise
            - error_message: None if valid, descriptive error if invalid
            - cleaned_query: Query with backticks removed
        """
        # Remove backticks (they don't add value to natural language prompts)
        cleaned_query = query.replace("`", "")

        # Check length
        if not cleaned_query or len(cleaned_query.strip()) == 0:
            return (
                False,
                "Query cannot be empty. Please enter a question or command.",
                cleaned_query,
            )

        if len(cleaned_query) > 2000:
            return (
                False,
                f"Query is too long ({len(cleaned_query)} characters). Please limit your query to 2000 characters.",
                cleaned_query,
            )

        # Check for unsafe patterns
        for pattern in self._compiled_patterns:
            if pattern.search(cleaned_query):
                logger.warning(f"Blocked unsafe query pattern: {pattern.pattern}")
                return (
                    False,
                    self._get_helpful_rejection_message(pattern.pattern),
                    cleaned_query,
                )

        return True, None, cleaned_query

    def _get_helpful_rejection_message(self, pattern: str) -> str:
        """
        Get a helpful rejection message based on the blocked pattern.

        Args:
            pattern: The regex pattern that was matched

        Returns:
            User-friendly error message with suggestions
        """
        if "bash" in pattern or "sh" in pattern or "$(" in pattern or "`" in pattern:
            return (
                "Your query contains shell command syntax. "
                "Please rephrase your question in natural language. "
                "For example, instead of 'kubectl get pods', ask 'Show me the pods in the cluster'."
            )

        if "eval" in pattern or "exec" in pattern or "import" in pattern:
            return (
                "Your query contains code execution patterns. "
                "Please ask your question in plain English without code snippets."
            )

        if "kubectl" in pattern or "docker" in pattern or "helm" in pattern:
            if "delete" in pattern or "remove" in pattern or "destroy" in pattern:
                return (
                    "I cannot execute destructive commands directly. "
                    "Please describe what you want to accomplish, and I'll provide safe recommendations."
                )

        if "DROP" in pattern or "DELETE" in pattern or "UNION" in pattern:
            return (
                "Your query contains SQL injection patterns. "
                "Please rephrase your question without SQL syntax."
            )

        if (
            "passwd" in pattern
            or "shadow" in pattern
            or "credentials" in pattern
            or "AKIA" in pattern
        ):
            return (
                "Your query attempts to access sensitive credential information. "
                "This is not allowed for security reasons."
            )

        if "FROM" in pattern or "RUN" in pattern or "CMD" in pattern:
            return (
                "Your query contains Dockerfile syntax. "
                "Please ask your question in natural language instead."
            )

        return (
            "Your query contains potentially unsafe patterns. "
            "Please rephrase your question in plain English without code or commands."
        )

    def sanitize_for_logging(self, text: str) -> str:
        """
        Sanitize text for safe logging by redacting sensitive information.

        Args:
            text: Text to sanitize

        Returns:
            Sanitized text with sensitive data replaced with [REDACTED]
        """
        sanitized = text

        for pattern in self._sensitive_compiled:
            sanitized = pattern.sub("[REDACTED]", sanitized)

        return sanitized

    def validate_aws_credentials(
        self, access_key: str, secret_key: str, session_token: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate AWS credential formats before attempting authentication.

        Args:
            access_key: AWS access key ID
            secret_key: AWS secret access key
            session_token: AWS session token

        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate access key format (AKIA followed by 16 alphanumeric characters)
        if not re.match(r"^AKIA[0-9A-Z]{16}$", access_key):
            return (
                False,
                "Invalid access key format. AWS access keys start with 'AKIA' followed by 16 characters.",
            )

        # Validate secret key length (40 characters)
        if len(secret_key) != 40:
            return (
                False,
                f"Invalid secret key length. AWS secret keys are exactly 40 characters (got {len(secret_key)}).",
            )

        # Validate session token (should be substantial length)
        if len(session_token) < 16:
            return (
                False,
                "Invalid session token. Session tokens should be at least 16 characters.",
            )

        return True, None

    def extract_resource_names(self, query: str) -> dict:
        """
        Extract resource names from query for targeted enrichment.

        Args:
            query: User query string

        Returns:
            Dictionary with extracted resource names:
            - pods: List of pod names
            - deployments: List of deployment names
            - services: List of service names
            - namespaces: List of namespace names
        """
        resources: Dict[str, List[str]] = {
            "pods": [],
            "deployments": [],
            "services": [],
            "namespaces": [],
        }

        # Extract pod names (common patterns)
        pod_patterns = [
            r"pod\s+([a-z0-9-]+)",
            r"pods?\s+named\s+([a-z0-9-]+)",
            r"([a-z0-9-]+-[a-z0-9]{5,10}-[a-z0-9]{5})",  # Pod name pattern
        ]

        for pattern in pod_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            resources["pods"].extend(matches)

        # Extract deployment names
        deployment_patterns = [
            r"deployment\s+([a-z0-9-]+)",
            r"deployments?\s+named\s+([a-z0-9-]+)",
        ]

        for pattern in deployment_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            resources["deployments"].extend(matches)

        # Extract service names
        service_patterns = [
            r"service\s+([a-z0-9-]+)",
            r"services?\s+named\s+([a-z0-9-]+)",
        ]

        for pattern in service_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            resources["services"].extend(matches)

        # Extract namespace names
        namespace_patterns = [
            r"namespace\s+([a-z0-9-]+)",
            r"in\s+([a-z0-9-]+)\s+namespace",
            r"-n\s+([a-z0-9-]+)",
        ]

        for pattern in namespace_patterns:
            matches = re.findall(pattern, query, re.IGNORECASE)
            resources["namespaces"].extend(matches)

        # Remove duplicates
        for key in resources:
            resources[key] = list(set(resources[key]))

        return resources
