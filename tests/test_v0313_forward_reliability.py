from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from btc_quant_agent.config import AppConfig
from btc_quant_agent.data.binance import DerivativeCollection
from btc_quant_agent.data.forward_store import (
    REQUIRED_RESEARCH_FIELDS,
    ForwardDerivativeRecord,
    ForwardDerivativeStore,
)
from btc_quant_agent.data.network_diagnostic import proxy_summary
from btc_quant_agent.domain import Candle, DerivativesSnapshot, RuntimeStage, ScanResult
from btc_quant_agent.opportunity_forward import (
    DAY_MS,
    ForwardObservation,
    OpportunityCampaign,
    OpportunityForwardConflict,
    OpportunityForwardStore,
    movement_outcome,
    observation_from_scan,
)

ROOT = Path(__file__).resolve().parents[1]
CAMPAIGN_PATH = ROOT / "configs/forward/v0.3.13_opportunity_shadow_campaign.json"


def _campaign() -> OpportunityCampaign:
    return OpportunityCampaign.load(CAMPAIGN_PATH)


def _derivative_record(*, successful: bool, run_id: str, started: int) -> ForwardDerivativeRecord:
    availability = {field: successful for field in REQUIRED_RESEARCH_FIELDS}
    collection = DerivativeCollection(
        collection_started_at_ms=started,
        observed_at_ms=started + 1_000,
        snapshot=DerivativesSnapshot(
            observed_at_ms=started + 1_000,
            mark_price=60_000.0 if successful else None,
            funding_rate=0.0001 if successful else None,
            open_interest=100.0 if successful else None,
            taker_buy_sell_ratio=1.1 if successful else None,
            basis_rate=0.0002 if successful else None,
            long_short_account_ratio=1.05 if successful else None,
        ),
        attempted_fields=REQUIRED_RESEARCH_FIELDS,
        field_availability=availability,
        endpoint_errors={} if successful else {field: "network unreachable" for field in availability},
    )
    return ForwardDerivativeRecord.from_collection(
        "BTCUSDT", run_id, collection, trigger_source="SCHEDULED"
    )


def _observation(
    slot: int,
    *,
    opportunity: bool = False,
    observed_at_ms: int | None = None,
) -> ForwardObservation:
    campaign = _campaign()
    return ForwardObservation.create(
        campaign=campaign,
        scheduled_slot_ms=slot,
        collection_started_at_ms=slot + 10,
        observed_at_ms=observed_at_ms or slot + 20,
        status="SUCCESSFUL_SCAN",
        market_data_health="OK",
        decision_close_ms=slot - 1,
        regime="RANGE",
        atr_15m=100.0,
        atr_percentile_decile=4,
        opportunity_id="OPP-1" if opportunity else None,
        detector_id="trend_pullback_opportunity" if opportunity else None,
        setup="TREND_PULLBACK" if opportunity else None,
        registry_version=campaign.registry_version,
        git_sha=campaign.start_git_sha,
        config_hash=campaign.config_hash,
    )


def _outcome(observation_id: str, horizon: int, value: float) -> dict[str, object]:
    return {
        "observation_id": observation_id,
        "horizon_minutes": horizon,
        "reference_time_ms": 1,
        "reference_price": 100.0,
        "future_high": 100.0 + value,
        "future_low": 100.0,
        "future_close": 100.0,
        "future_range_atr": value,
        "max_up_excursion_atr": value,
        "max_down_excursion_atr": 0.0,
        "max_abs_excursion_atr": value,
        "resolved_at_ms": 2,
        "resolution_source": "test",
    }


def test_network_diagnostic_redacts_proxy_credentials() -> None:
    report = proxy_summary({"HTTPS_PROXY": "http://alice:secret@proxy.example:7890"})
    assert report == {
        "configured": True,
        "scheme": "http",
        "host": "REDACTED_HOST",
        "port_configured": True,
        "credentials": True,
    }
    assert "alice" not in json.dumps(report)
    assert "secret" not in json.dumps(report)


