# Cluster Failure Scenarios for Testing

This document provides step-by-step instructions for creating various Kubernetes cluster failure scenarios that can be tested with the DevOps Chatbot v2.0 Playwright test suite.

## Prerequisites

1. **Kubernetes Cluster**: A test cluster with K8sGPT operator installed
2. **Test Application**: Deploy a sample application for testing
3. **K8sGPT Setup**: Ensure K8sGPT is scanning and producing results
4. **Playwright Tests**: The test suite configured and ready

## Sample Application Deployment

First, deploy a test application that we can break in various ways:

```yaml
# test-app.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: test-app
  namespace: default
spec:
  replicas: 2
  selector:
    matchLabels:
      app: test-app
  template:
    metadata:
      labels:
        app: test-app
    spec:
      containers:
      - name: nginx
        image: nginx:1.21
        ports:
        - containerPort: 80
        resources:
          requests:
            memory: "64Mi"
            cpu: "100m"
          limits:
            memory: "128Mi"
            cpu: "200m"

---
apiVersion: v1
kind: Service
metadata:
  name: test-app-service
  namespace: default
spec:
  selector:
    app: test-app
  ports:
    - port: 80
      targetPort: 80
  type: ClusterIP
```

```bash
kubectl apply -f test-app.yaml
```

## Failure Scenario 1: Pod CrashLoopBackOff

### How to Create the Failure
```bash
# Edit the deployment to cause a crash
kubectl patch deployment test-app -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "nginx",
          "command": ["sh", "-c", "exit 1"]
        }]
      }
    }
  }
}'
```

### Expected Test Results
- Weather widget shows "cloudy" or "stormy" state
- K8sGPT detects CrashLoopBackOff analyzer result
- Chat query "nginx pod is crashing" returns diagnosis with K8sGPT findings
- Safety notices may appear for suggested fixes

### Test Commands
```bash
# Run the specific chat test
npm run test:e2e -- --grep "pod crash troubleshooting"

# Run weather widget test
npm run test:e2e -- --grep "cloudy weather"
```

### Cleanup
```bash
kubectl rollout undo deployment test-app
```

## Failure Scenario 2: Image Pull BackOff

### How to Create the Failure
```bash
# Use a non-existent image
kubectl set image deployment/test-app nginx=nginx:nonexistent-tag-12345
```

### Expected Test Results
- Pods enter ImagePullBackOff status
- K8sGPT detects image pull issues
- Chat queries about "image pull" or "pod pending" show relevant findings
- Weather state reflects the issue severity

### Test Commands
```bash
npm run test:e2e -- --grep "image pull"
```

### Cleanup
```bash
kubectl set image deployment/test-app nginx=nginx:1.21
```

## Failure Scenario 3: Resource Exhaustion (OOM)

### How to Create the Failure
```bash
# Create a memory-hungry pod
kubectl run memory-hog --image=polinux/stress -- stress --vm 1 --vm-bytes 200M --timeout 60s
```

### Expected Test Results
- Pod gets OOMKilled
- K8sGPT detects resource exhaustion
- Chat queries about "memory" or "OOM" return relevant analysis
- Weather widget shows increased issue count

### Test Commands
```bash
npm run test:e2e -- --grep "storage issues"
```

## Failure Scenario 4: Node Not Ready

### How to Create the Failure
```bash
# Cordon a node (simulates maintenance mode)
kubectl cordon $(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')

# Or simulate by stopping kubelet (if you have access)
# systemctl stop kubelet
```

### Expected Test Results
- Node shows NotReady status
- K8sGPT detects node health issues
- Weather widget shows "stormy" state with critical issues
- Chat queries about "node not ready" provide diagnosis

### Test Commands
```bash
npm run test:e2e -- --grep "node health issues"
```

### Cleanup
```bash
kubectl uncordon $(kubectl get nodes -o jsonpath='{.items[0].metadata.name}')
```

## Failure Scenario 5: Deployment Unavailable

### How to Create the Failure
```bash
# Scale deployment to 0 replicas
kubectl scale deployment test-app --replicas=0

# Or create resource constraint
kubectl patch deployment test-app -p '{
  "spec": {
    "template": {
      "spec": {
        "containers": [{
          "name": "nginx",
          "resources": {
            "requests": {"cpu": "1000", "memory": "100Gi"}
          }
        }]
      }
    }
  }
}'
```

### Expected Test Results
- Deployment shows unavailable replicas
- K8sGPT detects deployment issues
- Chat queries about "deployment unavailable" return analysis
- Weather state reflects deployment problems

### Test Commands
```bash
npm run test:e2e -- --grep "deployment unavailable"
```

### Cleanup
```bash
kubectl scale deployment test-app --replicas=2
kubectl patch deployment test-app --type json -p='[{"op": "remove", "path": "/spec/template/spec/containers/0/resources"}]'
```

## Failure Scenario 6: PVC Pending

### How to Create the Failure
```yaml
# Create a PVC that can't be bound
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: test-pvc
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 1000Gi  # Request more than available
  storageClassName: default
```

```bash
kubectl apply -f pvc-test.yaml
```

### Expected Test Results
- PVC remains in Pending status
- K8sGPT detects storage issues
- Chat queries about "PVC pending" or "storage" show findings
- Weather widget includes storage-related issues

