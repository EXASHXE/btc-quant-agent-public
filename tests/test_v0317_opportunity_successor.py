from __future__ import annotations

import json
from pathlib import Path

import pytest

from btc_quant_agent.config import AppConfig, DataConfig
from btc_quant_agent.data.binance import BinancePublicClient
from btc_quant_agent.data.forward_store import ForwardDerivativeRecord
from btc_quant_agent.evidence_epoch import EvidenceEpochRegistry
from btc_quant_agent.forward_evidence import forward_operations_health
from btc_quant_agent.opportunity_forward import (
    CADENCE_MS,
    ForwardObservation,
    OpportunityCampaign,
    OpportunityCampaignRegistry,
    OpportunityForwardConflict,
    OpportunityForwardStore,
)

ROOT = Path(__file__).resolve().parents[1]
H35_PATH = ROOT / "configs/forward/v0.3.13_opportunity_shadow_campaign.json"
H36_PATH = ROOT / "configs/forward/v0.3.17_opportunity_successor_campaign.json"
OPPORTUNITY_REGISTRY = ROOT / "configs/forward/opportunity_forward_campaigns.json"
DERIVATIVES_REGISTRY = ROOT / "configs/forward/derivatives_evidence_epochs.json"


def _observation(
    campaign: OpportunityCampaign,
    index: int,
    *,
    success: bool = True,
    trigger_source: str = "SCHEDULED",
) -> ForwardObservation:
    slot = campaign.campaign_start_ms + index * CADENCE_MS
    return ForwardObservation.create(
        campaign=campaign,
        scheduled_slot_ms=slot,
        collection_started_at_ms=slot + 50_000,
        observed_at_ms=slot + 55_000,
        status="SUCCESSFUL_SCAN" if success else "MISSED_DECISION_SLOT",
        market_data_health="OK" if success else "UNAVAILABLE",
        decision_close_ms=slot - 1 if success else None,
        regime="RANGE" if success else None,
        atr_15m=100.0 if success else None,
        atr_percentile_decile=4 if success else None,
        opportunity_id=None,
        detector_id=None,
        setup=None,
        registry_version=campaign.registry_version,
        git_sha=campaign.start_git_sha,
        config_hash=campaign.config_hash,
        network_data_errors=() if success else ("process unavailable",),
        trigger_source=trigger_source,
    )


def _quality_now(campaign: OpportunityCampaign, last_index: int) -> int:
    return (
        campaign.campaign_start_ms
        + last_index * CADENCE_MS
        + campaign.post_boundary_delay_seconds * 1_000
        + 1
    )


def test_h35_is_immutable_data_quality_at_risk_archive(tmp_path: Path) -> None:
    registry = OpportunityCampaignRegistry.load(OPPORTUNITY_REGISTRY)
    campaign, lifecycle = registry.archive()
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    status = store.status(campaign, now_ms=campaign.campaign_start_ms + 31 * 86_400_000)
    assert lifecycle.formal_role == "DATA_QUALITY_AT_RISK_ARCHIVE"
    assert lifecycle.status == "H35_DATA_QUALITY_AT_RISK"
    assert status["hypothesis_state"] == "DATA_QUALITY_AT_RISK_ARCHIVE"
    assert status["data_quality_gate"]["wall_clock_gate_enabled"] is False


def test_successor_identity_and_start_are_registry_frozen(tmp_path: Path) -> None:
    registry = OpportunityCampaignRegistry.load(OPPORTUNITY_REGISTRY)
    campaign, lifecycle = registry.successor()
    assert campaign.campaign_id == "OPPORTUNITY_FORWARD_V0317_20260901T160000Z"
    assert campaign.campaign_start_ms == lifecycle.start_ms == 1788278400000
    raw = json.loads(H36_PATH.read_text(encoding="utf-8"))
    moved = tmp_path / "moved.json"
    raw["campaign_start_ms"] += CADENCE_MS
    moved.write_text(json.dumps(raw), encoding="utf-8")
    registry_raw = json.loads(OPPORTUNITY_REGISTRY.read_text(encoding="utf-8"))
    registry_raw["campaigns"][1]["config_path"] = str(moved)
    moved_registry = tmp_path / "registry.json"
    moved_registry.write_text(json.dumps(registry_raw), encoding="utf-8")
    with pytest.raises(ValueError, match="identity mismatch"):
        OpportunityCampaignRegistry.load(moved_registry)


