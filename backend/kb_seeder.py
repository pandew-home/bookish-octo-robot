"""
Knowledge Base Seeder for DevOps Chatbot v2.0

Seeds the knowledge base with initial DevOps solutions if empty or force-reset.
"""

import logging
import os
from datetime import datetime

from devops_kb.knowledge_base import KnowledgeBase
from devops_kb.solution import Solution

logger = logging.getLogger(__name__)

# Initial seed solutions for DevOps troubleshooting
INITIAL_SOLUTIONS = [
    {
        "title": "Fix Pod CrashLoopBackOff",
        "description": """A pod in CrashLoopBackOff state means the container keeps crashing.

Steps to diagnose and fix:
1. Check pod status: `kubectl describe pod <pod-name> -n <namespace>`
2. View container logs: `kubectl logs <pod-name> -n <namespace>`
3. Check for common issues:
   - Missing environment variables
   - Incorrect image or image pull errors
   - Insufficient resources (memory/CPU)
   - Application startup errors
4. Fix the underlying issue (fix code, add config, adjust resources)
5. Delete the pod to force a restart: `kubectl delete pod <pod-name> -n <namespace>`
6. Verify the pod starts successfully

For persistent debugging, add init containers or modify startup probes.""",
        "tags": ["pod", "crashloopbackoff", "troubleshooting", "logs"],
    },
    {
        "title": "Fix ImagePullBackOff Error",
        "description": """ImagePullBackOff means Kubernetes cannot pull the container image.

Common causes and fixes:
1. Image doesn't exist: Verify the image name and tag in the registry
2. Image registry authentication: Create an image pull secret
   `kubectl create secret docker-registry regcred --docker-server=<registry> --docker-username=<user> --docker-password=<pass>`
3. Private registry access: Add imagePullSecrets to pod spec
4. Rate limiting: Wait before retrying, or use a different image source
5. Network issues: Ensure nodes can reach the registry

Verify the fix:
- Check pod events: `kubectl describe pod <pod-name>`
- Pull the image manually: `docker pull <image>`
- Check registry credentials: `kubectl get secrets`""",
        "tags": ["image", "imagepullbackoff", "registry", "authentication"],
    },
    {
        "title": "Resolve PVC Pending Status",
        "description": """A PersistentVolumeClaim stuck in Pending means no PersistentVolume is available.

Troubleshooting steps:
1. Check PVC status: `kubectl get pvc -n <namespace>`
2. Describe the PVC: `kubectl describe pvc <pvc-name> -n <namespace>`
3. Verify storage class exists: `kubectl get storageclass`
4. Check available PVs: `kubectl get pv`
5. Common issues:
   - Storage class doesn't exist: Create it with `kubectl apply -f storage-class.yaml`
   - No available PV: Create a PersistentVolume or use dynamic provisioning
   - Access mode mismatch: Ensure PV supports the required access mode (ReadWriteOnce, ReadWriteMany, etc.)
   - Storage quota exceeded: Check cluster storage limits

For Kubernetes clusters with dynamic provisioning:
- Ensure the storage driver/provisioner is running
- Check provisioner logs: `kubectl logs -n kube-system -l app=provisioner`""",
        "tags": ["pvc", "storage", "persistent-volume", "pending"],
    },
    {
        "title": "Fix NodeNotReady Status",
        "description": """A node in NotReady state means it's not available for pod scheduling.

Diagnosis and recovery:
1. Check node status: `kubectl describe node <node-name>`
2. Check kubelet status: `ssh <node-ip>` then `systemctl status kubelet`
3. Check kubelet logs: `journalctl -u kubelet -n 100`
4. Common causes:
   - Network issues: Verify node network connectivity
   - Disk pressure: Check disk usage: `df -h`
   - Memory pressure: Check available memory: `free -h`
   - PID pressure: Check process count
   - Kubelet crashed: Restart kubelet: `systemctl restart kubelet`
5. Cordon the node to prevent new pods: `kubectl cordon <node-name>`
6. Drain existing pods: `kubectl drain <node-name> --ignore-daemonsets`
7. Reboot the node if necessary
8. Uncordon when ready: `kubectl uncordon <node-name>`""",
        "tags": ["node", "notready", "kubelet", "network", "resources"],
    },
    {
        "title": "Debug Service DNS Issues",
        "description": """Services not resolving in DNS can prevent inter-pod communication.

Troubleshooting:
1. Test DNS from a pod: `kubectl run -it --rm debug --image=busybox --restart=Never -- sh`
   Inside: `nslookup <service-name>.<namespace>.svc.cluster.local`
2. Check service exists: `kubectl get svc <service-name> -n <namespace>`
3. Check service endpoints: `kubectl get endpoints <service-name> -n <namespace>`
4. Verify pods match selector: `kubectl get pods -l <selector>`
5. Check CoreDNS logs: `kubectl logs -n kube-system -l k8s-app=kube-dns`
6. Common issues:
   - Service selector doesn't match pod labels
   - Pod labels are wrong or missing
   - CoreDNS pod not running or restarted too often
   - Network policy blocking DNS (port 53)
7. Check network policies: `kubectl get networkpolicy -A`

For persistent DNS issues, restart CoreDNS:
`kubectl rollout restart deployment/coredns -n kube-system`""",
        "tags": ["service", "dns", "networking", "coredns", "connectivity"],
    },
    {
        "title": "Handle Pod Eviction and Resource Limits",
        "description": """Pods can be evicted when nodes run low on resources.

Prevention and recovery:
1. Monitor resource usage: `kubectl top pods -n <namespace>`
2. Check node resources: `kubectl top nodes`
3. Set proper resource requests/limits:
   - Requests: Minimum guaranteed resources
   - Limits: Maximum allowed resources
4. Common eviction causes:
   - Memory pressure: Increase memory limit or reduce pod count
   - Disk pressure: Clean up logs and unused data
   - PID pressure: Reduce number of processes
5. Pod Priority and Preemption:
   - Set priorityClassName to protect critical pods
   - Lower priority pods are evicted first
6. Check eviction policies: `kubectl get pods -o json | grep "lastState"`
7. Increase node capacity:
   - Add more nodes to the cluster
   - Use autoscaling for dynamic provisioning

Immediate fix for evicted pod:
- Delete the pod: `kubectl delete pod <pod-name>`
- Wait for controller to restart it with better conditions""",
        "tags": ["eviction", "resources", "memory", "disk", "limits"],
    },
]


