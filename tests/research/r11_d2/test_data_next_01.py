"""Changed-invariant T2 checks. Synthetic fixtures only; no source/network I/O."""
import csv
import io
import json
import tempfile
import unittest
import zipfile
from collections import Counter
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from scripts.research.r11_d2 import binance_core_pilot as pilot


def funding(period="2024-01"):
    start = datetime.fromisoformat(period + "-01").replace(tzinfo=UTC)
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    count = (end - start).days * 3
    return [pilot.FUNDING_RATE_SCHEMA.copy()] + [
        [str(int(start.timestamp() * 1000) + i * 28800000), "8", "-0.0001"]
        for i in range(count)
    ]


def metrics():
    start = datetime(2024, 1, 1, tzinfo=UTC)
    return [pilot.METRICS_SCHEMA.copy()] + [
        [(start + timedelta(minutes=i * 5)).strftime("%Y-%m-%d %H:%M:%S"),
         "BTCUSDT", "74000.5", "3100000000", "1.5", "1.2", "1.4", "1.1"]
        for i in range(288)
    ]


def bars(period, monthly):
    start = datetime.fromisoformat(period + "-01" if monthly else period).replace(tzinfo=UTC)
    end = ((start.replace(day=28) + timedelta(days=4)).replace(day=1)
           if monthly else start + timedelta(days=1))
    return [pilot.BARS_SCHEMA.copy()] + [
        [str(t), "42", "43", "41", "42", "10", str(t + 59999),
         "420", "10", "5", "210", "0"]
        for t in range(int(start.timestamp() * 1000), int(end.timestamp() * 1000), 60000)
    ]


def record_set():
    return [dict(family=fam, symbol=sym, period=period, is_monthly=monthly,
                 is_reused_from_r10_d1=reused,
                 uri=pilot.object_url(fam, sym, period, monthly), **qc_ok())
            for fam, sym, period, monthly, reused in pilot.pilot_tasks()]


def qc_ok():
    return {"qc": "PASS", "errors": [], "missing_field_counts": {},
            "invalid_field_counts": {}, "publisher_checksum": "VERIFIED",
            "sha256": "a" * 64, "compressed_bytes": 1, "expanded_bytes": 1}


