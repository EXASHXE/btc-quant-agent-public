"""Fixed, read-only host queries. Never resyncs, starts services or a WSL distro."""

from __future__ import annotations

import base64
import datetime
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def query(command, timeout=15):
    try:
        p = subprocess.run(command, capture_output=True, timeout=timeout, check=False)

        def decode(raw):
            encoding = "utf-16le" if raw.count(b"\0") > len(raw) // 8 else "utf-8"
            try:
                return raw.decode(encoding).lstrip("\ufeff")
            except UnicodeDecodeError:
                return raw.decode("gb18030", errors="replace")

        return {
            "command": command,
            "exit": p.returncode,
            "stdout": decode(p.stdout)[:50000],
            "stderr": decode(p.stderr)[:5000],
            "stdout_bytes_base64": base64.b64encode(p.stdout).decode(),
        }
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"command": command, "error": str(e)}


def main():
    commands = [
        [
            "systemctl",
            "show",
            "systemd-timesyncd.service",
            "chrony.service",
            "chronyd.service",
            "ntp.service",
            "ntpsec.service",
            "openntpd.service",
            "--property=Id,LoadState,ActiveState,SubState,UnitFileState,MainPID,ExecMainStartTimestampMonotonic,FragmentPath,ConditionResult",
        ],
        [
            "systemctl",
            "list-unit-files",
            "*timesync*",
            "*chrony*",
            "*ntp*",
            "--no-pager",
        ],
        ["systemctl", "cat", "systemd-timesyncd.service"],
        ["timedatectl", "show", "--all"],
        ["timedatectl", "show-timesync", "--all"],
        ["timedatectl", "timesync-status", "--all"],
        [
            "journalctl",
            "-b",
            "-u",
            "systemd-timesyncd.service",
            "-u",
            "chrony.service",
            "-u",
            "ntpsec.service",
            "-n",
            "120",
            "-o",
            "short-monotonic",
            "--no-pager",
        ],
        [
            "journalctl",
            "-b",
            "-u",
            "systemd-journald.service",
            "--grep=Time jumped|Clock.*(jump|step|skew)",
            "--case-sensitive=no",
            "-n",
            "100",
            "-o",
            "short-monotonic",
            "--no-pager",
        ],
        [
            "journalctl",
            "-k",
            "-b",
            "--grep=clocksource|timekeeping|tsc|Hyper-V|TimeSync|unstable|suspend|resume",
            "--case-sensitive=no",
            "-n",
            "100",
            "-o",
            "short-monotonic",
            "--no-pager",
        ],
        [
            "dpkg-query",
            "-W",
            "-f=${Package} ${Version} ${db:Status-Abbrev}\n",
            "systemd",
            "systemd-timesyncd",
            "chrony",
            "ntpsec",
            "ntpdate",
            "openntpd",
        ],
        ["/mnt/c/Windows/system32/wsl.exe", "--version"],
        ["/mnt/c/Windows/system32/wsl.exe", "--list", "--verbose"],
        ["/mnt/c/Windows/system32/w32tm.exe", "/query", "/status", "/verbose"],
        ["/mnt/c/Windows/system32/w32tm.exe", "/query", "/source"],
    ]
    metadata = {}
    for name in [
        "/etc/os-release",
        "/etc/wsl.conf",
        "/etc/systemd/timesyncd.conf",
        "/proc/cmdline",
        "/proc/sys/kernel/random/boot_id",
        "/proc/self/timens_offsets",
        "/sys/module/hv_utils/parameters/timesync_implicit",
    ]:
        try:
            metadata[name] = Path(name).read_text()[:8000]
        except OSError as e:
            metadata[name] = str(e)
    for directory in [
        "/etc/systemd/timesyncd.conf.d",
        "/run/systemd/timesyncd.conf.d",
        "/usr/lib/systemd/timesyncd.conf.d",
    ]:
        for p in Path(directory).glob("*.conf"):
            metadata[str(p)] = p.read_text()[:5000]
    script = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Continue'
$os = Get-CimInstance Win32_OperatingSystem
$services = Get-CimInstance Win32_Service -Filter "Name='W32Time' OR Name='vmictimesync'" | Select-Object Name,State,StartMode
$version = Get-ItemProperty 'HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion'
$result = @{OS=@{Caption=$os.Caption;Version=$os.Version;BuildNumber=$os.BuildNumber;LastBootUTC=$os.LastBootUpTime.ToUniversalTime().ToString('o');DisplayVersion=$version.DisplayVersion;UBR=$version.UBR};Services=@($services);StopwatchFrequency=[Diagnostics.Stopwatch]::Frequency;StopwatchHighResolution=[Diagnostics.Stopwatch]::IsHighResolution}
$result | ConvertTo-Json -Depth 5 -Compress
foreach($provider in @('Microsoft-Windows-Time-Service','Microsoft-Windows-Kernel-General')) {
 $filter = @{LogName='System';ProviderName=$provider;StartTime=(Get-Date).AddHours(-24)}
 if($provider -eq 'Microsoft-Windows-Kernel-General'){$filter.Id=1}
 try { Get-WinEvent -FilterHashtable $filter -MaxEvents 20 -ErrorAction Stop | ForEach-Object { @{Provider=$_.ProviderName;Id=$_.Id;TimeCreatedUTC=$_.TimeCreated.ToUniversalTime().ToString('o');Message=$_.Message} | ConvertTo-Json -Compress } }
 catch { @{Provider=$provider;QueryLimitation=$_.Exception.Message} | ConvertTo-Json -Compress }
}
"""
    commands.append(
        [
            "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(script.encode("utf-16le")).decode(),
        ]
    )
    results = []
    for command in commands:
        value = query(command, 30 if "powershell.exe" in command[0] else 15)
        results.append(value)
        print(
            json.dumps(
                {
                    "command_head": command[:3],
                    "exit": value.get("exit"),
                    "error": value.get("error"),
                }
            ),
            flush=True,
        )
    (ROOT / "audit/P_HOST_QUERY_RESULTS.json").write_text(
        json.dumps(
            {
                "read_only": True,
                "settings_changes": 0,
                "exchange_requests": 0,
                "local_audit_time_UNQUALIFIED": datetime.datetime.now(
                    datetime.timezone.utc
                ).isoformat(),
                "metadata": metadata,
                "queries": results,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
