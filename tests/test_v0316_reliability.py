from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from btc_quant_agent.data.binance import DerivativeCollection
from btc_quant_agent.data.forward_store import (
    CADENCE_MS,
    REQUIRED_RESEARCH_FIELDS,
    ForwardDerivativeRecord,
    ForwardDerivativeStore,
)
from btc_quant_agent.domain import DerivativesSnapshot
from btc_quant_agent.evidence_epoch import EvidenceEpoch, EvidenceEpochRegistry
from btc_quant_agent.forward_evidence import forward_evidence_status
from btc_quant_agent.microstructure import AggTrade, MicrostructureStore
from btc_quant_agent.opportunity_forward import (
    ForwardObservation,
    OpportunityCampaign,
    OpportunityForwardStore,
)

ROOT = Path(__file__).resolve().parents[1]
EPOCH_PATH = ROOT / "configs/forward/v0.3.14_derivatives_evidence_epoch.json"
REGISTRY_PATH = ROOT / "configs/forward/derivatives_evidence_epochs.json"
OPPORTUNITY_PATH = ROOT / "configs/forward/v0.3.13_opportunity_shadow_campaign.json"
MICRO_CAMPAIGN_PATH = ROOT / "configs/forward/v0.3.15_microstructure_capture_campaign.json"
PROTOCOL_PATH = ROOT / "configs/forward/v0.3.16_microstructure_reliability_protocol.json"


def _epoch(epoch_id: str, start_ms: int = 0) -> EvidenceEpoch:
    return dataclasses.replace(
        EvidenceEpoch.load(EPOCH_PATH), epoch_id=epoch_id, epoch_start_ms=start_ms
    )


def _record(epoch: EvidenceEpoch, index: int, *, full: bool = True) -> ForwardDerivativeRecord:
    slot = epoch.epoch_start_ms + index * CADENCE_MS
    observed = slot + 1
    availability = {field: full for field in REQUIRED_RESEARCH_FIELDS}
    collection = DerivativeCollection(
        slot,
        observed,
        DerivativesSnapshot(
            observed_at_ms=observed,
            funding_rate=0.0001 if full else None,
            open_interest=100.0 if full else None,
            taker_buy_sell_ratio=1.0 if full else None,
            basis_rate=0.0001 if full else None,
            long_short_account_ratio=1.0 if full else None,
        ),
        REQUIRED_RESEARCH_FIELDS,
        availability,
        {} if full else {"all": "failed"},
    )
    return ForwardDerivativeRecord.from_collection(
        "BTCUSDT", f"{epoch.epoch_id}-{index}", collection,
        trigger_source="SCHEDULED", evidence_epoch=epoch
    )


def test_terminal_gap_failure_is_irreversible_after_future_success(tmp_path: Path) -> None:
    epoch = _epoch("OLD")
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    for index in range(5):
        store.append(_record(epoch, index, full=False))
    breached = store.evidence_epoch_metrics(epoch, now_ms=4 * CADENCE_MS + 20_001)
    assert breached["max_consecutive_bad_or_missing_slots"] == 5
    assert breached["eligibility_state"] == "FAILED_GAP_GATE_TERMINAL"
    for index in range(5, 45):
        store.append(_record(epoch, index))
    recovered = store.evidence_epoch_metrics(epoch, now_ms=44 * CADENCE_MS + 20_001)
    assert recovered["fully_available_scheduled_slots"] == 40
    assert recovered["eligibility_state"] == "FAILED_GAP_GATE_TERMINAL"


def test_successor_epoch_isolated_from_old_manual_and_legacy_rows(tmp_path: Path) -> None:
    old = _epoch("OLD", 0)
    successor = _epoch("SUCCESSOR", 10 * CADENCE_MS)
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    store.append(_record(old, 10))
    store.append(
        dataclasses.replace(
            _record(successor, 0), collection_id="manual", trigger_source="MANUAL"
        )
    )
    store.append(_record(successor, 1))
    metrics = store.evidence_epoch_metrics(successor, now_ms=11 * CADENCE_MS + 20_001)
    assert metrics["expected_scheduled_slots"] == 2
    assert metrics["recorded_scheduled_slots"] == 1
    assert metrics["fully_available_scheduled_slots"] == 1