class TestChangedQC(unittest.TestCase):
    def test_all_metric_numeric_columns_fail_closed(self):
        for column in range(2, 8):
            for value in ("invalid", "-1", "NaN", "sNaN", "Inf", "-Infinity"):
                with self.subTest(column=column, value=value):
                    rows = metrics()
                    rows[100][column] = value
                    result = pilot.qc_rows(iter(rows), "metrics", "BTCUSDT", "2024-01-01", False)
                    self.assertEqual(result["qc"], "FAIL")
                    self.assertEqual(result["valid_rows"], 287)
                    self.assertEqual(result["invalid_field_counts"],
                                     {pilot.METRICS_SCHEMA[column]: 1})
                    self.assertIn("INVALID_METRIC_VALUE", result["errors"])
                    self.assertEqual(result["pit_provenance"]["receiver_first_known"], "UNKNOWN")
                    self.assertEqual(result["pit_provenance"]["pit_terminal"], "PIT_UNKNOWN")

    def test_zero_and_positive_oi_pass_without_pit_promotion(self):
        for value in ("0", "0.1", "74000.5"):
            with self.subTest(value=value):
                rows = metrics()
                rows[1][2:4] = [value, value]
                result = pilot.qc_rows(iter(rows), "metrics", "BTCUSDT", "2024-01-01", False)
                self.assertEqual(result["qc"], "PASS")
                self.assertEqual(result["valid_rows"], 288)
                self.assertEqual(result["pit_provenance"]["economic_period_end"],
                                 "UNPROVEN_FROM_ARCHIVE_LABEL")

    def test_missing_oi_remains_partial_and_is_not_zero_imputed(self):
        rows = metrics()
        rows[1][2] = " "
        result = pilot.qc_rows(iter(rows), "metrics", "BTCUSDT", "2024-01-01", False)
        self.assertEqual(result["qc"], "PARTIAL_PASS")
        self.assertEqual(result["missing_field_counts"], {"sum_open_interest": 1})
        self.assertEqual(result["valid_rows"], 287)
        self.assertEqual(rows[1][2], " ")

    def test_metrics_endpoint_holes_and_duplicates_fail(self):
        for change in ("first", "last", "duplicate"):
            with self.subTest(change=change):
                rows = metrics()
                if change == "first":
                    del rows[1]
                elif change == "last":
                    rows.pop()
                else:
                    rows[2] = rows[1].copy()
                self.assertEqual(pilot.qc_rows(iter(rows), "metrics", "BTCUSDT",
                                              "2024-01-01", False)["qc"], "FAIL")

    def test_funding_calendar_controls_preserve_raw_jitter(self):
        for period, expected in (("2024-01", 93), ("2024-02", 87),
                                 ("2023-02", 84), ("2024-12", 93)):
            with self.subTest(period=period):
                rows = funding(period)
                rows[1][0] = str(int(rows[1][0]) + 5000)
                result = pilot.qc_rows(iter(rows), "fundingRate", "BTCUSDT", period, True)
                self.assertEqual(result["qc"], "PASS")
                self.assertEqual(result["expected_rows"], expected)
                self.assertEqual(result["missing_intervals"], 0)
                self.assertEqual(result["unexpected_intervals"], 0)
                self.assertTrue(result["timestamp_min_utc"].endswith("00:00:05+00:00"))
                self.assertTrue(result["timestamp_max_utc"].endswith("16:00:00+00:00"))

    def test_funding_missing_empty_and_extra_coverage_fail(self):
        for change in ("first", "last", "middle", "empty", "extra_next_month"):
            with self.subTest(change=change):
                rows = funding()
                if change in ("first", "last", "middle"):
                    del rows[{"first": 1, "last": -1, "middle": 40}[change]]
                elif change == "empty":
                    rows = rows[:1]
                else:
                    rows.append(["1706745600000", "8", "0.0001"])
                result = pilot.qc_rows(iter(rows), "fundingRate", "BTCUSDT", "2024-01", True)
                self.assertEqual(result["qc"], "FAIL")
                self.assertIn("ROW_COUNT_MISMATCH", result["errors"])

    def test_funding_shifted_month_and_off_grid_fail_even_at_93_rows(self):
        for shift in (-28800000, -1, 5001, 3600000, 28800000):
            with self.subTest(shift=shift):
                rows = funding()
                for row in rows[1:]:
                    row[0] = str(int(row[0]) + shift)
                result = pilot.qc_rows(iter(rows), "fundingRate", "BTCUSDT", "2024-01", True)
                self.assertEqual(result["total_rows"], 93)
                self.assertEqual(result["qc"], "FAIL")
                self.assertGreater(result["unexpected_intervals"], 0)

    def test_funding_duplicates_exact_and_same_slot_fail(self):
        for jitter in (0, 1, 5000):
            with self.subTest(jitter=jitter):
                rows = funding()
                rows[2][0] = str(int(rows[1][0]) + jitter)
                result = pilot.qc_rows(iter(rows), "fundingRate", "BTCUSDT", "2024-01", True)
                self.assertEqual(result["qc"], "FAIL")
                self.assertIn("DUPLICATE_FUNDING_SLOT", result["errors"])
                self.assertEqual(result["missing_intervals"], 1)

    def test_funding_nonmonotonic_and_malformed_fail(self):
        for change in ("reorder", "rate", "interval", "timestamp"):
            with self.subTest(change=change):
                rows = funding()
                if change == "reorder":
                    rows[1], rows[2] = rows[2], rows[1]
                else:
                    col, value = {"rate": (2, "NaN"), "interval": (1, "4"),
                                  "timestamp": (0, "bad")}[change]
                    rows[1][col] = value
                self.assertEqual(pilot.qc_rows(iter(rows), "fundingRate", "BTCUSDT",
                                              "2024-01", True)["qc"], "FAIL")

    def test_monthly_bars_complete_calendar_and_boundaries(self):
        for period, count in (("2024-01", 44640), ("2024-02", 41760), ("2024-12", 44640)):
            with self.subTest(period=period):
                rows = bars(period, True)
                result = pilot.qc_rows(iter(rows), "klines", "BTCUSDT", period, True)
                self.assertEqual(result["qc"], "PASS")
                self.assertEqual(result["expected_rows"], count)
        for change in ("first", "last", "duplicate", "shift", "empty"):
            with self.subTest(change=change):
                rows = bars("2024-01", True)
                if change in ("first", "last"):
                    del rows[1 if change == "first" else -1]
                elif change == "duplicate":
                    rows[2] = rows[1].copy()
                elif change == "shift":
                    for row in rows[1:]:
                        row[0] = str(int(row[0]) + 60000)
                        row[6] = str(int(row[6]) + 60000)
                else:
                    rows = rows[:1]
                self.assertEqual(pilot.qc_rows(iter(rows), "klines", "BTCUSDT",
                                              "2024-01", True)["qc"], "FAIL")

    def test_daily_monthly_representation_parity_positive_and_negative(self):
        # Parity alone is not calendar completeness; qc_rows checks that separately.
        with tempfile.TemporaryDirectory() as root:
            paths = [Path(root) / name for name in ("01.zip", "02.zip", "month.zip")]

            def write(path, rows):
                content = io.StringIO()
                csv.writer(content).writerows(rows)
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("fixture.csv", content.getvalue())

            first, last = bars("2024-01-01", False)[1:3]
            write(paths[0], [pilot.BARS_SCHEMA, first])
            write(paths[1], [pilot.BARS_SCHEMA, last])
            for change in ("none", "value", "missing", "duplicate", "header"):
                with self.subTest(change=change):
                    rows = [pilot.BARS_SCHEMA.copy(), first.copy(), last.copy()]
                    if change == "value":
                        rows[1][1] = "99"
                    elif change == "missing":
                        rows.pop()
                    elif change == "duplicate":
                        rows[2] = first.copy()
                    elif change == "header":
                        rows[0][1] = "different"
                    write(paths[2], rows)
                    result = pilot.compare_daily_vs_monthly(paths[:2], paths[2])
                    self.assertEqual(result["exact_byte_for_byte_rows_identical"],
                                     change == "none")