### Test Commands
```bash
npm run test:e2e -- --grep "storage issues"
```

### Cleanup
```bash
kubectl delete pvc test-pvc
```

## Failure Scenario 7: Service Networking Issues

### How to Create the Failure
```bash
# Delete the service endpoint
kubectl delete service test-app-service

# Or create a service with wrong selector
kubectl patch service test-app-service -p '{
  "spec": {
    "selector": {
      "app": "nonexistent-app"
    }
  }
}'
```

### Expected Test Results
- Service has no endpoints
- K8sGPT may detect service issues
- Chat queries about "service connectivity" or "networking" provide analysis

### Test Commands
```bash
npm run test:e2e -- --grep "network connectivity"
```

### Cleanup
```bash
kubectl patch service test-app-service -p '{
  "spec": {
    "selector": {
      "app": "test-app"
    }
  }
}'
```

## Failure Scenario 8: RBAC Permission Denied

### How to Create the Failure
```bash
# Create a service account with insufficient permissions
kubectl create serviceaccount test-sa

# Try to access resources it can't access (this will be detected by K8sGPT if configured)
```

### Expected Test Results
- Permission denied errors in pod logs/events
- K8sGPT detects RBAC issues
- Chat queries about "access denied" or "RBAC" return security analysis

### Test Commands
```bash
npm run test:e2e -- --grep "RBAC permission"
```

## Failure Scenario 9: Certificate/TLS Issues

### How to Create the Failure
```bash
# Create an ingress with expired certificate
# Or modify webhook configurations with invalid certs
kubectl patch validatingwebhookconfiguration k8sgpt-webhook -p '{
  "webhooks": [{
    "clientConfig": {
      "caBundle": "invalid-cert-data"
    }
  }]
}'
```

### Expected Test Results
- TLS validation failures
- K8sGPT detects certificate issues
- Chat queries about "certificate" or "TLS" provide diagnosis

## Failure Scenario 10: DNS Resolution Issues

### How to Create the Failure
```bash
# Break CoreDNS (if using default)
kubectl scale deployment coredns -n kube-system --replicas=0

# Or create a service that can't resolve
```

### Expected Test Results
- DNS resolution failures
- Service connectivity issues
- K8sGPT detects networking problems

### Test Commands
```bash
npm run test:e2e -- --grep "network connectivity"
```

### Cleanup
```bash
kubectl scale deployment coredns -n kube-system --replicas=2
```

## Running Tests Against Failures

### Automated Test Execution
```bash
# Run all error scenario tests
npm run test:e2e -- error-scenarios.spec.ts

# Run specific failure type
npm run test:e2e -- --grep "pod crash"

# Run with debugging
npm run test:e2e:debug -- --grep "deployment unavailable"
```

### Manual Test Verification
1. Create the failure scenario
2. Wait for K8sGPT to detect and analyze (usually 30-60 seconds)
3. Run the Playwright tests
4. Check the HTML report for screenshots and traces
5. Verify that:
   - Weather widget shows appropriate state
   - Chat responses include K8sGPT findings
   - Citations are displayed when available
   - Safety notices appear for destructive suggestions

### Observing Test Results

#### Weather Widget Changes
- **Sunny**: 0 issues
- **Cloudy**: 1-2 warnings or 3-5 issues
- **Stormy**: 2+ critical issues or 6+ total issues

#### Chat Response Validation
- Check for K8sGPT finding integration
- Verify citation display
- Confirm safety notice presence
- Validate response accuracy

#### Error Handling
- Network failures should show connection errors
- Authentication issues should redirect to login
- RBAC problems should show permission errors

## Test Data Correlation

The test mocks should reflect real K8sGPT CRD structures:

```yaml
# Example K8sGPT Result CRD
apiVersion: core.k8sgpt.ai/v1alpha1
kind: Result
metadata:
  name: pod-crashloopbackoff
spec:
  kind: Pod
  name: test-app-12345
  namespace: default
  details: |
    Pod is in CrashLoopBackOff state
    Last termination reason: Error
    Exit code: 1
  severity: "medium"
  analyzer: "podAnalyzer"
  parentObject: "test-app"
```

## Performance Testing

### K8sGPT Detection Time
- Measure time from failure creation to K8sGPT result creation
- Verify weather widget updates within polling interval (60s)
- Test chat response times with K8sGPT integration

### Test Execution Performance
- Full test suite should complete in <10 minutes
- Individual tests should complete in <30 seconds
- Parallel execution should improve overall runtime

## Troubleshooting Test Issues

### Common Problems
1. **K8sGPT not detecting issues**: Check operator configuration and analyzers
2. **Weather widget not updating**: Verify API endpoints and polling
3. **Chat responses missing findings**: Check mock data and API integration
4. **Tests timing out**: Increase timeouts or check network connectivity

### Debug Commands
```bash
# Check K8sGPT results
kubectl get results.core.k8sgpt.ai -A

# View specific result
kubectl describe result.core.k8sgpt.ai <result-name>

# Check chatbot logs
kubectl logs -l app=devops-chatbot

# Run tests with verbose output
DEBUG=pw:api npm run test:e2e
```

This comprehensive set of failure scenarios allows you to thoroughly test the DevOps Chatbot's ability to handle real-world Kubernetes issues, ensuring it provides accurate diagnoses and helpful recommendations to operators.