def test_registry_rejects_moving_or_mismatched_epoch_start(tmp_path: Path) -> None:
    epoch_path = tmp_path / "epoch.json"
    raw = json.loads(EPOCH_PATH.read_text(encoding="utf-8"))
    raw.update({"epoch_id": "MOVING", "epoch_start_ms": CADENCE_MS})
    epoch_path.write_text(json.dumps(raw), encoding="utf-8")
    registry_path = tmp_path / "registry.json"
    registry_path.write_text(
        json.dumps(
            {
                "epochs": [{
                    "epoch_id": "MOVING", "config_path": str(epoch_path),
                    "start_ms": 2 * CADENCE_MS, "status": "FORMAL_SUCCESSOR_PENDING",
                    "terminal_reason": None, "terminal_at_ms": None,
                    "superseded_by": None,
                    "formal_eligibility_role": "FORMAL_SUCCESSOR_PENDING",
                    "immutable_history": True,
                }]
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="identity mismatch"):
        EvidenceEpochRegistry.load(registry_path).formal_epoch(3 * CADENCE_MS)


def test_derivatives_and_unified_status_share_formal_epoch(tmp_path: Path) -> None:
    epoch = EvidenceEpoch.load(EPOCH_PATH)
    store = ForwardDerivativeStore(tmp_path / "derivatives.sqlite3")
    now = epoch.epoch_start_ms
    direct = store.status(
        evidence_epoch_path=EPOCH_PATH,
        evidence_epoch_registry_path=REGISTRY_PATH,
        now_ms=now,
    )
    unified = forward_evidence_status(
        derivatives_store_path=store.path,
        opportunity_store_path=tmp_path / "opportunity.sqlite3",
        epoch_path=EPOCH_PATH,
        epoch_registry_path=REGISTRY_PATH,
        campaign_path=OPPORTUNITY_PATH,
        microstructure_root=tmp_path / "micro",
        microstructure_campaign_path=MICRO_CAMPAIGN_PATH,
        now_ms=now,
    )
    assert direct["active_epoch"]["active_epoch_id"] == unified["derivatives"]["active_epoch"]["active_epoch_id"]
    assert direct["research_eligibility"] == unified["derivatives"]["active_epoch"]["eligibility_state"]


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        ("HTTP Error 451", "NETWORK_HTTP_451"),
        ("SSL unexpected EOF", "NETWORK_TLS"),
        ("read timed out", "NETWORK_TIMEOUT"),
        ("connection reset", "NETWORK_CONNECTION"),
        ("KeyError: -1", "MARKET_DATA_INSUFFICIENT"),
        ("KeyError: 'decision_close_ms'", "RUNTIME_CONTRACT_ERROR"),
    ],
)
def test_opportunity_miss_root_cause_is_deterministic(
    tmp_path: Path, error: str, expected: str
) -> None:
    campaign = OpportunityCampaign.load(OPPORTUNITY_PATH)
    store = OpportunityForwardStore(tmp_path / f"{expected}.sqlite3")
    observation = ForwardObservation.create(
        campaign=campaign,
        scheduled_slot_ms=campaign.campaign_start_ms,
        collection_started_at_ms=campaign.campaign_start_ms + 1,
        observed_at_ms=campaign.campaign_start_ms + 2,
        status="MISSED_DECISION_SLOT", market_data_health="UNAVAILABLE",
        decision_close_ms=None, regime=None, atr_15m=None,
        atr_percentile_decile=None, opportunity_id=None, detector_id=None,
        setup=None, registry_version=campaign.registry_version,
        git_sha=campaign.start_git_sha, config_hash=campaign.config_hash,
        network_data_errors=(error,),
    )
    store.append_observation(observation)
    audit = store.missed_slot_audit(campaign.campaign_id)
    assert audit["root_cause_distribution"] == {expected: 1}
    assert audit["data_quality_state"] == "H35_DATA_QUALITY_AT_RISK"


def _micro(tmp_path: Path, start_ms: int = 0) -> MicrostructureStore:
    return MicrostructureStore(
        tmp_path, "TEST_MICRO", start_ms, protocol_path=PROTOCOL_PATH
    )


def _healthy_coverage(store: MicrostructureStore, start: int, end: int) -> str:
    instance = store.instance_start(start, "instance")
    store.session_start(start, "trade", instance)
    store.session_start(start, "depth", instance)
    store.depth_sequence_state(start, instance, True)
    store.heartbeat(end, instance)
    return instance


