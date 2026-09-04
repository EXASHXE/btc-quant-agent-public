from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import (
    BinanceDataError,
    BinancePublicClient,
    DerivativeCollection,
)
from btc_quant_agent.evidence_epoch import EvidenceEpochRegistry
from btc_quant_agent.forward_diagnostics import (
    check_network_proxy,
    forward_doctor,
    recover_services,
)
from btc_quant_agent.microstructure import (
    MicrostructureStore,
)
from btc_quant_agent.opportunity_forward import (
    OpportunityCampaignRegistry,
)

ROOT = Path(__file__).resolve().parents[1]
DERIVATIVES_REGISTRY = ROOT / "configs/forward/derivatives_evidence_epochs.json"
OPPORTUNITY_REGISTRY = ROOT / "configs/forward/opportunity_forward_campaigns.json"
V0320_EPOCH = ROOT / "configs/forward/v0.3.20_derivatives_evidence_epoch.json"
V0320_OPPORTUNITY = ROOT / "configs/forward/v0.3.20_opportunity_successor_campaign.json"


def test_binance_collect_derivatives_empty_source_times_no_type_error() -> None:
    client = BinancePublicClient(DataConfig())
    # Mock all HTTP calls to raise BinanceDataError as _get does on HTTP 451
    mock_err = BinanceDataError("Binance public data request failed [HTTP_4XX_NON_RETRYABLE]: HTTP Error 451", "HTTP_4XX_NON_RETRYABLE", False)
    with patch.object(client, "_get", side_effect=mock_err):
        # Must not raise TypeError: 'int' object is not iterable
        res = client.collect_derivatives("BTCUSDT")
        assert isinstance(res, DerivativeCollection)
        assert res.observed_at_ms >= res.collection_started_at_ms
        assert not any(res.field_availability.values())
        assert "_observation_clock" in res.endpoint_telemetry
        assert res.endpoint_telemetry["_observation_clock"]["success"] is True


def test_microstructure_heartbeat_survives_sqlite_locked(tmp_path: Path) -> None:
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    # Ensure partition exists
    db_path = store._path(1_000_000)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE process_instances (instance_id TEXT, last_heartbeat_ms INTEGER, status TEXT)")
        conn.execute("INSERT INTO process_instances VALUES ('inst1', 1000000, 'ACTIVE')")

    # Simulate locked database on sqlite3.connect
    with patch("sqlite3.connect", side_effect=sqlite3.OperationalError("database is locked")):
        # Must not raise sqlite3.OperationalError
        store.heartbeat(1_001_000, "inst1")


def test_microstructure_status_uses_persistent_cache(tmp_path: Path) -> None:
    store = MicrostructureStore(tmp_path / "micro", "TEST_CAMPAIGN", 1_000_000)
    db_path = store._path(1_000_000)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE depth_events (event_time_ms INTEGER)")
        conn.execute("CREATE TABLE agg_trades (aggregate_trade_id INTEGER, receive_time_ms INTEGER, event_time_ms INTEGER)")
        conn.execute("CREATE TABLE book_samples (receive_time_ms INTEGER)")
        conn.execute("CREATE TABLE aggregates (interval_ms INTEGER, bucket_start_ms INTEGER)")
        conn.execute("CREATE TABLE audit_counters (name TEXT, value INTEGER)")
        conn.execute("CREATE TABLE coverage_segments (stream TEXT, start_ms INTEGER, end_ms INTEGER, sequence_valid INTEGER)")
        conn.execute("CREATE TABLE gaps (start_ms INTEGER, end_ms INTEGER, kind TEXT)")
        conn.execute("CREATE TABLE process_instances (instance_id TEXT, last_heartbeat_ms INTEGER, status TEXT)")
        conn.execute("CREATE TABLE clock_measurements (measured_at_ms INTEGER, offset_ms REAL, rtt_ms INTEGER, quality TEXT)")
        conn.execute("INSERT INTO depth_events VALUES (1000000)")
        conn.execute("INSERT INTO agg_trades VALUES (1, 1000005, 1000000)")
        conn.execute("INSERT INTO process_instances VALUES ('inst1', 1000005, 'ACTIVE')")

    # First call generates cache
    status1 = store.status(now_ms=1_001_000)
    assert status1["depth_events"] == 1
    assert status1["agg_trade_events"] == 1
    assert store._stats_cache_path.exists()

    # Second call reads from cache
    status2 = store.status(now_ms=1_001_000)
    assert status2["depth_events"] == 1
    assert status2["agg_trade_events"] == 1