def test_failed_derivative_attempt_remains_in_ledger(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    assert not store.append(_derivative_record(successful=False, run_id="failed", started=900_000))
    assert store.count() == 0
    metrics = store.reliability_metrics()
    assert metrics["total_attempt_count"] == 1
    assert metrics["scheduled_attempt_count"] == 1
    assert metrics["failed_attempt_count"] == 1
    assert metrics["fully_available_snapshot_count"] == 0
    assert metrics["scheduled_slot_success_rate"] == 0.0
    assert metrics["largest_gap_slots"] == 1


def test_collector_reports_scheduled_success_rate_and_gate_not_weakened(tmp_path: Path) -> None:
    store = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    store.append(_derivative_record(successful=False, run_id="failed", started=900_000))
    store.append(_derivative_record(successful=True, run_id="success", started=1_800_000))
    status = store.status(scheduler={"detected": True, "active": True})
    assert status["scheduled_slot_success_rate"] == 0.5
    assert status["consecutive_failure_count"] == 0
    assert status["research_gate"] == {
        "minimum_days": 30,
        "minimum_snapshots": 2_500,
        "minimum_required_field_availability": 0.95,
        "maximum_persistent_gap_slots": 4,
        "alpha_claim": "NONE",
    }


def test_systemd_proxy_file_is_optional_and_repo_example_has_no_secret() -> None:
    unit = (ROOT / "deploy/systemd/btc-quant-forward-derivatives.service").read_text()
    example = (ROOT / "deploy/systemd/network.env.example").read_text()
    assert "EnvironmentFile=-%h/.config/btc-quant-agent/network.env" in unit
    assert "BTC_QUANT_TRIGGER_SOURCE=SCHEDULED" in unit
    assert "secret" not in example.lower()
    assert "password" not in example.lower()


def test_opportunity_campaign_manifest_is_frozen() -> None:
    raw = json.loads(CAMPAIGN_PATH.read_text())
    assert raw["normal_runtime_mode"] == "RUNTIME_GATED"
    assert raw["direction_claim"] == "NONE"
    assert raw["movement_horizons_minutes"] == [240, 480]
    assert raw["control_matching_rules"]["outcome_fields_forbidden"] is True
    assert raw["immutability"]["execution"] == "DISABLED"
    assert raw["immutability"]["final_holdout"] == "SEALED"
    assert raw["h35"]["low_sample_state"] == "FORWARD_CAMPAIGN_ACCUMULATING"


def test_observation_is_idempotent_and_missed_slot_cannot_be_replaced(tmp_path: Path) -> None:
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    original = _observation(10 * DAY_MS)
    assert store.append_observation(original)
    assert not store.append_observation(original)
    replacement = dataclasses.replace(original, status="MISSED_DECISION_SLOT", payload_hash="changed")
    with pytest.raises(OpportunityForwardConflict, match="immutable"):
        store.append_observation(replacement)
    rows = store.observations(original.campaign_id)
    assert len(rows) == 1
    assert rows[0]["status"] == "SUCCESSFUL_SCAN"


def test_outcomes_are_separate_and_control_selection_does_not_rank_on_outcome(
    tmp_path: Path,
) -> None:
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    candidate = _observation(40 * DAY_MS, opportunity=True)
    controls = [_observation((index + 1) * DAY_MS) for index in range(6)]
    store.append_observation(candidate)
    for control in controls:
        store.append_observation(control)
    for index, row in enumerate([candidate, *controls]):
        store.append_outcome(_outcome(row.observation_id, 240, float(100 - index)))
    matches = store.control_matches(candidate.campaign_id, 240)
    assert len(matches) == 5
    assert all(row["time_separation_hours"] >= 24 for row in matches)
    # Nearest eligible timestamps win even though their outcome values are deliberately lower.
    assert [row["control_observation_id"] for row in matches] == [
        row.observation_id for row in reversed(controls[1:])
    ]
    stored = store.observations(candidate.campaign_id)[-1]
    assert "future_range_atr" not in stored
    assert store.audit(candidate.campaign_id)["direction_action_columns"] == []


def test_directionless_movement_uses_strict_next_open_and_frozen_atr() -> None:
    observation = {
        "observation_id": "OBS-1",
        "decision_close_ms": 59_999,
        "atr_15m": 10.0,
    }
    candles = [
        Candle("BTCUSDT", "1m", 60_000 + index * 60_000, 119_999 + index * 60_000,
               100.0, 103.0, 98.0, 101.0, 1.0)
        for index in range(240)
    ]
    result = movement_outcome(observation, 240, candles, resolved_at_ms=99)
    assert result["reference_time_ms"] == 60_000
    assert result["reference_price"] == 100.0
    assert result["future_range_atr"] == 0.5
    assert result["max_up_excursion_atr"] == 0.3
    assert result["max_down_excursion_atr"] == 0.2
    assert not ({"direction", "signed_return", "trade_return"} & result.keys())


def test_h35_remains_data_quality_at_risk_archive(tmp_path: Path) -> None:
    campaign = _campaign()
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    store.append_observation(_observation(campaign.campaign_start_ms, opportunity=True))
    status = store.status(campaign, now_ms=campaign.campaign_start_ms + 31 * DAY_MS)
    assert status["h35_state"] == "DATA_QUALITY_AT_RISK_ARCHIVE"
    assert status["direction_claim"] == "NONE"
    assert status["execution"] == "DISABLED"


def test_forward_scan_uses_runtime_gated_only_and_never_emits_signal() -> None:
    campaign = _campaign()
    result = ScanResult(
        action="LONG",
        health="OK",
        reason="forbidden actionable path",
        diagnostics={
            "decision_close_ms": 1,
            "regime": "RANGE",
            "atr": 100.0,
            "atr_percentile_decile": 4,
        },
        runtime_stage=RuntimeStage.ACTIONABLE_SIGNAL,
    )
    with pytest.raises(ValueError, match="actionable signal"):
        observation_from_scan(
            result,
            campaign,
            scheduled_slot_ms=1,
            collection_started_at_ms=2,
            observed_at_ms=3,
            config=AppConfig(),
            git_sha=campaign.start_git_sha,
        )


def test_unhealthy_runtime_scan_is_not_misclassified_as_success() -> None:
    campaign = _campaign()
    result = ScanResult(
        action="NO_SIGNAL",
        health="DATA_INVALID",
        reason="stale decision candle",
        reason_code="STALE_DECISION_DATA",
        runtime_stage=RuntimeStage.NO_OPPORTUNITY,
    )
    with pytest.raises(ValueError, match="STALE_DECISION_DATA"):
        observation_from_scan(
            result,
            campaign,
            scheduled_slot_ms=1,
            collection_started_at_ms=2,
            observed_at_ms=3,
            config=AppConfig(),
            git_sha=campaign.start_git_sha,
        )


def test_forward_store_restart_safe(tmp_path: Path) -> None:
    path = tmp_path / "opportunity.sqlite3"
    original = _observation(2 * DAY_MS)
    OpportunityForwardStore(path).append_observation(original)
    reopened = OpportunityForwardStore(path)
    assert reopened.observations(original.campaign_id)[0]["payload_hash"] == original.payload_hash


def test_execution_remains_disabled_and_final_holdout_remains_sealed() -> None:
    assert AppConfig().execution.mode == "disabled"
    raw = json.loads(CAMPAIGN_PATH.read_text())
    assert raw["immutability"]["execution"] == "DISABLED"
    assert raw["immutability"]["candidate_freeze"] == "NONE"
    assert raw["immutability"]["final_holdout"] == "SEALED"
