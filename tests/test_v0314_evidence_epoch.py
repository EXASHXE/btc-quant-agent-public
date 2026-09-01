from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any

from btc_quant_agent.config import AppConfig, DataConfig
from btc_quant_agent.data.binance import (
    BinanceDataError,
    BinancePublicClient,
    DerivativeCollection,
)
from btc_quant_agent.data.forward_store import (
    CADENCE_MS,
    REQUIRED_RESEARCH_FIELDS,
    ForwardDerivativeRecord,
    ForwardDerivativeStore,
)
from btc_quant_agent.domain import Candle, DerivativesSnapshot
from btc_quant_agent.evidence_epoch import EvidenceEpoch
from btc_quant_agent.forward_evidence import forward_evidence_status
from btc_quant_agent.opportunity_forward import (
    ForwardObservation,
    OpportunityCampaign,
    OpportunityForwardStore,
    resolve_opportunity_outcomes,
)

ROOT = Path(__file__).resolve().parents[1]
EPOCH_PATH = ROOT / "configs/forward/v0.3.14_derivatives_evidence_epoch.json"
CAMPAIGN_PATH = ROOT / "configs/forward/v0.3.13_opportunity_shadow_campaign.json"


def _epoch(start: int = 0) -> EvidenceEpoch:
    return dataclasses.replace(EvidenceEpoch.load(EPOCH_PATH), epoch_start_ms=start)


def _collection(started: int, *, full: bool = True) -> DerivativeCollection:
    observed = started + 5_000
    availability = {field: full for field in REQUIRED_RESEARCH_FIELDS}
    return DerivativeCollection(
        started,
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
        {} if full else {"open_interest": "failed"},
        {
            "open_interest": {
                "attempt_count": 1,
                "success": full,
                "final_error_class": None if full else "CONNECT_TIMEOUT",
                "attempts": [],
            }
        },
    )


def _record(
    run_id: str,
    slot: int,
    *,
    source: str = "SCHEDULED",
    full: bool = True,
    epoch: EvidenceEpoch | None = None,
) -> ForwardDerivativeRecord:
    return ForwardDerivativeRecord.from_collection(
        "BTCUSDT",
        run_id,
        _collection(slot + 20_000, full=full),
        trigger_source=source,
        evidence_epoch=epoch,
    )


def test_pre_epoch_rows_preserved_but_excluded_and_manual_never_improves_gate(
    tmp_path: Path,
) -> None:
    epoch = _epoch(CADENCE_MS)
    store = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    store.append(_record("legacy-fail", 0, full=False, epoch=epoch))
    store.append(_record("manual-full", CADENCE_MS, source="MANUAL", epoch=epoch))
    metrics = store.evidence_epoch_metrics(epoch, now_ms=2 * CADENCE_MS + 20_000)
    assert store.reliability_metrics()["total_attempt_count"] == 2
    assert metrics["expected_scheduled_slots"] == 2
    assert metrics["recorded_scheduled_slots"] == 0
    assert metrics["fully_available_scheduled_slots"] == 0
    assert metrics["missing_slots"] == 2
    assert metrics["manual_runs_count_for_eligibility"] is False


def test_wall_clock_missing_slots_form_consecutive_gap_and_gates_are_frozen(
    tmp_path: Path,
) -> None:
    epoch = _epoch()
    store = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    store.append(_record("slot-0", 0, epoch=epoch))
    metrics = store.evidence_epoch_metrics(epoch, now_ms=3 * CADENCE_MS + 20_000)
    assert metrics["expected_scheduled_slots"] == 4
    assert metrics["recorded_scheduled_slots"] == 1
    assert metrics["missing_slots"] == 3
    assert metrics["max_consecutive_bad_or_missing_slots"] == 3
    assert epoch.minimum_days == 30
    assert epoch.minimum_fully_available_snapshots == 2_500
    assert epoch.minimum_required_field_availability == 0.95
    assert epoch.maximum_consecutive_failed_or_missing_scheduled_slots == 4


def test_epoch_start_is_config_frozen_and_status_cannot_move_it(tmp_path: Path) -> None:
    epoch = EvidenceEpoch.load(EPOCH_PATH)
    store = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    first = store.evidence_epoch_metrics(epoch, now_ms=epoch.epoch_start_ms - 1)
    second = store.evidence_epoch_metrics(epoch, now_ms=epoch.epoch_start_ms + CADENCE_MS)
    assert first["epoch_start_ms"] == second["epoch_start_ms"] == 1788179400000
    assert first["eligibility_state"] == "INITIALIZING"


