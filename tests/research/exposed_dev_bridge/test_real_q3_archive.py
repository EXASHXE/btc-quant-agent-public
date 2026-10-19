"""One real PASS OKX day, bounded ZIP read, hashes before/after, no outcomes."""

from scripts.research.cross_venue import normalized_sources as n
from scripts.research.exposed_dev_bridge.inspection import intersection


def test_real_q3_pass_archive_bounded_read_and_utc8_raw_lineage():
    root = n.DATA_PARENT / "okx-swap-expansion"
    assert root.is_dir(), "This task requires the prechecked Q3 archive"
    snapshot = n.Snapshot.capture(root, "okx", "Q3")
    budget = n.Budget(expanded_cap=256 * 1024, compressed_cap=64 * 1024, object_cap=1)
    sources = n.expansion_sources(snapshot, budget)
    source = next(s for s in sources if s.record["family"] == "candlesticks"
                  and s.record["symbol"] == "BTC-USDT-SWAP" and s.record["period"] == "2026-07-01")
    assert source.selected and source.record["verdict"] == source.qc["verdict"] == "PASS"
    count, first, last = 0, None, None
    for bar in n.source_bars(source, budget):
        first = bar if first is None else first
        last = bar
        count += 1
    snapshot.verify()
    assert count == 1440 and source.scan["status"] == "FULL_STREAM_SCAN"
    assert source.actual_sha256 == source.record["local_sha256"]
    start, end = n.quarter_window("Q3")
    assert first.open_us == (start - 8 * 3600) * n.US
    assert last.open_us == (start + 16 * 3600 - 60) * n.US
    assert first.provenance["receiver_pit"] == "PIT_UNKNOWN"
    assert first.provenance["file_calendar_timezone"] == "UTC+08:00"
    assert snapshot.before == snapshot.after and snapshot.unchanged
    assert budget.compressed_read < 64 * 1024 and budget.expanded_read < 256 * 1024
    binance = n.Snapshot.capture(n.DATA_PARENT / "binance-usdm-expansion", "binance", "Q3")
    all_sources = sources + n.expansion_sources(binance, n.Budget(expanded_cap=0))
    result = intersection(all_sources, start, end, "BTC")
    assert result["candidate_aligned_minutes"] == 132000
    assert result["ranges_utc_us_half_open"] == [[start * n.US, (end - 8 * 3600) * n.US]]
    binance.verify()
    snapshot.verify()
