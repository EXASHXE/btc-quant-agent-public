"""Finite manual read-only Linux/Windows QPC comparison; no network or clock writes."""

from __future__ import annotations

import argparse
import base64
import json
import os
import selectors
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$ErrorActionPreference = 'Stop'
$frequency = [Diagnostics.Stopwatch]::Frequency
$start = [Diagnostics.Stopwatch]::GetTimestamp()
@{ready=$true;frequency=$frequency;isHighResolution=[Diagnostics.Stopwatch]::IsHighResolution} | ConvertTo-Json -Compress
for($i=0;$i -lt 15000;$i++) {
 $line = [Console]::ReadLine()
 if($null -eq $line -or $line -eq 'QUIT'){break}
 if($line -ne 'SAMPLE'){throw 'READ_ONLY_PROTOCOL_INVALID'}
 if(([Diagnostics.Stopwatch]::GetTimestamp()-$start)/[double]$frequency -gt 740){throw 'FINITE_HOST_DEADLINE'}
 $q1 = [Diagnostics.Stopwatch]::GetTimestamp()
 $utc = [DateTime]::UtcNow.Ticks
 $q2 = [Diagnostics.Stopwatch]::GetTimestamp()
 @{ordinal=$i;qpc_before=$q1;qpc_after=$q2;utc_ticks=$utc;frequency=$frequency} | ConvertTo-Json -Compress
}
"""


def clocks():
    a = time.monotonic_ns()
    result = {
        "mono_before_ns": a,
        "realtime_ns": time.time_ns(),
        "raw_ns": time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW),
        "boottime_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
    }
    result["mono_after_ns"] = time.monotonic_ns()
    return result


def line(process, timeout):
    deadline = time.monotonic() + timeout
    raw = b""
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while b"\n" not in raw:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not selector.select(remaining):
                raise TimeoutError("WINDOWS_REFERENCE_TIMEOUT")
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk or len(raw) + len(chunk) >= 10000:
                raise ValueError("WINDOWS_REFERENCE_MISSING_OR_OVERLONG")
            raw += chunk
    return json.loads(raw)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seconds", type=float, default=120)
    p.add_argument("--hz", type=float, default=5)
    p.add_argument("--name", default="P_PRECHANGE_WINDOWS_COMPARISON")
    p.add_argument(
        "--phase", choices=["PRE_CHANGE", "POST_CHANGE"], default="PRE_CHANGE"
    )
    args = p.parse_args()
    if not 1 <= args.seconds <= 720 or not 1 <= args.hz <= 5:
        raise ValueError("FINITE_DIAGNOSTIC_LIMIT")
    if not args.name.replace("_", "").isalnum():
        raise ValueError("SIMPLE_OUTPUT_NAME_REQUIRED")
    output = ROOT / "audit" / args.name
    if output.with_suffix(".jsonl").exists():
        raise ValueError("DIAGNOSTIC_OUTPUT_MUST_BE_UNUSED")
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    worker = subprocess.Popen(
        [
            "/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-EncodedCommand",
            base64.b64encode(SCRIPT.encode("utf-16le")).decode(),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    started = time.monotonic()
    rows = 0
    summary = {
        "schema": "P_PAIRED_WINDOWS_QPC_V1",
        "settings_changes": 0,
        "exchange_requests": 0,
        "post_change": args.phase == "POST_CHANGE",
        "boot_id": boot,
        "requested_Windows_elapsed_seconds": args.seconds,
        "UTC_qualification": False,
    }
    try:
        ready = line(worker, 15)
        assert ready["ready"] and ready["frequency"] > 0
        summary["Windows_reference"] = ready
        first = None
        with output.with_suffix(".jsonl").open("x") as log:
            for _ in range(int(args.seconds * args.hz * 3) + 100):
                if time.monotonic() - started > args.seconds * 2 + 30:
                    raise TimeoutError("FINITE_LINUX_FAILSAFE_DEADLINE")
                if Path("/proc/sys/kernel/random/boot_id").read_text().strip() != boot:
                    raise ValueError("BOOT_CHANGED")
                before = clocks()
                worker.stdin.write(b"SAMPLE\n")
                worker.stdin.flush()
                win = line(worker, 2)
                after = clocks()
                if first is None:
                    first = win
                elapsed = (win["qpc_before"] - first["qpc_before"]) / win["frequency"]
                log.write(
                    json.dumps(
                        {
                            "before": before,
                            "Windows": win,
                            "after": after,
                            "boot_id": boot,
                        }
                    )
                    + "\n"
                )
                log.flush()
                rows += 1
                if rows % 10 == 0:
                    os.fsync(log.fileno())
                if elapsed >= args.seconds:
                    break
                time.sleep(1 / args.hz)
            else:
                raise ValueError("FINITE_SAMPLE_BUDGET_EXHAUSTED")
            os.fsync(log.fileno())
        summary.update(
            status="COMPLETE_READ_ONLY_CAPTURE_NOT_AUTOMATIC_QUALIFICATION",
            samples=rows,
            Windows_elapsed_seconds=elapsed,
            Linux_monotonic_elapsed_seconds=time.monotonic() - started,
        )
    except BaseException as e:
        summary.update(status="FAILED_RETAIN_PARTIAL", samples=rows, error=str(e))
        raise
    finally:
        try:
            worker.stdin.write(b"QUIT\n")
            worker.stdin.flush()
            worker.stdin.close()
            worker.wait(timeout=3)
        except (OSError, subprocess.TimeoutExpired):
            worker.kill()
            worker.wait(timeout=3)
        summary.update(
            Windows_worker_returncode=worker.returncode,
            Windows_worker_stderr=worker.stderr.read(3000).decode(
                "utf-8", errors="replace"
            ),
            worker_closed=True,
        )
        output.with_suffix(".json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n"
        )
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
