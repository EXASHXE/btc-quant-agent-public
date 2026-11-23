"""Comprehensive S3 Release-Bound Zero-Retry V2 offline functional & negative QA suite.

All keys, certificates, clocks, wire responses, and funding debits in this file are
100% synthetic QA fixtures executed inside an isolated no-route Linux network namespace.
Zero external DNS, TCP, HTTPS, Binance, Feishu, or external API calls are permitted.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import socket
import sqlite3
import ssl
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

import test_h2a as accepted
from quant_personal_decision_b2.model import DecisionError
from quant_personal_live_public_b5 import egress, trust
from quant_personal_live_public_b5.admission import Adapter
from quant_personal_live_public_b5.approval import load_local_json, verify_envelope
from quant_personal_live_public_b5.collection import collect
from quant_personal_live_public_b5.contract import (
    APPROVAL_SCHEMA,
    AUTHORITY,
    BASE_MAX_WEIGHT,
    CONTRACT,
    DISABLED,
    GENUINE,
    HOST,
    INTERVALS,
    QA,
    ROUTES,
    SCOPE_SCHEMA,
    SYMBOL_ORDER,
    TASK,
    RouteRequest,
    digest,
)
from quant_personal_live_public_b5.decision import engine, replay
from quant_personal_live_public_b5.ledger import Active, Ledger
from quant_personal_live_public_b5.offline import FixtureWire, PROSPECTIVE_CUTOFF_MS, run_case
from quant_personal_live_public_b5.release import verify_release
from quant_personal_live_public_b5.stages import (
    CANARY_ROUTES,
    SCOPE_V2,
    STAGE_CONTRACT,
    TIMEOUT_PROFILE,
    ZERO_RETRY_PROFILE,
    StagePlan,
    market_requests,
)
from quant_personal_public_b1.clock import Sample
from quant_personal_public_b1.fixture import FixtureClock, fixture_reply
from quant_personal_public_b1.policy import SourceBlocked
from quant_personal_public_b1.session import RunIdentity
from quant_personal_public_b1.store import encode, sha
from quant_personal_public_b1.wire import Reply, WireFailure
from quant_personal_public_bridge_b4.routes import (
    DEPTH,
    FUNDING,
    INSTRUMENTS,
    KLINES,
    OI,
    OI_HISTORY,
    QUOTE,
    TIME,
)

from s3_plan_gate import (
    FORBIDDEN_DEBIT_SUBSTITUTES,
    audit_source_diff,
    build_plan_gate_document,
    evaluate_plan_a_funding_gate,
    evaluate_plan_b_diagnostic,
    validate_s3_v2_candidate_scope,
)

WORKROOT = Path(__file__).resolve().parents[1]
REPO = WORKROOT.parents[1]
S3_MATRIX_PATH = REPO / "workspaces/lt-v080-sol62-s3-market-offline-readiness-01/S3_REQUEST_BUDGET_MATRIX.json"

_AUDIT_INSTALLED = False


def _install_network_audit_fence() -> None:
    global _AUDIT_INSTALLED
    if _AUDIT_INSTALLED:
        return

    def guard(event: str, args: tuple) -> None:
        if event in {
            "socket.getaddrinfo",
            "socket.gethostbyname",
            "socket.gethostbyaddr",
            "socket.getnameinfo",
        }:
            raise RuntimeError(f"S3_QA_DNS_FORBIDDEN:{event}")
        if event in {"socket.connect", "socket.connect_ex"}:
            addr = args[1] if len(args) > 1 else None
            # Allow AF_UNIX string/bytes paths and loopback-only IPv4/IPv6 (127.0.0.1 / ::1).
            if isinstance(addr, tuple) and len(addr) >= 2:
                host = addr[0]
                if host not in {"127.0.0.1", "::1"}:
                    raise RuntimeError(f"S3_QA_EXTERNAL_SOCKET_FORBIDDEN:{host}")

    sys.addaudithook(guard)
    _AUDIT_INSTALLED = True


def setUpModule() -> None:
    assert os.readlink("/proc/self/ns/net") != os.readlink("/proc/1/ns/net"), "NETNS_NOT_ISOLATED"
    assert {name for _, name in socket.if_nameindex()} == {"lo"}, "NON_LOOPBACK_INTERFACE_PRESENT"
    _install_network_audit_fence()


def _ephemeral_cert_bundle(tmp: Path, san_dns: str) -> tuple[bytes, Path, Path]:
    """Generate a synthetic self-signed CA + server cert in tmpdir for loopback-only TLS QA."""
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "QA Synthetic Root CA")])
    now = datetime.datetime.now(datetime.timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    srv_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    srv_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, san_dns)])
    srv_cert = (
        x509.CertificateBuilder()
        .subject_name(srv_name)
        .issuer_name(ca_name)
        .public_key(srv_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=7))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(san_dns)]), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    ca_pem = ca_cert.public_bytes(serialization.Encoding.PEM)
    cert_path = tmp / f"{san_dns}.crt"
    key_path = tmp / f"{san_dns}.key"
    cert_path.write_bytes(srv_cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(
        srv_key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return ca_pem, cert_path, key_path


class V2BaseTest(accepted.LocalTest):
    def v2_scope(
        self,
        *,
        market: bool = True,
        profile: str = ZERO_RETRY_PROFILE,
        funding_debit: int | None = 1,
        funding_sha: str | None = "4" * 64,
        market_count: int = 37,
        market_weight: int | None = None,
        headroom_weight: int = 5,
        rolling_count: int = 96,
        rolling_weight: int = 120,
    ) -> dict:
        raw = self.scope(market)
        raw["activation_plan"]["timeout_profile"] = profile
        if market:
            if market_weight is None:
                debit_num = funding_debit if isinstance(funding_debit, int) else 1
                market_weight = 37 + 3 * debit_num
            raw["activation_plan"]["market"] = {"count": market_count, "weight": market_weight}
            total = {"count": 2 + market_count, "weight": 2 + market_weight}
            raw["budget"]["bootstrap"] = dict(total)
            raw["budget"]["total"] = dict(total)
            raw["budget"]["rolling_60s"] = {"count": rolling_count, "weight": rolling_weight}
            raw["budget"]["headroom_weight"] = headroom_weight
            raw["funding"] = {
                "documented_numeric_ip_weight": funding_debit,
                "official_evidence_sha256": funding_sha,
            }
        return raw

    def v2_active(self, *, scope: dict | None = None) -> Active:
        raw = self.v2_scope() if scope is None else scope
        return self.active(True, scope=raw)


class Group0IsolationTests(V2BaseTest):
    def test_00_private_namespace_and_network_audit_fence(self):
        self.assertNotEqual(os.readlink("/proc/self/ns/net"), os.readlink("/proc/1/ns/net"))
        self.assertEqual({name for _, name in socket.if_nameindex()}, {"lo"})
        with self.assertRaisesRegex(RuntimeError, "S3_QA_DNS_FORBIDDEN"):
            socket.getaddrinfo("fapi.binance.com", 443)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            with self.assertRaisesRegex(RuntimeError, "S3_QA_EXTERNAL_SOCKET_FORBIDDEN"):
                sock.connect(("1.1.1.1", 443))
        finally:
            sock.close()


class GroupBPlanABCAndNominalTests(V2BaseTest):
    def test_b1_v2_happy_nominal_synthetic_39_plan_a_and_replay(self):
        scope = self.v2_scope(funding_debit=1)
        approval = self.approve(scope)
        self.assertEqual(approval.scope.stage_plan.market_retry_limit, 0)
        validate_s3_v2_candidate_scope(scope, self.roots, envelope=self.envelope(scope), release="5" * 64, wall_ms=self.now)

        active = Active(Ledger.qa(self.state, approval), approval, self.clock, RunIdentity("S3-V2-BOOT", "S3-V2-RUN"))
        active.claim()
        seen_stages = ["CANARY"]
        pub = collect(active, "bootstrap", FixtureWire(self.clock), notify_stage=lambda: seen_stages.append("MARKET"))
        stage = pub["stage"]
        self.assertIsNone(stage["issue"])
        self.assertEqual(seen_stages, ["CANARY", "MARKET"])
        self.assertEqual(stage["stats"]["reserved_requests"], 39)
        self.assertEqual(stage["stats"]["reserved_weight"], 42)
        self.assertIsNotNone(pub["visible_venue_upper_ms"])

        # Verify exact request sequence matches pinned S3_REQUEST_BUDGET_MATRIX.json Plan A (39 requests).
        matrix = json.loads(S3_MATRIX_PATH.read_text(encoding="utf-8"))
        expected_routes = [(r["path"], r["symbol"], r["interval"]) for r in matrix["plans"]["A_FULL"]["requests"]]
        with active.ledger.store.connect() as db:
            rows = db.execute("SELECT route, request, retry, weight FROM attempts ORDER BY id").fetchall()
        self.assertEqual(len(rows), 39)
        self.assertTrue(all(r["retry"] == 0 for r in rows))
        actual_routes = []
        for r in rows:
            req_data = json.loads(r["request"])
            params = req_data.get("params", {})
            actual_routes.append((r["route"], params.get("symbol"), params.get("interval", params.get("period"))))
        self.assertEqual(actual_routes, expected_routes)

        # Verify B4/B2 admission, 5-frame causality, 32 completed bars, NO_SETUP & deterministic replay.
        adapter = Adapter(active.ledger)
        b2 = engine(adapter, self.root / "journal.sqlite")
        rebuilder = engine(adapter, self.root / "rebuild.sqlite")
        for symbol in SYMBOL_ORDER:
            market = adapter.read(symbol, scan=pub["scan_id"])
            self.assertEqual(market.source["evidence"], QA)
            self.assertEqual(set(market.bars.keys()), set(INTERVALS.keys()))
            for frame, bars in market.bars.items():
                self.assertEqual(len(bars), 32)
                for bar in bars:
                    self.assertLessEqual(bar.end_ms + 2000, market.cutoff_ms)
            card = b2.evaluate(symbol, scan=pub["scan_id"], as_of_ms=market.evaluated_ms)
            rebuilt = rebuilder.evaluate(symbol, scan=pub["scan_id"], as_of_ms=market.evaluated_ms)
            self.assertEqual(card["market_status"], "NO_SETUP")
            self.assertEqual(card["account_context_status"], "UNAVAILABLE")
            self.assertEqual(card["safe_position_size"], "UNKNOWN")
            self.assertEqual(card["source_lane"], QA)
            self.assertNotEqual(card["evidence"], GENUINE)
            c1 = {k: v for k, v in card.items() if k != "journal_recorded_wall_ms"}
            c2 = {k: v for k, v in rebuilt.items() if k != "journal_recorded_wall_ms"}
            self.assertEqual(c1, c2)
            self.assertEqual(replay(adapter, card)["evidence"], QA)

    def test_b2_v2_b2_decimal_scenarios_watch_executable_invalid_preserved(self):
        # Verify frozen B2/B4 Decimal costs, net-R, first obstruction, and no-chase rules are untouched.
        chase = run_case(self.root / "chase-case", "trend_pullback-long", chase=True)
        statuses = [c["market_status"] for c in chase["cards"]]
        self.assertEqual(statuses[:3], ["WATCH", "EXECUTABLE", "INVALID"])
        self.assertIn("MISSED_NO_CHASE", chase["cards"][2]["reasons"])
        exec_card = chase["cards"][1]
        self.assertIsNotNone(exec_card["plan"])
        self.assertEqual(exec_card["plan"]["schema"], "B2_MARKET_PLAN_V1")
        self.assertEqual(exec_card["plan"]["targets"][0]["label"], "TP1")
        self.assertIn("net_r", exec_card["plan"]["targets"][0])
        self.assertIn("first_obstacle_after_cost_r", exec_card["plan"])
        self.assertIn("fee_rate_each_side", exec_card["plan"])
        self.assertIn("slippage_bps_each_side", exec_card["plan"])
        self.assertIn("spread_usdt", exec_card["plan"])
        self.assertIn("funding", exec_card["plan"])
        self.assertEqual(exec_card["source_lane"], QA)
        self.assertEqual(exec_card["account_context_status"], "UNAVAILABLE")

        short_case = run_case(self.root / "short-case", "early_continuation-short")
        self.assertEqual([c["market_status"] for c in short_case["cards"]], ["WATCH", "EXECUTABLE", "EXECUTABLE", "EXECUTABLE"])

    def test_b3_plan_a_funding_weight_unknown_null_invalid_excessive_and_substitutes_fail_closed(self):
        # 1. Unknown / null / non-integer / boolean / negative / excessive d all fail closed.
        for bad_d in (None, "", "1", "500", False, True, 1.0, -1, 65, 500):
            with self.subTest(bad_d=bad_d):
                raw = self.v2_scope(funding_debit=bad_d, market_weight=40)
                with self.assertRaisesRegex(SourceBlocked, "FUNDING_WEIGHT_UNRESOLVED"):
                    self.approve(raw)
                with self.assertRaisesRegex(SourceBlocked, "FUNDING_WEIGHT_UNRESOLVED"):
                    RouteRequest(FUNDING, {"symbol": "BTCUSDT", "startTime": 1, "endTime": 2, "limit": 256}, funding_debit=bad_d).validate()
                gate = evaluate_plan_a_funding_gate(bad_d, "4" * 64)
                self.assertFalse(gate["live_qualification_allowed"])
                self.assertIsNone(gate["signable_combined_weight"])

        # 2. Missing / null / malformed official_evidence_sha256 fails closed even with integer d.
        for bad_sha in (None, "", "short", "z" * 64):
            raw = self.v2_scope(funding_debit=1, funding_sha=bad_sha, market_weight=40)
            with self.assertRaisesRegex(SourceBlocked, "FUNDING_WEIGHT_UNRESOLVED"):
                self.approve(raw)
            gate = evaluate_plan_a_funding_gate(1, bad_sha)
            self.assertEqual(gate["decision"], "FUNDING_WEIGHT_UNRESOLVED_MISSING_OFFICIAL_EVIDENCE")
            self.assertFalse(gate["live_qualification_allowed"])

        # 3. Necessary arithmetic bound d <= 8 under 64 cap:
        # d=8 -> 39 + 3*8 = 63 <= 64 (synthetic scope parses, still NOT live authorized without verified official evidence)
        scope_d8 = self.v2_scope(funding_debit=8, market_weight=37 + 24)
        approved_d8 = self.approve(scope_d8)
        self.assertEqual(approved_d8.scope.total.weight, 63)
        self.assertEqual(approved_d8.scope.stage_plan.market_retry_limit, 0)
        gate_d8_unverified = evaluate_plan_a_funding_gate(8, "4" * 64, external_official_verified=False)
        self.assertEqual(gate_d8_unverified["decision"], "FUNDING_WEIGHT_UNRESOLVED_MISSING_OFFICIAL_EVIDENCE")
        self.assertFalse(gate_d8_unverified["live_qualification_allowed"])

        # d=9 -> 39 + 3*9 = 66 > 64 -> refused!
        scope_d9 = self.v2_scope(funding_debit=9, market_weight=37 + 27)
        with self.assertRaisesRegex(SourceBlocked, "MARKET_STAGE_BUDGET_INVALID"):
            self.approve(scope_d9)
        with self.assertRaisesRegex(SourceBlocked, "PLAN_A_WEIGHT_EXCEEDS_CANDIDATE_CAP"):
            validate_s3_v2_candidate_scope(scope_d9, self.roots)
        gate_d9 = evaluate_plan_a_funding_gate(9, "4" * 64, external_official_verified=True)
        self.assertEqual(gate_d9["decision"], "PLAN_A_WEIGHT_EXCEEDS_CANDIDATE_CAP")
        self.assertFalse(gate_d9["live_qualification_allowed"])

        # 4. Forbidden substitutes (500/5min family cap, fundingInfo=0, premiumIndex=1, header delta, fixture=1) fail closed.
        for sub in FORBIDDEN_DEBIT_SUBSTITUTES:
            gate = evaluate_plan_a_funding_gate(0, "4" * 64, substitute_source=sub)
            self.assertEqual(gate["decision"], "DENIED_FORBIDDEN_DEBIT_SUBSTITUTE")
            self.assertFalse(gate["live_qualification_allowed"])
            self.assertIsNone(gate["signable_combined_weight"])

    def test_b4_plan_b_diagnostic_36_plan_weights_zero_cards_and_b2_b4_rejection(self):
        plan_b = evaluate_plan_b_diagnostic(PROSPECTIVE_CUTOFF_MS)
        self.assertEqual(plan_b["combined_requests"], 36)
        self.assertEqual(plan_b["combined_known_general_ip_weight"], 39)
        self.assertEqual(plan_b["market_stage_requests"], 34)
        self.assertEqual(plan_b["market_stage_known_general_ip_weight"], 37)
        self.assertEqual(plan_b["omitted_plan_a_slots"], [19, 26, 33])
        self.assertEqual(plan_b["funding_family_requests_5min"], 0)
        self.assertEqual(plan_b["oi_history_family_requests_5min"], 3)
        self.assertEqual(plan_b["strategy_status"], "NOT_EVALUATED")
        self.assertEqual(plan_b["market_cards"], 0)
        self.assertIsNone(plan_b["funding_cost"])
        self.assertIsNone(plan_b["net_r"])
        self.assertFalse(plan_b["decision_grade"])
        self.assertFalse(plan_b["can_pass_b2_b4_full_market_qualification"])
        self.assertFalse(plan_b["can_publish_market_card"])

        # Attempting to submit a 36-request Plan B budget to StagePlan.parse fails closed (full 37 market required).
        scope_b = self.v2_scope(market_count=34, market_weight=37, funding_debit=0)
        with self.assertRaisesRegex(SourceBlocked, "MARKET_STAGE_BUDGET_INVALID"):
            self.approve(scope_b)

        # Even if funding history returns empty for all 3 symbols, unchanged B4/B2 CANNOT qualify any symbol.
        active = self.v2_active()

        def omit_funding(req, reply):
            if req.route == FUNDING:
                return replace(reply, body=b"[]")
            return reply

        pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=omit_funding))
        self.assertIsNone(pub["stage"]["issue"])
        decide = engine(Adapter(active.ledger), self.root / "planb-journal.sqlite")
        for symbol in SYMBOL_ORDER:
            self.assertEqual(pub["stage"]["markets"][symbol]["issue"]["code"], "FUNDING_HISTORY_EMPTY")
            with self.assertRaisesRegex(DecisionError, "SYMBOL_INPUT_BLOCKED"):
                decide.evaluate(symbol, scan=pub["scan_id"])
            card = decide.evaluate(symbol, scan=pub["scan_id"], as_of_ms=pub["visible_venue_upper_ms"])
            self.assertEqual(card["market_status"], "SOURCE_BLOCKED")
            self.assertIsNone(card["plan"])
            self.assertIsNone(card["evaluation_receipt"])

    def test_b5_plan_c_cost_unverified_research_only(self):
        doc = build_plan_gate_document(candidate_wheel_sha256="0" * 64)
        plan_c = doc["plans"]["C_RESEARCH_ONLY"]
        self.assertEqual(plan_c["status"], "COST_UNVERIFIED_RESEARCH_ONLY")
        self.assertEqual(plan_c["authorization"], "NOT_AUTHORIZED")
        self.assertFalse(plan_c["live_eligible"])
        self.assertFalse(plan_c["alternative_cost_model_enabled"])
        self.assertFalse(plan_c["can_publish_market_card"])
        self.assertFalse(plan_c["can_modify_frozen_v1_enum"])

    def test_b6_s2_only_grant_never_enables_s3_and_rejects_v2_profile(self):
        # S2-only grant with V2 ZERO_RETRY_PROFILE fails immediately.
        s2_v2 = self.v2_scope(market=False, profile=ZERO_RETRY_PROFILE)
        with self.assertRaisesRegex(SourceBlocked, "ZERO_RETRY_MARKET_SCOPE_REQUIRED"):
            self.approve(s2_v2)

        # S2-only grant with legacy V1 profile runs exact 2 GETs and never unlocks Stage 2.
        s2_v1 = self.v2_scope(market=False, profile=TIMEOUT_PROFILE)
        with self.assertRaisesRegex(SourceBlocked, "S2_ONLY_GRANT_CANNOT_ENABLE_S3"):
            validate_s3_v2_candidate_scope(s2_v1, self.roots)
        active = self.active(False, scope=s2_v1)
        pub = collect(active, "bootstrap", FixtureWire(self.clock), notify_stage=lambda: self.fail("S3 started from S2"))
        self.assertEqual(pub["stage"]["market_status"], "NOT_EVALUATED")
        self.assertIsNone(pub["visible_venue_upper_ms"])
        self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 2)
        with self.assertRaisesRegex(SourceBlocked, "STAGE2_NOT_AUTHORIZED"):
            active.reserve("bootstrap", pub["scan_id"], 3, 0, RouteRequest(TIME, {}), self.clock.sample())

    def test_b7_five_frame_causality_forming_candle_gap_and_partial_failure(self):
        active = self.v2_active()

        def bad_klines(req, reply):
            if req.route != KLINES or req.params["interval"] != "5m":
                return reply
            rows = json.loads(reply.body)
            sym = req.params["symbol"]
            if sym == "BTCUSDT":
                # Forming candle breaching close grace (shifted forward by +300_000 ms)
                rows[-1][0] += 300_000
                rows[-1][6] += 300_000
            elif sym == "ETHUSDT":
                # Missing bar gap
                rows.pop(10)
            return replace(reply, body=json.dumps(rows).encode())

        pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=bad_klines))
        self.assertIsNone(pub["stage"]["issue"])
        self.assertEqual(pub["stage"]["markets"]["BTCUSDT"]["issue"]["code"], "KLINE_OUTSIDE_WINDOW")
        self.assertEqual(pub["stage"]["markets"]["ETHUSDT"]["issue"]["code"], "KLINE_GAP")
        self.assertIsNone(pub["stage"]["markets"]["SOLUSDT"]["issue"])
        decide = engine(Adapter(active.ledger), self.root / "causality-journal.sqlite")
        for bad_sym in ("BTCUSDT", "ETHUSDT"):
            card = decide.evaluate(bad_sym, scan=pub["scan_id"], as_of_ms=pub["visible_venue_upper_ms"])
            self.assertEqual(card["market_status"], "SOURCE_BLOCKED")
            self.assertIsNone(card["plan"])
        ok_card = decide.evaluate("SOLUSDT", scan=pub["scan_id"], as_of_ms=pub["visible_venue_upper_ms"])
        self.assertEqual(ok_card["market_status"], "NO_SETUP")


class GroupCFaultInjectionZeroRetryTests(V2BaseTest):
    def _fresh_v2_active(self, tag: str, **kwargs) -> Active:
        self.state = self.root / f"{tag}.sqlite"
        self.roots = replace(self.roots, state_path=self.state)
        scope = self.v2_scope(**kwargs)
        return self.v2_active(scope=scope)

    def test_c1_http_408_500_502_503_504_zero_retries_even_with_unused_budget(self):
        # Give maximum unused budget (46 market / 48 total, 62 market / 64 total weight) so unused budget exists!
        for status in (408, 500, 502, 503, 504):
            with self.subTest(status=status):
                active = self._fresh_v2_active(f"http_{status}", market_count=46, market_weight=62)
                calls = 0

                def inject(req, reply):
                    nonlocal calls
                    if req.route == KLINES:
                        calls += 1
                        return fixture_reply({}, status=status)
                    return reply

                pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=inject))
                stage = pub["stage"]
                self.assertEqual(calls, 1)
                self.assertEqual(stage["issue"]["code"], "TRANSIENT_HTTP_EXHAUSTED")
                self.assertEqual(stage["issue"]["detail"], str(status))
                self.assertEqual(stage["stats"]["reserved_requests"], 3)
                self.assertEqual(stage["stats"]["reserved_weight"], 3)
                self.assertIsNone(pub["visible_venue_upper_ms"])
                self.assertEqual(stage["markets"], {})
                with Ledger.open_qa(self.state).store.connect() as db:
                    rows = db.execute("SELECT route, retry FROM attempts ORDER BY id").fetchall()
                    self.assertEqual([tuple(r) for r in rows], [(TIME, 0), (INSTRUMENTS, 0), (KLINES, 0)])
                    self.assertEqual(db.execute("SELECT state FROM b5_control").fetchone()[0], "HALTED")
                with self.assertRaisesRegex(DecisionError, "SOURCE_RUN_BLOCKED"):
                    Adapter(active.ledger).read("BTCUSDT", scan=pub["scan_id"])
                with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_CONSUMED_OR_REVOKED"):
                    active.claim()
                with self.assertRaisesRegex(SourceBlocked, "TRANSIENT_HTTP_EXHAUSTED"):
                    active.begin_phase("bootstrap")

    def test_c2_http_429_451_403_418_zero_retries_and_persistent_stop(self):
        for status in (429, 451, 403, 418):
            with self.subTest(status=status):
                active = self._fresh_v2_active(f"stop_{status}", market_count=46, market_weight=62)

                def inject(req, reply):
                    if req.route == KLINES:
                        return fixture_reply({}, status=status, headers={"retry-after": "15"})
                    return reply

                pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=inject))
                stage = pub["stage"]
                self.assertEqual(stage["stats"]["reserved_requests"], 3)
                self.assertIsNone(pub["visible_venue_upper_ms"])
                self.assertEqual(stage["markets"], {})
                with Ledger.open_qa(self.state).store.connect() as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE retry > 0").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT state FROM b5_control").fetchone()[0], "HALTED")
                    stop, hold = db.execute("SELECT stop, cooldown_hold FROM budget_epoch").fetchone()
                    if status == 429:
                        self.assertEqual(hold, 15_000)
                    else:
                        self.assertEqual(stop, f"HTTP_{status}")
                with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_CONSUMED_OR_REVOKED"):
                    active.claim()

    def test_c3_http_3xx_redirects_no_follow_zero_retries(self):
        for status in (301, 302, 307, 308):
            with self.subTest(status=status):
                active = self._fresh_v2_active(f"redir_{status}", market_count=46, market_weight=62)

                def inject(req, reply):
                    if req.route == KLINES:
                        return fixture_reply({}, status=status, headers={"location": "https://evil.invalid/"})
                    return reply

                pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=inject))
                self.assertEqual(pub["stage"]["issue"]["code"], "HTTP_REDIRECT")
                self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 3)
                self.assertIsNone(pub["visible_venue_upper_ms"])
                with Ledger.open_qa(self.state).store.connect() as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE retry > 0").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT state FROM b5_control").fetchone()[0], "HALTED")

    def test_c4_tcp_tls_ca_dns_and_retryable_wire_errors_zero_retries(self):
        faults = [
            ("retryable_wire", WireFailure("TRANSIENT_WIRE_FAILURE", retryable=True), "TRANSIENT_WIRE_FAILURE"),
            ("retryable_connect", WireFailure("TRANSIENT_CONNECT_FAILURE", retryable=True), "TRANSIENT_CONNECT_FAILURE"),
            ("tls_fail", WireFailure("TLS_VERIFICATION_FAILED", retryable=False), "TLS_VERIFICATION_FAILED"),
            ("connect_fail", WireFailure("CONNECT_FAILED", retryable=False), "CONNECT_FAILED"),
            ("dns_fail", SourceBlocked("DNS_EGRESS_FAILED"), "DNS_EGRESS_FAILED"),
            ("ca_changed", SourceBlocked("SYSTEM_CA_BUNDLE_CHANGED"), "SYSTEM_CA_BUNDLE_CHANGED"),
            ("tcp_reset", ConnectionResetError("synthetic tcp reset"), "TRANSPORT_FAILED"),
            ("tcp_timeout", TimeoutError("synthetic tcp timeout"), "TRANSPORT_FAILED"),
        ]
        for label, exc, expected_code in faults:
            with self.subTest(label=label):
                active = self._fresh_v2_active(f"wire_{label}", market_count=46, market_weight=62)
                hits = 0

                def inject(req, reply):
                    nonlocal hits
                    if req.route == KLINES:
                        hits += 1
                        raise exc
                    return reply

                pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=inject))
                self.assertEqual(hits, 1)
                self.assertEqual(pub["stage"]["issue"]["code"], expected_code)
                self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 3)
                self.assertEqual(pub["stage"]["stats"]["reserved_weight"], 3)
                self.assertIsNone(pub["visible_venue_upper_ms"])
                with Ledger.open_qa(self.state).store.connect() as db:
                    self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE retry > 0").fetchone()[0], 0)
                    self.assertEqual(db.execute("SELECT state FROM b5_control").fetchone()[0], "HALTED")
                with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_CONSUMED_OR_REVOKED"):
                    active.claim()

    def test_c5_loopback_tls_ca_hostname_redirect_truncation_503_zero_lower_level_retry(self):
        # Test real egress._exchange / _tls_context / _dns_answers / _select_peer on loopback 127.0.0.1 only.
        ca_good, cert_good, key_good = _ephemeral_cert_bundle(self.root, HOST)
        ca_other, cert_bad_host, key_bad_host = _ephemeral_cert_bundle(self.root, "wrong-host.invalid")

        def run_server(cert_path: Path, key_path: Path, raw_http_reply: bytes, counter: list[int]):
            srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            srv_ctx.minimum_version = ssl.TLSVersion.TLSv1_2
            srv_ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen(2)
            port = listener.getsockname()[1]

            def serve():
                try:
                    listener.settimeout(3.0)
                    try:
                        client, _ = listener.accept()
                    except OSError:
                        return
                    with client:
                        try:
                            with srv_ctx.wrap_socket(client, server_side=True) as tls:
                                tls.settimeout(2.0)
                                data = tls.recv(4096)
                                if data:
                                    counter.append(1)
                                    tls.sendall(raw_http_reply)
                        except OSError:
                            pass
                finally:
                    listener.close()

            t = threading.Thread(target=serve, daemon=True)
            t.start()
            return port, t

        def dial_loopback(port: int) -> socket.socket:
            # Direct numeric AF_INET connect to 127.0.0.1 with ZERO DNS / getaddrinfo calls.
            conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            conn.settimeout(2.0)
            conn.connect(("127.0.0.1", port))
            return conn

        req = RouteRequest(TIME, {})
        proof_stub = {"peer": "127.0.0.1", "authority": f"{HOST}:443"}

        # 1. Untrusted CA fails TLS verification (non-retryable)
        c1: list[int] = []
        port, t = run_server(cert_good, key_good, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}", c1)
        with dial_loopback(port) as conn:
            with self.assertRaisesRegex(WireFailure, "TLS_VERIFICATION_FAILED") as cm:
                egress._exchange(conn, req, egress._tls_context(ca_other), time.monotonic() + 2.0, proof_stub, lambda: None)
            self.assertFalse(cm.exception.retryable)
        t.join(timeout=2.0)
        self.assertEqual(len(c1), 0)

        # 2. Wrong hostname SAN fails TLS verification (non-retryable)
        c2: list[int] = []
        port, t = run_server(cert_bad_host, key_bad_host, b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\n{}", c2)
        with dial_loopback(port) as conn:
            with self.assertRaisesRegex(WireFailure, "TLS_VERIFICATION_FAILED") as cm:
                egress._exchange(conn, req, egress._tls_context(ca_other), time.monotonic() + 2.0, proof_stub, lambda: None)
            self.assertFalse(cm.exception.retryable)
        t.join(timeout=2.0)
        self.assertEqual(len(c2), 0)

        # 3. HTTP 302 redirect on TLS wire -> complete=False, NOT followed, 1 request only
        c3: list[int] = []
        port, t = run_server(
            cert_good, key_good, b"HTTP/1.1 302 Found\r\nLocation: https://evil.invalid/\r\nContent-Length: 0\r\n\r\n", c3
        )
        with dial_loopback(port) as conn:
            reply = egress._exchange(conn, req, egress._tls_context(ca_good), time.monotonic() + 2.0, proof_stub, lambda: None)
        t.join(timeout=2.0)
        self.assertEqual((reply.status, reply.complete, len(c3)), (302, False, 1))

        # 4. Truncated HTTP body on TLS wire -> complete=False, HTTP_BODY_INCOMPLETE, 1 request only
        c4: list[int] = []
        port, t = run_server(
            cert_good, key_good, b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 100\r\n\r\n{\"part", c4
        )
        with dial_loopback(port) as conn:
            reply = egress._exchange(conn, req, egress._tls_context(ca_good), time.monotonic() + 2.0, proof_stub, lambda: None)
        t.join(timeout=2.0)
        self.assertEqual((reply.status, reply.complete, reply.issue, len(c4)), (200, False, "TRUNCATED_HTTP_BODY", 1))

        # 5. HTTP 503 on TLS wire -> returned as Reply(503), ZERO lower-level retry, 1 request only
        c5: list[int] = []
        port, t = run_server(cert_good, key_good, b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 2\r\n\r\n{}", c5)
        with dial_loopback(port) as conn:
            reply = egress._exchange(conn, req, egress._tls_context(ca_good), time.monotonic() + 2.0, proof_stub, lambda: None)
        t.join(timeout=2.0)
        self.assertEqual((reply.status, len(c5)), (503, 1))

        # 6. DNS peer outside approval / invalid packet fails closed
        with self.assertRaisesRegex(SourceBlocked, "DNS_PEER_OUTSIDE_APPROVAL"):
            egress._select_peer(("203.0.113.9",), ("198.51.100.1",))
        with self.assertRaisesRegex(SourceBlocked, "DNS_REPLY_INVALID"):
            egress._dns_answers(b"\x00" * 12, 1234)

    def test_c6_truncation_timeout_malformed_payload_and_headroom_exhaustion_zero_retries(self):
        # 1. Truncated reply
        active = self._fresh_v2_active("trunc")
        pub = collect(
            active,
            "bootstrap",
            FixtureWire(
                self.clock,
                mutate=lambda req, rep: replace(rep, body=b"", complete=False, issue="HTTP_BODY_INCOMPLETE")
                if req.route == KLINES
                else rep,
            ),
        )
        self.assertEqual(pub["stage"]["issue"]["code"], "HTTP_BODY_INCOMPLETE")
        self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 3)
        self.assertIsNone(pub["visible_venue_upper_ms"])

        # 2. Request timeout (> 1500ms)
        active = self._fresh_v2_active("req_timeout")

        def slow_kline(req, rep):
            if req.route == KLINES:
                self.clock.advance(2_000)
            return rep

        pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=slow_kline))
        self.assertEqual(pub["stage"]["issue"]["code"], "REQUEST_DEADLINE")
        self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 3)
        self.assertIsNone(pub["visible_venue_upper_ms"])
        with Ledger.open_qa(self.state).store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE retry > 0").fetchone()[0], 0)

        # 3. Malformed JSON & wrong Content-Type
        active = self._fresh_v2_active("bad_json")
        pub = collect(
            active,
            "bootstrap",
            FixtureWire(
                self.clock,
                mutate=lambda req, rep: replace(rep, body=b"{broken-json") if req.route == KLINES else rep,
            ),
        )
        self.assertIsNone(pub["stage"]["issue"])
        self.assertEqual(pub["stage"]["markets"]["BTCUSDT"]["issue"]["code"], "MALFORMED_JSON")
        self.assertEqual(pub["stage"]["markets"]["ETHUSDT"]["issue"]["code"], "MALFORMED_JSON")
        self.assertEqual(pub["stage"]["markets"]["SOLUSDT"]["issue"]["code"], "MALFORMED_JSON")
        with Ledger.open_qa(self.state).store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE retry > 0").fetchone()[0], 0)

        active = self._fresh_v2_active("bad_ctype")
        pub = collect(
            active,
            "bootstrap",
            FixtureWire(
                self.clock,
                mutate=lambda req, rep: replace(rep, headers={**rep.headers, "content-type": "text/html"})
                if req.route == KLINES
                else rep,
            ),
        )
        self.assertEqual(pub["stage"]["markets"]["BTCUSDT"]["issue"]["code"], "UNEXPECTED_CONTENT_TYPE")

        # 4. No headroom (rolling weight cap minus headroom exhausted)
        active = self._fresh_v2_active("no_headroom", rolling_weight=10, headroom_weight=8)
        pub = collect(active, "bootstrap", FixtureWire(self.clock))
        self.assertIsNotNone(pub["stage"]["issue"])
        self.assertLess(pub["stage"]["stats"]["reserved_requests"], 39)
        self.assertIsNone(pub["visible_venue_upper_ms"])
        with Ledger.open_qa(self.state).store.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM attempts WHERE retry > 0").fetchone()[0], 0)

        # 5. Unexplained shared-IP jump on response header
        active = self._fresh_v2_active("weight_jump")
        pub = collect(
            active,
            "bootstrap",
            FixtureWire(
                self.clock,
                mutate=lambda req, rep: replace(rep, headers={**rep.headers, "x-mbx-used-weight-1m": "99"})
                if req.route == KLINES
                else rep,
            ),
        )
        self.assertEqual(pub["stage"]["issue"]["code"], "SHARED_EGRESS_WEIGHT_JUMP")
        self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 3)
        self.assertIsNone(pub["visible_venue_upper_ms"])


class GroupDLedgerSecurityAndStateTests(V2BaseTest):
    def test_d1_direct_retry_index_rejected_before_reserve_and_pre_dispatch(self):
        active = self.v2_active()
        checked = []

        def inject_direct_retry():
            with active.ledger.store.connect() as db:
                before_count = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
                marker = json.loads(db.execute("SELECT payload FROM h2a_canary").fetchone()[0])
            req = next(market_requests(marker["cutoff_venue_ms"]))
            route_req = RouteRequest(req.route, req.params, funding_debit=1)
            for bad_retry in (1, 2):
                with self.assertRaisesRegex(SourceBlocked, "STAGE2_RETRY_POLICY_DENIED"):
                    active.reserve("bootstrap", 1, 3, bad_retry, route_req, self.clock.sample())
            with active.ledger.store.connect() as db:
                after_count = db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]
            self.assertEqual(before_count, after_count)
            checked.append(True)

        pub = collect(active, "bootstrap", FixtureWire(self.clock), notify_stage=inject_direct_retry)
        self.assertEqual(checked, [True])
        self.assertIsNone(pub["stage"]["issue"])

        # Now prove assert_pending ALSO rejects retry=1 before dispatch even if injected directly into SQLite.
        self.state = self.root / "pending_retry.sqlite"
        self.roots = replace(self.roots, state_path=self.state)
        active2 = self.v2_active()
        # Run canary only via manual reserve + settle? Simpler: run collect, revoke on boundary to stop after Canary.
        collect(active2, "bootstrap", FixtureWire(self.clock), notify_stage=active2.revoke)
        with active2.ledger.store.connect() as db:
            marker = json.loads(db.execute("SELECT payload FROM h2a_canary").fetchone()[0])
        req = next(market_requests(marker["cutoff_venue_ms"]))
        route_req = RouteRequest(req.route, req.params, funding_debit=1)
        # Re-open SQLite directly to simulate tampered pending row with retry=1 and state=CONSUMED.
        with sqlite3.connect(self.state) as db:
            db.execute("UPDATE b5_control SET state='CONSUMED', reason=NULL WHERE singleton=1")
            stamp = encode(active2.identity.stamp(self.clock.sample()).data())
            cur = db.execute(
                """INSERT INTO attempts(scan_id,logical_request,retry,route,weight,family,egress,request,reserved,accounted_mono)
                   VALUES (1,3,1,?,1,'GENERAL',?,?,?,?)""",
                (route_req.route, active2.ledger.store.egress, encode(route_req.data()), stamp, self.clock.sample().mono_ms),
            )
            fake_id = cur.lastrowid
            db.execute("INSERT INTO b4_sends VALUES (?,?)", (fake_id, stamp))
        with self.assertRaisesRegex(SourceBlocked, "STAGE2_RETRY_POLICY_DENIED"):
            active2.assert_pending(fake_id, route_req)

    def test_d2_manual_second_try_and_phase_replay_denied(self):
        active = self.v2_active()
        pub = collect(active, "bootstrap", FixtureWire(self.clock))
        self.assertIsNone(pub["stage"]["issue"])
        with self.assertRaisesRegex(SourceBlocked, "SCAN_PHASE_ALREADY_CONSUMED"):
            collect(active, "bootstrap", FixtureWire(self.clock))
        active.close()
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_NOT_RUNNING"):
            active.begin_phase("bootstrap")
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_CONSUMED_OR_REVOKED"):
            active.claim()

    def test_d3_abrupt_crash_and_restart_durable_reserve_no_resume(self):
        scope = self.v2_scope()
        approval = self.approve(scope)
        Ledger.qa(self.state, approval)
        script = """
