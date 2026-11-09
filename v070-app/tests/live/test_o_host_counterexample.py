"""Measured local host counterexample; contains no market data or authority."""

import json
from pathlib import Path
import pytest
from btc_quant_agent.platform.live.models import Blocked
from btc_quant_agent.platform.live.operational_clock import control_check


def test_measured_WSL_clock_domain_incoherence_is_not_reconciled_as_wall_only():
    root = Path(__file__).resolve().parents[2]
    evidence = json.loads((root / "contracts/O_HOST_CLOCK_COUNTEREXAMPLE.json").read_text())
    assert not evidence["host_qualified"]
    a, b = evidence["samples"]
    assert abs((b["raw_ms"] - b["mono_before_ms"]) - (a["raw_ms"] - a["mono_before_ms"])) > 2000
    with pytest.raises(Blocked, match="RAW_OR_BOOTTIME"):
        control_check(a, b)


def test_wide_auxiliary_sample_cannot_widen_the_50ms_clock_guard():
    from btc_quant_agent.platform.live.operational_clock import control_check

    a = {
        "wall_ms": 0,
        "mono_before_ms": 1000,
        "mono_after_ms": 1000,
        "raw_ms": 2000,
        "boottime_ms": 3000,
        "control_end_ms": 1000,
        "boot_id": "QA",
    }
    b = {
        **a,
        "mono_before_ms": 1100,
        "mono_after_ms": 1100,
        "raw_ms": 2180,
        "boottime_ms": 3100,
        "control_end_ms": 1200,
    }
    with pytest.raises(Blocked, match="CONTROL_SAMPLE_UNCERTAIN"):
        control_check(a, b)
