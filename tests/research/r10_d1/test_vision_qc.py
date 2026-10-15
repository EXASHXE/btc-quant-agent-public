"""All rows and archives here are SYNTHETIC; no source data or network access."""
import hashlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
import zipfile
from datetime import UTC

MODULE = Path(__file__).resolve().parents[3] / "scripts/research/r10_d1/vision_qc.py"
spec = importlib.util.spec_from_file_location("r10_d1_vision_qc", MODULE)
qc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qc)
DAY = qc.DAYS[0]


def bars():
    start = qc.day_ms(DAY)
    return [[str(start + i*60000), "10", "12", "9", "11", "2",
             str(start + i*60000 + 59999), "20", "2", "1", "10", "0"] for i in range(1440)]


def metrics():
    from datetime import datetime
    return [qc.METRICS] + [[datetime.fromtimestamp((qc.day_ms(DAY) + i*300000)/1000,
               UTC).strftime("%Y-%m-%d %H:%M:%S"), "BTCUSDT", *(["1"]*6)]
               for i in range(1, 289)]


class QCNegativeTests(unittest.TestCase):
    def archive(self, root, payload=None, member=None, truncated=False):
        path = root / f"BTCUSDT-1m-{DAY}.zip"
        body = payload if payload is not None else "\n".join(
            ",".join(row) for row in [qc.BARS, *bars()]).encode()
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(member or path.with_suffix(".csv").name, body)
        if truncated:
            path.write_bytes(path.read_bytes()[:-30])
        check = root / (path.name + ".CHECKSUM")
        check.write_text(hashlib.sha256(path.read_bytes()).hexdigest() + "  " + path.name + "\n")
        return path, check

    def test_valid_bar_archive_and_crc(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d))
            result = qc.qc_zip(p, c, "klines", DAY, qc.Budget())
            self.assertEqual((result["qc"], result["valid_rows"]), ("PASS", 1440))

    def test_wrong_publisher_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d))
            c.write_text("0"*64 + "  " + p.name + "\n")
            with self.assertRaisesRegex(qc.SafetyError, "PUBLISHER_CHECKSUM_MISMATCH"):
                qc.qc_zip(p, c, "klines", DAY, qc.Budget())

    def test_wrong_checksum_filename(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d))
            c.write_text(hashlib.sha256(p.read_bytes()).hexdigest() + "  other.zip\n")
            with self.assertRaisesRegex(qc.SafetyError, "CHECKSUM_IDENTITY"):
                qc.verify_checksum(p, c)

    def test_truncated_zip_with_matching_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d), truncated=True)
            with self.assertRaisesRegex(qc.SafetyError, "ZIP_OR_CSV_INTEGRITY"):
                qc.qc_zip(p, c, "klines", DAY, qc.Budget())

    def test_path_traversal_filename(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d), member="../escaped.csv")
            with self.assertRaisesRegex(qc.SafetyError, "ZIP_UNSAFE_MEMBER"):
                qc.qc_zip(p, c, "klines", DAY, qc.Budget())
            self.assertFalse((Path(d).parent / "escaped.csv").exists())

    def test_zip_expansion_bomb(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d), payload=b"x"*1000000)
            with self.assertRaisesRegex(qc.SafetyError, "ZIP_EXPANSION_RATIO"):
                qc.qc_zip(p, c, "klines", DAY, qc.Budget())

    def test_expanded_budget(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d))
            with self.assertRaisesRegex(qc.SafetyError, "EXPANDED_BUDGET"):
                qc.qc_zip(p, c, "klines", DAY, qc.Budget(expanded=10))

    def test_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p, c = self.archive(Path(d), payload=b"\xff,\xfe\n")
            with self.assertRaisesRegex(qc.SafetyError, "ZIP_OR_CSV_INTEGRITY"):
                qc.qc_zip(p, c, "klines", DAY, qc.Budget())

    def test_duplicate_one_minute_bar(self):
        rows = bars()
        result = qc.qc_rows(iter([qc.BARS, *rows, rows[0]]), "klines", DAY)
        self.assertEqual(result["duplicate_timestamps"], 1)
        self.assertEqual(result["qc"], "FAIL")

    def test_missing_five_minute_interval(self):
        rows = metrics()
        del rows[2]
        result = qc.qc_rows(iter(rows), "metrics", DAY)
        self.assertEqual((result["qc"], result["missing_intervals"]), ("FAIL", 1))

    def test_stock_vs_flow_misaligned(self):
        end = qc.day_ms(DAY) + 300000
        with self.assertRaisesRegex(qc.SafetyError, "STOCK_FLOW_TIME_MISALIGNED"):
            qc.metric_clock(end, end - 300000, end - 300000, end)
        with self.assertRaisesRegex(qc.SafetyError, "STOCK_FLOW_TIME_MISALIGNED"):
            qc.metric_clock(end, end, end, end + 300000)

    def test_shifted_start_vs_end_label(self):
        from datetime import datetime
        rows = metrics()
        for row in rows[1:]:
            dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
            row[0] = datetime.fromtimestamp(dt.timestamp() - 300, UTC).strftime(
                "%Y-%m-%d %H:%M:%S")
        result = qc.qc_rows(iter(rows), "metrics", DAY)
        self.assertIn("SHIFTED_START_VS_END_LABEL", result["errors"])
        self.assertEqual(result["observed_internal_grid_holes"], 0)
        self.assertEqual(result["time_contract"]["observed_grid"], "START_GRID")
        self.assertEqual(result["time_contract"]["proxy_first_utc"]["5"],
                         qc.iso(qc.day_ms(DAY) + 600000))

    def test_good_metrics_have_three_fixed_proxies(self):
        result = qc.qc_rows(iter(metrics()), "metrics", DAY)
        self.assertEqual(result["qc"], "PASS")
        self.assertEqual(set(result["time_contract"]["proxy_first_utc"]), {"5", "10", "15"})
        self.assertEqual(result["time_contract"]["pit"], "PIT_UNKNOWN")

    def test_missing_metric_field_preserves_label_grid(self):
        rows = metrics()
        rows[1][4] = ""
        result = qc.qc_rows(iter(rows), "metrics", DAY)
        self.assertEqual((result["rows"], result["timestamp_rows"]), (288, 288))
        self.assertEqual(result["missing_intervals"], 0)
        self.assertEqual(result["missing_field_counts"],
                         {"count_toptrader_long_short_ratio": 1})
        self.assertEqual(result["qc"], "FAIL")

    def test_nonfinite_and_schema_drift(self):
        rows = bars()
        rows[0][1] = "NaN"
        self.assertEqual(qc.qc_rows(iter(rows), "klines", DAY)["malformed_rows"], 1)
        with self.assertRaisesRegex(qc.SafetyError, "SCHEMA_DRIFT"):
            qc.qc_rows(iter([["wrong_header", *qc.BARS[1:]], *bars()]), "klines", DAY)

    def test_source_date_host_family_and_port_refused_before_network(self):
        good = qc.object_url("klines", DAY)
        bad = [good.replace("data.binance.vision", "example.org"), good.replace("https:", "http:"),
               good.replace("2022-09-15", "2022-09-22"), good + "?x=1",
               good.replace("data.binance.vision", "data.binance.vision:443"),
               good.replace("BTCUSDT", "ETHUSDT"), good.replace("klines", "openInterest")]
        with patch.object(qc, "build_opener") as build:
            fetcher = qc.Fetcher(qc.Budget())
            for url in bad:
                with self.subTest(url=url), self.assertRaises(qc.SafetyError):
                    fetcher.get(url, Path("unused"))
            build.return_value.open.assert_not_called()
        with self.assertRaises(qc.SafetyError):
            qc.object_url("klines", "2022-09-22")

    def test_source_row_outside_date_refused(self):
        rows = bars()
        rows[0][0] = str(qc.day_ms(DAY) - 60000)
        rows[0][6] = str(int(rows[0][0]) + 59999)
        result = qc.qc_rows(iter(rows), "klines", DAY)
        self.assertEqual(result["qc"], "FAIL")
        self.assertIn("OFF_GRID_OR_DATE", result["errors"])

    def test_extreme_timestamp_is_bounded(self):
        rows = bars()
        rows[0][0] = "9"*100
        result = qc.qc_rows(iter(rows), "klines", DAY)
        self.assertEqual(result["malformed_rows"], 1)
        self.assertEqual(result["qc"], "FAIL")

    def test_blank_first_csv_row(self):
        with self.assertRaisesRegex(qc.SafetyError, "CSV_SHAPE"):
            qc.qc_rows(iter([[]]), "klines", DAY)

    def test_compressed_budget_and_duplicate_object(self):
        budget = qc.Budget(compressed=10)
        budget.consume(10)
        with self.assertRaisesRegex(qc.SafetyError, "COMPRESSED_BUDGET"):
            budget.consume(1)
        url = qc.object_url("klines", DAY)
        budget.register(url)
        with self.assertRaisesRegex(qc.SafetyError, "OBJECT_ALREADY_REQUESTED"):
            budget.register(url)
        with self.assertRaisesRegex(qc.SafetyError, "BUDGET_CONFIGURATION"):
            qc.Budget(compressed=qc.COMPRESSED_CAP + 1)

    def test_redirect_refused(self):
        with self.assertRaisesRegex(qc.SafetyError, "REDIRECT_REFUSED"):
            qc.NoRedirect().redirect_request(None, None, 302, "", {}, "https://example.org")

    def test_retry_is_bounded(self):
        with tempfile.TemporaryDirectory() as d, patch.object(qc, "time") as clock:
            fetcher = qc.Fetcher(qc.Budget())
            with patch.object(fetcher.opener, "open", side_effect=URLError("synthetic")) as op:
                with self.assertRaisesRegex(qc.SafetyError, "HTTP_RETRIES_EXHAUSTED"):
                    fetcher.get(qc.object_url("klines", DAY), Path(d) / "file")
                self.assertEqual(op.call_count, 3)
                self.assertEqual(clock.sleep.call_count, 2)

    def test_http_budget_refused_before_read(self):
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as d:
            fetcher = qc.Fetcher(qc.Budget(compressed=10))
            url = qc.object_url("klines", DAY)
            response = MagicMock()
            response.status = 200
            response.geturl.return_value = url
            response.headers = {"Content-Length": "11"}
            response.__enter__.return_value = response
            with (patch.object(fetcher.opener, "open", return_value=response),
                  self.assertRaisesRegex(qc.SafetyError, "HTTP_SIZE_BUDGET")):
                fetcher.get(url, Path(d) / "file")
            response.read.assert_not_called()

    def test_forbidden_access_not_retried(self):
        with tempfile.TemporaryDirectory() as d:
            fetcher = qc.Fetcher(qc.Budget())
            exc = HTTPError(qc.object_url("klines", DAY), 403, "", {}, io.BytesIO())
            with patch.object(fetcher.opener, "open", side_effect=exc) as op:
                with self.assertRaisesRegex(qc.SafetyError, "HTTP_ACCESS_OR_STATUS_STOP"):
                    fetcher.get(qc.object_url("klines", DAY), Path(d) / "file")
                self.assertEqual(op.call_count, 1)


if __name__ == "__main__":
    unittest.main()