import os, sys
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from quant_personal_live_public_b5.approval import Limit
from quant_personal_live_public_b5.collection import collect
from quant_personal_live_public_b5.contract import RouteRequest
from quant_personal_live_public_b5.ledger import Active, Ledger
from quant_personal_live_public_b5.offline import FixtureWire, qa_approval
from quant_personal_live_public_b5.stages import StagePlan, market_requests
from quant_personal_public_b1.fixture import FixtureClock
from quant_personal_public_b1.session import RunIdentity
import json

path = Path(sys.argv[1])
release, scope_sha, run_id, signed_sha = sys.argv[2:]
base = qa_approval(path)
plan = StagePlan(37, 40, 0)
total = Limit(39, 42)
scope_obj = replace(base.scope, sha256=scope_sha, stage_plan=plan,
                    phase_limits=MappingProxyType({"bootstrap": total}), total=total, funding_debit=1)
appr = replace(base, run_id=run_id, release=release, signed_sha256=signed_sha, scope=scope_obj)
clock = FixtureClock()
active = Active(Ledger.open_qa(path), appr, clock, RunIdentity("v2-boot-1", "v2-proc-crash"))
active.claim()

def crash_on_stage2():
    with active.ledger.store.connect() as db:
        marker = json.loads(db.execute("SELECT payload FROM h2a_canary").fetchone()[0])
    req = next(market_requests(marker["cutoff_venue_ms"]))
    active.reserve("bootstrap", 1, 3, 0, RouteRequest(req.route, req.params, funding_debit=1), clock.sample())
    os._exit(23)

