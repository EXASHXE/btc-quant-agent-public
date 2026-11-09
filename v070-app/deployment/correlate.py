"""One finite read-only Windows/WSL correlation; never sets time or sync policy."""

from __future__ import annotations

import base64
import json
from pathlib import Path
import selectors
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from btc_quant_agent.platform.qualification.clock_diagnostics import run  # noqa:E402


def main(output):
    target = Path(output)
    if target.exists():
        raise ValueError("UNUSED_DIAGNOSTIC_OUTPUT_REQUIRED")
    script = r"""[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$OutputEncoding=[Text.UTF8Encoding]::new($false)
[Console]::WriteLine('G_WINDOWS_READY')
$rows=@(); for($i=0;$i -lt 350;$i++){
 $b=[Diagnostics.Stopwatch]::GetTimestamp(); $w=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds(); $a=[Diagnostics.Stopwatch]::GetTimestamp()
 $rows+=@{qpc_before=$b;qpc_after=$a;wall_ms=$w}; Start-Sleep -Milliseconds 100
}
$status=(w32tm /query /status /verbose 2>&1 | Out-String)
$v=@{frequency=[Diagnostics.Stopwatch]::Frequency;samples=$rows;time_service_status=$status;os=[Environment]::OSVersion.ToString()}
try{$v.service=(Get-Service W32Time | Select-Object Status,StartType)}catch{$v.service_error=$_.Exception.Message}
try{$v.time_events=@(Get-WinEvent -FilterHashtable @{LogName='System';ProviderName='Microsoft-Windows-Kernel-General';Id=1;StartTime=(Get-Date).AddHours(-2)} -MaxEvents 12 | Select-Object TimeCreated,Id,Message)}catch{$v.event_error=$_.Exception.Message}
$v | ConvertTo-Json -Depth 6 -Compress
"""
    cmd = [
        "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        script,
    ]
    process = None
    result: dict = {"status": "UNQUALIFIED_DIAGNOSTIC_ONLY", "host_changed": False}
    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert process.stdout is not None
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            if not selector.select(10):
                raise TimeoutError("WINDOWS_READY_TIMEOUT")
            marker = process.stdout.readline()
        if marker.strip() != b"G_WINDOWS_READY":
            raise ValueError("WINDOWS_READY_MISSING")
        result["guest"] = run(30)
        raw, errors = process.communicate(timeout=20)
        result.update(
            windows_stdout_base64=base64.b64encode(raw).decode(),
            windows_stderr_base64=base64.b64encode(errors).decode(),
            windows_exit=process.returncode,
        )
        if process.returncode:
            raise ValueError("WINDOWS_QUERY_FAILED")
        result["windows"] = json.loads(raw.decode("utf-8-sig"))
    except (OSError, ValueError, TimeoutError, subprocess.TimeoutExpired) as exc:
        result["error"] = str(exc)
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate(timeout=3)
            result["bounded_child_terminated"] = True
        target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in {"guest", "windows", "windows_stdout_base64", "windows_stderr_base64"}
            }
        )
    )


if __name__ == "__main__":
    main(sys.argv[1])
