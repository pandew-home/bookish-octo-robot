#!/usr/bin/env bash
# show-secrets.sh — prints all operational secrets for bookish-octo-robot
# Usage: bash local/scripts/show-secrets.sh

set -euo pipefail

RED='\033[0;31m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'
GREEN='\033[0;32m'; BOLD='\033[1m'; RESET='\033[0m'

b64() { echo "$1" | base64 -d; }
secret() {
  local ns=$1 name=$2 key=$3
  kubectl get secret "$name" -n "$ns" -o jsonpath="{.data.$key}" 2>/dev/null | base64 -d
}

header() { echo -e "\n${BOLD}${CYAN}══ $1 ══${RESET}"; }
row()    { printf "  ${GREEN}%-28s${RESET} %s\n" "$1" "$2"; }
warn()   { echo -e "  ${YELLOW}⚠  $1${RESET}"; }

echo -e "${BOLD}${RED}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║        bookish-octo-robot secrets        ║"
echo "  ║      DO NOT share or commit output       ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"

# ── Grafana ────────────────────────────────────────────────────────────────
header "Grafana  (monitoring)"
GF_USER=$(secret monitoring prometheus-grafana admin-user)
GF_PASS=$(secret monitoring prometheus-grafana admin-password)
row "URL"            "http://<node-ip>:30300/grafana"
row "Admin user"     "$GF_USER"
row "Admin password" "$GF_PASS"

# ── K8sGPT AI (OpenRouter) ─────────────────────────────────────────────────
header "K8sGPT AI secret  (k8sgpt-operator-system)"
KGPT_KEY=$(secret k8sgpt-operator-system k8sgpt-ai-secret openai-api-key)
row "OpenRouter API key" "$KGPT_KEY"
row "Backend"            "openai (via openrouter.ai)"
row "Model"              "openrouter/auto"
row "Base URL"           "https://openrouter.ai/api/v1"

# ── Grafana → K8s API token (Infinity datasource) ─────────────────────────
header "Grafana K8sGPT API token  (monitoring)"
GF_TOKEN=$(kubectl get secret alloy-k8sgpt-grafana-token -n monitoring \
  -o jsonpath='{.data.token}' 2>/dev/null | base64 -d)
row "SA"    "alloy-k8sgpt (monitoring)"
row "Token" "${GF_TOKEN:0:40}…"

# ── DevOps Chatbot ─────────────────────────────────────────────────────────
header "DevOps Chatbot  (devops-chatbot)"
CB_KEY=$(secret devops-chatbot devops-chatbot-secrets llm-api-key)
CB_MODEL=$(secret devops-chatbot devops-chatbot-secrets llm-model)
CB_PROVIDER=$(secret devops-chatbot devops-chatbot-secrets llm-provider)
row "LLM provider" "$CB_PROVIDER"
row "LLM model"    "$CB_MODEL"
row "LLM API key"  "$CB_KEY"

# ── Loki ───────────────────────────────────────────────────────────────────
header "Loki  (loki)"
LOKI_PASS=$(kubectl get secret loki -n loki \
  -o jsonpath='{.data}' 2>/dev/null \
  | python3 -c "import sys,json,base64; d=json.load(sys.stdin); [print(f'{k}: {base64.b64decode(v).decode()}') for k,v in d.items()]" 2>/dev/null || true)
if [[ -n "$LOKI_PASS" ]]; then
  while IFS= read -r line; do row "${line%%:*}" "${line#*: }"; done <<< "$LOKI_PASS"
else
  warn "No credentials found — Loki is running without auth"
fi

echo -e "\n${BOLD}Done.${RESET}\n"
