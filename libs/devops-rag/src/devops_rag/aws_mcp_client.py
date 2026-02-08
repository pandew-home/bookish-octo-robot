"""
AWS MCP Client for EKS context enrichment.

This module provides integration with AWS MCP server to enrich DevOps queries
with AWS infrastructure context for EKS clusters.
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from kubernetes import client, config

logger = logging.getLogger(__name__)


@dataclass
class AWSClusterContext:
    """AWS infrastructure context for EKS clusters"""
    cluster: Dict[str, Any]  # EKS cluster info (arn, name, version, endpoint, platform_version)
    region: str
    node_groups: List[Dict[str, Any]]  # Node group details (instance types, scaling, AMI, health)
    vpc: Dict[str, Any]  # VPC info (vpc_id, cidr_block, subnets)
    security_groups: List[Dict[str, Any]]  # Security group rules
    load_balancers: List[Dict[str, Any]]  # ALB/NLB configurations with target groups


class AWSMCPClient:
    """
    Client for AWS MCP server integration.
    
    Provides EKS-specific context enrichment by calling AWS MCP server
    to retrieve infrastructure details like VPC, security groups, load balancers.
    """
    
    def __init__(
        self,
        mcp_server_url: str = "http://aws-mcp-server.devops-tools.svc:8080",
        timeout: int = 10,
        enabled: Optional[bool] = None,
        credentials: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize AWS MCP client.
        
        Args:
            mcp_server_url: URL of AWS MCP server
            timeout: Request timeout in seconds
            enabled: Override auto-detection of EKS platform
        """
        self.mcp_server_url = mcp_server_url
        self.timeout = timeout
        self.enabled = enabled if enabled is not None else self.is_eks_cluster()
        self.credentials = credentials or None
        self.cluster_name = self._get_cluster_name()
        self.region = self._get_region()
        
        if self.enabled:
            logger.info(f"AWS MCP client enabled for cluster: {self.cluster_name} in region: {self.region}")
        else:
            logger.info("AWS MCP client disabled - not running on EKS")
    
    def is_eks_cluster(self) -> bool:
        """
        Detect if running on EKS platform.
        
        Returns:
            True if running on EKS, False otherwise
        """
        # Check environment variable first
        if os.getenv("CLUSTER_PLATFORM") == "eks":
            return True
        
        # Check for EKS-specific node labels
        try:
            # Try to load in-cluster config first
            try:
                config.load_incluster_config()
            except Exception:
                # Fall back to kubeconfig if not in cluster
                config.load_kube_config()
            
            v1 = client.CoreV1Api()
            nodes = v1.list_node(limit=1)
            if nodes.items:
                node = nodes.items[0]
                labels = node.metadata.labels or {}
                # EKS nodes have eks.amazonaws.com/* labels
                return any(label.startswith("eks.amazonaws.com/") for label in labels)
        except Exception as e:
            logger.warning(f"Failed to detect EKS platform: {e}")
        
        return False
    
    def _get_cluster_name(self) -> str:
        """Get EKS cluster name from environment or kubeconfig"""
        # Try environment variable first
        cluster_name = os.getenv("CLUSTER_NAME")
        if cluster_name:
            return cluster_name
        
        # Try to extract from kubeconfig context
        try:
            contexts, active_context = config.list_kube_config_contexts()
            if active_context and active_context.get('name'):
                # EKS contexts often have format: arn:aws:eks:region:account:cluster/cluster-name
                context_name = active_context['name']
                if '/cluster/' in context_name:
                    return context_name.split('/cluster/')[-1]
                return context_name
        except Exception:
            pass
        
        return os.getenv("CLUSTER_NAME", "unknown-cluster")
    
    def _get_region(self) -> str:
        """Get AWS region from environment or metadata"""
        # Try environment variable first
        region = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
        if region:
            return region
        
        # Try to extract from kubeconfig context (EKS ARN format)
        try:
            contexts, active_context = config.list_kube_config_contexts()
            if active_context and active_context.get('name'):
                context_name = active_context['name']
                # EKS ARN format: arn:aws:eks:region:account:cluster/cluster-name
                if 'arn:aws:eks:' in context_name:
                    parts = context_name.split(':')
                    if len(parts) >= 4:
                        return parts[3]  # region is 4th part
        except Exception:
            pass
        
        return os.getenv("AWS_REGION", "us-east-1")

    def _attach_credentials(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Attach AWS creds to payload if provided (avoid mutating original)."""
        if not self.credentials:
            return payload

        safe_payload = dict(payload)
        params = dict(safe_payload.get("params", {}))
        params["credentials"] = {
            "access_key_id": self.credentials.get("access_key_id"),
            "secret_access_key": self.credentials.get("secret_access_key"),
            "session_token": self.credentials.get("session_token"),
        }
        safe_payload["params"] = params
        return safe_payload
    
    def get_cluster_context(self, cluster_name: Optional[str] = None, region: Optional[str] = None) -> Optional[AWSClusterContext]:
        """
        Get comprehensive AWS context for EKS cluster.
        
        Args:
            cluster_name: EKS cluster name (defaults to auto-detected)
            region: AWS region (defaults to auto-detected)
            
        Returns:
            AWSClusterContext with infrastructure details or None if failed
        """
        if not self.enabled:
            logger.debug("AWS MCP client disabled, skipping context retrieval")
            return None
        
        cluster_name = cluster_name or self.cluster_name
        region = region or self.region
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "action": "get_cluster_context",
                    "params": {
                        "cluster_name": cluster_name,
                        "region": region
                    }
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=self._attach_credentials(payload),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                result = response.json().get("result", {})
                if result:
                    return AWSClusterContext(
                        cluster=result.get("cluster", {}),
                        region=result.get("region", region),
                        node_groups=result.get("node_groups", []),
                        vpc=result.get("vpc", {}),
                        security_groups=result.get("security_groups", []),
                        load_balancers=result.get("load_balancers", [])
                    )
                else:
                    logger.warning("AWS MCP server returned empty result")
                    return None
            else:
                logger.warning(f"AWS MCP server returned {response.status_code}: {response.text}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"AWS MCP server timeout after {self.timeout}s")
            return None
        except requests.exceptions.ConnectionError:
            logger.warning(f"Failed to connect to AWS MCP server at {self.mcp_server_url}")
            return None
        except Exception as e:
            logger.warning(f"Failed to get AWS context: {e}")
            return None
    
    def get_eks_cluster_info(self, cluster_name: Optional[str] = None, region: Optional[str] = None) -> Optional[Dict]:
        """
        Get EKS cluster details.
        
        Args:
            cluster_name: EKS cluster name
            region: AWS region
            
        Returns:
            Dictionary with EKS cluster info or None if failed
        """
        if not self.enabled:
            return None
        
        cluster_name = cluster_name or self.cluster_name
        region = region or self.region
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "action": "get_eks_cluster",
                    "params": {
                        "cluster_name": cluster_name,
                        "region": region
                    }
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=self._attach_credentials(payload),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json().get("result")
            else:
                logger.warning(f"Failed to get EKS cluster info: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to get EKS cluster info: {e}")
            return None
    
    def get_node_groups(self, cluster_name: Optional[str] = None, region: Optional[str] = None) -> List[Dict]:
        """
        Get EKS node group information.
        
        Args:
            cluster_name: EKS cluster name
            region: AWS region
            
        Returns:
            List of node group dictionaries
        """
        if not self.enabled:
            return []
        
        cluster_name = cluster_name or self.cluster_name
        region = region or self.region
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "action": "get_node_groups",
                    "params": {
                        "cluster_name": cluster_name,
                        "region": region
                    }
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=self._attach_credentials(payload),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json().get("result", [])
            else:
                logger.warning(f"Failed to get node groups: {response.status_code}")
                return []
                
        except Exception as e:
            logger.warning(f"Failed to get node groups: {e}")
            return []
    
    def get_vpc_info(self, vpc_id: str, region: Optional[str] = None) -> Optional[Dict]:
        """
        Get VPC and networking details.
        
        Args:
            vpc_id: VPC ID
            region: AWS region
            
        Returns:
            Dictionary with VPC info or None if failed
        """
        if not self.enabled:
            return None
        
        region = region or self.region
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "action": "get_vpc_info",
                    "params": {
                        "vpc_id": vpc_id,
                        "region": region
                    }
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=self._attach_credentials(payload),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json().get("result")
            else:
                logger.warning(f"Failed to get VPC info: {response.status_code}")
                return None
                
        except Exception as e:
            logger.warning(f"Failed to get VPC info: {e}")
            return None
    
    def get_load_balancers(self, cluster_name: Optional[str] = None, region: Optional[str] = None) -> List[Dict]:
        """
        Get cluster load balancers.
        
        Args:
            cluster_name: EKS cluster name
            region: AWS region
            
        Returns:
            List of load balancer dictionaries
        """
        if not self.enabled:
            return []
        
        cluster_name = cluster_name or self.cluster_name
        region = region or self.region
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "action": "get_load_balancers",
                    "params": {
                        "cluster_name": cluster_name,
                        "region": region
                    }
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=self._attach_credentials(payload),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json().get("result", [])
            else:
                logger.warning(f"Failed to get load balancers: {response.status_code}")
                return []
                
        except Exception as e:
            logger.warning(f"Failed to get load balancers: {e}")
            return []
    
    def get_security_groups(self, cluster_name: Optional[str] = None, vpc_id: Optional[str] = None, region: Optional[str] = None) -> List[Dict]:
        """
        Get security groups for cluster.
        
        Args:
            cluster_name: EKS cluster name
            vpc_id: VPC ID to filter security groups
            region: AWS region
            
        Returns:
            List of security group dictionaries
        """
        if not self.enabled:
            return []
        
        cluster_name = cluster_name or self.cluster_name
        region = region or self.region
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "query",
                "params": {
                    "action": "get_security_groups",
                    "params": {
                        "cluster_name": cluster_name,
                        "vpc_id": vpc_id,
                        "region": region
                    }
                },
                "id": 1
            }

            response = requests.post(
                f"{self.mcp_server_url}/",
                json=self._attach_credentials(payload),
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json().get("result", [])
            else:
                logger.warning(f"Failed to get security groups: {response.status_code}")
                return []
                
        except Exception as e:
            logger.warning(f"Failed to get security groups: {e}")
            return []


def format_aws_context(aws_context: AWSClusterContext) -> str:
    """
    Format AWS context for inclusion in LLM prompt.
    
    Args:
        aws_context: AWS cluster context
        
    Returns:
        Formatted string for LLM consumption
    """
    lines = ["# AWS Infrastructure Context"]
    
    # Region info
    lines.append(f"\n**Region**: {aws_context.region}")
    
    # EKS Cluster Info
    if aws_context.cluster:
        lines.append("\n## EKS Cluster")
        cluster = aws_context.cluster
        lines.append(f"- **Name**: {cluster.get('name', 'Unknown')}")
        lines.append(f"- **Version**: {cluster.get('version', 'Unknown')}")
        lines.append(f"- **Platform Version**: {cluster.get('platformVersion', 'Unknown')}")
        lines.append(f"- **Status**: {cluster.get('status', 'Unknown')}")
        lines.append(f"- **Endpoint**: {cluster.get('endpoint', 'Unknown')}")
        lines.append(f"- **ARN**: {cluster.get('arn', 'Unknown')}")
    
    # Node Groups
    if aws_context.node_groups:
        lines.append("\n## Node Groups")
        for ng in aws_context.node_groups:
            lines.append(f"- **{ng.get('nodegroupName', 'Unknown')}**:")
            lines.append(f"  - Instance Types: {', '.join(ng.get('instanceTypes', []))}")
            lines.append(f"  - Capacity Type: {ng.get('capacityType', 'Unknown')}")
            lines.append(f"  - Scaling: {ng.get('scalingConfig', {}).get('minSize', 0)}-{ng.get('scalingConfig', {}).get('maxSize', 0)} nodes")
            lines.append(f"  - Status: {ng.get('status', 'Unknown')}")
            lines.append(f"  - Health: {ng.get('health', {}).get('issues', 'No issues')}")
    
    # VPC Info
    if aws_context.vpc:
        lines.append("\n## VPC Configuration")
        vpc = aws_context.vpc
        lines.append(f"- **VPC ID**: {vpc.get('vpcId', 'Unknown')}")
        lines.append(f"- **CIDR Block**: {vpc.get('cidrBlock', 'Unknown')}")
        if vpc.get('subnets'):
            lines.append("- **Subnets**:")
            for subnet in vpc.get('subnets', []):
                subnet_type = "Public" if subnet.get('mapPublicIpOnLaunch') else "Private"
                lines.append(f"  - {subnet.get('subnetId', 'Unknown')} ({subnet_type}): {subnet.get('cidrBlock', 'Unknown')}")
    
    # Security Groups
    if aws_context.security_groups:
        lines.append("\n## Security Groups")
        for sg in aws_context.security_groups[:5]:  # Limit to first 5 to avoid overwhelming LLM
            lines.append(f"- **{sg.get('groupName', 'Unknown')}** ({sg.get('groupId', 'Unknown')}):")
            lines.append(f"  - Description: {sg.get('description', 'No description')}")
            
            # Ingress rules
            ingress_rules = sg.get('ipPermissions', [])
            if ingress_rules:
                lines.append("  - Ingress Rules:")
                for rule in ingress_rules[:3]:  # Limit rules to avoid clutter
                    protocol = rule.get('ipProtocol', 'Unknown')
                    from_port = rule.get('fromPort', 'Any')
                    to_port = rule.get('toPort', 'Any')
                    sources = []
                    for ip_range in rule.get('ipRanges', []):
                        sources.append(ip_range.get('cidrIp', 'Unknown'))
                    for sg_ref in rule.get('userIdGroupPairs', []):
                        sources.append(f"SG:{sg_ref.get('groupId', 'Unknown')}")
                    source_str = ', '.join(sources) if sources else 'Any'
                    lines.append(f"    - {protocol}:{from_port}-{to_port} from {source_str}")
    
    # Load Balancers
    if aws_context.load_balancers:
        lines.append("\n## Load Balancers")
        for lb in aws_context.load_balancers:
            lines.append(f"- **{lb.get('loadBalancerName', 'Unknown')}**:")
            lines.append(f"  - Type: {lb.get('type', 'Unknown')}")
            lines.append(f"  - Scheme: {lb.get('scheme', 'Unknown')}")
            lines.append(f"  - State: {lb.get('state', {}).get('code', 'Unknown')}")
            lines.append(f"  - DNS Name: {lb.get('dnsName', 'Unknown')}")
    
    return "\n".join(lines)