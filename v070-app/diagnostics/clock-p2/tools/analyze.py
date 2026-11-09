"""Analyze read-only paired counters; Windows QPC supplies elapsed time, never UTC authority."""

from __future__ import annotations

import argparse
import json
from itertools import pairwise
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLOCKS = ("mono_before_ns", "raw_ns", "boottime_ns", "realtime_ns")


def analyze(rows):
    if len(rows) < 2:
        raise ValueError("TWO_REFERENCE_SAMPLES_REQUIRED")
    first, last = rows[0], rows[-1]
    freq = first["Windows"]["frequency"]
    boot = first["boot_id"]
    if freq <= 0:
        raise ValueError("QPC_FREQUENCY_INVALID")
    previous = None
    for r in rows:
        w = r["Windows"]
        if r["boot_id"] != boot:
            raise ValueError("BOOT_CHANGE")
        if w["frequency"] != freq:
            raise ValueError("QPC_FREQUENCY_CHANGED")
        if w["qpc_before"] > w["qpc_after"]:
            raise ValueError("QPC_PAIR_REVERSED")
        if previous is not None and w["qpc_before"] < previous:
            raise ValueError("QPC_REGRESSION")
        previous = w["qpc_after"]
        for side in ("before", "after"):
            if r[side]["mono_after_ns"] < r[side]["mono_before_ns"]:
                raise ValueError("LINUX_PAIR_REVERSED")
        if r["after"]["mono_before_ns"] < r["before"]["mono_after_ns"]:
            raise ValueError("LINUX_MONOTONIC_ROLLBACK")
    wl = (last["Windows"]["qpc_before"] - first["Windows"]["qpc_after"]) / freq
    wu = (last["Windows"]["qpc_after"] - first["Windows"]["qpc_before"]) / freq
    if wl <= 0:
        raise ValueError("REFERENCE_ELAPSED_NOT_POSITIVE")
    rates = {}
    for key in CLOCKS:
        lo = (last["before"][key] - first["after"][key]) / 1e9
        hi = (last["after"][key] - first["before"][key]) / 1e9
        rates[key] = {
            "elapsed_seconds_bounds": [lo, hi],
            "relative_rate_to_Windows_bounds": [lo / wu, hi / wl],
            "rate_midpoint": (lo + hi) / (wl + wu),
            "endpoint_IPC_uncertainty_seconds": (hi - lo) / 2,
        }
    stamps = [r[side] for r in rows for side in ("before", "after")]
    wall_jumps = []
    for a, b in pairwise(stamps):
        delta = (b["realtime_ns"] - b["mono_before_ns"]) - (
            a["realtime_ns"] - a["mono_before_ns"]
        )
        uncertainty = (a["mono_after_ns"] - a["mono_before_ns"]) + (
            b["mono_after_ns"] - b["mono_before_ns"]
        )
        if abs(delta) > 50000000 + uncertainty:
            wall_jumps.append(
                {
                    "mono_ns": b["mono_before_ns"],
                    "wall_minus_mono_change_ms": delta / 1e6,
                    "paired_uncertainty_ms": uncertainty / 1e6,
                }
            )
    ranges = {}
    for key in CLOCKS[1:]:
        offsets = [s[key] - s["mono_before_ns"] for s in stamps]
        ranges[key] = (max(offsets) - min(offsets)) / 1e6
    utc_elapsed = (last["Windows"]["utc_ticks"] - first["Windows"]["utc_ticks"]) / 1e7
    windows_utc_jumps = []
    for a, b in pairwise(rows):
        x, y = a["Windows"], b["Windows"]
        change = (y["utc_ticks"] - x["utc_ticks"]) / 1e7 - (
            y["qpc_before"] - x["qpc_before"]
        ) / freq
        uncertainty = (
            (x["qpc_after"] - x["qpc_before"]) + (y["qpc_after"] - y["qpc_before"])
        ) / freq
        if abs(change) > 0.05 + uncertainty:
            windows_utc_jumps.append(change)
    from btc_quant_agent.platform.live.operational_clock import HASH, control_check

    def control(s):
        return {
            "mono_before_ms": s["mono_before_ns"] // 1000000,
            "mono_after_ms": s["mono_after_ns"] // 1000000,
            "wall_ms": s["realtime_ns"] // 1000000,
            "raw_ms": s["raw_ns"] // 1000000,
            "boottime_ms": s["boottime_ns"] // 1000000,
            "control_end_ms": s["mono_after_ns"] // 1000000,
            "boot_id": boot,
        }

    violations = []
    for index, (a, b) in enumerate(pairwise(stamps)):
        try:
            control_check(control(a), control(b))
            control_check(control(stamps[0]), control(b))
        except ValueError as e:
            violations.append({"sample": index + 1, "reason": str(e)})
    max_span = max(s["mono_after_ns"] - s["mono_before_ns"] for s in stamps)
    return {
        "schema": "P_CLOCK_DOMAIN_ANALYSIS_V1",
        "paired_reference_samples": len(rows),
        "boot_id": boot,
        "Windows_QPC_elapsed_seconds_bounds": [wl, wu],
        "Windows_UTC_elapsed_seconds": utc_elapsed,
        "Windows_UTC_steps_over_50ms_observed": windows_utc_jumps,
        "Windows_UTC_independently_qualified": False,
        "rates": rates,
        "Linux_offset_ranges_ms": ranges,
        "Linux_wall_steps": wall_jumps,
        "Linux_pair_span_max_ns": max_span,
        "IPC_mono_roundtrip_max_ms": max(
            (r["after"]["mono_after_ns"] - r["before"]["mono_before_ns"]) / 1e6
            for r in rows
        ),
        "O_control_policy_sha256": HASH,
        "O_control_guard_rejection_count": len(violations),
        "O_control_guard_first_rejections": violations[:8],
        "control_clock_criteria_pass": not violations and max_span <= 5000000,
        "host_qualified": False,
        "qualification_scope": "Read-only clock-domain assessment; capture metadata determines pre/post phase. No automatic host or strict UTC qualification.",
        "upstream_cause": "NOT_PROVEN",
        "new_exchange_requests": 0,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--name", default="P_PRECHANGE_WINDOWS_COMPARISON")
    args = p.parse_args()
    if not args.name.replace("_", "").isalnum():
        raise ValueError("SIMPLE_NAME_REQUIRED")
    path = ROOT / "audit" / args.name
    rows = [
        json.loads(line) for line in path.with_suffix(".jsonl").read_text().splitlines()
    ]
    report = analyze(rows)
    metadata = json.loads(path.with_suffix(".json").read_text())
    if not metadata["status"].startswith("COMPLETE") or not metadata["worker_closed"]:
        raise ValueError("CAPTURE_INCOMPLETE_OR_WORKER_NOT_CLOSED")
    report["capture_phase"] = "POST_CHANGE" if metadata["post_change"] else "PRE_CHANGE"
    report["requested_Windows_elapsed_seconds"] = metadata[
        "requested_Windows_elapsed_seconds"
    ]
    path.with_suffix(".analysis.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in report.items()
                if k not in ["Linux_wall_steps", "O_control_guard_first_rejections"]
            }
        )
    )


if __name__ == "__main__":
    main()