def test_quiet_bucket_complete_from_coverage_not_event_count(tmp_path: Path) -> None:
    store = _micro(tmp_path)
    _healthy_coverage(store, 0, 1_000)
    status = store.status(1_000)
    assert status["agg_trade_events"] == 0
    assert status["aggregate_completeness_by_interval_ms"]["1000"] == {
        "closed": 1, "complete": 1, "ratio": 1.0
    }


def test_eventful_bucket_with_partial_coverage_is_incomplete(tmp_path: Path) -> None:
    store = _micro(tmp_path)
    _healthy_coverage(store, 0, 500)
    store.append_trade(AggTrade(100, 1, 100.0, 1.0, False, "BUY", 100, 120, 1))
    status = store.status(1_000)
    assert status["agg_trade_events"] == 1
    assert status["aggregate_completeness_by_interval_ms"]["1000"]["complete"] == 0


def test_orphan_lease_closes_coverage_and_records_host_gap(tmp_path: Path) -> None:
    store = _micro(tmp_path)
    instance = _healthy_coverage(store, 1, 5_000)
    assert instance == "instance"
    assert store.recover_orphan_instances(21_000) == 1
    status = store.status(21_000)
    assert status["orphan_instance_count"] == 1
    assert status["connected_seconds"] == pytest.approx(19.999)
    assert status["gap_type_counts"] == {"PROCESS_OR_HOST_GAP": 1}


def test_fast_restart_recovers_old_instance_after_lease_on_new_heartbeat(
    tmp_path: Path,
) -> None:
    store = _micro(tmp_path)
    _healthy_coverage(store, 1, 5_000)
    replacement = store.instance_start(10_000, "replacement")
    store.session_start(10_000, "trade", replacement)
    store.session_start(10_000, "depth", replacement)
    store.depth_sequence_state(10_000, replacement, True)
    store.heartbeat(21_000, replacement)
    status = store.status(21_000)
    assert status["orphan_instance_count"] == 1
    assert status["gap_type_counts"] == {"PROCESS_OR_HOST_GAP": 1}


def test_gap_taxonomy_and_resync_are_reported_separately(tmp_path: Path) -> None:
    store = _micro(tmp_path)
    store.gap(100, "TRADE_DISCONNECT", "socket")
    store.gap(200, "DEPTH_SEQUENCE_GAP", "pu")
    status = store.status(300)
    assert status["gap_count"] == 2
    assert status["resync_count"] == 1
    assert status["gap_type_counts"] == {
        "DEPTH_SEQUENCE_GAP": 1, "TRADE_DISCONNECT": 1
    }


def test_clock_adjustment_is_diagnostic_and_raw_timestamp_is_unchanged(tmp_path: Path) -> None:
    store = _micro(tmp_path)
    trade = AggTrade(100, 1, 100.0, 1.0, False, "BUY", 100, 120, 1)
    store.append_trade(trade)
    store.append_clock_measurement(
        request_send_ms=100, response_receive_ms=110, server_time_ms=115
    )
    status = store.status(200)
    assert status["latency_ms"]["raw_signed_receive_minus_exchange"]["p50"] == 20
    assert status["latency_ms"]["clock_adjusted_diagnostic"]["p50"] == 30.0
    assert status["clock"]["raw_timestamps_modified"] is False


def test_finalized_partition_is_immutable_and_drift_is_detected(tmp_path: Path) -> None:
    store = _micro(tmp_path)
    instance = _healthy_coverage(store, 1, 1_000)
    store.instance_end(1_000, instance)
    manifest = store.finalize_partitions(90_000_000)
    partition = tmp_path / "microstructure-1970-01-01.sqlite3"
    assert partition.name in manifest
    first_digest = manifest[partition.name]["sha256"]
    assert store.finalize_partitions(91_000_000)[partition.name]["sha256"] == first_digest
    with pytest.raises(RuntimeError, match="immutable"):
        store.append_trade(AggTrade(2, 2, 1.0, 1.0, False, "BUY", 2, 2, 2))
    with partition.open("ab") as handle:
        handle.write(b"drift")
    audit = store.partition_integrity_audit()
    assert audit["integrity_ok"] is False
    assert audit["checksum_drift"] == [partition.name]
