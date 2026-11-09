"""Bounded read-only Linux clock telemetry; no sockets or clock changes."""

import datetime
import json
import platform
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]


def main():
    meta = {
        "system": platform.platform(),
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
        "local_audit_UTC": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    for n in [
        "/sys/devices/system/clocksource/clocksource0/current_clocksource",
        "/sys/devices/system/clocksource/clocksource0/available_clocksource",
    ]:
        try:
            meta[n] = Path(n).read_text().strip()
        except OSError as error:
            meta[n] = str(error)
    for cmd in [
        ["timedatectl", "show", "--property=NTPSynchronized", "--property=NTP", "--property=Timezone"],
        ["systemctl", "is-active", "systemd-timesyncd", "chronyd", "chrony"],
    ]:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=4)
            meta[" ".join(cmd)] = {
                "exit": result.returncode,
                "stdout": result.stdout[:1000],
                "stderr": result.stderr[:500],
            }
        except (OSError, subprocess.TimeoutExpired) as error:
            meta[" ".join(cmd)] = str(error)
    samples = []
    start = time.monotonic()
    while time.monotonic() - start < 30:
        a = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        item = {
            "mono_before_ns": a,
            "realtime_ns": time.clock_gettime_ns(time.CLOCK_REALTIME),
            "raw_ns": time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW),
            "boottime_ns": time.clock_gettime_ns(time.CLOCK_BOOTTIME),
            "mono_after_ns": time.clock_gettime_ns(time.CLOCK_MONOTONIC),
        }
        samples.append(item)
        time.sleep(0.05)
    offsets = {
        k: [s[k] - s["mono_before_ns"] for s in samples] for k in ["realtime_ns", "raw_ns", "boottime_ns"]
    }
    receipt = {
        "schema": "O_READONLY_HOST_CLOCK_TELEMETRY_V1",
        "metadata": meta,
        "elapsed_seconds": time.monotonic() - start,
        "samples": samples,
        "offset_ranges_ns": {k: max(v) - min(v) for k, v in offsets.items()},
        "bracket_max_ns": max(s["mono_after_ns"] - s["mono_before_ns"] for s in samples),
        "independent_UTC_uncertainty": "NOT_ESTABLISHED",
        "host_qualified": False,
        "Windows_host_time_service_root_cause": "NOT_ESTABLISHED_NO_HOST_SETTINGS_ACCESSED",
        "live_exchange_requests": 0,
        "settings_changes": 0,
    }
    (ROOT / "audit/O_HOST_CLOCK_TELEMETRY.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({k: v for k, v in receipt.items() if k != "samples"}))


if __name__ == "__main__":
    main()
