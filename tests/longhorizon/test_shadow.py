from btc_quant_agent.platform.canary.longhorizon import SYMBOLS
from btc_quant_agent.platform.canary.public_data import normalize
from btc_quant_agent.platform.canary.warmup import assess, contract
from btc_quant_agent.platform.selection.sources import STRUCTURE, FrozenUniverse, SourceHistory
from btc_quant_agent.platform.canary import clock_domain as d
from .fixtures import structural_replay


def test_201_completed_native_shaped_bars_reuse_l23_and_keep_rank_risk_vetoes(tmp_path):
    c, _, _, journal, e = structural_replay(tmp_path)
    report = e.report()
    assert report["L23_scan_count"] >= 2
    assert report["candidate_states"] and set(report["candidate_states"].values()) == {"WATCH"}
    assert all(row["structural_warmup"] and row["beta_bar_count_minimum"] for row in report["symbols"].values())
    assert report["opportunity_funnel"]["enabled_playbooks"] == ["trend_pullback", "breakout_retest", "bollinger_reversion"]
    assert not report["ranking_qualified"] and report["risk"]["entry_eligible_blocked"]
    bars = tuple(b for symbol in SYMBOLS for b in e.contiguous(symbol, STRUCTURE))
    end = max(b.end for b in bars)
    with d.decision_clock(c.sample(), e.scope.hash):
        history = SourceHistory(bars, FrozenUniverse(tuple(sorted(SYMBOLS)), "BTCUSDT", end, decision_ts=c.wall()))
        ready = assess(history)
        strict = assess(history, full_beta_reference_required=True)
    assert all(m["completed_5m_bars"] == 201 for m in ready["members"].values())
    assert not ready["strategy_ready"] and strict["contract"]["action_minimum_aligned_bars"] == 289
    assert contract()["structural_minimum"] == 66
    assert journal.audit_replay(normalize)["complete_retained_raw_replay"]
