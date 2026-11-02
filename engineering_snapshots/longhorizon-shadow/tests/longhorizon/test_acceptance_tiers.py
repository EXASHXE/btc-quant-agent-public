"""Account and ranking vetoes cannot masquerade as source failures."""

import pytest

from btc_quant_agent.platform.canary.longhorizon_acceptance import capacity_plan, replay_outcomes, tier_outcomes
from .fixtures import engine_at


def model(**updates):
    return {"exposure": "PUBLIC_CANARY", "L23_scan_count": 1, "source_lifecycle": {},
            "per_symbol": {}, "storage": {}, "opportunity_funnel": {"episodes": 0}, **updates}


def test_no_setup_is_separate_from_account_and_rank_veto():
    result = tier_outcomes(model(risk={"account_inputs": "MISSING"}, ranking_qualified=False))
    assert result["TIER1_SOURCE_INTEGRITY"]["outcome"] == "UNKNOWN"
    assert result["TIER1_SOURCE_INTEGRITY"]["reasons"] == []
    assert result["TIER2_MARKET_SIDE_SHADOW"]["outcome"] == "NO_SETUP"
    assert result["TIER3_ACCOUNT_EXECUTION_READINESS"]["outcome"] == "ACCOUNT_VETO"
    assert result["TIER3_ACCOUNT_EXECUTION_READINESS"]["readiness"] == "UNKNOWN"


@pytest.mark.parametrize("data,source,shadow", [
    ({"L23_scan_count": 0}, "UNKNOWN", "NOT_EVALUATED"),
    ({"opportunity_funnel": {"episodes": 1}}, "UNKNOWN", "UNKNOWN"),
    ({"opportunity_funnel": {"episodes": 1}, "clock_epoch_failure": "LOCAL_WALL_CLOCK_JUMP"},
     "SOURCE_VETO", "SOURCE_VETO"),
    ({"exposure": "SYNTHETIC"}, "NOT_EVALUATED", "NOT_EVALUATED"),
])
def test_missingness_and_source_fault_outcomes_are_distinct(data, source, shadow):
    result = tier_outcomes(model(**data))
    assert result["TIER1_SOURCE_INTEGRITY"]["outcome"] == source
    assert result["TIER2_MARKET_SIDE_SHADOW"]["outcome"] == shadow
    assert not result["TIER1_SOURCE_INTEGRITY"]["qualified"]


def test_only_actually_observed_later_native_quotes_count():
    result = tier_outcomes(model(opportunity_funnel={"episodes": 1}, modeled_response_survival={
        "1": {"known_evaluations": 1}, "3": {"known_evaluations": 0}, "5": {"known_evaluations": 0}}))
    assert result["TIER2_MARKET_SIDE_SHADOW"]["observed_modeled_native_quote_responses"] == 1
    assert result["TIER2_MARKET_SIDE_SHADOW"]["outcome"] == "OBSERVED_MARKET_SIDE_ONLY"
    assert result["TIER3_ACCOUNT_EXECUTION_READINESS"]["missing"][-1] == "verified fills"


def test_capacity_does_not_increase_retention_or_quota():
    plan = capacity_plan()
    assert plan["wire_ceiling_36h_bytes"] > plan["raw_cap_bytes"]
    assert plan["wire_ceiling_48h_bytes"] > plan["raw_cap_bytes"]
    assert plan["raw_minimum_hours"] == 36 and plan["raw_cap_bytes"] == 8 * 1024**3
    assert not plan["full_48h_plus_audit_capacity_proven"]
    assert not plan["post_run_audit_option"]["retention_increase_implemented"]


def test_retained_pair_parity_does_not_claim_full_window_replay():
    r = replay_outcomes({"status": "PARITY_VERIFIED", "checked_pairs": 2, "unpaired_raw_chunks": 0,
                         "expired_raw_chunks": 1, "complete_retained_raw_replay": False})
    assert r["retained_chunk_parity"] == "PARITY_VERIFIED"
    assert r["full_window_raw_replay_status"] == "INCOMPLETE_FULL_RAW_REPLAY"
    assert not r["full_48h_coverage_established"]


def test_runtime_reports_three_tiers_and_preserves_retention(tmp_path):
    _, _, _, _, engine = engine_at(tmp_path)
    r = engine.report()
    assert r["three_tier_acceptance"]["TIER1_SOURCE_INTEGRITY"]["outcome"] == "NOT_EVALUATED"
    assert r["storage"]["raw_retention_hours"] == 36
    assert r["storage"]["capacity_plan"]["full_window_raw_replay_commitment"] == "INCOMPLETE_FULL_RAW_REPLAY"
