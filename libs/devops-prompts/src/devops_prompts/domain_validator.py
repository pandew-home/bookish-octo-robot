"""Domain validation for DevOps queries."""

from typing import Tuple


class DomainValidator:
    """Validate that queries are related to DevOps/Kubernetes/AWS/Helm/ArgoCD/GitOps."""

    # DevOps-related keywords
    DEVOPS_KEYWORDS = {
        # Kubernetes
        "kubernetes",
        "k8s",
        "pod",
        "pods",
        "deployment",
        "deployments",
        "service",
        "services",
        "ingress",
        "configmap",
        "secret",
        "pvc",
        "persistentvolumeclaim",
        "statefulset",
        "daemonset",
        "job",
        "cronjob",
        "namespace",
        "node",
        "nodes",
        "cluster",
        "kubectl",
        "kubelet",
        "apiserver",
        "etcd",
        "container",
        "containers",
        "image",
        "registry",
        "helm",
        "chart",
        "release",
        "argocd",
        "flux",
        "gitops",
        "kyverno",
        "cilium",
        "calico",
        "istio",
        "linkerd",
        "cert-manager",
        "prometheus",
        "grafana",
        "loki",
        "jaeger",
        "vault",
        # AWS
        "aws",
        "eks",
        "ec2",
        "elb",
        "alb",
        "nlb",
        "iam",
        "iam role",
        "irsa",
        "vpc",
        "security group",
        "subnet",
        "route53",
        "s3",
        "rds",
        "dynamodb",
        "lambda",
        "cloudformation",
        "terraform",
        # DevOps concepts
        "deployment",
        "rollout",
        "replica",
        "scale",
        "autoscale",
        "hpa",
        "vpa",
        "resource",
        "cpu",
        "memory",
        "storage",
        "volume",
        "mount",
        "health",
        "liveness",
        "readiness",
        "startup",
        "probe",
        "event",
        "events",
        "log",
        "logs",
        "monitoring",
        "alert",
        "metric",
        "metrics",
        "trace",
        "tracing",
        "debug",
        "troubleshoot",
        "issue",
        "error",
        "failure",
        "crash",
        "restart",
        "pending",
        "terminating",
        "evicted",
        "oom",
        "crashloop",
        "imagepull",
        "network",
        "dns",
        "connectivity",
        "latency",
        "throughput",
        "bandwidth",
        "firewall",
        "policy",
        "rbac",
        "permission",
        "access",
        "authentication",
        "authorization",
        "tls",
        "ssl",
        "certificate",
        "secret",
        "encryption",
        "backup",
        "restore",
        "disaster recovery",
        "ha",
        "high availability",
        "failover",
        "load balancing",
        "service mesh",
        "sidecar",
        "init container",
        "webhook",
        "operator",
        "crd",
        "custom resource",
        "admission",
        "validation",
        "mutation",
        "patch",
        "kustomize",
        "overlay",
        "base",
        "sync",
        "drift",
        "reconciliation",
        "controller",
        "reconcile",
        "finalizer",
        "owner reference",
        "garbage collection",
        "eviction",
        "preemption",
        "priority",
        "qos",
        "request",
        "limit",
        "quota",
        "resource quota",
        "network policy",
        "pod security",
        "pod security policy",
        "pod security standards",
        "securitycontext",
        "runasuser",
        "runasgroup",
        "fsgroup",
        "selinux",
        "apparmor",
        "seccomp",
        "capabilities",
        "privileged",
        "privileged container",
        "container runtime",
        "docker",
        "containerd",
        "cri",
        "oci",
        "image registry",
        "image pull",
        "image push",
        "image scan",
        "vulnerability",
        "cve",
        "security scan",
        "compliance",
        "audit",
        "audit log",
        "api audit",
        "etcd backup",
        "cluster upgrade",
        "version",
        "compatibility",
        "deprecation",
        "migration",
        "workload",
        "workloads",
        "application",
        "app",
        "service",
        "microservice",
        "sidecar",
        "init container",
        "ephemeral container",
        "temporary container",
        "debug container",
        "distroless",
        "scratch",
        "alpine",
        "ubuntu",
        "centos",
        "rhel",
        "debian",
        "busybox",
        "pause",
        "init",
        "systemd",
        "cgroup",
        "namespace",
        "uts namespace",
        "ipc namespace",
        "pid namespace",
        "network namespace",
        "user namespace",
        "mount namespace",
        "cgroup namespace",
        "devops",
        "sre",
        "site reliability",
        "infrastructure",
        "infrastructure as code",
        "iac",
        "configuration management",
        "provisioning",
        "orchestration",
        "automation",
        "ci/cd",
        "continuous integration",
        "continuous deployment",
        "continuous delivery",
        "pipeline",
        "build",
        "test",
        "deploy",
        "release",
        "version control",
        "git",
        "github",
        "gitlab",
        "gitea",
        "bitbucket",
        "branch",
        "merge",
        "pull request",
        "pr",
        "commit",
        "push",
        "pull",
        "rebase",
        "cherry-pick",
        "tag",
        "release tag",
        "semantic versioning",
        "semver",
        "changelog",
        "release notes",
    }

    def is_devops_query(self, query: str) -> bool:
        """Check if query is related to DevOps/Kubernetes/AWS/Helm/ArgoCD/GitOps.

        Args:
            query: User query string

        Returns:
            True if query is DevOps-related, False otherwise
        """
        query_lower = query.lower()

        # Check for DevOps keywords (use word boundaries to avoid partial matches)
        import re
        for keyword in self.DEVOPS_KEYWORDS:
            # Use word boundaries for better matching
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, query_lower):
                return True

        return False

    def get_rejection_message(self) -> str:
        """Get helpful rejection message for non-DevOps queries.

        Returns:
            Rejection message string
        """
        return (
            "I'm specialized in DevOps and Kubernetes troubleshooting. "
            "I can help with:\n"
            "- Kubernetes cluster issues (pods, deployments, services, etc.)\n"
            "- AWS/EKS infrastructure problems\n"
            "- Helm chart deployments and configurations\n"
            "- ArgoCD and GitOps workflows\n"
            "- Container and networking issues\n"
            "- Cluster monitoring and health\n\n"
            "Please ask me about your DevOps or Kubernetes problem!"
        )

    def validate_query(self, query: str) -> Tuple[bool, str]:
        """Validate query and return result with message.

        Args:
            query: User query string

        Returns:
            Tuple of (is_valid, message)
        """
        if self.is_devops_query(query):
            return True, ""
        else:
            return False, self.get_rejection_message()
