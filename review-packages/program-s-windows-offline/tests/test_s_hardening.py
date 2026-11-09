"""S negative gates. Synthetic authority is isolated unit data, never live permission."""

import json
from tests.test_windows_capture_offline import setUpModule as setUpModule, tearDownModule as tearDownModule
import os
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from win_capture.access import Admission, load_access, source_hash, POLICY_HASH, J_HASH, HOLDOUT
from win_capture.bundle import canonical_bytes
from win_capture.transport import CaptureError, WindowsHttpsTransport
from win_capture.win_clock import WindowsClockError, check_windows_pair_coherence, DualWindowsClockMonitor
from win_capture.retention import cache_status, purge_receipt
from tests.fixtures import LoopbackMockVenue


def stamp(ms=100000):
    n = ms * 1000000
    return {
        "boot_session_id": "SYNTHETIC_TEST_BOOT",
        "qpc_freq": 10000000,
        "qpc_before_ns": n,
        "qpc_after_ns": n,
        "qpc_before_ms": ms,
        "qpc_after_ms": ms,
        "unbiased_before_ns": n,
        "unbiased_after_ns": n,
        "unbiased_before_ms": ms,
        "unbiased_after_ms": ms,
        "tick64_ms": ms,
        "win_utc_ns": n + 1000000000000000000,
        "win_utc_ms": ms + 1000000000000,
        "strict_utc_qualified": False,
    }


