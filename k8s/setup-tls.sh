#!/bin/bash
# TLS Setup Script for DevOps Chatbot
# Supports: Let's Encrypt with cert-manager, Self-signed certificates, or existing certificates

set -e

NAMESPACE="devops-chatbot"
SECRET_NAME="devops-chatbot-tls"
DOMAIN="${DOMAIN:-5f361a88-3ba6-486a-990a-f146df27e219.k8s.civo.com}"
EMAIL="${EMAIL:-admin@example.com}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================="
echo "DevOps Chatbot TLS Setup"
echo "=================================="
echo ""

# Function to print colored output
print_info() {
    echo -e "${GREEN}✓${NC} $1"
}

print_warn() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Check if kubectl is available
if ! command -v kubectl &> /dev/null; then
    print_error "kubectl not found. Please install kubectl first."
    exit 1
fi

# Check if namespace exists
if ! kubectl get namespace $NAMESPACE &> /dev/null; then
    print_error "Namespace '$NAMESPACE' not found. Please create it first."
    exit 1
fi

echo "1. Choose TLS setup method:"
echo "   a) Let's Encrypt (cert-manager) - Recommended for production"
echo "   b) Self-signed certificate - For testing/development"
echo "   c) Existing certificate - If you have your own cert"
echo ""
read -p "Choose option (a/b/c): " OPTION

case $OPTION in
    a)
        echo ""
        print_info "Setting up Let's Encrypt with cert-manager..."

        # Check if cert-manager is installed
        if ! kubectl get ns cert-manager &> /dev/null; then
            print_warn "cert-manager not found. Installing..."
            kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.13.0/cert-manager.yaml
            print_info "Waiting for cert-manager to be ready..."
            kubectl wait --for=condition=Ready pod -l app.kubernetes.io/name=cert-manager -n cert-manager --timeout=300s 2>/dev/null || true
        else
            print_info "cert-manager already installed"
        fi

        # Create ClusterIssuer
        echo ""
        read -p "Enter your email for Let's Encrypt notifications [$EMAIL]: " EMAIL_INPUT
        EMAIL="${EMAIL_INPUT:-$EMAIL}"

        print_info "Creating Let's Encrypt ClusterIssuer..."
        kubectl apply -f - <<EOF
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: $EMAIL
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
    - http01:
        ingress:
          class: traefik
EOF

        # Update ingress with cert-manager annotation
        print_info "Updating ingress with cert-manager configuration..."
        kubectl annotate ingress devops-chatbot -n $NAMESPACE \
            cert-manager.io/cluster-issuer=letsencrypt-prod \
            --overwrite 2>/dev/null || true

        print_info "Let's Encrypt setup complete!"
        print_warn "Note: Certificate issuance may take a few minutes. Monitor with:"
        echo "    kubectl describe certificate devops-chatbot-tls -n $NAMESPACE"
        ;;

    b)
        echo ""
        print_info "Generating self-signed certificate..."

        # Generate self-signed certificate
        CERT_FILE="/tmp/tls-$RANDOM.crt"
        KEY_FILE="/tmp/tls-$RANDOM.key"

        openssl req -x509 -newkey rsa:4096 -keyout "$KEY_FILE" -out "$CERT_FILE" \
            -days 365 -nodes -subj "/CN=$DOMAIN" 2>/dev/null

        print_info "Certificate generated: $CERT_FILE"
        print_info "Private key generated: $KEY_FILE"

        # Create or update secret
        if kubectl get secret $SECRET_NAME -n $NAMESPACE &>/dev/null 2>&1; then
            print_info "Updating existing TLS secret..."
            kubectl delete secret $SECRET_NAME -n $NAMESPACE
        fi

        print_info "Creating TLS secret..."
        kubectl create secret tls $SECRET_NAME \
            --cert="$CERT_FILE" \
            --key="$KEY_FILE" \
            -n $NAMESPACE

        # Cleanup temp files
        rm -f "$CERT_FILE" "$KEY_FILE"

        print_info "Self-signed certificate setup complete!"
        print_warn "Note: Browsers will show certificate warnings. Use -k flag with curl to ignore."
        echo "    curl -k https://$DOMAIN"
        ;;

    c)
        echo ""
        read -p "Enter path to certificate file (.crt/.pem): " CERT_FILE
        read -p "Enter path to private key file (.key): " KEY_FILE

        if [ ! -f "$CERT_FILE" ] || [ ! -f "$KEY_FILE" ]; then
            print_error "Certificate or key file not found"
            exit 1
        fi

        print_info "Creating TLS secret from existing certificate..."

        # Delete existing secret if it exists
        if kubectl get secret $SECRET_NAME -n $NAMESPACE &>/dev/null 2>&1; then
            print_info "Updating existing TLS secret..."
            kubectl delete secret $SECRET_NAME -n $NAMESPACE
        fi

        kubectl create secret tls $SECRET_NAME \
            --cert="$CERT_FILE" \
            --key="$KEY_FILE" \
            -n $NAMESPACE

        print_info "TLS secret created successfully!"
        ;;

    *)
        print_error "Invalid option"
        exit 1
        ;;
esac

echo ""
echo "=================================="
echo "Applying ingress configuration..."
echo "=================================="

# Apply ingress
kubectl apply -f k8s/ingress.yaml

echo ""
print_info "TLS setup complete!"
echo ""
echo "Verify with:"
echo "  kubectl get ingress -n $NAMESPACE"
echo "  kubectl describe ingress devops-chatbot -n $NAMESPACE"
echo ""
echo "Test HTTPS:"
echo "  curl -k https://$DOMAIN"
echo ""
echo "For more information, see k8s/tls-setup.md"