def _endpoint_payload(path: str) -> Any:
    if path.endswith("premiumIndex"):
        return {"markPrice": "100", "indexPrice": "100", "lastFundingRate": "0.1", "time": 1}
    if path.endswith("openInterest"):
        return {"openInterest": "10", "time": 1}
    if path.endswith("openInterestHist"):
        return [
            {"sumOpenInterest": "9", "timestamp": 1},
            {"sumOpenInterest": "10", "timestamp": 2},
        ]
    if path.endswith("takerlongshortRatio"):
        return [{"buySellRatio": "1", "timestamp": 1}]
    if path.endswith("globalLongShortAccountRatio"):
        return [{"longShortRatio": "1", "timestamp": 1}]
    if path.endswith("basis"):
        return [{"basisRate": "0.01", "timestamp": 1}]
    raise AssertionError(path)


def test_retry_succeeds_after_transient_error_and_telemetry_persists(
    tmp_path: Path, monkeypatch: Any
) -> None:
    client = BinancePublicClient(DataConfig())
    calls = 0

    def fake_get(path: str, params: dict[str, Any] | None = None) -> Any:
        nonlocal calls
        if path.endswith("openInterest"):
            calls += 1
            if calls == 1:
                raise BinanceDataError("timeout", "TLS_HANDSHAKE_TIMEOUT", True)
        return _endpoint_payload(path)

    monkeypatch.setattr(client, "_get", fake_get)
    collection = client.collect_derivatives("BTCUSDT")
    assert collection.endpoint_telemetry is not None
    assert collection.endpoint_telemetry["open_interest"]["attempt_count"] == 2
    assert collection.field_availability["open_interest"] is True
    store = ForwardDerivativeStore(tmp_path / "forward.sqlite3")
    slot = collection.collection_started_at_ms // CADENCE_MS * CADENCE_MS
    epoch = _epoch(slot)
    record = ForwardDerivativeRecord.from_collection(
        "BTCUSDT", "retry", collection, trigger_source="SCHEDULED", evidence_epoch=epoch
    )
    store.append(record)
    metrics = store.evidence_epoch_metrics(epoch, now_ms=slot + 20_000)
    assert metrics["fully_available_scheduled_slots"] == 1
    persisted = metrics["recent_endpoint_telemetry"][0]["endpoints"]
    assert persisted["open_interest"]["attempt_count"] == 2


def test_retry_stops_at_three_and_nonretryable_stops_at_one(monkeypatch: Any) -> None:
    client = BinancePublicClient(DataConfig())
    transient_calls = 0

    def transient(path: str, params: dict[str, Any] | None = None) -> Any:
        nonlocal transient_calls
        if path.endswith("openInterest"):
            transient_calls += 1
            raise BinanceDataError("timeout", "READ_TIMEOUT", True)
        return _endpoint_payload(path)

    monkeypatch.setattr(client, "_get", transient)
    result = client.collect_derivatives("BTCUSDT")
    assert transient_calls == 3
    assert result.endpoint_telemetry is not None
    assert result.endpoint_telemetry["open_interest"]["final_error_class"] == "READ_TIMEOUT"

    schema_calls = 0

    def schema(path: str, params: dict[str, Any] | None = None) -> Any:
        nonlocal schema_calls
        if path.endswith("openInterest"):
            schema_calls += 1
            raise BinanceDataError("schema", "SCHEMA_ERROR", False)
        return _endpoint_payload(path)

    monkeypatch.setattr(client, "_get", schema)
    client.collect_derivatives("BTCUSDT")
    assert schema_calls == 1


def test_retry_keeps_original_slot_and_final_observed_time(monkeypatch: Any) -> None:
    client = BinancePublicClient(DataConfig())
    monkeypatch.setattr(client, "_get", lambda path, params=None: _endpoint_payload(path))
    collection = client.collect_derivatives("BTCUSDT")
    record = ForwardDerivativeRecord.from_collection(
        "BTCUSDT", "one", collection, trigger_source="SCHEDULED", evidence_epoch=_epoch()
    )
    assert record.observed_at_ms >= record.collection_started_at_ms
    assert record.scheduled_slot_ms == record.collection_started_at_ms // CADENCE_MS * CADENCE_MS