collect(active, "bootstrap", FixtureWire(clock), notify_stage=crash_on_stage2)
"""
        res = subprocess.run(
            [sys.executable, "-c", script, str(self.state), approval.release, approval.scope.sha256, approval.run_id, approval.signed_sha256],
            check=False,
        )
        self.assertEqual(res.returncode, 23)
        reopened = Active(Ledger.open_qa(self.state), approval, self.clock, RunIdentity("v2-boot-2", "v2-proc-restart"))
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_CONSUMED_OR_REVOKED"):
            reopened.claim()
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_PROCESS_OWNERSHIP"):
            reopened.begin_phase("bootstrap")
        with reopened.ledger.store.connect() as db:
            rows = db.execute("SELECT route, retry, response, weight FROM attempts ORDER BY id").fetchall()
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[2]["route"], KLINES)
            self.assertEqual(rows[2]["retry"], 0)
            self.assertIsNone(rows[2]["response"])
            self.assertEqual(rows[2]["weight"], 1)

    def test_d4_parallel_claimant_exactly_one_winner(self):
        scope = self.v2_scope()
        approval = self.approve(scope)
        Ledger.qa(self.state, approval)
        gate_file = self.root / "go.flag"
        worker = """
import os, sys, time, sqlite3
from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
from quant_personal_live_public_b5.approval import Limit
from quant_personal_live_public_b5.ledger import Active, Ledger
from quant_personal_live_public_b5.offline import qa_approval
from quant_personal_live_public_b5.stages import StagePlan
from quant_personal_public_b1.fixture import FixtureClock
from quant_personal_public_b1.policy import SourceBlocked
from quant_personal_public_b1.session import RunIdentity

