# ruff: noqa: E402
# Source/bootstrap path is established before optional installed Quant imports.
"""Offline unittest suite for Windows-native capture adapter (runs under py -3.14 on Windows)."""

from __future__ import annotations

from contextlib import closing
import ipaddress
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import patch

POC_ROOT = Path(__file__).resolve().parents[1]
if str(POC_ROOT) not in sys.path:
    sys.path.insert(0, str(POC_ROOT))

from tests.fixtures import LoopbackMockVenue, TRIGGER
from win_capture.bundle import BundleLedger
from win_capture.capture import WindowsCollector, capture_session, main as capture_cli
from win_capture.transport import CaptureError, WindowsHttpsTransport
from win_capture.win_clock import (
    DualWindowsClockMonitor,
    WindowsClockError,
    check_windows_pair_coherence,
    query_w32tm_readonly,
    sample_windows_clocks,
)

_ORIG_SOCKET_CONNECT = socket.socket.connect
_ORIG_CREATE_CONN = socket.create_connection


def _assert_loopback_addr(address: Any) -> None:
    if isinstance(address, tuple) and address:
        host = str(address[0])
        try:
            ip = ipaddress.ip_address(host)
        except ValueError as exc:
            raise RuntimeError(f"NON_LOOPBACK_HOST_FORBIDDEN:{host}") from exc
        if not ip.is_loopback:
            raise RuntimeError(f"NON_LOOPBACK_IP_FORBIDDEN:{host}")


def _guarded_connect(self, address):
    _assert_loopback_addr(address)
    return _ORIG_SOCKET_CONNECT(self, address)


def _guarded_create_connection(address, *args, **kwargs):
    _assert_loopback_addr(address)
    return _ORIG_CREATE_CONN(address, *args, **kwargs)


def setUpModule() -> None:
    socket.socket.connect = _guarded_connect  # type: ignore[method-assign]
    socket.create_connection = _guarded_create_connection


def tearDownModule() -> None:
    socket.socket.connect = _ORIG_SOCKET_CONNECT  # type: ignore[method-assign]
    socket.create_connection = _ORIG_CREATE_CONN


class WindowsClockAndCaptureOfflineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="win_cap_test_"))

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_01_live_windows_hardware_clocks_and_readonly_w32tm(self) -> None:
        if os.name != "nt":
            self.skipTest("Windows native clock test")
        s1 = sample_windows_clocks()
        s2 = sample_windows_clocks()
        self.assertGreater(s1["qpc_freq"], 0)
        self.assertEqual(s1["boot_session_id"], s2["boot_session_id"])
        self.assertFalse(s1["strict_utc_qualified"])
        self.assertLessEqual(s1["qpc_after_ms"] - s1["qpc_before_ms"], 5)
        self.assertLessEqual(s1["unbiased_after_ms"] - s1["unbiased_before_ms"], 5)
        coh = check_windows_pair_coherence(s1, s2)
        self.assertLessEqual(coh["qpc_vs_unbiased_diff_ms"], 5.0)
        w32 = query_w32tm_readonly()
        self.assertTrue(w32["supported"])
        self.assertFalse(w32["strict_utc_qualified"])

    def test_02_wall_jump_recorded_non_fatal_when_qpc_unbiased_coherent(self) -> None:
        base = {
            "boot_session_id": "boot-a",
            "qpc_freq": 10_000_000,
            "qpc_before_ns": 1_000_000_000,
            "qpc_after_ns": 1_000_100_000,
            "qpc_before_ms": 1000,
            "qpc_after_ms": 1000,
            "unbiased_before_ns": 1_000_000_000,
            "unbiased_after_ns": 1_000_100_000,
            "unbiased_before_ms": 1000,
            "unbiased_after_ms": 1000,
            "tick64_ms": 1000,
            "win_utc_ns": 1_793_925_000_000_000_000,
            "win_utc_ms": 1_793_925_000_000,
            "strict_utc_qualified": False,
        }
        seq = [
            dict(base),
            {
                **base,
                "qpc_before_ns": 11_000_000_000,
                "qpc_after_ns": 11_000_100_000,
                "qpc_before_ms": 11000,
                "qpc_after_ms": 11000,
                "unbiased_before_ns": 11_000_000_000,
                "unbiased_after_ns": 11_000_100_000,
                "unbiased_before_ms": 11000,
                "unbiased_after_ms": 11000,
                "tick64_ms": 11000,
                "win_utc_ns": base["win_utc_ns"] + 12_286_000_000,  # +2286ms host wall step
                "win_utc_ms": base["win_utc_ms"] + 12286,
            },
        ]
        idx = 0

        def next_sample():
            nonlocal idx
            val = seq[min(idx, len(seq) - 1)]
            idx += 1
            return val

        mon = DualWindowsClockMonitor(sampler=next_sample)
        mon.sample()
        self.assertEqual(len(mon.wall_jumps_observed), 1)
        self.assertGreater(mon.wall_jumps_observed[0]["adj_wall_vs_qpc_ms"], 2200.0)

    def test_03_dual_clock_faults_fail_closed(self) -> None:
        anchor = {
            "boot_session_id": "boot-a",
            "qpc_freq": 10_000_000,
            "qpc_before_ns": 1_000_000_000,
            "qpc_after_ns": 1_000_000_000,
            "qpc_before_ms": 1000,
            "qpc_after_ms": 1000,
            "unbiased_before_ns": 1_000_000_000,
            "unbiased_after_ns": 1_000_000_000,
            "unbiased_before_ms": 1000,
            "unbiased_after_ms": 1000,
            "tick64_ms": 1000,
            "win_utc_ns": 1_793_925_000_000_000_000,
            "win_utc_ms": 1_793_925_000_000,
            "strict_utc_qualified": False,
        }
        # S0ix sleep / Unbiased freeze: QPC +1000ms, Unbiased +0ms -> >50ms divergence
        with self.assertRaises(WindowsClockError) as cm:
            check_windows_pair_coherence(
                anchor,
                {
                    **anchor,
                    "qpc_before_ns": 2_000_000_000,
                    "qpc_after_ns": 2_000_000_000,
                    "qpc_before_ms": 2000,
                    "qpc_after_ms": 2000,
                    "tick64_ms": 2000,
                },
            )
        self.assertIn("WIN_QPC_VS_UNBIASED_DIVERGENCE", str(cm.exception))

        # QPC rollback
        with self.assertRaises(WindowsClockError) as cm2:
            check_windows_pair_coherence(
                anchor,
                {**anchor, "qpc_before_ns": 900_000_000, "qpc_after_ns": 900_000_000},
            )
        self.assertIn("WIN_ELAPSED_CLOCK_ROLLBACK", str(cm2.exception))

        # Span > 5ms
        with self.assertRaises(WindowsClockError) as cm3:
            check_windows_pair_coherence(
                anchor, {**anchor, "qpc_after_ns": anchor["qpc_before_ns"] + 6_000_000}
            )
        self.assertIn("WIN_QPC_BRACKET_SPAN_UNCERTAIN", str(cm3.exception))

        # Boot change
        with self.assertRaises(WindowsClockError) as cm4:
            check_windows_pair_coherence(anchor, {**anchor, "boot_session_id": "boot-b"})
        self.assertIn("WIN_BOOT_SESSION_CHANGED", str(cm4.exception))

        # GTC64 rollback
        with self.assertRaises(WindowsClockError) as cm5:
            check_windows_pair_coherence(anchor, {**anchor, "tick64_ms": 999})
        self.assertIn("WIN_TICK64_ROLLBACK", str(cm5.exception))

    def test_04_end_to_end_loopback_capture_watch_and_flat_bundles(self) -> None:
        for flat in (False, True):
            tag = "flat" if flat else "watch"
            venue = LoopbackMockVenue(self.tmp / f"certs_{tag}", flat=flat, minutes=30)
            out_dir = self.tmp / f"bundle_{tag}"
            try:
                manifest = capture_session(out_dir, qa=venue.qa)
            finally:
                venue.close()

            self.assertEqual(manifest["schema"], "WIN_CAPTURE_HANDOFF_BUNDLE_V1")
            self.assertEqual(manifest["evidence_class"], "WIN_CAPTURE_LOOPBACK_QA_V1")
            self.assertFalse(manifest["strict_utc_qualified"])
            self.assertFalse(manifest["source_qualified"])
            self.assertFalse(manifest["economically_validated"])
            self.assertEqual(manifest["account"], "ACCOUNT_UNKNOWN/ACCOUNT_VETO")
            self.assertEqual(manifest["requests"], 14)
            self.assertEqual(manifest["request_weight"], 17)
            self.assertEqual(len(manifest["records"]), 3 * (80 + 100))
            self.assertEqual(len(manifest["swing_market"]["observations"]), 3)
            self.assertTrue((out_dir / "bundle_manifest.json").is_file())
            self.assertTrue((out_dir / "ledger.sqlite").is_file())

            with closing(sqlite3.connect(out_dir / "ledger.sqlite")) as db:
                self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
                kinds = [r[0] for r in db.execute("SELECT kind FROM events ORDER BY seq").fetchall()]
            self.assertEqual(kinds[0], "LEDGER_INIT")
            self.assertEqual(kinds[1], "SESSION_START")
            self.assertEqual(kinds[-1], "BUNDLE_SEALED")
            self.assertNotIn("SESSION_FAILED", kinds)

    def test_05_tls_and_route_and_host_rejections(self) -> None:
        venue = LoopbackMockVenue(self.tmp / "certs_wrong_sni", sni_host="wrong.invalid")
        try:
            with self.assertRaises(ssl.SSLError):
                capture_session(self.tmp / "out_wrong_sni", qa=venue.qa)
        finally:
            venue.close()

        with self.assertRaises(CaptureError):
            WindowsHttpsTransport(qa={"host": "8.8.8.8", "port": 443, "cafile": "unused"})

        venue_ok = LoopbackMockVenue(self.tmp / "certs_route")
        try:
            tr = WindowsHttpsTransport(qa=venue_ok.qa)
            mon = DualWindowsClockMonitor()
            with self.assertRaises(CaptureError):
                tr.get("/fapi/v1/order", {"symbol": "BTCUSDT"}, 2.0, mon)
            self.assertEqual(venue_ok.calls, [])
        finally:
            venue_ok.close()

    def test_06_http_error_zero_retries_and_wire_schema_faults(self) -> None:
        venue_418 = LoopbackMockVenue(self.tmp / "c418", http_status=418)
        out_418 = self.tmp / "b418"
        try:
            with self.assertRaises(CaptureError) as cm:
                capture_session(out_418, qa=venue_418.qa)
            self.assertIn("WIN_HTTP_DENIED_OR_LIMITED_418_NO_RETRY", str(cm.exception))
            self.assertEqual(len(venue_418.calls), 1)  # strictly retries=0
            self.assertFalse((out_418 / "bundle_manifest.json").exists())
        finally:
            venue_418.close()

        for fault, expected in (
            ("duplicate_key", "WIN_JSON_DUPLICATE_KEY"),
            ("nan_json", "WIN_JSON_NONFINITE"),
            ("trailing_json", "Expecting"),
            ("oversize", "WIN_RESPONSE_SIZE_LIMIT_TRUNCATED_RECEIPT"),
            ("non_json", "WIN_NON_JSON_RESPONSE"),
            ("bad_exchange_info", "WIN_WRONG_INSTRUMENT_OR_INACTIVE_SYMBOL"),
            ("time_regression", "WIN_SERVER_TIME_REGRESSION"),
            ("time_wide_bracket", "WIN_TIME_BRACKETS_UNRECONCILABLE"),
        ):
            v = LoopbackMockVenue(self.tmp / f"c_{fault}", wire_fault=fault)
            try:
                with self.assertRaises(Exception) as exc_ctx:
                    capture_session(self.tmp / f"b_{fault}", qa=v.qa)
                if fault != "trailing_json":
                    self.assertIn(expected, str(exc_ctx.exception))
            finally:
                v.close()

    def test_07_series_observation_window_and_used_weight_faults(self) -> None:
        for sfault in ("gap", "incomplete", "insufficient"):
            v = LoopbackMockVenue(self.tmp / f"cs_{sfault}", series_fault=sfault)
            try:
                with self.assertRaises(CaptureError):
                    capture_session(self.tmp / f"bs_{sfault}", qa=v.qa)
            finally:
                v.close()

        for mfault in ("wrong_interval", "wrong_cycle", "no_current"):
            v = LoopbackMockVenue(self.tmp / f"cm_{mfault}", market_fault=mfault)
            try:
                with self.assertRaises(CaptureError):
                    capture_session(self.tmp / f"bm_{mfault}", qa=v.qa)
            finally:
                v.close()

        # Inside 120s grace window -> rejected
        v_grace = LoopbackMockVenue(self.tmp / "c_grace", minutes=1)
        try:
            with self.assertRaises(CaptureError) as cm:
                capture_session(self.tmp / "b_grace", qa=v_grace.qa)
            self.assertIn("WIN_CURRENT_OBSERVATION_NOT_CURRENT", str(cm.exception))
        finally:
            v_grace.close()

        # Outside configured shorter window_minutes=20 -> rejected
        v_win = LoopbackMockVenue(self.tmp / "c_win", minutes=30)
        try:
            with self.assertRaises(CaptureError) as cm:
                capture_session(self.tmp / "b_win", qa=v_win.qa, window_minutes=20)
            self.assertIn("WIN_OUTSIDE_MANUAL_REVIEW_WINDOW", str(cm.exception))
        finally:
            v_win.close()

        # Shared rate limit weight near ceiling (>2000) -> rejected
        v_wt = LoopbackMockVenue(self.tmp / "c_wt", extra_headers={"x-mbx-used-weight-1m": "2001"})
        try:
            with self.assertRaises(CaptureError) as cm:
                capture_session(self.tmp / "b_wt", qa=v_wt.qa)
            self.assertIn("WIN_SHARED_RATE_BUDGET_UNCERTAIN", str(cm.exception))
        finally:
            v_wt.close()

    def test_08_holdout_overlap_and_budget_deadline_blocked_before_socket(self) -> None:
        v = LoopbackMockVenue(self.tmp / "c_hold")
        try:
            with self.assertRaises(CaptureError) as cm:
                capture_session(
                    self.tmp / "b_hold",
                    qa=v.qa,
                    exclusions=[(TRIGGER - 14_400_000, TRIGGER)],
                )
            self.assertIn("WIN_HOLDOUT_DATE_OVERLAP_FORBIDDEN", str(cm.exception))
            self.assertFalse(any("/fapi/v1/klines" in c for c in v.calls))
        finally:
            v.close()

        # Expired QPC deadline blocks BEFORE GET socket open
        v_dead = LoopbackMockVenue(self.tmp / "c_dead")
        try:
            tr = WindowsHttpsTransport(qa=v_dead.qa)
            mon = DualWindowsClockMonitor()
            led = BundleLedger(self.tmp / "b_dead", evidence_class="WIN_CAPTURE_LOOPBACK_QA_V1")
            try:
                col = WindowsCollector(led, transport=tr, clock_monitor=mon)
                col.deadline_qpc_ms = col.start["qpc_before_ms"] - 10
                with self.assertRaises(CaptureError) as cm:
                    col.get("/fapi/v1/time", {})
                self.assertIn("WIN_FINITE_REQUEST_BUDGET_OR_DEADLINE", str(cm.exception))
                self.assertEqual(v_dead.calls, [])
            finally:
                led.close()
        finally:
            v_dead.close()

    def test_09_durability_unused_dir_lock_and_crash_rollback(self) -> None:
        existing = self.tmp / "used_dir"
        existing.mkdir()
        with self.assertRaises(CaptureError) as cm:
            BundleLedger(existing, evidence_class="WIN_CAPTURE_LOOPBACK_QA_V1")
        self.assertIn("WIN_OUTPUT_DIR_MUST_BE_UNUSED", str(cm.exception))

        out = self.tmp / "locked_dir"
        led = BundleLedger(out, evidence_class="WIN_CAPTURE_LOOPBACK_QA_V1")
        try:
            if os.name == "nt":
                from win_capture.bundle import acquire_exclusive_lock

                with self.assertRaises(CaptureError) as cm2:
                    acquire_exclusive_lock(out / "capture.lock")
                self.assertIn("WIN_EXCLUSIVE_LOCK_CONFLICT", str(cm2.exception))
        finally:
            led.close()

        # Simulate mid-transaction crash via subprocess os._exit(73)
        crash_dir = self.tmp / "crash_dir"
        script = f"""
import os, sqlite3
from pathlib import Path
import sys
sys.path.insert(0, {str(POC_ROOT)!r})
from win_capture.bundle import BundleLedger
led = BundleLedger(Path({str(crash_dir)!r}), evidence_class="WIN_CAPTURE_LOOPBACK_QA_V1")
conn = led._connect()
conn.execute("INSERT INTO events(kind, payload_json, prev_sha256, entry_sha256) VALUES('UNCOMMITTED','{{}}','0','0')")
os._exit(73)
"""
        proc = subprocess.run([sys.executable, "-c", script], capture_output=True)
        self.assertEqual(proc.returncode, 73)
        self.assertFalse((crash_dir / "bundle_manifest.json").exists())
        with closing(sqlite3.connect(crash_dir / "ledger.sqlite")) as db:
            self.assertEqual(db.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            kinds = [r[0] for r in db.execute("SELECT kind FROM events ORDER BY seq").fetchall()]
        self.assertEqual(kinds, ["LEDGER_INIT"])

    def test_10_cli_blocks_live_network_by_default(self) -> None:
        never_dir = self.tmp / "cli_never_created"
        with patch("socket.create_connection", side_effect=AssertionError("SOCKET_CALLED")):
            with self.assertRaises(SystemExit) as cm:
                capture_cli(["--output", str(never_dir)])
        self.assertIn("BLOCKED_LIVE_NETWORK_REQUIRES_EXPLICIT_OWNER_APPROVAL", str(cm.exception))
        self.assertFalse(never_dir.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
