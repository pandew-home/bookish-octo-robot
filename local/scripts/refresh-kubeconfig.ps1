param(
    [string]$ClusterName = "bookish-octo-robot"
)

$ErrorActionPreference = "Stop"

$kubeConfigPath = if ($env:KUBECONFIG -and $env:KUBECONFIG.Trim().Length -gt 0) {
    $env:KUBECONFIG
} else {
    Join-Path $HOME ".kube\config"
}

if (-not (Get-Command civo -ErrorAction SilentlyContinue)) {
    Write-Error "civo CLI is not installed or not on PATH"
    exit 1
}

if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Write-Error "kubectl is not installed or not on PATH"
    exit 1
}

$kubeDir = Split-Path -Parent $kubeConfigPath
if (-not (Test-Path $kubeDir)) {
    New-Item -ItemType Directory -Path $kubeDir -Force | Out-Null
}

if (Test-Path $kubeConfigPath) {
    $timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
    Copy-Item -Path $kubeConfigPath -Destination "$kubeConfigPath.$timestamp.bak" -Force
}

civo kubernetes config $ClusterName --save --yes | Out-Null

try {
    kubectl config use-context $ClusterName | Out-Null
} catch {
    # Continue even if context switch fails; civo merge may still have succeeded.
}

$currentContext = ""
try {
    $currentContext = (kubectl config current-context).Trim()
} catch {
    $currentContext = "<unknown>"
}

Write-Host "Refreshed kubeconfig for cluster: $ClusterName"
Write-Host "Current context: $currentContext"
