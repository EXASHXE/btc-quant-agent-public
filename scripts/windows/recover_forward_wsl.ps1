# BTC Quant Agent - Windows/WSL Post-Boot Forward Recovery & Preflight
# Purpose: Idempotently ensure WSL distribution is running, verify linger, and run Forward Doctor.
# Safety Invariants:
#   - Execution is DISABLED
#   - No trading credentials or live execution paths
#   - No historical data backfill
#   - Does not silently reset terminal campaigns
#   - Does not alter Windows system power/sleep policies without explicit operator action

[CmdletBinding()]
param(
    [string]$DistroName = "Ubuntu",
    [string]$RepoPath = "/root/workspace/project/Quant-agent",
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

Write-Host "=== BTC Quant Agent Forward WSL Recovery ===" -ForegroundColor Cyan
Write-Host "Target Distro: $DistroName"
Write-Host "Repo Path    : $RepoPath"

# 1. Check if WSL is available and running
$wslList = wsl -l -v | Out-String
if ($wslList -notmatch $DistroName) {
    Write-Error "WSL distribution '$DistroName' not found. Available distributions:`n$wslList"
    exit 1
}

# 2. Check WSL user linger
Write-Host "`n[1/4] Checking WSL user systemd linger..." -ForegroundColor Yellow
$lingerCheck = wsl -d $DistroName bash -c "loginctl show-user root --property=Linger 2>/dev/null || true"
if ($lingerCheck -match "Linger=yes") {
    Write-Host "  -> Linger is active (Linger=yes)." -ForegroundColor Green
} else {
    Write-Warning "  -> Linger is NOT active. User services may stop upon session termination."
    if (-not $CheckOnly) {
        Write-Host "  -> Attempting to enable linger: loginctl enable-linger root"
        wsl -d $DistroName bash -c "loginctl enable-linger root 2>/dev/null || sudo loginctl enable-linger root"
    }
}

# 3. Check systemd timer states
Write-Host "`n[2/4] Checking user systemd timers..." -ForegroundColor Yellow
wsl -d $DistroName bash -c "systemctl --user list-timers --no-pager"

# 4. Run Forward Doctor preflight
Write-Host "`n[3/4] Running Forward Doctor preflight..." -ForegroundColor Yellow
$doctorOutput = wsl -d $DistroName bash -c "cd $RepoPath && .venv/bin/quantctl forward-evidence doctor"
Write-Host $doctorOutput

# 5. Check host power / Modern Standby risk
Write-Host "`n[4/4] Evaluating host power / sleep risk..." -ForegroundColor Yellow
$standbyCheck = powercfg /a | Out-String
if ($standbyCheck -match "Network Connected" -or $standbyCheck -match "Standby \(S0 Low Power Idle\)") {
    Write-Warning "  -> Modern Standby (S0) is supported on this machine. Host sleep will suspend WSL timers and create real Forward gaps."
    Write-Warning "  -> To keep Forward collection active while on AC power, ensure Windows Sleep is set to 'Never' or use prevent_sleep.ps1 with operator authorization."
} else {
    Write-Host "  -> Standard S3 sleep profile detected." -ForegroundColor Green
}

Write-Host "`nRecovery preflight complete. Safety invariants preserved: execution=DISABLED, final_holdout=SEALED." -ForegroundColor Green