def seed_knowledge_base(kb: KnowledgeBase, force_reseed: bool = False) -> bool:
    """
    Seed the knowledge base with initial DevOps solutions.

    Args:
        kb: KnowledgeBase instance to seed
        force_reseed: If True, reseed even if KB already has solutions

    Returns:
        True if seeding was successful, False otherwise
    """
    try:
        # Check if KB already has content
        existing_solutions = kb.get_all_solutions()

        if existing_solutions and not force_reseed:
            logger.info(
                f"Knowledge base already has {len(existing_solutions)} solutions, skipping seed"
            )
            return True

        if force_reseed and existing_solutions:
            logger.info(
                f"Force reseed enabled, clearing {len(existing_solutions)} existing solutions"
            )
            # Note: In production, you'd want to backup first

        logger.info(
            f"Seeding knowledge base with {len(INITIAL_SOLUTIONS)} initial solutions..."
        )

        seeded_count = 0
        for solution_data in INITIAL_SOLUTIONS:
            try:
                # Create Solution object
                solution = Solution(
                    problem_description=solution_data["title"],
                    resolution_steps=solution_data["description"],
                    tags=solution_data["tags"],
                    created_at=datetime.now(),
                )

                # Add to KB
                kb.add_solution(solution)
                logger.info(f"  ✓ Seeded: {solution_data['title']}")
                seeded_count += 1

            except Exception as e:
                logger.error(f"  ✗ Failed to seed '{solution_data['title']}': {e}")
                continue

        logger.info(
            f"Knowledge base seeding complete: {seeded_count}/{len(INITIAL_SOLUTIONS)} solutions added"
        )
        return seeded_count > 0

    except Exception as e:
        logger.error(f"Knowledge base seeding failed: {e}")
        return False


def should_seed_kb() -> bool:
    """
    Check if knowledge base seeding is enabled.

    Returns:
        True if seeding should be performed
    """
    seeding_enabled = os.getenv("KB_SEEDING_ENABLED", "false").lower() in (
        "true",
        "1",
        "yes",
    )
    return seeding_enabled


def should_force_reseed() -> bool:
    """
    Check if force reseed is enabled.

    Returns:
        True if force reseed should be performed
    """
    force_reseed = os.getenv("KB_FORCE_RESEED", "false").lower() in ("true", "1", "yes")
    return force_reseed
