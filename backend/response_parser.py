"""Response parsing and safety detection for LLM responses."""

import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass


@dataclass
class ParsedResponse:
    """Parsed LLM response with extracted components."""
    
    content: str
    recommendations: List[str]
    commands: List[str]
    warnings: List[str]
    safety_notices: List[str]
    kb_citations: List[str]
    k8sgpt_references: List[str]
    has_unsafe_commands: bool


class ResponseParser:
    """Parse and analyze LLM responses for safety and structure."""

    # Unsafe command patterns
    UNSAFE_PATTERNS = [
        r'\b(delete|remove|destroy|drop|prune|purge)\b.*\b(namespace|cluster|database|volume|pvc)\b',
        r'\brm\s+-rf\b',
        r'\bkubectl\s+delete\s+(namespace|pvc|pv)\b',
        r'\bargocd\s+app\s+delete\b',
        r'\bhelm\s+uninstall\b',
        r'\bdocker\s+system\s+prune\b',
        r'\bDROP\s+(DATABASE|TABLE)\b',
        r'\bTRUNCATE\s+TABLE\b',
    ]

    # Command extraction patterns
    COMMAND_PATTERNS = [
        r'```(?:bash|sh|shell)?\s*\n(.*?)```',  # Code blocks
        r'`([^`\n]+)`',  # Inline code (single line only)
    ]

    def __init__(self):
        """Initialize response parser."""
        self.unsafe_regex = re.compile('|'.join(self.UNSAFE_PATTERNS), re.IGNORECASE | re.MULTILINE)

    def parse(self, response: str, kb_results: Optional[List[Dict[str, Any]]] = None) -> ParsedResponse:
        """Parse LLM response and extract components.

        Args:
            response: Raw LLM response text
            kb_results: Knowledge base results used in prompt (for citation matching)

        Returns:
            ParsedResponse with extracted components
        """
        # Extract commands
        commands = self._extract_commands(response)

        # Detect unsafe commands
        has_unsafe = self._detect_unsafe_commands(commands)

        # Extract recommendations
        recommendations = self._extract_recommendations(response)

        # Extract warnings
        warnings = self._extract_warnings(response)

        # Generate safety notices if needed
        safety_notices = []
        if has_unsafe:
            safety_notices = self._generate_safety_notices(commands)

        # Extract KB citations
        kb_citations = self._extract_kb_citations(response, kb_results)

        # Extract K8sGPT references
        k8sgpt_references = self._extract_k8sgpt_references(response)

        return ParsedResponse(
            content=response,
            recommendations=recommendations,
            commands=commands,
            warnings=warnings,
            safety_notices=safety_notices,
            kb_citations=kb_citations,
            k8sgpt_references=k8sgpt_references,
            has_unsafe_commands=has_unsafe
        )

    def _extract_commands(self, response: str) -> List[str]:
        """Extract commands from response.

        Args:
            response: LLM response text

        Returns:
            List of extracted commands
        """
        commands = []

        # Extract from code blocks
        code_block_pattern = r'```(?:bash|sh|shell)?\s*\n(.*?)```'
        matches = re.finditer(code_block_pattern, response, re.MULTILINE | re.DOTALL)
        for match in matches:
            block_content = match.group(1).strip()
            # Split by newlines to get individual commands
            for line in block_content.split('\n'):
                line = line.strip()
                if line and len(line) > 3 and not line.startswith('#'):
                    commands.append(line)

        # Extract inline code
        inline_pattern = r'`([^`\n]+)`'
        matches = re.finditer(inline_pattern, response)
        for match in matches:
            command = match.group(1).strip()
            if command and len(command) > 3:
                commands.append(command)

        # Deduplicate while preserving order
        seen = set()
        unique_commands = []
        for cmd in commands:
            if cmd not in seen:
                seen.add(cmd)
                unique_commands.append(cmd)

        return unique_commands

    def _detect_unsafe_commands(self, commands: List[str]) -> bool:
        """Detect if any commands are potentially unsafe.

        Args:
            commands: List of commands to check

        Returns:
            True if unsafe commands detected
        """
        for command in commands:
            if self.unsafe_regex.search(command):
                return True
        return False

    def _extract_recommendations(self, response: str) -> List[str]:
        """Extract recommendations from response.

        Args:
            response: LLM response text

        Returns:
            List of recommendations
        """
        recommendations = []

        # Look for numbered lists or bullet points in recommendation sections
        patterns = [
            r'(?:Recommended Actions?|Recommendations?|Fix|Solution|Remediation)[:\s]*\n((?:[-*\d.]+\s+.+\n?)+)',
            r'(?:^|\n)(\d+\.\s+.+?)(?=\n\d+\.|\n\n|$)',
            r'(?:^|\n)([-*]\s+.+?)(?=\n[-*]|\n\n|$)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, response, re.MULTILINE | re.IGNORECASE)
            for match in matches:
                rec = match.group(1).strip()
                if rec and len(rec) > 10:  # Filter out very short matches
                    recommendations.append(rec)

        return recommendations[:10]  # Limit to 10 recommendations

    def _extract_warnings(self, response: str) -> List[str]:
        """Extract warnings from response.

        Args:
            response: LLM response text

        Returns:
            List of warnings
        """
        warnings = []

        # Look for warning sections or keywords
        patterns = [
            r'(?:Warning|Caution|Note|Important)[:\s]*(.+?)(?=\n\n|$)',
            r'⚠️\s*(.+?)(?=\n\n|$)',
            r'(?:^|\n)((?:Be careful|Take care|Ensure|Make sure).+?)(?=\n\n|$)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, response, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            for match in matches:
                warning = match.group(1).strip()
                if warning and len(warning) > 10:
                    warnings.append(warning)

        return warnings[:5]  # Limit to 5 warnings

    def _generate_safety_notices(self, commands: List[str]) -> List[str]:
        """Generate safety notices for unsafe commands.

        Args:
            commands: List of commands

        Returns:
            List of safety notices
        """
        notices = []

        for command in commands:
            if self.unsafe_regex.search(command):
                notices.append(
                    f"⚠️ SAFETY WARNING: The command '{command[:50]}...' contains potentially "
                    f"destructive operations. Please review carefully and ensure you have backups "
                    f"before executing. Consider testing in a non-production environment first."
                )

        return notices

    def _extract_kb_citations(
        self,
        response: str,
        kb_results: Optional[List[Dict[str, Any]]]
    ) -> List[str]:
        """Extract knowledge base citations from response.

        Args:
            response: LLM response text
            kb_results: Knowledge base results used in prompt

        Returns:
            List of KB article titles referenced
        """
        if not kb_results:
            return []

        citations = []

        # Look for references to KB article titles
        for result in kb_results:
            title = result.get("title", "")
            if title and title.lower() in response.lower():
                citations.append(title)

        return citations

    def _extract_k8sgpt_references(self, response: str) -> List[str]:
        """Extract K8sGPT finding references from response.

        Args:
            response: LLM response text

        Returns:
            List of K8sGPT references
        """
        references = []

        # Look for K8sGPT mentions
        patterns = [
            r'K8sGPT\s+(?:finding|result|analysis|report)[:\s]*(.+?)(?=\n\n|$)',
            r'(?:According to|Based on)\s+K8sGPT[:\s]*(.+?)(?=\n\n|$)',
        ]

        for pattern in patterns:
            matches = re.finditer(pattern, response, re.MULTILINE | re.IGNORECASE | re.DOTALL)
            for match in matches:
                ref = match.group(1).strip()
                if ref and len(ref) > 10:
                    references.append(ref)

        return references[:5]  # Limit to 5 references

    def add_safety_warnings_to_response(self, parsed: ParsedResponse) -> str:
        """Add safety warnings to response content.

        Args:
            parsed: Parsed response

        Returns:
            Response with safety warnings prepended
        """
        if not parsed.safety_notices:
            return parsed.content

        warnings_section = "\n\n".join(parsed.safety_notices)
        return f"{warnings_section}\n\n---\n\n{parsed.content}"

    def format_response_with_metadata(self, parsed: ParsedResponse) -> Dict[str, Any]:
        """Format parsed response with metadata.

        Args:
            parsed: Parsed response

        Returns:
            Dictionary with response and metadata
        """
        return {
            "content": parsed.content,
            "recommendations": parsed.recommendations,
            "commands": parsed.commands,
            "warnings": parsed.warnings,
            "safety_notices": parsed.safety_notices,
            "kb_citations": parsed.kb_citations,
            "k8sgpt_references": parsed.k8sgpt_references,
            "has_unsafe_commands": parsed.has_unsafe_commands,
            "metadata": {
                "recommendation_count": len(parsed.recommendations),
                "command_count": len(parsed.commands),
                "warning_count": len(parsed.warnings),
                "citation_count": len(parsed.kb_citations),
                "k8sgpt_reference_count": len(parsed.k8sgpt_references),
            }
        }
