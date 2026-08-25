import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from btc_quant_agent.data.binance_archive import (
    _months,
    _parse_klines,
    _write_parquet,
    read_parquet_candles,
)


class BinanceArchiveTests(unittest.TestCase):
    def test_months_and_dataset_boundaries_are_utc(self) -> None:
        start = datetime(2021, 11, 1, tzinfo=UTC)
        end = datetime(2022, 2, 1, tzinfo=UTC)
        self.assertEqual(_months(start, end), [(2021, 11), (2021, 12), (2022, 1), (2022, 2)])

    def test_parse_audits_ohlc_volume_duplicates_and_order(self) -> None:
        rows = [
            ["60000", "100", "101", "99", "100.5", "1", "119999", "100", "1", "0.5", "50", "0"],
            ["0", "100", "99", "101", "100", "-1", "59999", "100", "1", "0.5", "50", "0"],
            ["0", "100", "101", "99", "100", "0", "59999", "100", "1", "0.5", "50", "0"],
        ]
        parsed, audit = _parse_klines(rows)
        self.assertEqual(len(parsed), 3)
        self.assertEqual(audit["duplicates"], 1)
        self.assertEqual(audit["out_of_order"], 1)
        self.assertEqual(audit["invalid_ohlc"], 1)
        self.assertEqual(audit["negative_volume"], 1)
        self.assertEqual(audit["zero_volume"], 1)

    def test_parquet_round_trip_preserves_binance_boundaries(self) -> None:
        rows, _ = _parse_klines(
            [["0", "100", "101", "99", "100.5", "1", "59999", "100", "1", "0.5", "50", "0"]]
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _write_parquet(root / "1m/year=1970/month=01/data.parquet", rows)
            candles = read_parquet_candles(root, start_ms=0, end_ms=60_000)
        self.assertEqual(len(candles), 1)
        self.assertEqual(candles[0].open_time_ms, 0)
        self.assertEqual(candles[0].close_time_ms, 59_999)


if __name__ == "__main__":
    unittest.main()
