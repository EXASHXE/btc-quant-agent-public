<#
.SYNOPSIS
    Prevents Windows from entering Modern Standby or Sleep during forward data collection.
.DESCRIPTION
    Uses Windows Kernel32 SetThreadExecutionState API to signal continuous system activity
    (ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_AWAYMODE_REQUIRED).
#>

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public class SleepBlocker {
    [DllImport("kernel32.dll", CharSet = CharSet.Auto, SetLastError = true)]
    public static extern uint SetThreadExecutionState(uint esFlags);

    public const uint ES_SYSTEM_REQUIRED = 0x00000001;
    public const uint ES_DISPLAY_REQUIRED = 0x00000002;
    public const uint ES_AWAYMODE_REQUIRED = 0x00000040;
    public const uint ES_CONTINUOUS = 0x80000000;
}
"@

Write-Host "=== Windows Sleep Prevention Active ===" -ForegroundColor Green
Write-Host "Keeping system awake for BTC Quant Agent forward collection..."
Write-Host "Press Ctrl+C to terminate and allow normal Windows sleep."

# Set continuous execution flag
[SleepBlocker]::SetThreadExecutionState([SleepBlocker]::ES_CONTINUOUS -bor [SleepBlocker]::ES_SYSTEM_REQUIRED -bor [SleepBlocker]::ES_AWAYMODE_REQUIRED) | Out-Null

try {
    while ($true) {
        Start-Sleep -Seconds 60
        # Re-assert execution state every minute
        [SleepBlocker]::SetThreadExecutionState([SleepBlocker]::ES_CONTINUOUS -bor [SleepBlocker]::ES_SYSTEM_REQUIRED -bor [SleepBlocker]::ES_AWAYMODE_REQUIRED) | Out-Null
    }
}
finally {
    # Reset to normal state
    [SleepBlocker]::SetThreadExecutionState([SleepBlocker]::ES_CONTINUOUS) | Out-Null
    Write-Host "Sleep prevention released. Normal power policy restored." -ForegroundColor Yellow
}
