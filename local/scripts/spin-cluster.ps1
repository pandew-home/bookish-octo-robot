<#
.SYNOPSIS
    Spin up/down Civo Kubernetes cluster nodes to save costs
.DESCRIPTION
    This script scales the bookish-octo-robot cluster node pool to 0 (spin down)
    or optionally back to 2 (spin up).
.PARAMETER Action
    Action to perform: "down" (spin down to 0 nodes) or "up" (spin up to 2 nodes)
.PARAMETER ClusterName
    Name of the Civo cluster (default: bookish-octo-robot)
.EXAMPLE
    .\spin-cluster.ps1 -Action down
    Spin down the cluster to 0 nodes
.EXAMPLE
    .\spin-cluster.ps1 -Action up
    Spin up the cluster back to 2 nodes
#>

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("up", "down")]
    [string]$Action,

    [Parameter(Mandatory=$false)]
    [string]$ClusterName = "bookish-octo-robot"
)

$ErrorActionPreference = "Stop"

function Write-Status {
    param([string]$Message, [string]$Type = "Info")
    $colors = @{
        "Info" = "Cyan"
        "Success" = "Green"
        "Warning" = "Yellow"
        "Error" = "Red"
    }
    Write-Host "$Message" -ForegroundColor $colors[$Type]
}

Write-Status "=== Civo Cluster Node Scaler ===" -Type "Info"
Write-Status "Cluster: $ClusterName" -Type "Info"
Write-Status "Action: $Action" -Type "Info"
Write-Host ""

# Determine target count
if ($Action -eq "down") {
    $targetCount = 0
    $actionDesc = "spin down"
} else {
    $targetCount = 2
    $actionDesc = "spin up"
}

# Check Civo CLI is available
try {
    $null = Get-Command civo -ErrorAction Stop
    $civoVersion = (civo version 2>&1)
    Write-Status "Civo CLI found: $civoVersion" -Type "Success"
} catch {
    Write-Status "Civo CLI not found!" -Type "Error"
    Write-Host ""
    Write-Host "Please install Civo CLI first:"
    Write-Host "  https://github.com/civo/cli/releases"
    Write-Host ""
    Write-Host "Or use winget: winget install Civo.CIVO"
    exit 1
}

# Check for API key
$apiKey = $env:CIVO_API_KEY
if (-not $apiKey) {
    Write-Status "CIVO_API_KEY not set in environment" -Type "Warning"
    Write-Host "Attempting to use cached credentials..."
}

# Get cluster info using Civo API directly (more reliable)
$headers = @{
    "Content-Type" = "application/json"
}
if ($apiKey) {
    $headers["Authorization"] = "Bearer $apiKey"
}

try {
    Write-Status "Fetching cluster info..." -Type "Info"
    $clusters = Invoke-RestMethod -Uri "https://api.civo.com/v2/kubernetes/clusters" -Headers $headers
    $cluster = $clusters.items | Where-Object { $_.name -eq $ClusterName } | Select-Object -First 1
    
    if (-not $cluster) {
        throw "Cluster '$ClusterName' not found"
    }
    
    $clusterId = $cluster.id
    Write-Status "Found cluster: $ClusterName (ID: $clusterId)" -Type "Success"
    
    # Get node pools
    Write-Status "Fetching node pools..." -Type "Info"
    $pools = Invoke-RestMethod -Uri "https://api.civo.com/v2/kubernetes/$clusterId/node_pools" -Headers $headers
    
    Write-Status "Current node pools:" -Type "Info"
    $pools.pools | ForEach-Object {
        Write-Host "  - Pool: $($_.name), ID: $($_.id), Count: $($_.count)"
    }
    
    # Scale each node pool
    $pools.pools | ForEach-Object {
        $poolId = $_.id
        $poolName = $_.name
        $currentCount = $_.count
        
        if ($currentCount -eq $targetCount) {
            Write-Status "Pool '$poolName' already at $targetCount nodes, skipping" -Type "Warning"
            return
        }
        
        Write-Status "Scaling pool '$poolName' from $currentCount to $targetCount nodes..." -Type "Info"
        
        $body = @{
            count = $targetCount
        } | ConvertTo-Json
        
        $null = Invoke-RestMethod -Uri "https://api.civo.com/v2/kubernetes/$clusterId/node_pools/$poolId" `
            -Headers $headers `
            -Method Put `
            -Body $body
        
        Write-Status "Scale $actionDesc initiated for pool '$poolName'" -Type "Success"
    }
    
} catch {
    Write-Status "Error: $_" -Type "Error"
    exit 1
}

Write-Host ""
Write-Status "=== Complete ===" -Type "Success"
Write-Status "Nodes are being $actionDesc. This may take a few minutes." -Type "Info"
Write-Status "Use 'kubectl get nodes' to monitor status." -Type "Info"