path, gate, release, scope_sha, run_id, signed_sha, sess = sys.argv[1:]
base = qa_approval(Path(path))
plan = StagePlan(37, 40, 0)
total = Limit(39, 42)
scope_obj = replace(base.scope, sha256=scope_sha, stage_plan=plan,
                    phase_limits=MappingProxyType({"bootstrap": total}), total=total, funding_debit=1)
appr = replace(base, run_id=run_id, release=release, signed_sha256=signed_sha, scope=scope_obj)
active = Active(Ledger.open_qa(Path(path)), appr, FixtureClock(), RunIdentity("parallel-boot", sess))
while not os.path.exists(gate):
    time.sleep(0.005)
try:
    active.claim()
    print("WON:" + sess)
except (SourceBlocked, sqlite3.OperationalError) as exc:
    code = getattr(exc, "code", type(exc).__name__)
    print("DENIED:" + sess + ":" + code)
"""
        procs = [
            subprocess.Popen(
                [
                    sys.executable, "-c", worker, str(self.state), str(gate_file),
                    approval.release, approval.scope.sha256, approval.run_id, approval.signed_sha256, f"sess-{i}",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            for i in (1, 2)
        ]
        time.sleep(0.15)
        gate_file.write_text("GO", encoding="ascii")
        outputs = []
        for p in procs:
            out, err = p.communicate(timeout=10)
            self.assertEqual(p.returncode, 0, err)
            outputs.append(out.strip())
        winners = [o for o in outputs if o.startswith("WON:")]
        denials = [o for o in outputs if o.startswith("DENIED:")]
        self.assertEqual(len(winners), 1, outputs)
        self.assertEqual(len(denials), 1, outputs)

    def test_d5_stale_wrong_signatures_and_scope_mutation_fail_closed(self):
        scope = self.v2_scope()
        env = self.envelope(scope)

        # Swapped owner/controller signatures
        swapped = {**env, "owner_signature": env["controller_signature"], "controller_signature": env["owner_signature"]}
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_SIGNATURE_INVALID"):
            self.approve(scope, swapped)

        # Wrong / truncated signature
        for field in ("owner_signature", "controller_signature"):
            bad = {**env, field: "0" * 128}
            with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_SIGNATURE_INVALID"):
                self.approve(scope, bad)

        # Expired and early timestamps
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_EXPIRED_OR_EARLY"):
            self.approve(scope, env, at=self.now + 60_000)
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_EXPIRED_OR_EARLY"):
            self.approve(scope, env, at=self.now - 1_001)

        # Post-sign scope mutations (profile, funding, symbols, budget)
        for mutator in (
            lambda s: s["activation_plan"].__setitem__("timeout_profile", TIMEOUT_PROFILE),
            lambda s: s["funding"].__setitem__("documented_numeric_ip_weight", 2),
            lambda s: s["symbols"].append("DOGEUSDT"),
            lambda s: s["budget"].__setitem__("headroom_weight", 4),
        ):
            mutated = json.loads(json.dumps(scope))
            mutator(mutated)
            with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_BINDING_MISMATCH"):
                self.approve(mutated, env)

        # Duplicate JSON key and NaN in load_local_json
        dup = self.root / "dup.json"
        dup.write_text('{"a":1,"a":2}', encoding="ascii")
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_JSON_INVALID") as cm_dup:
            load_local_json(dup)
        self.assertIsInstance(cm_dup.exception.__cause__, SourceBlocked)
        self.assertEqual(cm_dup.exception.__cause__.code, "DUPLICATE_APPROVAL_FIELD")
        nan = self.root / "nan.json"
        nan.write_text('{"a":NaN}', encoding="ascii")
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_JSON_INVALID"):
            load_local_json(nan)

    def test_d6_altered_code_dependency_hash_and_release_mismatch_fail_closed(self):
        wheel_path = Path(os.environ["S3_CANDIDATE_WHEEL"])
        wheel_sha = os.environ["S3_CANDIDATE_WHEEL_SHA256"]
        clean_target = Path(os.environ["S3_CLEAN_TARGET"])

        # Positive verify_release
        verify_release(wheel_path, wheel_sha)
        # Wrong digest
        with self.assertRaisesRegex(SourceBlocked, "RELEASE_WHEEL_DIGEST_MISMATCH"):
            verify_release(wheel_path, "f" * 64)
        # Wrong release in approval claims
        with self.assertRaisesRegex(SourceBlocked, "ACTIVATION_BINDING_MISMATCH"):
            self.approve(self.v2_scope(), release="a" * 64)

        # Tampering 1 byte in candidate or any pinned dependency (B1, B2, B4) must fail verify_release!
        tamper_targets = [
            "quant_personal_live_public_b5/collection.py",
            "quant_personal_live_public_b5/ledger.py",
            "quant_personal_live_public_b5/stages.py",
            "quant_personal_public_b1/budget.py",
            "quant_personal_decision_b2/risk.py",
            "quant_personal_public_bridge_b4/admission.py",
        ]
        for rel in tamper_targets:
            with self.subTest(tampered=rel):
                copy_dir = self.root / f"tamper_{rel.replace('/', '_')}"
                shutil.copytree(clean_target, copy_dir)
                target_file = copy_dir / rel
                target_file.write_bytes(target_file.read_bytes() + b"\n# tamper\n")
                res = subprocess.run(
                    [
                        sys.executable, "-P", "-B", "-c",
                        "import sys; from pathlib import Path; "
                        "from quant_personal_live_public_b5.release import verify_release; "
                        "from quant_personal_public_b1.policy import SourceBlocked\n"
                        "try:\n"
                        "    verify_release(Path(sys.argv[1]), sys.argv[2])\n"
                        "except SourceBlocked as exc:\n"
                        "    print(exc.code); sys.exit(0)\n"
                        "sys.exit(1)\n",
                        str(wheel_path), wheel_sha,
                    ],
                    env={**os.environ, "PYTHONPATH": str(copy_dir)},
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(res.returncode, 0, res.stderr)
                self.assertEqual(res.stdout.strip(), "INSTALLED_RELEASE_MISMATCH")

    def test_d7_stale_clock_and_torn_durable_state_fail_closed(self):
        # 1. Monotonic clock regression fails closed.
        class RegressingClock(FixtureClock):
            def __init__(self):
                super().__init__()
                self.calls = 0

            def sample(self):
                self.calls += 1
                s = super().sample()
                if self.calls >= 8:
                    return Sample(s.wall_ms, s.mono_ms - 5_000)
                return s

        self.clock = RegressingClock()
        self.state = self.root / "clock_reg.sqlite"
        self.roots = replace(self.roots, state_path=self.state)
        active = self.v2_active()
        pub = collect(active, "bootstrap", FixtureWire(self.clock))
        self.assertIsNotNone(pub["stage"]["issue"])
        self.assertEqual(pub["stage"]["issue"]["category"], "CLOCK_BLOCKED")
        self.assertIsNone(pub["visible_venue_upper_ms"])

        # 2. Excessive venue serverTime offset (> 300s) fails closed.
        self.clock = FixtureClock()
        self.state = self.root / "clock_drift.sqlite"
        self.roots = replace(self.roots, state_path=self.state)
        active = self.v2_active()

        def bad_time(req, rep):
            if req.route == TIME:
                body = json.loads(rep.body)
                body["serverTime"] += 400_000
                return replace(rep, body=json.dumps(body).encode())
            return rep

        pub = collect(active, "bootstrap", FixtureWire(self.clock, mutate=bad_time))
        self.assertEqual(pub["stage"]["issue"]["code"], "VENUE_CLOCK_OFFSET_UNBOUNDED")
        self.assertEqual(pub["stage"]["issue"]["category"], "CLOCK_BLOCKED")
        self.assertIsNone(pub["visible_venue_upper_ms"])

        # 3. Torn/corrupted SQLite ledger fails closed on open_qa / read.
        torn = self.root / "torn.sqlite"
        torn.write_bytes(b"SQLite format 3\x00" + b"\xff" * 64)
        with self.assertRaises(sqlite3.DatabaseError):
            Ledger.open_qa(torn)

        # 4. Tampered publication digest / receipt digest fails closed.
        self.state = self.root / "tamper_pub.sqlite"
        self.roots = replace(self.roots, state_path=self.state)
        active = self.v2_active()
        pub = collect(active, "bootstrap", FixtureWire(self.clock))
        with sqlite3.connect(self.state) as db:
            db.execute("DROP TRIGGER lock_publications_UPDATE")
            db.execute("UPDATE publications SET sha256='0000'")
        with self.assertRaisesRegex(DecisionError, "PUBLICATION_DIGEST_MISMATCH"):
            Adapter(active.ledger).read("BTCUSDT", scan=pub["scan_id"])

    def test_d8_grants_exhausted_denied(self):
        # Complete nominal 39-request V2 run exhausts exact 39-request grant; any 40th attempt is denied.
        active = self.v2_active()
        pub = collect(active, "bootstrap", FixtureWire(self.clock))
        self.assertEqual(pub["stage"]["stats"]["reserved_requests"], 39)
        with self.assertRaisesRegex(SourceBlocked, "STAGE2_BUDGET_EXHAUSTED"):
            active.reserve("bootstrap", pub["scan_id"], 40, 0, RouteRequest(TIME, {}), self.clock.sample())


class GroupEFCompatibilityMixedAndDefaultDenyTests(V2BaseTest):
    def test_e1_v1_profile_legacy_semantics_preserved_and_v2_rejects_missing_or_legacy_for_s3(self):
        # 1. In candidate wheel, V1 profile still parses with market_retry_limit=1 (preserving frozen H2-A regressions).
        v1_scope = self.v2_scope(profile=TIMEOUT_PROFILE)
        v1_approved = self.approve(v1_scope)
        self.assertEqual(v1_approved.scope.stage_plan.market_retry_limit, 1)

        # 2. Missing / null / empty / unknown timeout_profile fails closed in StagePlan.parse!
        for bad_profile in (None, "", "UNKNOWN_PROFILE", "B5_SCAN60S_REQUEST1500MS_ZERO_RETRY_V1"):
            bad = self.v2_scope(profile=bad_profile)
            with self.assertRaisesRegex(SourceBlocked, "CANARY_SCOPE_INVALID"):
                self.approve(bad)
        missing = self.v2_scope()
        del missing["activation_plan"]["timeout_profile"]
        with self.assertRaisesRegex(SourceBlocked, "CANARY_SCOPE_INVALID"):
            self.approve(missing)

        # 3. Release-bound S3 V2 scope validator rejects legacy V1 profile, missing selector, and B5 V1 schema!
        with self.assertRaisesRegex(SourceBlocked, "S3_LEGACY_V1_PROFILE_DENIED"):
            validate_s3_v2_candidate_scope(v1_scope, self.roots)
        with self.assertRaisesRegex(SourceBlocked, "S3_TIMEOUT_PROFILE_MISSING"):
            validate_s3_v2_candidate_scope(missing, self.roots)
        b5_v1_scope = dict(self.v2_scope())
        b5_v1_scope["schema"] = SCOPE_SCHEMA
        del b5_v1_scope["activation_plan"]
        with self.assertRaisesRegex(SourceBlocked, "S3_V2_SCOPE_SCHEMA_REQUIRED"):
            validate_s3_v2_candidate_scope(b5_v1_scope, self.roots)

    def test_e2_mixed_old_wheel_new_scope_and_cross_wheel_install_denied(self):
        h2a_target = os.environ["S3_LEGACY_H2A_TARGET"]
        b5_target = os.environ["S3_LEGACY_B5_TARGET"]
        cand_wheel = os.environ["S3_CANDIDATE_WHEEL"]
        cand_sha = os.environ["S3_CANDIDATE_WHEEL_SHA256"]
        h2a_wheel = os.environ["S3_H2A_WHEEL"]
        h2a_sha = hashlib.sha256(Path(h2a_wheel).read_bytes()).hexdigest()

        # 1. Old H2-A post1 parser rejects new V2 scope (ZERO_RETRY_PROFILE).
        v2_raw_json = json.dumps(self.v2_scope())
        probe_h2a = """
