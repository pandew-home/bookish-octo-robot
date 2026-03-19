# Civo API Key Setup Script
# Run this once to configure your Civo API key

Write-Host "=== Civo API Key Setup ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Get your API key from: https://www.civo.com/account" -ForegroundColor Yellow
Write-Host ""

$apiKey = Read-Host "Enter your Civo API Key"

if ($apiKey -and $apiKey.Length -gt 0) {
    # Set for current session
    $env:CIVO_API_KEY = $apiKey
    
    # Make persistent for current user
    [System.Environment]::SetEnvironmentVariable('CIVO_API_KEY', $apiKey, 'User')
    
    Write-Host ""
    Write-Host "API key configured successfully!" -ForegroundColor Green
    Write-Host ""
    Write-Host "You can now run:"
    Write-Host "  .\spin-cluster.ps1 -Action down  # Spin down to 0 nodes (save money)"
    Write-Host "  .\spin-cluster.ps1 -Action up   # Spin up to 2 nodes"
} else {
    Write-Host "No API key provided." -ForegroundColor Red
}
