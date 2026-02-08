"""Template loading and management."""

from pathlib import Path
from typing import Optional, Dict, Any

try:
    import yaml
except ImportError:
    yaml = None


class TemplateLoader:
    """Load and manage query templates from YAML files."""

    def __init__(self, templates_path: str = "/data/knowledge-base/templates"):
        """Initialize template loader.

        Args:
            templates_path: Path to templates directory
        """
        self.templates_path = Path(templates_path)
        self.templates_path.mkdir(parents=True, exist_ok=True)
        self._template_cache: Dict[str, Dict[str, Any]] = {}

    def get_template(self, template_type: str) -> Dict[str, Any]:
        """Get template by type, combining base + specific templates.

        Args:
            template_type: Template type (e.g., "troubleshooting", "networking", "deployment")

        Returns:
            Combined template dictionary
        """
        # Check cache first
        if template_type in self._template_cache:
            return self._template_cache[template_type]

        # Load base template
        base_template = self._load_template_file("base.yaml")
        if not base_template:
            base_template = self._get_default_base_template()

        # Load specific template
        specific_template = self._load_template_file(f"{template_type}.yaml")
        if not specific_template:
            specific_template = self._get_default_template(template_type)

        # Merge templates (specific overrides base)
        merged_template = {**base_template, **specific_template}

        # Cache the result
        self._template_cache[template_type] = merged_template

        return merged_template

    def _load_template_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """Load template from YAML file.

        Args:
            filename: Template filename

        Returns:
            Template dictionary or None if file not found
        """
        template_file = self.templates_path / filename
        if not template_file.exists():
            return None

        try:
            if yaml is None:
                # Fallback to simple JSON parsing if yaml not available
                import json
                with open(template_file, "r") as f:
                    return json.load(f)
            else:
                with open(template_file, "r") as f:
                    return yaml.safe_load(f)
        except Exception:
            return None

    def _get_default_base_template(self) -> Dict[str, Any]:
        """Get default base template.

        Returns:
            Base template dictionary
        """
        return {
            "name": "base",
            "description": "Base template for all queries",
            "system_rules": (
                "You are a Kubernetes troubleshooting assistant for EKS clusters. "
                "Provide clear, actionable advice. "
                "Include specific commands and code examples. "
                "Reference Kubernetes API documentation when relevant. "
                "Reference K8sGPT findings when relevant to the query. "
                "Never fabricate resource names, events, or log entries. "
                "Before recommending actions, evaluate whether the proposed solution contains destructive or irreversible steps (e.g., deleting namespaces/resources, rm -rf, database drops, ArgoCD prune). "
                "If any action cannot be undone, explicitly include a prominent warning at the top of your reply and suggest safer alternatives."
            ),
            "constraints": (
                "Keep responses concise and focused. "
                "Prioritize the most likely root cause. "
                "Suggest verification steps. "
                "Do not omit warnings for destructive/irreversible operations. "
                "Provide rollback or mitigation procedures when possible and require explicit confirmation steps."
            ),
            "output_format": (
                "1. Assessment (2-3 sentences)\n"
                "2. Evidence (data points from cluster context)\n"
                "3. Recommended Fix (step-by-step, prefer IaC/GitOps)\n"
                "4. Safety Notice (if applicable)\n"
                "5. Verification (commands to confirm fix)\n"
                "6. Related KB Articles (if any)"
            ),
        }

    def _get_default_template(self, template_type: str) -> Dict[str, Any]:
        """Get default template for a specific type.

        Args:
            template_type: Template type

        Returns:
            Template dictionary
        """
        templates = {
            "troubleshooting": {
                "name": "troubleshooting",
                "description": "Template for troubleshooting cluster issues",
                "system_rules": (
                    "Focus on identifying the root cause of the problem. "
                    "Provide step-by-step debugging guidance. "
                    "Include kubectl commands and API calls to investigate. "
                    "Reference K8sGPT Result CRDs when available for cluster diagnostics. "
                    "Cite knowledge base sources when used."
                ),
                "constraints": (
                    "Prioritize non-destructive investigation steps. "
                    "Suggest safe remediation actions. "
                    "Include rollback procedures if applicable."
                ),
                "output_format": (
                    "1. Issue Assessment\n"
                    "2. Investigation Steps\n"
                    "3. Root Cause\n"
                    "4. Remediation\n"
                    "5. Verification"
                ),
            },
            "analysis": {
                "name": "analysis",
                "description": "Template for analyzing cluster state and performance",
                "system_rules": (
                    "Provide comprehensive analysis of cluster state. "
                    "Identify trends and patterns. "
                    "Recommend optimizations."
                ),
                "constraints": (
                    "Focus on actionable insights. "
                    "Include metrics and thresholds. "
                    "Suggest monitoring improvements."
                ),
                "output_format": (
                    "1. Current State\n"
                    "2. Trends and Patterns\n"
                    "3. Issues Identified\n"
                    "4. Recommendations\n"
                    "5. Optimization Opportunities"
                ),
            },
            "deployment": {
                "name": "deployment",
                "description": "Template for deployment and configuration issues",
                "system_rules": (
                    "Focus on deployment configuration and best practices. "
                    "Provide Helm and ArgoCD guidance. "
                    "Include GitOps recommendations."
                ),
                "constraints": (
                    "Ensure changes are version-controlled. "
                    "Include rollback procedures. "
                    "Suggest testing strategies."
                ),
                "output_format": (
                    "1. Configuration Assessment\n"
                    "2. Issues Found\n"
                    "3. Recommended Changes\n"
                    "4. Deployment Strategy\n"
                    "5. Verification and Rollback"
                ),
            },
            "gitops": {
                "name": "gitops",
                "description": "Template for GitOps and ArgoCD issues",
                "system_rules": (
                    "Focus on GitOps workflows and ArgoCD/Flux. "
                    "Provide guidance on sync, drift, and reconciliation. "
                    "Include repository structure recommendations."
                ),
                "constraints": (
                    "Ensure all changes are git-tracked. "
                    "Maintain declarative state. "
                    "Include audit trail."
                ),
                "output_format": (
                    "1. GitOps State Assessment\n"
                    "2. Sync Status Analysis\n"
                    "3. Drift Detection\n"
                    "4. Remediation Steps\n"
                    "5. Prevention Measures"
                ),
            },
            "security": {
                "name": "security",
                "description": "Template for security and RBAC issues",
                "system_rules": (
                    "Focus on security best practices and RBAC. "
                    "Provide least-privilege recommendations. "
                    "Include compliance guidance."
                ),
                "constraints": (
                    "Prioritize security over convenience. "
                    "Include audit logging. "
                    "Suggest monitoring and alerting."
                ),
                "output_format": (
                    "1. Security Assessment\n"
                    "2. Vulnerabilities Found\n"
                    "3. RBAC Recommendations\n"
                    "4. Remediation Steps\n"
                    "5. Monitoring and Compliance"
                ),
            },
            "networking": {
                "name": "networking",
                "description": "Template for networking and DNS issues",
                "system_rules": (
                    "Focus on network connectivity, DNS resolution, and service mesh. "
                    "Provide network policy and ingress guidance. "
                    "Include service mesh troubleshooting (Istio, Linkerd, Cilium)."
                ),
                "constraints": (
                    "Prioritize non-disruptive diagnostics. "
                    "Include packet capture and tcpdump guidance. "
                    "Suggest network policy testing."
                ),
                "output_format": (
                    "1. Network Connectivity Assessment\n"
                    "2. DNS Resolution Analysis\n"
                    "3. Service Mesh Status\n"
                    "4. Root Cause\n"
                    "5. Remediation and Verification"
                ),
            },
            "general": {
                "name": "general",
                "description": "General template for miscellaneous queries",
                "system_rules": (
                    "Provide helpful DevOps guidance. "
                    "Ask clarifying questions if needed. "
                    "Suggest relevant resources."
                ),
                "constraints": (
                    "Keep responses focused and actionable. "
                    "Include relevant documentation links."
                ),
                "output_format": (
                    "1. Summary\n"
                    "2. Guidance\n"
                    "3. Next Steps"
                ),
            },
        }

        return templates.get(template_type, {})

    def save_template(self, template_type: str, template_data: Dict[str, Any]) -> bool:
        """Save template to YAML file.

        Args:
            template_type: Template type
            template_data: Template data dictionary

        Returns:
            True if saved successfully, False otherwise
        """
        template_file = self.templates_path / f"{template_type}.yaml"

        try:
            if yaml is None:
                # Fallback to JSON if yaml not available
                import json
                with open(template_file, "w") as f:
                    json.dump(template_data, f, indent=2)
            else:
                with open(template_file, "w") as f:
                    yaml.dump(template_data, f, default_flow_style=False)

            # Clear cache for this template
            if template_type in self._template_cache:
                del self._template_cache[template_type]

            return True
        except Exception:
            return False

    def clear_cache(self) -> None:
        """Clear template cache."""
        self._template_cache.clear()