import json, os, sys
from pathlib import Path
from quant_personal_live_public_b5.approval import Scope
from quant_personal_live_public_b5.trust import TrustRoots
from quant_personal_public_b1.policy import SourceBlocked
raw = json.loads(sys.argv[1])
roots = TrustRoots(b"1"*32, b"2"*32, Path(raw["storage"]["ledger"]), raw["network"]["egress_id"], os.geteuid(), "2"*64)
try:
    Scope.parse(raw, roots)
except SourceBlocked as exc:
    print(exc.code); sys.exit(0)
sys.exit(1)
"""
        r1 = subprocess.run(
            [sys.executable, "-P", "-B", "-c", probe_h2a, v2_raw_json],
            env={**os.environ, "PYTHONPATH": h2a_target},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r1.returncode, 0, r1.stderr)
        self.assertEqual(r1.stdout.strip(), "CANARY_SCOPE_INVALID")

        # 2. Old B5 0.8.0b5 parser rejects H2A_OWNER_PUBLIC_SCOPE_V2 completely.
        r2 = subprocess.run(
            [sys.executable, "-P", "-B", "-c", probe_h2a, v2_raw_json],
            env={**os.environ, "PYTHONPATH": b5_target},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r2.returncode, 0, r2.stderr)
        self.assertEqual(r2.stdout.strip(), "SCOPE_FIELDS_INVALID")

        # 3. Cross-wheel verify_release mismatch: V1 post1 wheel vs installed V2 post4 fails closed.
        with self.assertRaisesRegex(SourceBlocked, "INSTALLED_RELEASE_MISMATCH"):
            verify_release(Path(h2a_wheel), h2a_sha)

        # 4. Cross-wheel verify_release mismatch: V2 post4 wheel vs installed V1 post1 fails closed.
        probe_rel = """
