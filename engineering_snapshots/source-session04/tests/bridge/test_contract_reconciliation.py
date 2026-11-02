"""Adopted contract replacements; the three original failing tests stay byte-identical."""

from btc_quant_agent.platform.advisory import gate
from btc_quant_agent.platform.bridge.adapters import PublicPayloadAdapter
from btc_quant_agent.platform.bridge.admission import compile_snapshot
from btc_quant_agent.platform.bridge.fixtures import OfflineFixtureProvider
from btc_quant_agent.platform.bridge.runtime import BridgeStore, ReadOnlyScanner, candidate_from_json


def test_reconciled_missing_quote_preserves_committed_watch(config, tmp_path):
    source = OfflineFixtureProvider(config, "missing_quote")
    store = BridgeStore(tmp_path / "scan.sqlite")
    result = ReadOnlyScanner(config, store).scan(source.snapshot(50))
    watch = next(r for r in result["records"] if r["symbol"] == "BTCUSDT")
    assert watch["state"] == "WATCH" and "EXECUTABLE_QUOTE_MISSING" in watch["veto_reasons"]
    assert result["persistence"] and all(x["notification_status"] == "PENDING" for x in result["persistence"])
    assert store.positions() == []


def test_reconciled_strong_analytical_setup_needs_bound_source_authority(config, tmp_path):
    source = OfflineFixtureProvider(config)
    initial = ReadOnlyScanner(config, BridgeStore(tmp_path / "scan.sqlite")).scan(source.snapshot(50))
    raw = next(r["candidate"] for r in initial["records"] if r["symbol"] == "BTCUSDT")
    candidate = candidate_from_json(raw)
    batch = source.snapshot(51)
    a = compile_snapshot(
        PublicPayloadAdapter("binance", "PERPETUAL", 60).normalize(batch, config.platform.universe), config
    )
    unbound = gate(candidate, a.events["BTCUSDT"], config.platform)
    assert "REAL_MARKET_SOURCE_NOT_AUTHORIZED" in unbound.veto_reasons and unbound.risk is None
    bound = gate(candidate, a.events["BTCUSDT"], config.platform, source_admission=a.admission["BTCUSDT"])
    assert bound.action == "ENTRY_ELIGIBLE" and bound.risk.quantity > 0


def test_reconciled_verified_provider_evidence_reaches_durable_entry_without_llm_or_order(config, tmp_path):
    source = OfflineFixtureProvider(config)
    store = BridgeStore(tmp_path / "scan.sqlite")
    scanner = ReadOnlyScanner(config, store)
    scanner.scan(source.snapshot(50))
    result = scanner.scan(source.snapshot(51))
    row = next(r for r in result["records"] if r["symbol"] == "BTCUSDT")
    assert row["state"] == "ENTRY_ELIGIBLE" and row["plan"]["risk"] is not None
    for receipt in result["persistence"]:
        notification = store.get_notification(receipt["event_id"])
        assert notification["status"] == "PENDING" and notification["attempts"] == 0
        with store._connect() as db:
            assert db.execute(
                "SELECT 1 FROM platform_decisions WHERE id=?", (receipt["decision_id"],)
            ).fetchone()
    assert store.positions() == [] and result["notification_mode"] == "PREVIEW_ONLY"
