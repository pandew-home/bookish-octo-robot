#!/usr/bin/env bash

set -euo pipefail

CLUSTER_NAME="${1:-bookish-octo-robot}"
KUBECONFIG_PATH="${KUBECONFIG:-$HOME/.kube/config}"

if ! command -v civo >/dev/null 2>&1; then
  echo "civo CLI is not installed or not on PATH" >&2
  exit 1
fi

if ! command -v kubectl >/dev/null 2>&1; then
  echo "kubectl is not installed or not on PATH" >&2
  exit 1
fi

mkdir -p "$(dirname "$KUBECONFIG_PATH")"

if [ -f "$KUBECONFIG_PATH" ]; then
  cp "$KUBECONFIG_PATH" "$KUBECONFIG_PATH.$(date +%Y%m%d-%H%M%S).bak"
fi

civo kubernetes config "$CLUSTER_NAME" --save --yes

kubectl config use-context "$CLUSTER_NAME" >/dev/null 2>&1 || true

echo "Refreshed kubeconfig for cluster: $CLUSTER_NAME"
echo "Current context: $(kubectl config current-context)"