class TestChangedManifests(unittest.TestCase):
    def test_plan_reconciles_215_not_222(self):
        tasks = pilot.pilot_tasks()
        self.assertEqual(len(tasks), 215)
        self.assertEqual(sum(task[4] for task in tasks), 21)
        self.assertEqual(len(tasks) - sum(task[4] for task in tasks), 194)
        self.assertEqual(Counter((task[0], task[3]) for task in tasks), {
            ("klines", False): 69, ("klines", True): 2,
            ("markPriceKlines", False): 69, ("metrics", False): 69,
            ("fundingRate", True): 2, ("trades", False): 2, ("aggTrades", False): 2})
        self.assertEqual(len({pilot.object_url(*t[:4]) for t in tasks}), 215)
        self.assertEqual(pilot.manifest_summary(record_set())["errors"], [])

    def test_manifest_missing_duplicate_wrong_source_and_unverified_fail(self):
        for change in ("missing", "duplicate", "uri", "checksum", "invalid",
                       "missing_field_pass", "unfinished", "reused_flag", "failed"):
            with self.subTest(change=change):
                records = record_set()
                if change == "missing":
                    records.pop()
                elif change == "duplicate":
                    records[-1] = records[0].copy()
                elif change == "uri":
                    records[0]["uri"] = "https://example.invalid/other.zip"
                elif change == "checksum":
                    records[0]["publisher_checksum"] = "UNKNOWN"
                elif change == "invalid":
                    records[0]["invalid_field_counts"] = {"sum_open_interest": 1}
                elif change == "missing_field_pass":
                    records[0]["missing_field_counts"] = {"sum_open_interest": 1}
                elif change == "unfinished":
                    del records[0]["qc"]
                elif change == "reused_flag":
                    records[0]["is_reused_from_r10_d1"] = False
                else:
                    records[0]["qc"] = "FAIL"
                self.assertTrue(pilot.manifest_summary(records)["errors"])

    def test_manifest_partial_is_explicit_not_full_pass(self):
        records = record_set()
        records[0].update(qc="PARTIAL_PASS", missing_field_counts={"sum_open_interest": 1})
        self.assertEqual(pilot.manifest_summary(records)["errors"], [])
        self.assertEqual(records[0]["qc"], "PARTIAL_PASS")

    def test_execute_offline_manifest_success_and_failure(self):
        for change in ("none", "missing_zip", "missing_checksum", "bad_oi", "parity"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as root:
                workspace = Path(root)
                (workspace / "reports").mkdir()
                for fam, sym, period, monthly, _ in pilot.pilot_tasks():
                    path = workspace / "data" / fam / pilot.object_url(
                        fam, sym, period, monthly).rsplit("/", 1)[1]
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"synthetic stub; qc mocked")
                    path.with_name(path.name + ".CHECKSUM").write_text("synthetic stub")
                if change in ("missing_zip", "missing_checksum"):
                    target = path if change == "missing_zip" else path.with_name(path.name + ".CHECKSUM")
                    target.unlink()
                bad_rows = metrics()
                bad_rows[1][2] = "NaN"
                bad_qc = {**qc_ok(), **pilot.qc_rows(iter(bad_rows), "metrics", "BTCUSDT",
                                                    "2024-01-01", False)}

                def synthetic_qc(_path, _checksum, fam, *_args, bad_qc=bad_qc, change=change):
                    return bad_qc if change == "bad_oi" and fam == "metrics" else qc_ok()

                with patch.object(pilot, "safe_workspace"), \
                        patch.object(pilot.Fetcher, "get", side_effect=AssertionError("NETWORK")) as fetch, \
                        patch.object(pilot, "qc_zip", side_effect=synthetic_qc), \
                        patch.object(pilot, "compare_daily_vs_monthly", return_value={
                            "exact_byte_for_byte_rows_identical": change != "parity"}), \
                        redirect_stdout(io.StringIO()):
                    code = pilot.execute(workspace, acquire=False)
                    fetch.assert_not_called()
                receipt = json.loads((workspace / "reports/offline-qc.json").read_text())
                self.assertEqual(code, 0 if change == "none" else 2)
                self.assertEqual(receipt["manifest_version"], 2)
                self.assertEqual(receipt["newly_acquired_objects"], 0)
                self.assertEqual(receipt["total_objects_attempted"], 215)
                self.assertEqual(receipt["total_objects_evaluated"],
                                 214 if change.startswith("missing_") else 215)
                self.assertEqual(receipt["reused_objects_from_r10_d1"], 21)
                self.assertEqual(receipt["calibration_sample_objects"], 194)
                self.assertIn("PIT_UNKNOWN", receipt["gates"])
                self.assertFalse((workspace / "reports/acquisition.json").exists())
                self.assertEqual(receipt["terminal"].endswith("ACCEPTED_WITH_LIMITS"), change == "none")

    def test_acquire_missing_checksum_stops_without_qc_or_network(self):
        # Mocked acquisition path verifies missing-pair STOP; no source request occurs.
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            (workspace / "reports").mkdir()
            def missing_checksum(url, _path):
                return None if url.endswith(".CHECKSUM") else {"attempts": 0}

            with patch.object(pilot, "safe_workspace"), \
                    patch.object(pilot.Fetcher, "get", side_effect=missing_checksum), \
                    patch.object(pilot, "qc_zip") as qc, \
                    patch.object(pilot, "compare_daily_vs_monthly", return_value={
                        "exact_byte_for_byte_rows_identical": False}), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(pilot.execute(workspace, acquire=True), 2)
                qc.assert_not_called()
            receipt = json.loads((workspace / "reports/acquisition.json").read_text())
            self.assertEqual(receipt["total_objects_evaluated"], 0)
            self.assertEqual(receipt["newly_acquired_objects"], 0)
            self.assertTrue(receipt["inventory"]["errors"])

    def test_early_failure_manifest_cannot_claim_full_evaluation(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root)
            (workspace / "reports").mkdir()
            fam, sym, period, monthly, _ = pilot.pilot_tasks()[0]
            path = workspace / "data" / fam / pilot.object_url(
                fam, sym, period, monthly).rsplit("/", 1)[1]
            path.parent.mkdir(parents=True)
            path.write_bytes(b"synthetic stub")
            path.with_name(path.name + ".CHECKSUM").write_text("synthetic stub")
            with patch.object(pilot, "safe_workspace"), \
                    patch.object(pilot.Fetcher, "get", side_effect=AssertionError("NETWORK")), \
                    patch.object(pilot, "qc_zip", side_effect=pilot.SafetyError("TEST_STOP")), \
                    redirect_stdout(io.StringIO()):
                self.assertEqual(pilot.execute(workspace, acquire=False), 2)
            receipt = json.loads((workspace / "reports/offline-qc.json").read_text())
            self.assertEqual(receipt["total_objects_attempted"], 1)
            self.assertEqual(receipt["total_objects_evaluated"], 0)
            self.assertEqual(receipt["inventory"]["expected_objects"], 215)
            self.assertEqual(receipt["safety_code"], "TEST_STOP")
            self.assertIn("MANIFEST_OBJECT_COVERAGE", receipt["inventory"]["errors"])


if __name__ == "__main__":
    unittest.main()