class STests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="S_UNIT_SYNTHETIC_")
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def record(self):
        r = self.root
        evidence = {
            "eligibility": {
                "operator_physical_country": "KR",
                "egress_country": "KR",
                "declaration_kind": "OWNER_DECLARATION_NOT_LEGAL_CERTIFICATION",
                "applicable_restriction_found": False,
                "review_status": "VERIFIED_OPERATIONAL_SCOPE",
                "official_references": [
                    "https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Check-Server-Time"
                ],
                "reviewed_at_UTC": "SYNTHETIC_NOT_REAL_REVIEW",
                "review_boot_id": "SYNTHETIC_TEST_BOOT",
                "review_qpc_ms": 99999,
            },
            "advisory_use_and_cache": {
                "purpose": "PERSONAL_NONCOMMERCIAL_READONLY_ADVISORY",
                "cache_hours": 24,
                "retention_permission_reviewed": True,
            },
            "holdout_exclusions": {"metadata_complete": True, "excluded_UTC_ms_ranges": [list(HOLDOUT)]},
        }
        a = {
            "schema_version": "J_OPERATIONAL_ACCESS_V1",
            "status": "VERIFIED",
            "policy_sha256": J_HASH,
            "region": "KR",
            "reviewer_reference": "SYNTHETIC_QA_NOT_REAL_REVIEWER",
            "retention_days": 1,
            "operational_rolling_lookback_only": True,
            "proxy": {"host": "127.0.0.1", "port": 9, "permitted_reference": "SYNTHETIC_QA"},
        }
        for k, v in evidence.items():
            p = r / (k + ".json")
            p.write_bytes(canonical_bytes(v))
            import hashlib

            a[k] = {"path": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
        p = r / "access.json"
        p.write_bytes(canonical_bytes(a))
        import hashlib

        g = {
            "schema": "S_ONE_MANUAL_SCAN_AUTH_V1",
            "owner_reference": "SYNTHETIC_UNIT_NOT_OWNER",
            "session": "SYNTHETIC_SESSION_0001",
            "source_sha256": source_hash(),
            "policy_sha256": POLICY_HASH,
            "access_sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            "output_path": str((r / "unused").absolute()),
            "host": "fapi.binance.com",
            "routes": ["/fapi/v1/exchangeInfo", "/fapi/v1/klines", "/fapi/v1/time"],
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "method": "GET",
            "max_requests": 24,
            "max_weight": 40,
            "max_seconds": 120,
            "retention_hours": 24,
            "boot_id": "SYNTHETIC_TEST_BOOT",
            "not_before_qpc_ms": 99999,
            "not_after_qpc_ms": 200000,
            "reservation_db": str(r / "reservation.sqlite"),
            "current_source_review_sha256": a["eligibility"]["sha256"],
        }
        q = r / "owner_SYNTHETIC.json"
        q.write_bytes(canonical_bytes(g))
        return p, q, a, g

    def test_access_evidence_and_consumed_session(self):
        p, q, a, g = self.record()
        clock = SimpleNamespace(sample=stamp)
        x = Admission(p, q, self.root / "unused", clock, _qa=True)
        self.assertTrue(x.receipt["consumed_before_network"])
        with self.assertRaisesRegex(CaptureError, "ALREADY_CONSUMED"):
            Admission(p, q, self.root / "unused", clock, _qa=True)
        with self.assertRaisesRegex(CaptureError, "EXCLUDED"):
            x.check(
                "/fapi/v1/klines",
                {
                    "symbol": "BTCUSDT",
                    "interval": "4h",
                    "startTime": HOLDOUT[0],
                    "endTime": HOLDOUT[0] + 14400000,
                    "limit": 1,
                },
            )
        with self.assertRaises(CaptureError):
            x.check("/fapi/v1/order", {})

    def test_evidence_hash_and_missing_holdout(self):
        p, q, a, g = self.record()
        (self.root / "eligibility.json").write_text("{}")
        with self.assertRaisesRegex(CaptureError, "EVIDENCE_HASH"):
            load_access(p)

    def test_wrong_code_and_boot_and_stale_scope(self):
        for key, value in [
            ("source_sha256", "0" * 64),
            ("boot_id", "OTHER"),
            ("host", "api.binance.com"),
            ("max_requests", 25),
            ("not_after_qpc_ms", 99999),
        ]:
            p, q, a, g = self.record()
            g[key] = value
            q.write_bytes(canonical_bytes(g))
            with self.assertRaises(CaptureError):
                Admission(p, q, self.root / "unused", SimpleNamespace(sample=stamp), _qa=True)

    def test_real_boot_unavailable_never_uses_frequency_fallback(self):
        from win_capture.win_clock import _windows_boot_identifier

        with patch("win_capture.win_clock._NTDLL", None):
            with self.assertRaisesRegex(WindowsClockError, "REAL_BOOT"):
                _windows_boot_identifier(10000000)

    def test_suspend_resume_restart_and_tick_faults(self):
        a = stamp()
        b = stamp(101000)
        for kind in ["boot", "unbiased", "tick"]:
            c = dict(b)
            if kind == "boot":
                c["boot_session_id"] = "NEW_BOOT"
            if kind == "unbiased":
                c["unbiased_before_ns"] = c["unbiased_after_ns"] = a["unbiased_before_ns"]
            if kind == "tick":
                c["tick64_ms"] += 1000
            with self.assertRaises(WindowsClockError):
                check_windows_pair_coherence(a, c)

    def test_retention_expiry_and_no_automatic_purge(self):
        with self.assertRaisesRegex(CaptureError, "CACHE_EXPIRED"):
            cache_status(stamp(), stamp(100000 + 86400000))
        x = purge_receipt(self.root / "absent", "SYNTHETIC_OWNER_TEST", "a" * 64)
        self.assertFalse(x["worker_performed_deletion"])
        with self.assertRaises(CaptureError):
            purge_receipt(self.root, "owner", "a" * 64)

    def test_production_transport_default_denied(self):
        with self.assertRaisesRegex(CaptureError, "ACCESS_AND_LOCAL_CONNECT"):
            WindowsHttpsTransport()

    def test_CONNECT_status_TLS_denial_timeout_no_retries(self):
        # Module socket guards inherited from accepted native test suite.
        for status in [403, 418, 429, 451]:
            v = LoopbackMockVenue(self.root / str(status), http_status=status)
            v.connect_tunnel = True
            try:
                from win_capture.capture import capture_session

                with self.assertRaises(CaptureError):
                    capture_session(self.root / ("b" + str(status)), qa=v.qa)
                self.assertEqual(len(v.calls), 1)
                self.assertEqual(v.connect_calls, 1)
            finally:
                v.close()
        v = LoopbackMockVenue(self.root / "deny")
        v.connect_tunnel = True
        v.connect_denied = True
        try:
            with self.assertRaises(OSError):
                WindowsHttpsTransport(qa=v.qa).get(
                    "/fapi/v1/time", {}, 1, DualWindowsClockMonitor(sampler=stamp)
                )
            self.assertEqual(v.connect_calls, 1)
            self.assertEqual(v.calls, [])
        finally:
            v.close()
        for fault in ["certificate", "timeout"]:
            v = LoopbackMockVenue(
                self.root / fault,
                sni_host="wrong.invalid" if fault == "certificate" else "fapi.binance.com",
                wire_fault="hang" if fault == "timeout" else None,
            )
            v.connect_tunnel = True
            try:
                with self.assertRaises(OSError):
                    WindowsHttpsTransport(qa=v.qa).get(
                        "/fapi/v1/time", {}, 0.1, DualWindowsClockMonitor(sampler=stamp)
                    )
                self.assertEqual(v.connect_calls, 1)
            finally:
                v.close()

    def test_source_review_unsynced_is_not_qualified(self):
        from win_capture.win_clock import query_w32tm_readonly

        if os.name != "nt":
            self.skipTest("native Windows only, not counted as Windows PASS on Linux")
        with patch(
            "win_capture.win_clock.subprocess.run",
            return_value=SimpleNamespace(
                returncode=0, stdout="Leap Indicator:3; Source:Local CMOS Clock", stderr=""
            ),
        ):
            x = query_w32tm_readonly()
            self.assertFalse(x["strict_utc_qualified"])
            self.assertIn("CMOS", x["status_text_unqualified"])

    def test_missing_holdout_metadata_and_wrong_region(self):
        p, q, a, g = self.record()
        x = self.root / "holdout_exclusions.json"
        x.write_bytes(canonical_bytes({"metadata_complete": True, "excluded_UTC_ms_ranges": []}))
        import hashlib

        a["holdout_exclusions"]["sha256"] = hashlib.sha256(x.read_bytes()).hexdigest()
        p.write_bytes(canonical_bytes(a))
        with self.assertRaisesRegex(CaptureError, "FINAL_HOLDOUT"):
            load_access(p)
        p, q, a, g = self.record()
        a["region"] = "UNKNOWN"
        p.write_bytes(canonical_bytes(a))
        with self.assertRaises(CaptureError):
            load_access(p)

    def test_synthetic_authority_is_blocked_in_production_profile(self):
        p, q, a, g = self.record()
        with self.assertRaisesRegex(CaptureError, "SYNTHETIC_RECORD"):
            Admission(p, q, self.root / "unused", SimpleNamespace(sample=stamp))

    def test_stale_source_review_is_blocked_before_reservation(self):
        p, q, a, g = self.record()
        e = self.root / "eligibility.json"
        x = json.loads(e.read_text())
        x["review_qpc_ms"] = -86400000
        e.write_bytes(canonical_bytes(x))
        import hashlib

        a["eligibility"]["sha256"] = hashlib.sha256(e.read_bytes()).hexdigest()
        p.write_bytes(canonical_bytes(a))
        with self.assertRaisesRegex(CaptureError, "SOURCE_REVIEW_STALE"):
            Admission(p, q, self.root / "unused", SimpleNamespace(sample=stamp), _qa=True)
        self.assertFalse((self.root / "reservation.sqlite").exists())

    def test_no_proxy_fallback_on_closed_local_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        t = WindowsHttpsTransport(
            proxy={"host": "127.0.0.1", "port": port},
            admission=SimpleNamespace(
                check=lambda *a: None, grant={"not_after_qpc_ms": 101000}, clock=SimpleNamespace(sample=stamp)
            ),
        )
        with self.assertRaises(OSError):
            t.get("/fapi/v1/time", {}, 0.1, DualWindowsClockMonitor(sampler=stamp))

    def test_ntfs_reparse_and_output_reuse(self):
        if os.name != "nt":
            self.skipTest("actual NTFS only")
        import subprocess
        from win_capture.bundle import BundleLedger, verify_ntfs

        verify_ntfs(self.root)
        target = self.root / "target"
        target.mkdir()
        junction = self.root / "junction"
        p = subprocess.run(["cmd.exe", "/c", "mklink", "/J", str(junction), str(target)], capture_output=True)
        self.assertEqual(p.returncode, 0)
        try:
            with self.assertRaises(CaptureError):
                verify_ntfs(junction)
        finally:
            os.rmdir(junction)
        with self.assertRaises(CaptureError):
            BundleLedger(target, evidence_class="WIN_CAPTURE_LOOPBACK_QA_V1")

    def test_absolute_deadline_cuts_slow_drip_without_retry(self):
        import time

        v = LoopbackMockVenue(self.root / "slow_drip", wire_fault="slow_drip")
        v.connect_tunnel = True
        try:
            t = time.perf_counter()
            with self.assertRaises(Exception):
                WindowsHttpsTransport(qa=v.qa).get(
                    "/fapi/v1/time", {}, 0.15, DualWindowsClockMonitor(sampler=stamp)
                )
            self.assertLess(time.perf_counter() - t, 0.9)
            self.assertEqual(v.connect_calls, 1)
            self.assertEqual(len(v.calls), 1)
        finally:
            v.close()

    def test_durable_sample_is_taken_after_atomic_raw_fsync(self):
        from win_capture.bundle import BundleLedger
        import hashlib

        led = BundleLedger(self.root / "durability", evidence_class="WIN_CAPTURE_LOOPBACK_QA_V1")
        raw = b"{}"
        sha = hashlib.sha256(raw).hexdigest()
        wire = {
            "host": "fapi.binance.com",
            "route": "/fapi/v1/time",
            "params": {},
            "status": 200,
            "headers": {},
            "response_complete": True,
            "raw_bytes": raw,
            "body_sha256": sha,
            "request_sample": stamp(),
            "receive_sample": stamp(),
            "tls": {},
        }

        def sampled_after_fsync():
            files = list((led.directory / "responses").glob("*.bin"))
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].read_bytes(), raw)
            return stamp()

        try:
            record = led.persist_response("SYNTHETIC", 1, wire, sampled_after_fsync)
            self.assertEqual(record["durable_sample_semantics"], "POST_RAW_FSYNC_ACK")
        finally:
            led.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