def test_prestart_observation_cannot_be_created_or_appended(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    with pytest.raises(ValueError, match="pre-start"):
        ForwardObservation.create(
            campaign=campaign,
            scheduled_slot_ms=campaign.campaign_start_ms - CADENCE_MS,
            collection_started_at_ms=campaign.campaign_start_ms,
            observed_at_ms=campaign.campaign_start_ms,
            status="MISSED_DECISION_SLOT",
            market_data_health="UNAVAILABLE",
            decision_close_ms=None,
            regime=None,
            atr_15m=None,
            atr_percentile_decile=None,
            opportunity_id=None,
            detector_id=None,
            setup=None,
            registry_version=campaign.registry_version,
            git_sha=campaign.start_git_sha,
            config_hash=campaign.config_hash,
        )


def test_missed_slot_cannot_later_be_replaced_by_success(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    missed = _observation(campaign, 0, success=False)
    store.append_observation(missed, campaign=campaign)
    success = _observation(campaign, 0)
    with pytest.raises(OpportunityForwardConflict, match="immutable"):
        store.append_observation(success, campaign=campaign)
    assert store.observations(campaign.campaign_id)[0]["status"] == "MISSED_DECISION_SLOT"


def test_wall_clock_denominator_and_missing_slots_drive_scan_ratio(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    store.append_observation(_observation(campaign, 0), campaign=campaign)
    store.append_observation(_observation(campaign, 2), campaign=campaign)
    quality = store.data_quality_metrics(campaign, now_ms=_quality_now(campaign, 2))
    assert quality["expected_scheduled_slots"] == 3
    assert quality["recorded_scheduled_slots"] == 2
    assert quality["missing_wall_clock_slots"] == 1
    assert quality["successful_scheduled_scan_ratio"] == pytest.approx(2 / 3)
    assert quality["miss_root_causes"] == {"PROCESS_OR_HOST_GAP": 1}


def test_manual_and_legacy_rows_do_not_improve_success_ratio(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    store.append_observation(
        _observation(campaign, 0, trigger_source="MANUAL"), campaign=campaign
    )
    quality = store.data_quality_metrics(campaign, now_ms=_quality_now(campaign, 0))
    assert quality["successful_scheduled_scans"] == 0
    assert quality["successful_scheduled_scan_ratio"] == 0.0


def test_terminal_miss_gate_cannot_recover_after_later_successes(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    for index in range(5):
        store.append_observation(
            _observation(campaign, index, success=False), campaign=campaign
        )
    terminal = store.data_quality_metrics(campaign, now_ms=_quality_now(campaign, 4))
    assert terminal["max_consecutive_missed_decision_slots"] == 5
    assert terminal["state"] == "DATA_QUALITY_TERMINAL"
    for index in range(5, 45):
        store.append_observation(_observation(campaign, index), campaign=campaign)
    later = store.data_quality_metrics(campaign, now_ms=_quality_now(campaign, 44))
    assert later["successful_scheduled_scans"] == 40
    assert later["state"] == "DATA_QUALITY_TERMINAL"


def test_h36_cannot_be_evaluable_before_all_frozen_gates(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    store.append_observation(_observation(campaign, 0), campaign=campaign)
    status = store.status(campaign, now_ms=_quality_now(campaign, 0))
    assert status["hypothesis_state"] == "FORWARD_CAMPAIGN_ACCUMULATING"
    assert status["hypothesis_gate"] == {
        "minimum_resolved_opportunities": 30,
        "preferred_resolved_opportunities": 50,
        "minimum_calendar_days": 30,
        "minimum_unique_matched_controls": 100,
        "minimum_distinct_utc_days": 20,
        "distinct_resolved_days": 0,
    }


def test_no_direction_columns_and_safety_state_remain_frozen(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(H36_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    assert store.audit(campaign.campaign_id)["direction_action_columns"] == []
    assert AppConfig().execution.mode == "disabled"
    raw = json.loads(H36_PATH.read_text(encoding="utf-8"))
    assert raw["direction_claim"] == "NONE"
    assert raw["immutability"]["final_holdout"] == "SEALED"


def test_derivatives_old_terminal_and_successor_start_remain_frozen() -> None:
    registry = EvidenceEpochRegistry.load(DERIVATIVES_REGISTRY)
    old = next(item for item in registry.entries if item.epoch_id.endswith("V0314_001"))
    successor = next(item for item in registry.entries if item.epoch_id.endswith("V0316_002"))
    assert old.status == "FAILED_GAP_GATE_TERMINAL"
    assert old.terminal_at_ms == 1788183927140
    assert successor.start_ms == 1788255000000


def test_derivatives_observed_at_conservatively_extends_for_server_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def payload(path: str, params: object = None) -> object:
        if path.endswith("premiumIndex"):
            return {"markPrice": "100", "indexPrice": "100", "lastFundingRate": "0.1", "time": 2_000}
        if path.endswith("openInterest"):
            return {"openInterest": "10", "time": 1_000}
        if path.endswith("openInterestHist"):
            return [{"sumOpenInterest": "9", "timestamp": 900}, {"sumOpenInterest": "10", "timestamp": 1_000}]
        if path.endswith("takerlongshortRatio"):
            return [{"buySellRatio": "1", "timestamp": 1_000}]
        if path.endswith("globalLongShortAccountRatio"):
            return [{"longShortRatio": "1", "timestamp": 1_000}]
        if path.endswith("basis"):
            return [{"basisRate": "0.01", "timestamp": 1_000}]
        raise AssertionError(path)

    client = BinancePublicClient(DataConfig())
    monkeypatch.setattr(client, "_get", payload)
    monkeypatch.setattr("btc_quant_agent.data.binance.time.time", lambda: 1.0)
    collection = client.collect_derivatives("BTCUSDT")
    assert collection.observed_at_ms == 2_000
    assert collection.snapshot.observed_at_ms == 2_000
    assert collection.endpoint_telemetry is not None
    assert collection.endpoint_telemetry["_observation_clock"]["conservative_clock_extension_ms"] == 1_000
    ForwardDerivativeRecord.from_collection("BTCUSDT", "clock", collection)


def test_operations_health_is_structured_and_cannot_authorize_execution() -> None:
    report = {
        "derivatives": {"successor_v0316": {
            "scheduler_active": True, "terminal_failure": False,
            "max_consecutive_bad_or_missing_slots": 0,
        }},
        "opportunity_forward": {"successor_h36": {
            "scheduler_active": True,
            "data_quality_gate": {
                "terminal_failure": False,
                "max_consecutive_missed_decision_slots": 0,
            },
            "oldest_unresolved_mature_age_seconds": 0,
        }},
        "microstructure_forward": {
            "service": {"active": True},
            "heartbeat_age_seconds": 1,
            "partition_integrity": {"integrity_ok": True},
        },
    }
    health = forward_operations_health(report)
    assert health["state"] == "HEALTHY"
    assert health["direction_claim"] == "NONE"
    assert health["execution"] == "DISABLED"
    assert health["final_holdout"] == "SEALED"
