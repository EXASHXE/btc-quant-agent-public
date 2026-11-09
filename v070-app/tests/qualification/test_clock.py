import pytest
from btc_quant_agent.platform.native.clock import Clock


def scripted(points):
    c = Clock()
    it = iter(points)
    c.pair = lambda: next(it)
    return c


def test_scheduler_delay_stops_as_uncertainty_not_proven_step():
    c = scripted(
        [
            {"wall_ms": 1000, "mono_before_ms": 1000, "mono_after_ms": 1000},
            {"wall_ms": 1100, "mono_before_ms": 1000, "mono_after_ms": 1100},
        ]
    )
    c.sample()
    with pytest.raises(ValueError, match="BRACKET_UNCERTAIN"):
        c.sample()
    assert c.failure_evidence["proven_wall_step"] is False
    assert c.failure_evidence["sample_span_ms"] == 100


def test_proven_wall_step_retains_sample_and_sticky_epoch():
    c = scripted(
        [
            {"wall_ms": 1000, "mono_before_ms": 1000, "mono_after_ms": 1000},
            {"wall_ms": 2705, "mono_before_ms": 1010, "mono_after_ms": 1010},
            {"wall_ms": 1020, "mono_before_ms": 1020, "mono_after_ms": 1020},
        ]
    )
    c.sample()
    with pytest.raises(ValueError, match="50MS"):
        c.sample()
    saved = c.failure_evidence
    with pytest.raises(ValueError, match="50MS"):
        c.sample()
    assert c.failure_evidence == saved and saved["proven_wall_step"] is True


def test_clock_boundaries_not_relaxed():
    c = scripted(
        [
            {"wall_ms": 1000, "mono_before_ms": 1000, "mono_after_ms": 1000},
            {"wall_ms": 1060, "mono_before_ms": 1010, "mono_after_ms": 1010},
        ]
    )
    c.sample()
    with pytest.raises(ValueError, match="50MS"):
        c.sample()


def test_readonly_timex_never_uses_adjustment_modes():
    from btc_quant_agent.platform.qualification.clock_diagnostics import timex_readonly

    value = timex_readonly()
    assert value.get("modes", 0) == 0
