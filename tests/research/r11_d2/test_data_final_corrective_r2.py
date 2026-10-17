"""F1/F2 regression tests using synthetic rows/ZIPs and mocked receipt I/O only."""
import csv
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts.research.r11_d2 import binance_core_pilot as pilot
from tests.research.r11_d2.test_binance_core_pilot import make_zip
from tests.research.r11_d2.test_data_next_01 import metrics, qc_ok, record_set

START = 1704067200000
END = 1704153600000
FEBRUARY = 1706745600000


def trades(family, timestamps):
    header = pilot.TRADES_SCHEMA if family == "trades" else pilot.AGG_TRADES_SCHEMA
    rows = [header.copy()]
    for i, timestamp in enumerate(timestamps):
        if family == "trades":
            rows.append([str(5001 + i), "100", "2", "200", str(timestamp), "true"])
        else:
            rows.append([str(1001 + i), "100", "2", str(5001 + i * 3),
                         str(5003 + i * 3), str(timestamp), "false"])
    return rows


def write_archive(root, family, rows, filename_period="2024-01-01"):
    path = root / f"BTCUSDT-{family}-{filename_period}.zip"
    content = io.StringIO()
    csv.writer(content).writerows(rows)
    payload = make_zip(path.with_suffix(".csv").name, content.getvalue())
    path.write_bytes(payload)
    check = path.with_name(path.name + ".CHECKSUM")
    check.write_text(f"{hashlib.sha256(payload).hexdigest()}  {path.name}\n")
    return path, check


def metric_record(records):
    return next(r for r in records if r["family"] == "metrics"
                and r["symbol"] == "BTCUSDT" and r["period"] == "2024-01-01")


class TestTradeCorrectiveR2(unittest.TestCase):
    def test_same_millisecond_sparse_and_daily_boundary_positives(self):
        for family in pilot.TRADE_FAMILIES:
            with self.subTest(family=family):
                rows = trades(family, [START, START, START + 17, START + 7199123, END - 1])
                result = pilot.qc_rows(iter(rows), family, "BTCUSDT", "2024-01-01", False)
                self.assertEqual(result["qc"], "PASS")
                self.assertEqual(result["valid_rows"], 5)
                self.assertEqual(result["duplicate_timestamps"], 1)
                self.assertEqual(result["expected_rows"], 0)
                self.assertEqual(result["missing_intervals"], 0)
                self.assertEqual(result["unexpected_intervals"], 0)
                sparse = pilot.qc_rows(iter(trades(family, [START + 123])), family,
                                       "BTCUSDT", "2024-01-01", False)
                self.assertEqual(sparse["qc"], "PASS")

    def test_wrong_february_day_and_exclusive_utc_end_fail(self):
        for family in pilot.TRADE_FAMILIES:
            for timestamp in (START - 1, END, FEBRUARY):
                with self.subTest(family=family, timestamp=timestamp):
                    result = pilot.qc_rows(iter(trades(family, [timestamp])), family,
                                           "BTCUSDT", "2024-01-01", False)
                    self.assertEqual(result["qc"], "FAIL")
                    self.assertEqual(result["valid_rows"], 0)
                    self.assertEqual(result["unexpected_intervals"], 1)
                    self.assertIn("TRADE_TIMESTAMP_OUTSIDE_DAY", result["errors"])

    def test_header_only_and_empty_csv_fail(self):
        for family in pilot.TRADE_FAMILIES:
            with self.subTest(family=family):
                result = pilot.qc_rows(iter(trades(family, [])), family,
                                       "BTCUSDT", "2024-01-01", False)
                self.assertEqual(result["qc"], "FAIL")
                self.assertEqual(result["total_rows"], 0)
                self.assertIn("NO_VALID_TRADE_OBSERVATIONS", result["errors"])
                with self.assertRaisesRegex(pilot.SafetyError, "EMPTY_CSV"):
                    pilot.qc_rows(iter([]), family, "BTCUSDT", "2024-01-01", False)

    def test_invalid_rows_do_not_hide_behind_one_valid_observation(self):
        for family in pilot.TRADE_FAMILIES:
            mutations = [(1, "NaN"), (1, "Inf"), (1, "0"), (2, "-1"), (0, "5000.1"),
                         (-1, "unknown"), (4 if family == "trades" else 5, "bad")]
            mutations += [(3, "-1"), (3, "NaN")] if family == "trades" else [(3, "-1"), (4, "0")]
            for column, value in mutations:
                with self.subTest(family=family, column=column, value=value):
                    rows = trades(family, [START, START + 1])
                    rows[2][column] = value
                    result = pilot.qc_rows(iter(rows), family, "BTCUSDT", "2024-01-01", False)
                    self.assertEqual(result["qc"], "FAIL")
                    self.assertEqual(result["valid_rows"], 1)
                    self.assertIn("MALFORMED_ROW", result["errors"])
            rows = trades(family, [START, START + 1])
            rows[2].pop()
            self.assertEqual(pilot.qc_rows(iter(rows), family, "BTCUSDT",
                                          "2024-01-01", False)["qc"], "FAIL")

    def test_native_id_and_schema_checks_remain(self):
        for family in pilot.TRADE_FAMILIES:
            for change in ("duplicate_id", "decreasing_id", "header"):
                with self.subTest(family=family, change=change):
                    rows = trades(family, [START, START])
                    if change == "header":
                        rows[0][-1] = "other_schema"
                        with self.assertRaisesRegex(pilot.SafetyError, "SCHEMA_DRIFT"):
                            pilot.qc_rows(iter(rows), family, "BTCUSDT", "2024-01-01", False)
                    else:
                        rows[2][0] = str(int(rows[1][0]) - int(change == "decreasing_id"))
                        self.assertEqual(pilot.qc_rows(iter(rows), family, "BTCUSDT",
                                                      "2024-01-01", False)["qc"], "FAIL")

    def test_trade_period_requires_canonical_daily_identity(self):
        for family in pilot.TRADE_FAMILIES:
            for period, monthly in (("2024-01", True), ("2024-01-01T01:00:00", False),
                                    ("2024-01-01T00:00:00+08:00", False)):
                with self.subTest(family=family, period=period), \
                        self.assertRaisesRegex(pilot.SafetyError, "TRADE_DAILY_PERIOD"):
                    pilot.qc_rows(iter(trades(family, [START])), family,
                                  "BTCUSDT", period, monthly)

    def test_archive_identity_empty_and_wrong_day_are_checked_after_checksum(self):
        with tempfile.TemporaryDirectory() as root:
            for family in pilot.TRADE_FAMILIES:
                for timestamps in ([], [FEBRUARY], [START - 1], [END], [START, START, END - 1]):
                    with self.subTest(family=family, timestamps=timestamps):
                        path, check = write_archive(Path(root), family, trades(family, timestamps))
                        result = pilot.qc_zip(path, check, family, "BTCUSDT",
                                              "2024-01-01", False, pilot.Budget())
                        self.assertEqual(result["publisher_checksum"], "VERIFIED")
                        self.assertEqual(result["qc"], "PASS" if timestamps == [START, START, END - 1]
                                         else "FAIL")
                path, check = write_archive(Path(root), family, trades(family, [START]), "2024-02-01")
                with self.assertRaisesRegex(pilot.SafetyError, "TRADE_ARCHIVE_IDENTITY"):
                    pilot.qc_zip(path, check, family, "BTCUSDT", "2024-01-01", False, pilot.Budget())


