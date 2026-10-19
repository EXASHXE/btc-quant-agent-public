"""One tiny actual Q3 archive, full streaming read, no writes to any source."""

import pytest

from scripts.research.cross_venue import US
from scripts.research.cross_venue import normalized_sources as n
from scripts.research.cross_venue import pipeline as p


def test_bounded_real_q3_okx_day_and_metadata_intersection():
    root = n.DATA_PARENT / "okx-swap-expansion"
    if not root.exists():
        pytest.skip("Explicit Q3 source root is absent")
    snapshot = n.Snapshot.capture(root, "okx", "Q3")
    budget = n.Budget(expanded_cap=256 * 1024, compressed_cap=64 * 1024, object_cap=1)
    sources = n.expansion_sources(snapshot, budget)
    source = next(s for s in sources if s.record["family"] == "candlesticks"
                  and s.record["symbol"] == "BTC-USDT-SWAP" and s.record["period"] == "2026-07-01")
    assert source.selected
    count = 0
    first = last = None
    for bar in n.source_bars(source, budget):
        first = bar if first is None else first
        last = bar
        count += 1
    snapshot.verify()
    assert count == 1440 and source.scan["status"] == "FULL_STREAM_SCAN"
    assert first.open_us == (n.quarter_window("Q3")[0] - 8 * 3600) * US
    assert last.open_us - first.open_us == 1439 * 60 * US
    assert source.actual_sha256 == source.record["local_sha256"]
    assert budget.compressed_read < 64 * 1024 and budget.expanded_read < 256 * 1024
    assert snapshot.before == snapshot.after and snapshot.unchanged
    binance = n.Snapshot.capture(n.DATA_PARENT / "binance-usdm-expansion", "binance", "Q3")
    binance_sources = n.expansion_sources(binance, n.Budget(expanded_cap=0))
    for asset in ("BTC", "ETH"):
        metadata = p.metadata_intersection(sources + binance_sources, "Q3", asset)
        start, end = n.quarter_window("Q3")
        assert metadata["candidate_aligned_minutes"] == 132000
        assert metadata["candidate_ranges_utc_us_half_open"] == [[start * US, (end - 8 * 3600) * US]]
        assert metadata["evidence"] == "METADATA_BOUNDS_REQUIRE_STREAM_CONFIRMATION"
    binance.verify()
    snapshot.verify()
