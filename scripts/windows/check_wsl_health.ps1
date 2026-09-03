<#
.SYNOPSIS
    Monitors WSL instance health, systemd user services, and proxy port availability from Windows.
#>

$ErrorActionPreference = "Continue"

Write-Host "=== WSL Forward Services Health Check ===" -ForegroundColor Cyan

# 1. Check WSL process running
$wslList = wsl --list --running
if ($wslList -notmatch "Ubuntu") {
    Write-Host "CRITICAL: WSL Ubuntu instance is NOT running!" -ForegroundColor Red
    exit 2
}
Write-Host "[OK] WSL Ubuntu is running." -ForegroundColor Green

# 2. Check proxy port 7897 (Clash Verge)
try {
    $tcp = New-Object System.Net.Sockets.TcpClient
    $tcp.Connect("127.0.0.1", 7897)
    $tcp.Close()
    Write-Host "[OK] Local proxy port 7897 is reachable." -ForegroundColor Green
}
catch {
    Write-Host "WARNING: Local proxy port 7897 is not accepting connections!" -ForegroundColor Yellow
}

# 3. Run doctor inside WSL
Write-Host "Querying quantctl forward-evidence doctor..." -ForegroundColor Gray
$doctorJson = wsl -d Ubuntu bash -c "cd /root/workspace/project/Quant-agent && .venv/bin/quantctl forward-evidence doctor"
Write-Host $doctorJson

Write-Host "=== Check Complete ===" -ForegroundColor Cyan
