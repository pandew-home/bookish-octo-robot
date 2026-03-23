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

    # Unsafe patterns that should be blocked.
    #
    # This is a DevOps chatbot — users WILL ask about kubectl delete, Dockerfile
    # syntax, shell scripts, Python imports, pip install, etc. Block only genuine
    # security threats: credential content leaking to the LLM, root filesystem
    # destruction, and SQL injection (defensive, for future DB integration).
    UNSAFE_PATTERNS = [
        # Actual credentials — never send to LLM
        r"AKIA[0-9A-Z]{16}",                         # AWS access key
        r"-----BEGIN\s+(RSA\s+)?PRIVATE\s+KEY-----", # RSA private key
        r"-----BEGIN\s+EC\s+PRIVATE\s+KEY-----",     # EC private key

        # Genuinely destructive shell — rm targeting root filesystem
        r"\brm\s+-[rf]{1,3}\s+/",                    # rm -rf / or rm -r / etc.
        r":\(\)\s*\{[^}]*\};\s*:",                   # Fork bomb :(){ :|:& };:

        # SQL injection (defensive, in case of future DB integration)
        r"'\s*OR\s+'1'\s*=\s*'1",                    # ' OR '1'='1
        r";\s*DROP\s+TABLE",                          # ; DROP TABLE
        r"\bUNION\s+SELECT\b",                        # UNION SELECT
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
            - cleaned_query: Query with shell-special chars escaped/stripped
        """
        # Strip characters that have no value in natural-language queries but
        # can confuse downstream processing: backticks, null bytes, zero-width
        # spaces.  Everything else (Dockerfile keywords, kubectl flags, $(),
        # shebang lines, etc.) is left intact — this is a DevOps chatbot and
        # users routinely include that kind of syntax in their questions.
        cleaned_query = query.replace("`", "").replace("\x00", "")

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
        if "AKIA" in pattern or "PRIVATE" in pattern or "EC PRIVATE" in pattern:
            return (
                "Your query appears to contain credential material (API keys or private keys). "
                "Please do not paste secrets into your question — describe what you need instead."
            )

        if "rm" in pattern or r":\(" in pattern:
            return (
                "Your query contains a destructive filesystem operation. "
                "Please describe what you are trying to accomplish and I will help safely."
            )

        if "DROP" in pattern or "UNION" in pattern or "OR" in pattern:
            return (
                "Your query contains patterns that look like SQL injection. "
                "Please rephrase your question."
            )

        return (
            "Your query contains a pattern that cannot be processed. "
            "Please rephrase your question."
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