def test_source_timestamp_after_final_observation_is_rejected() -> None:
    collection = dataclasses.replace(
        _collection(0),
        snapshot=dataclasses.replace(_collection(0).snapshot, funding_time_ms=6_000),
    )
    try:
        ForwardDerivativeRecord.from_collection("BTCUSDT", "future", collection)
    except ValueError as exc:
        assert "source timestamp" in str(exc)
    else:
        raise AssertionError("future source timestamp was accepted")


def _observation(campaign: OpportunityCampaign) -> ForwardObservation:
    return ForwardObservation.create(
        campaign=campaign,
        scheduled_slot_ms=0,
        collection_started_at_ms=1,
        observed_at_ms=2,
        status="SUCCESSFUL_SCAN",
        market_data_health="OK",
        decision_close_ms=59_999,
        regime="RANGE",
        atr_15m=10.0,
        atr_percentile_decile=4,
        opportunity_id="OPP",
        detector_id="trend_pullback_opportunity",
        setup="TREND_PULLBACK",
        registry_version=campaign.registry_version,
        git_sha=campaign.start_git_sha,
        config_hash=campaign.config_hash,
    )


class _CandleClient:
    def historical_klines(self, symbol: str, interval: str, start: int, end: int) -> list[Candle]:
        count = (end - start + 1) // 60_000
        return [
            Candle(symbol, interval, start + index * 60_000, start + (index + 1) * 60_000 - 1,
                   100.0, 101.0, 99.0, 100.0, 1.0)
            for index in range(count)
        ]


def test_outcome_resolver_idempotent_and_does_not_mutate_observation(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(CAMPAIGN_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    observation = _observation(campaign)
    store.append_observation(observation)
    before = dict(store.observations(campaign.campaign_id)[0])
    now = 500 * 60_000
    assert resolve_opportunity_outcomes(_CandleClient(), store, campaign, now_ms=now)["resolved"] == 2  # type: ignore[arg-type]
    assert resolve_opportunity_outcomes(_CandleClient(), store, campaign, now_ms=now)["resolved"] == 0  # type: ignore[arg-type]
    assert dict(store.observations(campaign.campaign_id)[0]) == before


def test_immature_outcomes_remain_unresolved_and_safety_is_frozen(tmp_path: Path) -> None:
    campaign = OpportunityCampaign.load(CAMPAIGN_PATH)
    store = OpportunityForwardStore(tmp_path / "opportunity.sqlite3")
    store.append_observation(_observation(campaign))
    result = resolve_opportunity_outcomes(_CandleClient(), store, campaign, now_ms=60_000)  # type: ignore[arg-type]
    assert result["resolved"] == 0
    assert campaign.campaign_id == "OPPORTUNITY_FORWARD_V0313_20260831T050656Z"
    assert AppConfig().execution.mode == "disabled"


def test_unified_forward_watchdog_separates_epoch_and_archive(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "btc_quant_agent.forward_evidence.scheduler_status",
        lambda: {"detected": True, "active": True},
    )
    monkeypatch.setattr(
        "btc_quant_agent.forward_evidence.opportunity_scheduler_status",
        lambda: {"detected": True, "active": True},
    )
    monkeypatch.setattr(
        "btc_quant_agent.forward_evidence.opportunity_resolver_scheduler_status",
        lambda: {"detected": True, "active": True},
    )
    report = forward_evidence_status(
        derivatives_store_path=tmp_path / "derivatives.sqlite3",
        opportunity_store_path=tmp_path / "opportunity.sqlite3",
        epoch_path=EPOCH_PATH,
        campaign_path=CAMPAIGN_PATH,
        now_ms=EvidenceEpoch.load(EPOCH_PATH).epoch_start_ms - 1,
    )
    assert report["derivatives"]["active_epoch"]["eligibility_state"] == "INITIALIZING"
    assert report["derivatives"]["archive_pre_epoch"]["all_rows_preserved"] is True
    assert report["opportunity_forward"]["successor_h36"]["resolver_scheduler_active"] is True
    assert report["alpha_interpretation"] == "NONE"