def test_v0320_derivatives_epoch_preregistration() -> None:
    assert V0320_EPOCH.exists()
    registry = EvidenceEpochRegistry.load(DERIVATIVES_REGISTRY)

    # V0316_002 must be terminal archive
    v0316 = next(e for e in registry.entries if e.epoch_id == "DERIVATIVES_PIT_EPOCH_V0316_002")
    assert v0316.status == "FAILED_GAP_GATE_TERMINAL"
    assert v0316.formal_eligibility_role == "FORMAL_TERMINAL"
    assert v0316.superseded_by == "DERIVATIVES_PIT_EPOCH_V0320_001"
    assert "Standby" in str(v0316.terminal_reason)

    # V0320_001 was active in v0.3.20 and terminalized in v0.3.21
    v0320 = next(e for e in registry.entries if e.epoch_id == "DERIVATIVES_PIT_EPOCH_V0320_001")
    assert v0320.formal_eligibility_role in {"FORMAL_ACTIVE", "FORMAL_TERMINAL"}
    assert v0320.status in {"ACTIVE_ACCUMULATING", "FAILED_GAP_GATE_TERMINAL"}
    assert v0320.start_ms == 1788417000000


def test_v0320_opportunity_successor_preregistration() -> None:
    assert V0320_OPPORTUNITY.exists()
    registry = OpportunityCampaignRegistry.load(OPPORTUNITY_REGISTRY)

    # H36 must be terminal archive
    h36 = next(c for c in registry.campaigns if c.campaign_id == "OPPORTUNITY_FORWARD_V0317_20260901T160000Z")
    assert h36.status == "DATA_QUALITY_TERMINAL_ARCHIVE"
    assert h36.formal_role == "DATA_QUALITY_TERMINAL_ARCHIVE"
    assert h36.superseded_by == "OPPORTUNITY_FORWARD_V0320_20260903T063000Z"

    # H37 was active in v0.3.20 and terminalized in v0.3.21
    h37 = next(c for c in registry.campaigns if c.campaign_id == "OPPORTUNITY_FORWARD_V0320_20260903T063000Z")
    assert h37.hypothesis_id == "H37_OPPORTUNITY_FORWARD_REPLICATION_RECOVERY"
    assert h37.formal_role in {"FORMAL_SUCCESSOR_ACTIVE", "DATA_QUALITY_TERMINAL_ARCHIVE"}
    assert h37.start_ms == 1788417000000

    campaign, lifecycle = registry.preregistered_successor()
    assert campaign.campaign_id in {
        "OPPORTUNITY_FORWARD_V0320_20260903T063000Z",
        "OPPORTUNITY_FORWARD_V0321_20260903T180000Z",
    }
    assert lifecycle.hypothesis_id in {
        "H37_OPPORTUNITY_FORWARD_REPLICATION_RECOVERY",
        "H38_OPPORTUNITY_FORWARD_REPLICATION_LOCAL_RECOVERY",
    }


def test_forward_doctor_structure_and_safety_invariants() -> None:
    doc = forward_doctor()
    assert "status" in doc
    assert "issues" in doc
    assert "wsl_systemd" in doc
    assert "systemd_units" in doc
    assert "network" in doc
    assert "chains" in doc
    assert "campaigns" in doc

    # Safety invariants
    invariants = doc["safety_invariants"]
    assert invariants["execution"] == "DISABLED"
    assert invariants["final_holdout"] == "SEALED"
    assert invariants["qualified_direction_engine"] == "NONE"
    assert invariants["strategy"] == "EXPERIMENTAL"
    assert invariants["immutable_evidence_policy"] == "NO_BACKFILL_OR_HISTORY_REWRITE"


def test_recover_services_dry_run() -> None:
    res = recover_services(dry_run=True)
    assert res["status"] == "DRY_RUN_COMPLETE"
    assert res["dry_run"] is True
    assert len(res["actions_planned"]) > 0
    assert len(res["actions_executed"]) == 0
    assert res["invariants_preserved"]["historical_data_mutated"] is False
    assert res["invariants_preserved"]["slots_backfilled"] is False
    assert res["invariants_preserved"]["execution_enabled"] is False


def test_network_proxy_check_detects_http_451() -> None:
    mock_err = HTTPError("https://fapi.binance.com/fapi/v1/ping", 451, "Unavailable For Legal Reasons", {}, None)  # type: ignore[arg-type]
    with patch("urllib.request.urlopen", side_effect=mock_err):
        net = check_network_proxy()
        assert net["binance_reachability"] == "HTTP_451_REGION_RESTRICTED"
        assert "restricted location" in net["binance_detail"]

    mock_opener = MagicMock(side_effect=mock_err)
    net_inject = check_network_proxy(url_opener=mock_opener)
    assert net_inject["binance_reachability"] == "HTTP_451_REGION_RESTRICTED"
    assert "restricted location" in net_inject["binance_detail"]
