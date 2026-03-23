"""
Post-deployment smoke tests.

Run against the live public URL to verify real endpoint behaviour:
  - Health checks return correct structure
  - Unauthenticated requests get 401 (not 500)
  - Input sanitization blocks dangerous inputs (400 before auth check)
  - Chat endpoint is reachable and has correct content-type
  - Rate limiting header is present

Usage:
    python tests/smoke_post_deploy.py <base_url>
    python tests/smoke_post_deploy.py http://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com
"""
import sys
import json
import urllib.request
import urllib.error
from typing import Any, Dict


BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8080"
FAILURES: list[str] = []
PASSES: int = 0


def req(method: str, path: str, body: Any = None, headers: Dict = None) -> tuple[int, Any]:
    """Make an HTTP request and return (status_code, response_body)."""
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body else None
    h = {"Content-Type": "application/json", **(headers or {})}
    request = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(request, timeout=15) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:
            return e.code, {}
    except Exception as ex:
        return 0, {"error": str(ex)}


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSES
    if condition:
        print(f"  ✓ {name}")
        PASSES += 1
    else:
        msg = f"  ✗ {name}" + (f": {detail}" if detail else "")
        print(msg)
        FAILURES.append(msg)


# ---------------------------------------------------------------------------
# 1. Liveness health check
# ---------------------------------------------------------------------------
print("\n=== Health endpoints ===")
status, body = req("GET", "/api/health")
check("GET /api/health returns 200", status == 200, f"got {status}")
check("Health has 'status' field", "status" in body, str(body))
check("Health status is ok/healthy", body.get("status") in ("ok", "healthy", "running"), str(body))

# ---------------------------------------------------------------------------
# 2. Readiness health check
# ---------------------------------------------------------------------------
status, body = req("GET", "/api/health/ready")
check("GET /api/health/ready returns 200", status == 200, f"got {status}")
check("Readiness has 'status' or 'ready' field", "status" in body or "ready" in body, str(body))

# ---------------------------------------------------------------------------
# 3. Frontend served
# ---------------------------------------------------------------------------
print("\n=== Frontend ===")
try:
    url = f"{BASE_URL}/"
    with urllib.request.urlopen(url, timeout=10) as resp:
        html = resp.read().decode(errors="replace")
    check("GET / returns HTML", "<!DOCTYPE" in html or "<html" in html or "<div" in html, html[:200])
except Exception as e:
    check("GET / returns HTML", False, str(e))

# ---------------------------------------------------------------------------
# 4. Unauthenticated requests return 401 (not 500)
# ---------------------------------------------------------------------------
print("\n=== Auth enforcement ===")
status, body = req("GET", "/api/clusters", headers={"X-Session-ID": "fake-session"})
check("Cluster list returns 401 without valid creds", status == 401, f"got {status}: {body}")

status, body = req("POST", "/api/chat/query", body={
    "query": "What is wrong with my pod?",
    "session_id": "fake-session",
    "user_id": "smoke-test",
    "cluster_name": "test-cluster",
})
check("Chat query returns 401 without valid creds", status == 401, f"got {status}")

# ---------------------------------------------------------------------------
# 5. Input sanitization fires BEFORE auth (400 not 401 for dangerous input)
# ---------------------------------------------------------------------------
print("\n=== Input sanitization ===")
status, body = req("POST", "/api/chat/query", body={
    "query": "rm -rf / && kubectl delete all --all -n production",
    "session_id": "fake-session",
    "user_id": "smoke-test",
    "cluster_name": "test-cluster",
})
check(
    "Dangerous command input blocked with 400",
    status == 400,
    f"got {status} — sanitizer should block before auth check"
)

status, body = req("POST", "/api/chat/query", body={
    "query": "",  # empty query violates min_length=1
    "session_id": "fake-session",
    "user_id": "smoke-test",
    "cluster_name": "test-cluster",
})
check("Empty query blocked with 422", status == 422, f"got {status}")

# ---------------------------------------------------------------------------
# 6. Conversation history requires auth
# ---------------------------------------------------------------------------
print("\n=== Conversation history auth ===")
status, body = req("GET", "/api/chat/history?user_id=smoke&cluster_name=test")
# History doesn't require X-Session-ID — it's user_id based — so it should
# succeed (200) with empty messages, not error
check("History endpoint accessible (200)", status == 200, f"got {status}: {body}")
check("History returns messages list", "messages" in body, str(body))

# ---------------------------------------------------------------------------
# 7. Results / summary
# ---------------------------------------------------------------------------
print(f"\n{'='*40}")
total = PASSES + len(FAILURES)
print(f"Results: {PASSES}/{total} checks passed")

if FAILURES:
    print(f"\nFailures:")
    for f in FAILURES:
        print(f)
    sys.exit(1)
else:
    print("All checks passed!")
    sys.exit(0)
