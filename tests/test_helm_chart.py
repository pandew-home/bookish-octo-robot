"""
Helm chart deployment tests for helm/devops-chatbot/.

Run with:
    pytest tests/test_helm_chart.py -v

Requires: helm 3.14+ on PATH.
"""
import subprocess
import yaml
import pytest
import re
from pathlib import Path

CHART = "helm/devops-chatbot/"
REPO_ROOT = Path(__file__).parent.parent

BASE_FLAGS = [
    "--set", "image.tag=test-sha",
    "--set", "llm.apiKey=placeholder",
    "--set", "llm.createSecret=true",
]


def helm_template(*extra_flags) -> list[dict]:
    """Run helm template and return parsed list of K8s resource dicts."""
    cmd = ["helm", "template", "devops-chatbot", str(REPO_ROOT / CHART)] + BASE_FLAGS + list(extra_flags)
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=REPO_ROOT)
    assert result.returncode == 0, f"helm template failed:\n{result.stderr}"
    docs = list(yaml.safe_load_all(result.stdout))
    return [d for d in docs if d is not None]


def find(docs: list[dict], kind: str, name: str = None) -> dict:
    """Return first matching resource by kind (and optionally name)."""
    for doc in docs:
        if doc.get("kind") == kind:
            if name is None or doc["metadata"]["name"] == name:
                return doc
    raise AssertionError(f"{kind}{' ' + name if name else ''} not found in rendered templates")


# ---------------------------------------------------------------------------
# Lint
# ---------------------------------------------------------------------------

def test_helm_lint_strict_passes():
    result = subprocess.run(
        ["helm", "lint", "--strict", str(REPO_ROOT / CHART)],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )
    assert result.returncode == 0, f"helm lint --strict failed:\n{result.stdout}\n{result.stderr}"


# ---------------------------------------------------------------------------
# Resource inventory
# ---------------------------------------------------------------------------

def test_renders_exactly_8_resource_kinds():
    docs = helm_template("--set", "ingress.enabled=true")
    kinds = sorted({d["kind"] for d in docs})
    assert kinds == [
        "Deployment",
        "Ingress",
        "PersistentVolumeClaim",
        "PodDisruptionBudget",
        "ResourceQuota",
        "Secret",
        "Service",
        "ServiceAccount",
    ], f"Unexpected kinds: {kinds}"


def test_ingress_absent_when_disabled():
    docs = helm_template("--set", "ingress.enabled=false")
    kinds = [d["kind"] for d in docs]
    assert "Ingress" not in kinds


def test_ingress_present_when_enabled():
    docs = helm_template("--set", "ingress.enabled=true")
    ingress = find(docs, "Ingress")
    assert ingress is not None


# ---------------------------------------------------------------------------
# PVC — keep annotation (never deleted on helm uninstall)
# ---------------------------------------------------------------------------

def test_pvc_has_keep_annotation():
    docs = helm_template()
    pvc = find(docs, "PersistentVolumeClaim")
    annotations = pvc["metadata"].get("annotations", {})
    assert annotations.get("helm.sh/resource-policy") == "keep", (
        f"PVC missing 'helm.sh/resource-policy: keep'. Got annotations: {annotations}"
    )


def test_pvc_name_comes_from_values():
    docs = helm_template("--set", "pvc.name=my-custom-pvc")
    pvc = find(docs, "PersistentVolumeClaim")
    assert pvc["metadata"]["name"] == "my-custom-pvc"


# ---------------------------------------------------------------------------
# Secret
# ---------------------------------------------------------------------------

def test_secret_has_all_required_keys():
    docs = helm_template()
    secret = find(docs, "Secret")
    data = secret.get("data", {})
    for key in ("llm-api-key", "llm-provider", "llm-model"):
        assert key in data, f"Secret missing key: {key}. Got: {list(data.keys())}"


def test_secret_name_matches_deployment_envfrom():
    """Deployment envFrom must reference the same secret name rendered by secret.yaml."""
    docs = helm_template()
    secret = find(docs, "Secret")
    secret_name = secret["metadata"]["name"]

    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    env_secret_refs = [
        e["valueFrom"]["secretKeyRef"]["name"]
        for e in chatbot.get("env", [])
        if "valueFrom" in e and "secretKeyRef" in e["valueFrom"]
    ]
    assert secret_name in env_secret_refs, (
        f"Deployment references secret names {env_secret_refs!r} but rendered secret is {secret_name!r}"
    )


# ---------------------------------------------------------------------------
# Deployment — image & labels
# ---------------------------------------------------------------------------

def test_image_tag_rendered_from_values():
    docs = helm_template("--set", "image.tag=abc123")
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    assert chatbot["image"].endswith(":abc123"), f"Unexpected image: {chatbot['image']}"


def test_image_repository_rendered_from_values():
    docs = helm_template("--set", "image.repository=myregistry.io/myapp")
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    assert chatbot["image"].startswith("myregistry.io/myapp:"), f"Unexpected image: {chatbot['image']}"


