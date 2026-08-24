import json
import tempfile
import unittest
from pathlib import Path

from btc_quant_agent.data.collector import collect_derivative_snapshot
from btc_quant_agent.data.derivatives import HistoricalDerivativeStore
from btc_quant_agent.data.manifest import build_manifest
from btc_quant_agent.domain import DerivativesSnapshot


class FakeDerivativeClient:
    def derivatives(self, _symbol: str, *, include_order_book: bool = False):
        return DerivativesSnapshot(
            observed_at_ms=1_000,
            mark_price=100.0,
            funding_rate=0.0001,
            funding_time_ms=1_000,
            order_book_imbalance=0.2 if include_order_book else None,
            order_book_time_ms=1_000 if include_order_book else None,
        )


class DataManifestTests(unittest.TestCase):
    def test_collector_appends_real_snapshot_and_writes_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "derivatives.csv"
            manifest_path = Path(directory) / "data_manifest.json"
            manifest = collect_derivative_snapshot(
                FakeDerivativeClient(),  # type: ignore[arg-type]
                dataset,
                include_order_book=False,
                manifest_path=manifest_path,
            )
            store = HistoricalDerivativeStore.from_csv(dataset)
            self.assertEqual(len(store.as_rows()), 1)
            self.assertEqual(manifest.records, 1)
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["checksum_sha256"], manifest.checksum_sha256)
            self.assertEqual(payload["field_coverage"]["order_book_imbalance"], 0.0)

    def test_manifest_reports_large_timestamp_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "sample.csv"
            dataset.write_text("timestamp,value\n0,1\n1000,2\n", encoding="utf-8")
            manifest = build_manifest(
                dataset,
                source="test",
                rows=[{"timestamp": 0, "value": 1}, {"timestamp": 1_000, "value": 2}],
                timestamp_field="timestamp",
                expected_interval_ms=100,
            )
            self.assertEqual(manifest.known_gaps, ("0->1000",))


if __name__ == "__main__":
    unittest.main()
