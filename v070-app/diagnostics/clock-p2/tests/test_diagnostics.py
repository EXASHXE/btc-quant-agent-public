import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from analyze import analyze
from windows_elapsed import line


def record(t, *, mono_rate=1):
    m = int(t * 1e9 * mono_rate)
    r = int(t * 1e9)
    s = {
        "mono_before_ns": m,
        "mono_after_ns": m,
        "raw_ns": r,
        "boottime_ns": m,
        "realtime_ns": 1000000000000000000 + m,
    }
    return {
        "boot_id": "SYNTHETIC_DIAGNOSTIC_TEST",
        "before": s.copy(),
        "after": s.copy(),
        "Windows": {
            "frequency": 10000000,
            "qpc_before": int(t * 1e7),
            "qpc_after": int(t * 1e7),
            "utc_ticks": int(t * 1e7) + 621355968000000000,
        },
    }


def test_interval_ratios_and_O_guard_accept_stable_counters_without_UTC_promotion():
    d = analyze([record(0), record(1), record(120)])
    assert d["rates"]["raw_ns"]["relative_rate_to_Windows_bounds"] == [1, 1]
    assert (
        d["control_clock_criteria_pass"]
        and not d["host_qualified"]
        and not d["Windows_UTC_independently_qualified"]
    )


def test_windows_elapsed_detects_slow_adjusted_clock_and_keeps_50ms_guard():
    d = analyze(
        [
            record(0, mono_rate=0.94),
            record(1, mono_rate=0.94),
            record(120, mono_rate=0.94),
        ]
    )
    assert d["rates"]["mono_before_ns"]["rate_midpoint"] == pytest.approx(0.94)
    assert d["rates"]["raw_ns"]["rate_midpoint"] == 1
    assert (
        not d["control_clock_criteria_pass"]
        and d["O_control_guard_rejection_count"] > 0
    )


@pytest.mark.parametrize(
    "fault",
    [
        "boot",
        "qpc_regression",
        "frequency",
        "reversed_qpc",
        "reversed_linux",
        "insufficient",
    ],
)
def test_invalid_reference_fails_closed(fault):
    rows = [record(0), record(1), record(2)]
    if fault == "boot":
        rows[-1]["boot_id"] = "OTHER"
    if fault == "qpc_regression":
        rows[-1]["Windows"].update(qpc_before=0, qpc_after=0)
    if fault == "frequency":
        rows[-1]["Windows"]["frequency"] = 100
    if fault == "reversed_qpc":
        rows[-1]["Windows"]["qpc_after"] = 0
    if fault == "reversed_linux":
        rows[-1]["after"]["mono_after_ns"] = 0
    if fault == "insufficient":
        rows = rows[:1]
    with pytest.raises(ValueError):
        analyze(rows)


def test_IPC_scheduling_uncertainty_is_in_interval_instead_of_assumed_zero():
    a, b = record(0), record(120)
    for s in [a, b]:
        for k in s["before"]:
            s["before"][k] -= 1000000
        for k in s["after"]:
            s["after"][k] += 1000000
    d = analyze([a, b])
    lo, hi = d["rates"]["raw_ns"]["relative_rate_to_Windows_bounds"]
    assert lo < 1 < hi and d["rates"]["raw_ns"][
        "endpoint_IPC_uncertainty_seconds"
    ] == pytest.approx(0.002)


def test_real_Windows_comparison_is_rejected_by_original_O_controls():
    import json

    rows = [
        json.loads(x)
        for x in (ROOT / "audit/P_PRECHANGE_WINDOWS_COMPARISON.jsonl")
        .read_text()
        .splitlines()
    ]
    d = analyze(rows)
    assert not d["control_clock_criteria_pass"] and not d["host_qualified"]
    assert d["rates"]["mono_before_ns"]["relative_rate_to_Windows_bounds"][1] < 0.99


def test_partial_pipe_response_times_out_and_complete_pipe_parses():
    import os
    from types import SimpleNamespace

    r, w = os.pipe()
    with os.fdopen(r, "rb", buffering=0) as stream:
        p = SimpleNamespace(stdout=stream)
        os.write(w, b'{"ready":')
        with pytest.raises(TimeoutError):
            line(p, 0.02)
        os.write(w, b'{"ready":true}\n')
        assert line(p, 1) == {"ready": True}
        os.close(w)
