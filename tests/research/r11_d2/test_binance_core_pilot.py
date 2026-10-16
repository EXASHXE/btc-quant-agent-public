"""Synthetic unit tests for R11-D2 Binance Core Historical Data Foundation Pilot.

Tests deterministic validation logic, negative safety cases, schema adherence,
and duplicate representation checks entirely on synthetic in-memory fixtures.
Zero external network calls; zero real source data embedded.
"""
from __future__ import annotations

import csv
from datetime import UTC, datetime
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.research.r11_d2.binance_core_pilot import (
    AGG_TRADES_SCHEMA,
    BARS_SCHEMA,
    FUNDING_RATE_SCHEMA,
    METRICS_SCHEMA,
    TRADES_SCHEMA,
    Budget,
    SafetyError,
    compare_daily_vs_monthly,
    qc_rows,
    qc_zip,
    verify_checksum,
)


def make_zip(filename: str, csv_content: str, compress_type: int = zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compress_type) as zf:
        zf.writestr(filename, csv_content)
    return buf.getvalue()


class TestBinanceCorePilotQC(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_checksum_verification_success(self) -> None:
        zip_bytes = b"sample_zip_content"
        digest = hashlib.sha256(zip_bytes).hexdigest()
        zip_path = self.tmp / "test.zip"
        zip_path.write_bytes(zip_bytes)
        checksum_path = self.tmp / "test.zip.CHECKSUM"
        checksum_path.write_text(f"{digest}  test.zip\n")

        verified = verify_checksum(zip_path, checksum_path)
        self.assertEqual(verified, digest)

    def test_checksum_verification_mismatch_fails(self) -> None:
        zip_bytes = b"sample_zip_content"
        zip_path = self.tmp / "test.zip"
        zip_path.write_bytes(zip_bytes)
        checksum_path = self.tmp / "test.zip.CHECKSUM"
        checksum_path.write_text(f"{'0'*64}  test.zip\n")

        with self.assertRaises(SafetyError) as ctx:
            verify_checksum(zip_path, checksum_path)
        self.assertEqual(str(ctx.exception), "PUBLISHER_CHECKSUM_MISMATCH")

    def test_zip_traversal_rejection(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../evil.csv", "a,b,c\n")
        zip_path = self.tmp / "evil.zip"
        zip_path.write_bytes(buf.getvalue())
        checksum_path = self.tmp / "evil.zip.CHECKSUM"
        digest = hashlib.sha256(buf.getvalue()).hexdigest()
        checksum_path.write_text(f"{digest}  evil.zip\n")

        budget = Budget()
        with self.assertRaises(SafetyError) as ctx:
            qc_zip(zip_path, checksum_path, "klines", "BTCUSDT", "2024-01-01", False, budget)
        self.assertIn(str(ctx.exception), ("ZIP_MEMBER_NAME", "ZIP_TRAVERSAL"))

    def test_kline_ohlc_violation_fails(self) -> None:
        # High lower than Open
        rows = [
            BARS_SCHEMA,
            ["1704067200000", "42000", "41000", "40000", "41500", "10", "1704067259999", "420000", "100", "5", "210000", "0"]
        ]
        res = qc_rows(iter(rows), "klines", "BTCUSDT", "2024-01-01", False)
        self.assertIn("MALFORMED_ROW", res["errors"])

    def test_kline_valid_structure(self) -> None:
        rows = [BARS_SCHEMA]
        start = int(datetime(2024, 1, 1, 0, 0, tzinfo=UTC).timestamp() * 1000)
        for i in range(1440):
            t = start + i * 60000
            rows.append([
                str(t), "42000.0", "42500.0", "41900.0", "42200.0", "10.0",
                str(t + 59999), "422000.0", "50", "5.0", "211000.0", "0"
            ])
        res = qc_rows(iter(rows), "klines", "BTCUSDT", "2024-01-01", False)
        self.assertEqual(res["qc"], "PASS")
        self.assertEqual(res["total_rows"], 1440)
        self.assertEqual(res["duplicate_timestamps"], 0)
        self.assertEqual(res["missing_intervals"], 0)

    def test_metrics_valid_structure_and_pit_semantics(self) -> None:
        rows = [METRICS_SCHEMA]
        start = int(datetime(2024, 1, 1, 0, 0, tzinfo=UTC).timestamp())
        for i in range(288):
            dt_str = datetime.fromtimestamp(start + i * 300, UTC).strftime("%Y-%m-%d %H:%M:%S")
            rows.append([
                dt_str, "BTCUSDT", "74000.5", "3100000000.0", "1.5", "1.2", "1.4", "1.1"
            ])
        res = qc_rows(iter(rows), "metrics", "BTCUSDT", "2024-01-01", False)
        self.assertEqual(res["qc"], "PASS")
        self.assertEqual(res["total_rows"], 288)
        self.assertEqual(res["observed_grid_type"], "START_GRID_00:00_TO_23:55")
        self.assertIn("pit_provenance", res)
        self.assertEqual(res["pit_provenance"]["pit_terminal"], "PIT_UNKNOWN")
        self.assertIn("sum_open_interest", res["pit_provenance"]["stock_snapshot_fields"])
        self.assertIn("sum_taker_long_short_vol_ratio", res["pit_provenance"]["interval_flow_fields"])

    def test_funding_rate_valid_structure(self) -> None:
        rows = [FUNDING_RATE_SCHEMA]
        start = int(datetime(2024, 1, 1, 0, 0, tzinfo=UTC).timestamp() * 1000)
        for i in range(93):
            jitter = 1 if i % 10 == 0 else 0  # small publisher engine jitter
            t = start + i * (8 * 3600 * 1000) + jitter
            rows.append([str(t), "8", "0.00037500"])
        res = qc_rows(iter(rows), "fundingRate", "BTCUSDT", "2024-01", True)
        self.assertEqual(res["qc"], "PASS")
        self.assertEqual(res["total_rows"], 93)
        self.assertEqual(res["expected_rows"], 93)

    def test_agg_trades_valid_structure(self) -> None:
        rows = [
            AGG_TRADES_SCHEMA,
            ["1001", "42100.5", "0.15", "5001", "5002", "1704067200123", "true"],
            ["1002", "42101.0", "0.20", "5003", "5003", "1704067200456", "false"],
        ]
        res = qc_rows(iter(rows), "aggTrades", "BTCUSDT", "2024-01-01", False)
        self.assertEqual(res["qc"], "PASS")
        self.assertEqual(res["total_rows"], 2)

    def test_trades_valid_structure(self) -> None:
        rows = [
            TRADES_SCHEMA,
            ["5001", "42100.5", "0.10", "4210.05", "1704067200100", "true"],
            ["5002", "42100.5", "0.05", "2105.025", "1704067200123", "true"],
        ]
        res = qc_rows(iter(rows), "trades", "BTCUSDT", "2024-01-01", False)
        self.assertEqual(res["qc"], "PASS")
        self.assertEqual(res["total_rows"], 2)

    def test_daily_vs_monthly_parity_check(self) -> None:
        # Create 2 synthetic daily zip files and 1 synthetic monthly zip file
        daily_files = []
        all_rows = []
        for d in range(1, 3):
            d_str = f"2024-01-0{d}"
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(BARS_SCHEMA)
            for i in range(5):
                t = (d * 86400 + i * 60) * 1000
                row = [str(t), "42000", "42100", "41900", "42050", "1.0", str(t + 59999), "42050", "10", "0.5", "21025", "0"]
                writer.writerow(row)
                all_rows.append(row)
            zip_p = self.tmp / f"BTCUSDT-1m-{d_str}.zip"
            zip_p.write_bytes(make_zip(f"BTCUSDT-1m-{d_str}.csv", csv_buf.getvalue()))
            daily_files.append(zip_p)

        monthly_buf = io.StringIO()
        m_writer = csv.writer(monthly_buf)
        m_writer.writerow(BARS_SCHEMA)
        for r in all_rows:
            m_writer.writerow(r)
        monthly_p = self.tmp / "BTCUSDT-1m-2024-01.zip"
        monthly_p.write_bytes(make_zip("BTCUSDT-1m-2024-01.csv", monthly_buf.getvalue()))

        res = compare_daily_vs_monthly(daily_files, monthly_p)
        self.assertTrue(res["exact_byte_for_byte_rows_identical"])
        self.assertEqual(res["representation_verdict"], "DUPLICATE_IDENTICAL_REPRESENTATION")


if __name__ == "__main__":
    unittest.main()
