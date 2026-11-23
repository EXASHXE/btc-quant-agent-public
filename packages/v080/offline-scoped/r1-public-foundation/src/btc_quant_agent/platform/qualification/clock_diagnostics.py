"""Bounded read-only wall/mono/raw/boot cross-process diagnostics; no time setters."""

from __future__ import annotations

import ctypes
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def pair():
    before = time.monotonic_ns()
    wall = time.time_ns()
    after = time.monotonic_ns()
    raw = time.clock_gettime_ns(time.CLOCK_MONOTONIC_RAW) if hasattr(time, "CLOCK_MONOTONIC_RAW") else None
    boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME) if hasattr(time, "CLOCK_BOOTTIME") else None
    return {
        "pid": os.getpid(),
        "wall_ns": wall,
        "mono_before_ns": before,
        "mono_after_ns": after,
        "raw_ns": raw,
        "boot_ns": boot,
        "span_ns": after - before,
        "offset_low_ns": wall - after,
        "offset_high_ns": wall - before,
    }


def timex_readonly():
    if sys.platform != "linux" or ctypes.sizeof(ctypes.c_long) != 8:
        return {"status": "UNAVAILABLE_PLATFORM"}

    class Timeval(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_long), ("tv_usec", ctypes.c_long)]

    class Timex(ctypes.Structure):
        _fields_ = [
            ("modes", ctypes.c_uint),
            ("offset", ctypes.c_long),
            ("freq", ctypes.c_long),
            ("maxerror", ctypes.c_long),
            ("esterror", ctypes.c_long),
            ("status", ctypes.c_int),
            ("constant", ctypes.c_long),
            ("precision", ctypes.c_long),
            ("tolerance", ctypes.c_long),
            ("time", Timeval),
            ("tick", ctypes.c_long),
            ("ppsfreq", ctypes.c_long),
            ("jitter", ctypes.c_long),
            ("shift", ctypes.c_int),
            ("stabil", ctypes.c_long),
            ("jitcnt", ctypes.c_long),
            ("calcnt", ctypes.c_long),
            ("errcnt", ctypes.c_long),
            ("stbcnt", ctypes.c_long),
            ("tai", ctypes.c_int),
            ("padding", ctypes.c_int * 11),
        ]

    state = Timex()  # modes=0: read-only; no clock or synchronization configuration writes.
    libc = ctypes.CDLL(None, use_errno=True)
    function = libc.adjtimex
    function.argtypes = [ctypes.POINTER(Timex)]
    function.restype = ctypes.c_int
    result = function(ctypes.byref(state))
    return {
        "return_state": result,
        "errno": ctypes.get_errno(),
        "modes": state.modes,
        "status_bits": state.status,
        "STA_UNSYNC": bool(state.status & 0x40),
        "offset_reported": state.offset,
        "maxerror_us": state.maxerror,
        "esterror_us": state.esterror,
        "frequency_scaled_ppm": state.freq,
        "note": "Reported NTP status is not independently measured absolute UTC uncertainty",
    }


def run(seconds=15):
    if not 1 <= seconds <= 30:
        raise ValueError("BOUNDED_1_TO_30_SECONDS")
    child = "import json,time,os; b=time.monotonic_ns(); w=time.time_ns(); a=time.monotonic_ns(); print(json.dumps(dict(pid=os.getpid(),wall_ns=w,mono_before_ns=b,mono_after_ns=a)))"
    samples = []
    crossings = []
    start = time.monotonic()
    deadline = start + seconds
    next_child = start
    while time.monotonic() < deadline:
        samples.append(pair())
        if time.monotonic() >= next_child:
            parent_before = pair()
            result = subprocess.run(
                [sys.executable, "-I", "-c", child], capture_output=True, text=True, timeout=3, check=True
            )
            parent_after = pair()
            crossings.append(
                {
                    "parent_before": parent_before,
                    "child": json.loads(result.stdout),
                    "parent_after": parent_after,
                }
            )
            next_child += 1
        time.sleep(0.01)
    anchor = samples[0]
    changes = [
        {
            "low_ms": (s["offset_low_ns"] - anchor["offset_high_ns"]) / 1e6,
            "high_ms": (s["offset_high_ns"] - anchor["offset_low_ns"]) / 1e6,
        }
        for s in samples
    ]
    proved = [i for i, d in enumerate(changes) if d["low_ms"] > 50 or d["high_ms"] < -50]
    uncertain = [i for i, d in enumerate(changes) if d["low_ms"] < -50 or d["high_ms"] > 50]
    host = {}
    for name, path in [
        ("clocksource", "/sys/devices/system/clocksource/clocksource0/current_clocksource"),
        ("available_clocksources", "/sys/devices/system/clocksource/clocksource0/available_clocksource"),
        ("boot_id", "/proc/sys/kernel/random/boot_id"),
    ]:
        try:
            host[name] = Path(path).read_text().strip()
        except OSError:
            host[name] = "UNKNOWN"
    cross_ok = all(
        x["parent_before"]["mono_before_ns"]
        <= x["child"]["mono_before_ns"]
        <= x["child"]["mono_after_ns"]
        <= x["parent_after"]["mono_after_ns"]
        for x in crossings
    )
    return {
        "status": "HOST_CLOCK_UNQUALIFIED",
        "bounded_stability": "STOP_THRESHOLD_OBSERVED"
        if uncertain
        else "NO_THRESHOLD_CROSSING_IN_BOUNDED_SAMPLE",
        "elapsed_seconds": time.monotonic() - start,
        "platform": platform.platform(),
        "host": host,
        "clock_info": {
            name: vars(getattr(time, "get_clock_info")(name))
            for name in ("time", "monotonic", "perf_counter")
        },
        "NTP_readonly": timex_readonly(),
        "samples": samples,
        "cross_process": crossings,
        "cross_process_mono_order_valid": cross_ok,
        "offset_change_low_min_ms": min(d["low_ms"] for d in changes),
        "offset_change_high_max_ms": max(d["high_ms"] for d in changes),
        "max_sample_span_ms": max(s["span_ns"] for s in samples) / 1e6,
        "proved_step_indices": proved,
        "unsafe_or_uncertain_indices": uncertain,
        "absolute_UTC_uncertainty_ms": None,
        "native_independent_probes": "NOT_RUN",
        "suspend_resume": "Not intentionally induced; boot-minus-mono/raw samples retained",
        "qualified": False,
        "reason": "Bounded local stability cannot establish independent UTC or erase the historical stop",
    }
