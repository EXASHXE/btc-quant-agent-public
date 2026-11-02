from __future__ import annotations

from pathlib import Path

from .binance import BinancePublicClient
from .derivatives import HistoricalDerivativeStore, write_historical_derivatives_csv
from .manifest import DataManifest, build_manifest, write_manifest


def collect_derivative_snapshot(
    client: BinancePublicClient,
    path: str | Path,
    *,
    symbol: str = "BTCUSDT",
    include_order_book: bool = False,
    manifest_path: str | Path | None = None,
) -> DataManifest:
    target = Path(path)
    existing = (
        HistoricalDerivativeStore.from_csv(target).as_rows() if target.exists() else []
    )
    snapshot = client.derivatives(symbol, include_order_book=include_order_book)
    by_timestamp = {int(row["observed_at_ms"]): row for row in existing}
    by_timestamp[snapshot.observed_at_ms] = HistoricalDerivativeStore((snapshot,)).as_rows()[0]
    rows = [by_timestamp[key] for key in sorted(by_timestamp)]
    store = HistoricalDerivativeStore.from_rows(rows)
    write_historical_derivatives_csv(target, store.as_snapshots())
    manifest = build_manifest(
        target,
        source="Binance USD-M public REST point-in-time collector",
        rows=rows,
        timestamp_field="observed_at_ms",
        expected_interval_ms=15 * 60_000,
    )
    write_manifest(manifest_path or target.with_suffix(".manifest.json"), manifest)
    return manifest
