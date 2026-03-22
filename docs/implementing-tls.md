# Implementing TLS on the Civo Cluster

## Current State (as of 2026-03-22)

| Component | Status | Notes |
|---|---|---|
| cert-manager | Installed | ClusterIssuers exist but not Ready |
| letsencrypt-prod ClusterIssuer | **Not Ready** | Placeholder email `example.com` |
| letsencrypt-staging ClusterIssuer | **Not Ready** | Same email problem |
| devops-chatbot-tls Certificate | **Not Ready** | Blocked on issuer |
| Traefik Middleware CRDs | **Not installed** | `kubectl api-resources \| grep traefik` returns nothing |
| Ingress | HTTP only | TLS block and redirect stripped |

---

## Step 1 — Fix the cert-manager ClusterIssuer email

The issuers are failing because the email is set to `devops-notifications@example.com`.
Patch both issuers with a real email address:

```bash
kubectl patch clusterissuer letsencrypt-prod --type=merge -p '
{
  "spec": {
    "acme": {
      "email": "your-real-email@example.com"
    }
  }
}'

kubectl patch clusterissuer letsencrypt-staging --type=merge -p '
{
  "spec": {
    "acme": {
      "email": "your-real-email@example.com"
    }
  }
}'
```

Verify both become Ready:

```bash
kubectl get clusterissuer
# Both should show READY=True within ~30 seconds
```

---

## Step 2 — Check Traefik CRD availability

```bash
kubectl api-resources | grep traefik
```

### If nothing shows up (CRDs not installed):

k3s bundles Traefik v2. Apply the Traefik CRDs manually:

```bash
# Check the installed Traefik version first
kubectl get pods -n kube-system -l app.kubernetes.io/name=traefik -o jsonpath='{.items[0].spec.containers[0].image}'

# Apply CRDs for Traefik v2 (traefik.io/v1alpha1)
kubectl apply -f https://raw.githubusercontent.com/traefik/traefik/v2.11/docs/content/reference/dynamic-configuration/kubernetes-crd-definition-v1.yml
```

> **API version note:** This cluster uses the **new** `traefik.io/v1alpha1` group.
> The old `traefik.containo.us/v1alpha1` was deprecated in Traefik v2.10 and removed in v3.
> Use `traefik.io/v1alpha1` in all Middleware manifests.

---

## Step 3 — Update `k8s/ingress.yaml`

Replace the current plain-HTTP ingress with this full TLS version:

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: devops-chatbot
  namespace: devops-chatbot
  labels:
    app: devops-chatbot
  annotations:
    traefik.ingress.kubernetes.io/router.entrypoints: web,websecure
    traefik.ingress.kubernetes.io/router.middlewares: devops-chatbot-redirect-https@kubernetescrd
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  ingressClassName: traefik
  tls:
  - hosts:
    - 5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com
    secretName: devops-chatbot-tls
  rules:
  - host: 5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: devops-chatbot
            port:
              number: 80

---
apiVersion: traefik.io/v1alpha1
kind: Middleware
metadata:
  name: redirect-https
  namespace: devops-chatbot
spec:
  redirectScheme:
    scheme: https
    permanent: true
```

Key differences from the broken original:
- Uses `traefik.io/v1alpha1` (not `traefik.containo.us/v1alpha1`)
- Middleware ref is `devops-chatbot-redirect-https@kubernetescrd` (namespace-prefixed)
- Uses `cert-manager.io/cluster-issuer` annotation (not `issuer`)

---

## Step 4 — Apply and verify

```bash
kubectl apply -f k8s/ingress.yaml

# Watch certificate provisioning
kubectl describe certificate devops-chatbot-tls -n devops-chatbot

# Should go through: Requested → Approved → Issued
# Takes ~60-90 seconds for HTTP-01 ACME challenge
kubectl get certificate -n devops-chatbot
# READY=True means cert is provisioned

# Test HTTPS
curl -I https://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com/api/health

# Test HTTP redirect
curl -I http://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com/
# Should return: HTTP/1.1 301 Moved Permanently
#                Location: https://...
```

---

## If the certificate gets stuck

```bash
# Check cert-manager logs
kubectl logs -n cert-manager deployment/cert-manager | tail -30

# Check the CertificateRequest
kubectl get certificaterequest -n devops-chatbot
kubectl describe certificaterequest -n devops-chatbot

# Check the ACME challenge (HTTP-01 needs port 80 accessible from internet)
kubectl get challenge -n devops-chatbot
kubectl describe challenge -n devops-chatbot
```

Common causes:
- Firewall blocking port 80 on the Civo load balancer (needed for HTTP-01 challenge)
- Issuer still not Ready (check email fix from Step 1)
- Traefik not routing `/.well-known/acme-challenge/` to cert-manager solver pod

---

## Also update the GitHub Actions deploy workflow

Once TLS is live, remove `KB_FORCE_RESEED` guard and update the smoke test to check HTTPS:

```yaml
# In deploy.yml smoke test, add:
curl -sf https://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com/api/health
```