def test_git_sha_label_in_pod_template():
    docs = helm_template("--set", "podLabels.gitSha=deadbeef")
    deployment = find(docs, "Deployment")
    pod_labels = deployment["spec"]["template"]["metadata"]["labels"]
    assert "git-sha" in pod_labels, f"git-sha label missing from pod template. Labels: {pod_labels}"
    assert pod_labels["git-sha"] == "deadbeef"


def test_replica_count_from_values():
    docs = helm_template("--set", "replicaCount=3")
    deployment = find(docs, "Deployment")
    assert deployment["spec"]["replicas"] == 3


# ---------------------------------------------------------------------------
# Deployment — security context (Kyverno-enforced, must not be removed)
# ---------------------------------------------------------------------------

def test_pod_security_context_run_as_non_root():
    docs = helm_template()
    deployment = find(docs, "Deployment")
    pod_sc = deployment["spec"]["template"]["spec"]["securityContext"]
    assert pod_sc.get("runAsNonRoot") is True
    assert pod_sc.get("runAsUser") == 1000


def test_container_security_context():
    docs = helm_template()
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    sc = chatbot["securityContext"]
    assert sc.get("runAsNonRoot") is True
    assert sc.get("allowPrivilegeEscalation") is False
    assert sc.get("readOnlyRootFilesystem") is True


def test_container_capabilities_drop_all():
    docs = helm_template()
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    drop = chatbot["securityContext"].get("capabilities", {}).get("drop", [])
    assert "ALL" in drop, f"Expected 'ALL' in capabilities.drop, got: {drop}"


# ---------------------------------------------------------------------------
# Deployment — resource requests/limits
# ---------------------------------------------------------------------------

def test_container_has_resource_requests_and_limits():
    docs = helm_template()
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    resources = chatbot.get("resources", {})
    assert "requests" in resources, "Container missing resource requests"
    assert "limits" in resources, "Container missing resource limits"
    assert "cpu" in resources["requests"]
    assert "memory" in resources["requests"]


# ---------------------------------------------------------------------------
# Deployment — probes
# ---------------------------------------------------------------------------

def test_liveness_probe_on_api_health():
    docs = helm_template()
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    probe = chatbot.get("livenessProbe", {})
    assert probe.get("httpGet", {}).get("path") == "/api/health"


def test_readiness_probe_on_api_health_ready():
    docs = helm_template()
    deployment = find(docs, "Deployment")
    containers = deployment["spec"]["template"]["spec"]["containers"]
    chatbot = next(c for c in containers if c["name"] == "chatbot")
    probe = chatbot.get("readinessProbe", {})
    assert probe.get("httpGet", {}).get("path") == "/api/health/ready"


# ---------------------------------------------------------------------------
# Ingress
# ---------------------------------------------------------------------------

def test_ingress_host_from_values():
    docs = helm_template("--set", "ingress.enabled=true", "--set", "ingress.host=chat.example.com")
    ingress = find(docs, "Ingress")
    rules = ingress["spec"].get("rules", [])
    assert any(r.get("host") == "chat.example.com" for r in rules), (
        f"Expected host chat.example.com in ingress rules: {rules}"
    )


def test_ingress_tls_absent_when_disabled():
    docs = helm_template("--set", "ingress.enabled=true", "--set", "ingress.tls.enabled=false")
    ingress = find(docs, "Ingress")
    assert not ingress["spec"].get("tls"), "TLS should be absent when ingress.tls.enabled=false"


def test_ingress_tls_present_when_enabled():
    docs = helm_template(
        "--set", "ingress.enabled=true",
        "--set", "ingress.tls.enabled=true",
        "--set", "ingress.host=chat.example.com",
    )
    ingress = find(docs, "Ingress")
    tls = ingress["spec"].get("tls", [])
    assert tls, "TLS should be present when ingress.tls.enabled=true"
    hosts_in_tls = [h for entry in tls for h in entry.get("hosts", [])]
    assert "chat.example.com" in hosts_in_tls


# ---------------------------------------------------------------------------
# PodDisruptionBudget
# ---------------------------------------------------------------------------

def test_pdb_min_available_from_values():
    docs = helm_template("--set", "pdb.minAvailable=2")
    pdb = find(docs, "PodDisruptionBudget")
    assert pdb["spec"]["minAvailable"] == 2


# ---------------------------------------------------------------------------
# No committed secrets
# ---------------------------------------------------------------------------

def test_no_api_keys_in_chart_files():
    """Ensure no real API key patterns are committed into the chart source."""
    secret_patterns = re.compile(r"sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}")
    chart_dir = REPO_ROOT / CHART
    for path in chart_dir.rglob("*"):
        if path.is_file() and path.suffix in (".yaml", ".yml", ".tpl", ".json"):
            content = path.read_text(errors="replace")
            match = secret_patterns.search(content)
            assert not match, f"Possible API key found in {path.relative_to(REPO_ROOT)}: {match.group()}"


def test_default_llm_api_key_is_empty():
    """values.yaml default for llm.apiKey must be empty string."""
    values_path = REPO_ROOT / CHART / "values.yaml"
    values = yaml.safe_load(values_path.read_text())
    assert values["llm"]["apiKey"] == "", (
        f"llm.apiKey default must be empty string, got: {values['llm']['apiKey']!r}"
    )