import sys
from pathlib import Path
from quant_personal_live_public_b5.release import verify_release
from quant_personal_public_b1.policy import SourceBlocked
try:
    verify_release(Path(sys.argv[1]), sys.argv[2])
except SourceBlocked as exc:
    print(exc.code); sys.exit(0)
sys.exit(1)
"""
        r3 = subprocess.run(
            [sys.executable, "-P", "-B", "-c", probe_rel, cand_wheel, cand_sha],
            env={**os.environ, "PYTHONPATH": h2a_target},
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(r3.returncode, 0, r3.stderr)
        self.assertEqual(r3.stdout.strip(), "INSTALLED_RELEASE_MISMATCH")

    def test_f1_exact_three_file_diff_no_production_trust_roots_and_default_deny_under_audit_hook(self):
        audit, _ = audit_source_diff()
        self.assertTrue(audit["byte_exact_match_with_pinned_patch"])
        self.assertEqual(audit["changed_src_files"], ["collection.py", "ledger.py", "stages.py"])
        self.assertIsNone(trust._PROVISIONED)
        with self.assertRaisesRegex(SourceBlocked, DISABLED):
            trust.production_roots()

        script = """
import sys
from quant_personal_live_public_b5.cli import main
def check(event, args):
    if event.startswith('socket.') or event in ('open', 'sqlite3.connect', 'subprocess.Popen'):
        raise RuntimeError(event)
sys.addaudithook(check)
raise SystemExit(main(sys.argv[1:]))
"""
        for cmd in ("preflight", "live-once", "revoke"):
            env = {
                **os.environ,
                "B5_ENABLED": "1",
                "ACTIVATION_APPROVED": "1",
                "HTTPS_PROXY": "http://127.0.0.1:7",
                "BINANCE_API_KEY": "fake",
            }
            res = subprocess.run(
                [sys.executable, "-c", script, cmd, "--wheel", "/nonexistent", "--scope", "/nonexistent", "--activation", "/nonexistent"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual((res.returncode, res.stdout, res.stderr.strip()), (3, "", DISABLED))


if __name__ == "__main__":
    unittest.main()