class TestManifestCorrectiveR2(unittest.TestCase):
    def test_exact_pass_and_real_partial_diagnostics_positive(self):
        records = record_set()
        self.assertEqual(pilot.manifest_summary(records), {
            "expected_objects": 215, "attempted_objects": 215, "evaluated_objects": 215,
            "reused_objects": 21, "calibration_sample_objects": 194, "errors": []})
        rows = metrics()
        rows[1][2] = ""
        rows[1][3] = " "
        qc = pilot.qc_rows(iter(rows), "metrics", "BTCUSDT", "2024-01-01", False)
        self.assertEqual(qc["qc"], "PARTIAL_PASS")
        self.assertEqual(qc["valid_rows"], 287)
        self.assertEqual(qc["missing_field_counts"],
                         {"sum_open_interest": 1, "sum_open_interest_value": 1})
        metric_record(records).update(qc)
        self.assertEqual(pilot.manifest_summary(records)["errors"], [])

    def test_partial_requires_positive_typed_known_missing_fields(self):
        for missing in ({}, None, [], {"sum_open_interest": 0}, {"sum_open_interest": -1},
                        {"sum_open_interest": True}, {"sum_open_interest": 1.0},
                        {"sum_open_interest": "1"}, {"sum_open_interest": float("nan")},
                        {"sum_open_interest": float("inf")}, {"sum_open_interest": 289},
                        {"unrecognized_field": 1}):
            with self.subTest(missing=missing):
                records = record_set()
                metric_record(records).update(qc="PARTIAL_PASS", total_rows=288, valid_rows=287,
                                              missing_field_counts=missing)
                self.assertIn("MANIFEST_QC_CONTRADICTION", pilot.manifest_summary(records)["errors"])
        records = record_set()
        record = metric_record(records)
        record.update(qc="PARTIAL_PASS", valid_rows=0)
        del record["missing_field_counts"]
        self.assertIn("MANIFEST_QC_CONTRADICTION", pilot.manifest_summary(records)["errors"])

    def test_partial_rejects_impossible_row_accounting_and_wrong_family(self):
        for total, valid, count in ((None, 0, 1), (0, 0, 1), (True, 0, 1), (1, True, 1),
                                    (1, 1, 1), (10, 0, 1), (10, 9, 2), (1, -1, 1)):
            with self.subTest(total=total, valid=valid, count=count):
                records = record_set()
                metric_record(records).update(qc="PARTIAL_PASS", total_rows=total, valid_rows=valid,
                                              missing_field_counts={"sum_open_interest": count})
                self.assertIn("MANIFEST_QC_CONTRADICTION", pilot.manifest_summary(records)["errors"])
        records = record_set()
        records[0].update(qc="PARTIAL_PASS", valid_rows=0,
                          missing_field_counts={"sum_open_interest": 1})
        self.assertIn("MANIFEST_QC_CONTRADICTION", pilot.manifest_summary(records)["errors"])

    def test_pass_rejects_missing_invalid_and_contradictory_diagnostics(self):
        mutations = [
            ("missing_field_counts", {"sum_open_interest": 0}),
            ("missing_field_counts", {"sum_open_interest": 1}),
            ("invalid_field_counts", {"sum_open_interest": 0}),
            ("invalid_field_counts", {"sum_open_interest": 1}),
            ("missing_field_counts", None), ("invalid_field_counts", []),
            ("errors", None), ("errors", ["MALFORMED_ROW"]),
            ("total_rows", 0), ("total_rows", True), ("valid_rows", 0),
            ("malformed_rows", 1), ("missing_intervals", 1),
            ("unexpected_intervals", 1), ("duplicate_timestamps", 1),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                records = record_set()
                metric_record(records)[field] = value
                self.assertIn("MANIFEST_QC_CONTRADICTION", pilot.manifest_summary(records)["errors"])
        for field in ("errors", "missing_field_counts", "invalid_field_counts", "total_rows", "valid_rows"):
            with self.subTest(absent=field):
                records = record_set()
                del metric_record(records)[field]
                self.assertIn("MANIFEST_QC_CONTRADICTION", pilot.manifest_summary(records)["errors"])

    def test_partial_with_invalid_or_errors_and_unknown_status_fail(self):
        for field, value in (("invalid_field_counts", {"sum_open_interest": 1}),
                             ("errors", ["GRID_ANOMALY"]), ("qc", "FAIL"),
                             ("qc", "PASS"), ("qc", "OTHER")):
            with self.subTest(field=field, value=value):
                records = record_set()
                metric_record(records).update(qc="PARTIAL_PASS", total_rows=288, valid_rows=287,
                                              missing_field_counts={"sum_open_interest": 1})
                metric_record(records)[field] = value
                self.assertTrue(pilot.manifest_summary(records)["errors"])

    def test_trade_same_time_duplicates_do_not_contradict_pass_manifest(self):
        records = record_set()
        record = next(r for r in records if r["family"] == "trades")
        record.update(pilot.qc_rows(iter(trades("trades", [START, START])), "trades",
                                    record["symbol"], record["period"], False))
        self.assertEqual(pilot.manifest_summary(records)["errors"], [])

    def test_v2_writer_partial_consistency_and_acquisition_count_semantics(self):
        # Entire acquisition path is mocked. No source bytes or endpoint calls.
        for status in ("PASS", "PARTIAL_PASS", "UNJUSTIFIED_PARTIAL"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as root:
                workspace = Path(root)
                (workspace / "reports").mkdir()
                first_url = pilot.object_url(*pilot.pilot_tasks()[0][:4])

                def fetched(url, _path, first_url=first_url):
                    return {"attempts": int(url == first_url), "bytes": 1}

                def checked(_path, _check, family, *_args, status=status):
                    result = qc_ok()
                    if family == "metrics" and status != "PASS":
                        result.update(qc="PARTIAL_PASS", valid_rows=0)
                        if status == "PARTIAL_PASS":
                            result["missing_field_counts"] = {"sum_open_interest": 1}
                    return result

                with patch.object(pilot, "safe_workspace"), \
                        patch.object(pilot.Fetcher, "get", side_effect=fetched), \
                        patch.object(pilot, "qc_zip", side_effect=checked), \
                        patch.object(pilot, "compare_daily_vs_monthly", return_value={
                            "exact_byte_for_byte_rows_identical": True}), \
                        redirect_stdout(io.StringIO()):
                    code = pilot.execute(workspace, acquire=True)
                receipt = json.loads((workspace / "reports/acquisition.json").read_text())
                self.assertEqual(code, 2 if status == "UNJUSTIFIED_PARTIAL" else 0)
                self.assertEqual(receipt["manifest_version"], 2)
                self.assertEqual(receipt["newly_acquired_objects"], 1)
                self.assertEqual(receipt["total_objects_attempted"], 215)
                self.assertEqual(receipt["total_objects_evaluated"], 215)
                self.assertEqual(receipt["calibration_sample_objects"], 194)
                self.assertEqual(receipt["reused_objects_from_r10_d1"], 21)
                self.assertEqual(receipt["inventory"]["errors"],
                                 ["MANIFEST_QC_CONTRADICTION"] if status == "UNJUSTIFIED_PARTIAL" else [])
                self.assertIn("PIT_UNKNOWN", receipt["gates"])


if __name__ == "__main__":
    unittest.main()
