# TLS/HTTPS Setup for DevOps Chatbot

## Overview
The ingress is now configured to use HTTPS with automatic HTTP→HTTPS redirect.

## Option 1: Let's Encrypt with cert-manager (Recommended for Production)

### Prerequisites
- cert-manager must be installed in your cluster

### Installation Steps

1. **Install cert-manager** (if not already installed):
```bash
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
```

2. **Create ClusterIssuer for Let's Encrypt**:
```bash
kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: admin@example.com  # Change this
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
    - http01:
        ingress:
          class: traefik
EOF
```

3. **Update ingress.yaml** to use cert-manager:
```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt-prod
spec:
  tls:
  - hosts:
    - your-domain.com
    secretName: devops-chatbot-tls
```

4. **Apply ingress**:
```bash
kubectl apply -f k8s/ingress.yaml
```

cert-manager will automatically create and renew the TLS certificate.

---

## Option 2: Self-Signed Certificate (Testing/Development)

### Generate Self-Signed Certificate

```bash
# Generate private key and certificate (valid for 365 days)
openssl req -x509 -newkey rsa:4096 -keyout tls.key -out tls.crt -days 365 -nodes \
  -subj "/CN=5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com"

# Create Kubernetes secret
kubectl create secret tls devops-chatbot-tls \
  --cert=tls.crt \
  --key=tls.key \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -

# Cleanup
rm tls.key tls.crt
```

### Apply Ingress
```bash
kubectl apply -f k8s/ingress.yaml
```

---

## Option 3: Existing Certificate

If you have an existing TLS certificate from your certificate provider:

```bash
# Create secret from existing certificate and key
kubectl create secret tls devops-chatbot-tls \
  --cert=/path/to/certificate.crt \
  --key=/path/to/private.key \
  -n devops-chatbot \
  --dry-run=client -o yaml | kubectl apply -f -

# Apply ingress
kubectl apply -f k8s/ingress.yaml
```

---

## Verification

### Check Ingress Status
```bash
kubectl get ingress -n devops-chatbot
kubectl describe ingress devops-chatbot -n devops-chatbot
```

### Verify TLS Certificate
```bash
# Check certificate secret exists
kubectl get secret devops-chatbot-tls -n devops-chatbot

# View certificate details
kubectl get secret devops-chatbot-tls -n devops-chatbot -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -text -noout
```

### Test HTTPS Connection
```bash
# Test with curl (ignore self-signed warnings for testing)
curl -k https://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com

# Check HTTP redirect
curl -v http://5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com
# Should see 301/302 redirect to https://...
```

---

## HTTP/HTTPS Redirect

The ingress is configured with Traefik middleware to:
- Accept requests on both http (port 80) and https (port 443)
- Automatically redirect HTTP to HTTPS with a permanent 301 redirect
- Force SSL/TLS for all traffic

---

## Security Headers

To further harden HTTPS, consider adding these annotations to the ingress:

```yaml
annotations:
  # Add security headers
  traefik.ingress.kubernetes.io/router.middlewares: devops-chatbot-secure-headers@kubernetescrd
```

And create a Traefik middleware:

```yaml
apiVersion: traefik.containo.us/v1alpha1
kind: Middleware
metadata:
  name: secure-headers
  namespace: devops-chatbot
spec:
  headers:
    sslRedirect: true
    sslHost: your-domain.com
    sslProxyHeaders:
      X-Forwarded-Proto: https
    stsSeconds: 31536000  # 1 year
    stsIncludeSubdomains: true
    stsPreload: true
```

---

## Troubleshooting

### Certificate Not Issued
```bash
# Check cert-manager logs
kubectl logs -n cert-manager deploy/cert-manager

# Check certificate status
kubectl describe certificate devops-chatbot-tls -n devops-chatbot
```

### HTTP Still Working
If HTTP redirection isn't working, verify:
```bash
# Check Traefik middleware
kubectl get middleware -n devops-chatbot
kubectl describe middleware redirect-https -n devops-chatbot
```

### Self-Signed Certificate Warnings
In browsers or curl, this is expected for self-signed certs. Add `-k` flag to curl or bypass in browser.
For production, use a trusted certificate from Option 1.

---

## Maintenance

### Renewing Self-Signed Certificates
Every 365 days, regenerate and update the secret:
```bash
# Follow Option 2 steps above
```

### Let's Encrypt Certificates
cert-manager automatically renews certificates 30 days before expiration.
Monitor cert-manager logs for any renewal issues.

