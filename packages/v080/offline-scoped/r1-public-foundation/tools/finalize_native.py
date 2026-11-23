"""Assemble Program E worker evidence, preserving failures and qualification gates."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / name).read_text())


def sha(name):
    return hashlib.sha256((ROOT / name).read_bytes()).hexdigest()


def write(name, obj):
    (ROOT / name).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def main():
    cases = ET.parse(ROOT / "audit/release_final.xml").getroot().findall(".//testcase")
    counts = {"PASS": 0, "FAIL": 0, "ERROR": 0, "SKIP": 0}
    for c in cases:
        state = (
            "ERROR"
            if c.find("error") is not None
            else "FAIL"
            if c.find("failure") is not None
            else "SKIP"
            if c.find("skipped") is not None
            else "PASS"
        )
        counts[state] += 1
    assert counts == {"PASS": 451, "FAIL": 0, "ERROR": 0, "SKIP": 0}, counts
    new = [c for c in cases if ".native." in c.attrib["classname"]]
    assert len(new) == 53
    inputs = read("audit/original_inputs.json")
    failures = []
    for row in inputs["files"]:
        p = ROOT.parent / row["path"]
        if (
            not p.is_file()
            or hashlib.sha256(p.read_bytes()).hexdigest() != row["sha256"]
            or p.stat().st_mtime_ns != row["mtime_ns"]
        ):
            failures.append(row["path"])
    for path, expected in inputs["session03_metadata"].items():
        p = ROOT.parent / path
        s = p.stat()
        if [s.st_size, s.st_mtime_ns, s.st_ctime_ns, s.st_mode, s.st_ino] != expected:
            failures.append(path)
    assert not failures, failures
    demo = read("E3_END_TO_END_SYNTHETIC_NETWORK_ACCEPTANCE.json")
    assert (
        demo["status"] == "PASS" and demo["completed_wire_candles"] == 542 and demo["local_sessions"] == 194
    )
    wheel = "release/wheelhouse/quant_advisory_platform-0.7.0.post1-py3-none-any.whl"
    codehash = read("audit/final_binding.json")["source_sha256"]
    flags = {
        "IMPLEMENTED": True,
        "INTEGRATED": True,
        "OFFLINE_TESTED": True,
        "RELEASE_CANDIDATE_READY": True,
        "NATIVE_ADMISSION_READY": False,
        "SOURCE_QUALIFIED": False,
        "SHADOW_QUALIFIED": False,
        "ECONOMICALLY_VALIDATED": False,
        "account": "ACCOUNT_UNKNOWN/ACCOUNT_VETO",
        "S2": "RESEARCH_ONLY_DISABLED",
        "S3": "RESEARCH_ONLY_DISABLED",
    }
    write(
        "E0_BASELINE_AND_INTERFACE_FREEZE.json",
        {
            "status": "VERIFIED_AND_FROZEN_WORKER_EVIDENCE",
            "D_Controller_decision": "ACCEPT_OFFLINE_RELEASE_CANDIDATE_SCOPED",
            "D_code_manifest_sha256": "7e199645ec32768ee94d7594dfd4b44ee24e3262ae30ba874cdd386484700207",
            "D_report_manifest_sha256": "30f9b372393b91eac498f3899d6b78d16bf93e60ab9ce25ebae5c0d83119eaa9",
            "D_947_readonly_verification": "PASS_BEFORE_AND_AFTER",
            "original_inputs": "audit/original_inputs.json",
            "original_hash_records": len(inputs["files"]),
            "Session03_metadata_records": len(inputs["session03_metadata"]),
            "Session03_seal_sha256": inputs["session03_seal_sha256"],
            "historical_metadata_compatibility": "Historical sealed file sizes/mtimes verified; current-host inode/ctime baselined separately, payloads unopened",
            "reuse": {
                "kline_parser": "Accepted D qualified_source.decode_binance_kline directly reused",
                "receipt_hashing": "Original SHA256/canonical JSON and native quarantine schema retained; no native qualification string accepted",
                "closed_candle_validator": "Accepted D closed-bar semantics reused through explicit synthetic network adapter",
                "Ed25519": "Original canonical verifier via D owner_verifier; AST equivalence test retained",
                "Source_S1_Shadow_HTML_C": "Accepted D modules remain callable and regression-tested",
                "new_native_journal": "FULL-sync SQLite reservation/event/frame/normalized-ack ledger; incompatible synthetic journal is not overlaid",
                "clock": "Original conservative native-minus-monotonic union and sticky wall epoch constraints retained in actual I/O adapter; new E proof schema is not claimed as historical qualification",
                "transport": "Standard ssl/socket + installed websockets Sans-I/O; narrower CONNECT-only control avoids original direct/SOCKS fallback and private HTTP internals",
            },
            "contract": {
                "schema": "E_CANDLE_GRANT_V1",
                "venue": "BINANCE_USDM_FUTURES",
                "WS": "wss://fstream.binance.com/market/stream",
                "clock": "https://fapi.binance.com/fapi/v1/time",
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
                "timeframes": ["1H optional", "4H mandatory", "1D mandatory"],
                "source_sha256": codehash,
                "executable_sha256": sha(wheel),
                "config_binding": "Canonical complete strict E_CANDLE_CONFIG_V1, including numeric proxy, exact six mandatory or all nine streams and non-weakenable safety constants",
                "signed_fields": [
                    "venue/endpoints/streams",
                    "source/config/wheel/rights hashes",
                    "Owner and independent auditor identities",
                    "issued/start/end UTC milliseconds",
                    "single-use session and unused output",
                    "requests/messages/outgoing/storage/retention budgets",
                ],
                "lineage": [
                    "durable full signed authorization",
                    "hash-chained raw observations",
                    "immutable preparation",
                    "post-fsync normalized availability ack",
                    "terminal reason and closure",
                    "external independent capture audit",
                ],
            },
            "source_qualified": False,
        },
    )
    write(
        "E1_NATIVE_CAPTURE_IMPLEMENTATION.json",
        {
            "status": "IMPLEMENTED_OFFLINE_TESTED_DEFAULT_DENY",
            "entrypoints": [
                "quant-native doctor",
                "quant-native capture",
                "quant-native inspect",
                "quant-native recover",
                "quant-native audit-challenge",
                "quant-native verify-audit",
            ],
            "callable": "btc_quant_agent.platform.native.runtime.run_native",
            "modules": ["contract", "journal", "clock", "transport", "runtime", "bridge", "audit", "cli"],
            "native_entry": "Frozen installed independent roots and exact signed Owner/auditor capability required before any socket; synthetic capabilities are restricted to loopback",
            "reservation": "Global cross-phase lease + per-registry lease; FULL-sync unique grant/session/output and singleton active reservation before transport; consumed after attempted capture, never retried",
            "transport": "Finite foreground CONNECT-only original-target TLS/hostname/SNI; numeric proxy only, no DNS retry/fallback, WS query subscriptions only, no private streams",
            "wire_validation": [
                "exact combined wrapper/stream",
                "outer and inner symbols",
                "interval",
                "e=kline",
                "x strictly true for completed admission",
                "UTC open/end alignment",
                "T+1 exclusive end",
                "strict numeric OHLCV",
                "actual receive vs available/durable times",
                "duplicate suppression and correction stop",
            ],
            "time_and_control": "Hard open UTC window <=24h; two independent startup clock calls; refresh every120s; bounded automatic pong/client heartbeat; 10/s outgoing control guard; no reconnect",
            "durability": "Raw admission and budget debit atomic; normalized receipt exposed only after durable preparation and ack; immutable event chain and raw/normalized materializations verified",
            "request_counter_semantics": "Conservative attempted CONNECT charges, not evidence of exchange acceptance; local synthetic tests make zero real native market requests",
            "runtime_limits": [
                "fragmented/binary WS frames fail closed; never normalized",
                "retention expiry requires Owner-approved purge and blocks subsequent capture; no unattended deletion service",
            ],
            "native_market_requests": 0,
            "qualification": flags,
        },
    )
    write(
        "E2_RUNTIME_SAFETY_AND_RECOVERY.json",
        {
            "status": "OFFLINE_SAFETY_TESTS_PASS_NATIVE_AUTHORITY_BLOCKED",
            "new_unique_tests": len(new),
            "JUnit": "audit/release_final.xml",
            "JUnit_sha256": sha("audit/release_final.xml"),
            "tests": [c.attrib["name"] for c in new],
            "crash_boundaries": [
                "before reservation: no network",
                "after reservation: consumed and CRASHED",
                "after durable raw write: frame retained, no automatic restart",
            ],
            "enforcement": {
                "queue_high": 96,
                "queue_hard": 128,
                "requests": "charged durably before socket attempts",
                "incoming": "charged with immutable raw frame",
                "storage": "physical SQLite size plus conservative transaction/terminal reserves and actual free disk checked",
                "failed_writes": "exception before/after commit preserves transaction outcome; no receipt from unacknowledged preparation",
                "cleanup": "bounded socket I/O, signal handlers, close every registered socket, preserve FAILED_CLOSURE on close or terminal persistence failure",
            },
            "zero_silent_admitted_frame_loss": "All admitted rows are durably settled or explicitly retained unresolved after crash; no dropped row is claimed completed",
            "no_unauthorized_reconnect": True,
            "native_market_requests": 0,
        },
    )
    perf = ROOT / "artifacts/native_performance/0/registry.sqlite"
    db = sqlite3.connect(perf)
    stopped = json.loads(db.execute("SELECT body FROM events WHERE kind='TERMINAL'").fetchone()[0])
    perf_counts = db.execute("SELECT incoming FROM sessions").fetchone()[0]
    completed = db.execute("SELECT count(*) FROM receipts").fetchone()[0]
    db.close()
    write(
        "audit/native_performance.json",
        {
            "status": "STOPPED_AS_REQUIRED_CLOCK_UNQUALIFIED",
            "predeclaration": "audit/low_rate_contract.json",
            "contract_sha256": sha("audit/low_rate_contract.json"),
            "terminal": stopped,
            "admitted_frames_before_stop": perf_counts,
            "completed_before_stop": completed,
            "cause": "System wall/monotonic comparison exceeded retained50ms threshold; root cause NOT_ESTABLISHED",
            "performance_PASS": False,
            "no_threshold_relaxation": True,
            "prior_failed_assertion_log": "audit/native_benchmark.log",
            "M1B_150_per_second": "PARTIAL_UNCHANGED_NOT_REPLACED",
            "native_market_requests": 0,
        },
    )
    write(
        "E2_CLOCK_TLS_ACCEPTANCE.json",
        {
            "status": "LOCAL_OFFLINE_MECHANISM_TESTED_REAL_NATIVE_UNQUALIFIED",
            "Controller_acceptance": "PENDING",
            "local_TLS": "Actual loopback HTTP CONNECT and TLS sockets; fabricated certificate CA with original-target hostname/SNI; certificate rejection exercised",
            "sandbox": "Default sandbox denies AF_INET; user-authorized local-only tests ran with sandbox escalation, all external connects denied by test runner",
            "clock": "Actual I/O for paired time probes, conservative envelope <=100ms, age<=300s, refresh120s, sticky conservative50ms discontinuity",
            "observed_host_clock_issue": read("audit/native_performance.json"),
            "live_venue_proxy_TLS": "UNVERIFIED_NOT_RUN",
            "native_UTC_probes": "NOT_RUN",
            "synthetic_clock_proofs": "QA only; not independent native proof",
            "native_admission_ready": False,
        },
    )
    write(
        "E3_NATIVE_TO_PRODUCT_INTEGRATION.json",
        {
            "status": "INTEGRATED_OFFLINE_SYNTHETIC_NETWORK_WITH_NATIVE_BLOCKED_BOUNDARY",
            "adapter": "native.bridge.replay_synthetic_session validates immutable native-wire receipts and permits only SYNTHETIC_NETWORK conversion to D synthetic source",
            "genuine_native": "Immutable observations retained NATIVE_UNQUALIFIED; Source inspection and existing HTML display SOURCE_BLOCKED",
            "source_boundaries": [
                "parser-only quarantine never imported",
                "partial/rejected/unacknowledged frames ineligible",
                "clock proof separate from Source qualification",
                "warmup/latest/gaps/staleness computed as-of durable receipt times",
                "optional hourly can be omitted by exact signed six-stream policy",
            ],
            "causal_availability": "Actual transport receive sample preserved; post-fsync preparation time used for normalization; no timestamp rebasing in D adapter",
            "D_native_schema_limit": "Accepted D RCDecision/export are synthetic-only. Genuine native positive-S1 promotion requires separately accepted versioned product/evaluator admission; no relabeling or automatic promotion is implemented",
            "S1_and_UI": "Existing D S1, persistence, HTML document/table renderer and C method reused; no new strategy or frontend",
            "regression": "All398 inherited D tests executed separately identifiable in451 unique final tests",
            "demo_receipt": "E3_END_TO_END_SYNTHETIC_NETWORK_ACCEPTANCE.json",
            "source_qualified": False,
        },
    )
    sources = {
        "connect": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Connect",
        "routing": "https://developers.binance.com/en/docs/products/derivatives-trading-usds-futures/websocket-market-streams/Important-WebSocket-Change-Notice",
        "wire": "https://developers.binance.info/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/ws-streams/market",
        "clock": "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data",
        "terms": "https://www.binance.com/en/terms",
    }
    write(
        "E4_SOURCE_RIGHTS_VERIFICATION.json",
        {
            "status": "RIGHTS_UNVERIFIED",
            "checked_UTC_date": "2026-11-07",
            "official_documentation": sources,
            "verified_technical_scope": "Market route for kline streams, combined wrapper, e/E/s/k fields and explicit completed flag; public server-time endpoint separately bound in grant",
            "documented_limits": {
                "WS_lifetime_hours": 24,
                "server_ping_minutes": 3,
                "server_pong_timeout_minutes": 10,
                "incoming_control_messages_per_second": 10,
                "max_streams": 1024,
            },
            "applicable_entity": "UNKNOWN",
            "Owner_region_and_host_eligibility": "UNKNOWN",
            "personal_noncommercial_research": "UNVERIFIED",
            "prospective_collection": "UNVERIFIED_NO_GRANT",
            "cache_retention": "UNVERIFIED_NO_GRANT",
            "retrospective_REST_warmup": "NOT_AUTHORIZED",
            "rights_rule": "Technical public API documentation does not establish collection or retention rights. No external market request made.",
            "Session04_BBO_grant_covers_candles": False,
            "native_market_requests": 0,
        },
    )
    write(
        "E4_INDEPENDENT_SIGNER_AND_TRUST.json",
        {
            "status": "NATIVE_BLOCKED_AUTHORITY",
            "original_verifier": "Original canonical signed_bytes/verify_signature via accepted D; AST equivalence regression passed",
            "installed_E_roots": {"owner_keys": 0, "auditor_keys": 0, "rights_root": None},
            "historical_original_public_maps": {"session02": 1, "session03": 1, "session04": 0},
            "historical_scope": "Existing historical Session02/03 public identities are not an E candle grant or independent current capture audit; no historical trust file modified",
            "genuine_Owner_identity": "NOT_PROVISIONED_FOR_E",
            "genuine_auditor_identity": "NOT_PROVISIONED_FOR_E",
            "private_Owner_keys_read_or_generated": 0,
            "QA_keys": "Fabricated ephemeral local test keys only, never installed as native roots",
            "final_executable_sha256": sha(wheel),
            "final_source_sha256": codehash,
            "signature_order": "Independently provision public roots/rights/config, freeze build, then independent Owner signs exact final hashes and future bounded window",
            "capture_audit": "Detached E_CAPTURE_AUDIT_V1 challenge and signature verifier bind exact session/grant/terminal/prefix; genuine audit remains absent",
            "actual_signed_UTC_window": None,
        },
    )
    blockers = [
        "RIGHTS_UNVERIFIED: entity/region/research/prospective/cache/retention",
        "Independent current Owner and auditor E roots plus final-hash exact signed grant absent",
        "No current signed UTC window or unused genuinely approved output",
        "Actual venue CONNECT/TLS and native independent time probes not run",
        "Observed local wall/monotonic discontinuity in synthetic performance measurement; host clock requires independent qualification",
        "Native warmup/availability/Shadow outcomes/economic samples absent",
        "Genuine native positive-product schema admission requires separate Controller acceptance; synthetic D model cannot be relabeled",
    ]
    write(
        "E4_NATIVE_ADMISSION_DECISION.json",
        {
            "status": "NATIVE_BLOCKED_AUTHORITY",
            "admission_ready": False,
            "blockers": blockers,
            "engineering_runtime_implemented": True,
            "clock_guard_weakened": False,
            "native_market_requests": 0,
        },
    )
    for name in ("E5_NATIVE_DIAGNOSTIC_STATUS.json", "E5_NATIVE_EVIDENCE_ACCEPTANCE.json"):
        write(
            name,
            {
                "status": "NOT_RUN",
                "reason": "NATIVE_BLOCKED_AUTHORITY",
                "genuine_window": None,
                "native_market_requests": 0,
                "native_connections": 0,
                "completed_native_candles": 0,
                "source_qualified": False,
                "shadow_qualified": False,
                "economic_validation": False,
                "Controller_acceptance": "PENDING_NOT_SELF_ACCEPTED",
            },
        )
    write(
        "E6_PROSPECTIVE_SOURCE_ACCUMULATION_PLAN.json",
        {
            "status": "PREPARED_NOT_STARTED_NON_AUTHORIZING",
            "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            "required_each_symbol": {
                "1D": 60,
                "4H": 60,
                "1H": "optional; omit from signed scope unless confirmation coverage is independently adequate",
            },
            "retrospective_REST": "NOT_AUTHORIZED",
            "prospective_time_without_gaps": "Approximately60–61 days for60 full daily bars; no future session claimed run",
            "manual_sequence": [
                "Independent rights and final-hash Owner/auditor ceremony",
                "One signed foreground window around each required4H UTC close",
                "Verify terminal and independent capture audit; inspect raw/normalized chain",
                "Review advisory once or twice daily from qualified as-of prefix",
                "Obtain a new separate bounded grant for every subsequent window; never renew/reconnect automatically",
            ],
            "practical_candidate": {
                "UTC_closes": ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"],
                "capture_window_seconds": 20,
                "signed_streams": "Six mandatory4H/1D series; optional1H needs separate adequate schedule",
                "manual_capture_starts_per_day": 6,
                "advisory_reviews_per_day": "1–2",
                "proposed_budgets_NOT_AUTHORITY": {
                    "messages_per_session": 2000,
                    "requests": 5,
                    "outgoing_controls": 20,
                    "storage_bytes_max": 1073741824,
                    "retention_seconds_max": 7776000,
                },
                "traffic_note": "Partial250ms updates, controls and probes count against budgets. Size whole retained registry before signing; if growth approaches cap stop and obtain permitted rotation preserving consumed-session identities, never silently delete evidence.",
            },
            "gap_protocol": "Missing/late/revised required bars stop eligibility. Do not fabricate or use unauthorized warmup. Independently authorize backfill or wait for new contiguous full prefix.",
            "stage_matrix": {
                stage: "NOT_ESTABLISHED"
                for stage in [
                    "native_transport",
                    "source_correctness",
                    "independent_clock",
                    "warmup",
                    "seven_day_availability",
                    "genuine_Shadow_lifecycle",
                    "economic_support",
                ]
            },
            "M1B_150_per_second": "PARTIAL_UNCHANGED",
            "automatic_Program_F_dispatch": False,
        },
    )
    write(
        "E7_TEST_MATRIX.json",
        {
            "status": "OFFLINE_REGRESSION_PASS_NATIVE_MEASUREMENT_CLOCK_BLOCKED",
            "final_unique_counts": counts,
            "final_JUnit": "audit/release_final.xml",
            "final_JUnit_sha256": sha("audit/release_final.xml"),
            "inherited_D_executed": 398,
            "new_E_unique": 53,
            "inherited_D_original_evidence": "audit/D_accepted_tests.xml",
            "historical_counts_additive": False,
            "prior_failures_preserved": True,
            "gates": {
                "clean_offline_install": "PASS",
                "pip_check": "PASS",
                "installed_quant_and_quant_native": "PASS",
                "new_runtime_local_HTTP_WS_TLS": "PASS",
                "fault_injection_and_crashes": "PASS",
                "full_Source_S1_Shadow_HTML_C": "PASS_194_LOCAL_SESSIONS_542_COMPLETED_SYNTHETIC_CANDLES",
                "Ruff": "PASS",
                "compile": "PASS",
                "scoped_mypy": "PASS_25_SOURCE_FILES",
                "wheel_reproducible": "PASS_BYTE_IDENTICAL_TWICE",
                "predeclared_native_low_rate_measurement": "STOPPED_AS_REQUIRED_CLOCK_UNQUALIFIED_NOT_PERFORMANCE_PASS",
                "genuine_native_diagnostic": "NOT_RUN",
                "Windows_native": "NOT_RUN",
            },
            "source_qualified": False,
            "native_market_requests": 0,
        },
    )
    write(
        "E7_PRESERVATION_AFTER.json",
        {
            "status": "PASS",
            "original_hash_records": len(inputs["files"]),
            "sealed_Session03_metadata": len(inputs["session03_metadata"]),
            "Session03_seal_sha256": inputs["session03_seal_sha256"],
            "failures": failures,
            "A_B_C_D_Source_LONG": "READ_ONLY_PRESERVED",
            "protected_payloads_and_FINAL_HOLDOUT_reads": 0,
            "native_market_requests": 0,
            "orders_trades_alerts_account_calls": 0,
            "new_PRIMARY": 0,
        },
    )
    write(
        "E7_INTEGRATED_ACCEPTANCE.json",
        {
            "status": "E_NATIVE_RUNTIME_OFFLINE_READY_AUTHORITY_BLOCKED",
            "worker_recommendation_only": True,
            "Controller_acceptance": "PENDING",
            "phases": {
                "E0": "COMPLETED_VERIFIED_INTERFACE_FROZEN",
                "E1": "IMPLEMENTED_DEFAULT_DENY_FINITE_RUNTIME",
                "E2": "LOCAL_OFFLINE_ENFORCEMENT_AND_FAULTS_TESTED_HOST_CLOCK_BLOCK_PRESERVED",
                "E3": "SYNTHETIC_NETWORK_FULL_PRODUCT_PASS_NATIVE_PRODUCT_BLOCKED",
                "E4": "RIGHTS_AND_INDEPENDENT_SIGNER_BLOCKED_ACTION_PACKET_COMPLETE",
                "E5": "NOT_RUN_NATIVE_BLOCKED_AUTHORITY",
                "E6": "PREPARED_MANUAL_FINITE_PLAN_NOT_STARTED",
                "E7": "REPRODUCIBLE_LOCAL_RELEASE_AND_CONTROLLER_HANDOFF",
            },
            "qualification_dimensions": flags,
            "tests": counts,
            "new_E_unique_tests": 53,
            "actual_native_market_requests": 0,
            "genuine_signed_UTC_window": None,
            "source_hash": codehash,
            "wheel_sha256": sha(wheel),
            "scientific_decision": "INSUFFICIENT_SUPPORT",
            "blockers": blockers,
            "subagents": 0,
            "new_PRIMARY": 0,
            "publication": "PUBLIC_SAFE_REPRODUCIBLE_CODE_PACKET_ONLY_NO_REMOTE_WRITE",
            "next_Controller_decision": "Independently accept or reject scoped offline runtime; keep native blocked and require genuine rights/signing plus independently qualified host clock before considering one signed diagnostic. No automatic Program F dispatch.",
        },
    )
    (
        ROOT / "E7_IMPLEMENTATION_FINAL.md"
    ).write_text("""# Program E engineering handoff — Controller acceptance pending

Recommendation: E_NATIVE_RUNTIME_OFFLINE_READY_AUTHORITY_BLOCKED.
E0–E3 implementation and offline integration complete; E4 independent authority
and rights remain blocked; E5 NOT_RUN; E6 manual plan prepared; E7 release handed off.

Actual package: quant-advisory-platform0.7.0.post1. Existing quant remains available;
quant-native exposes doctor/capture/inspect/recover/audit-challenge/verify-audit.
Runtime implements durable single-use reservation before I/O, shared/per-registry
leases, CONNECT-only original-target TLS/SNI, strict completed-kline parsing,
actual clock startup/refresh, queue/budget/disk guards, immutable raw/normalized
lineage, terminal cleanup and external capture-auditor verification. Default
independent trust is empty. All actual native entrypoints fail before connecting.

Final clean regression:451 PASS,0 FAIL/ERROR/SKIP.398 inherited D tests and53 new E
tests are uniquely identified; historical D evidence retained separately.
Actual loopback HTTP CONNECT/TLS/WS tests and crash/fault injection pass.
Ruff, compile and scoped mypy25 source files pass; repeated wheels are byte
identical. Exact hashes and public materialization are in audit manifests and
E7_REPRODUCIBLE_RELEASE.json. Native Windows NOT_RUN.

Final synthetic network replay:194 finite local sessions,542 completed wire
candles, original causal receipt times preserved. BTC ARMED; ETH/SOL NO_SETUP;
original plan survives later TARGET_FIRST observation and restart. Actual
export consumed by C remains MISSING_COVERAGE/INSUFFICIENT_SUPPORT, zero genuine
economic samples. See artifacts/network_release/product/latest.html and
artifacts/network_release/evaluation/scientific_report.md. These are fabricated
network QA only. Genuine native observations stay separate, SOURCE_BLOCKED;
accepted D's synthetic-only decision/export cannot be relabeled as native.

The predeclared low-rate system-clock measurement stopped on retained50ms wall/
monotonic discontinuity and preserved FAILED_CLOSURE. Its cause is not established;
this is not a performance pass. No threshold was weakened. Current host/native
clock qualification remains blocked; M1B150/s remains PARTIAL unchanged.

Official route/schema/time documentation checked; entity/region/research/cache/
retention rights remain RIGHTS_UNVERIFIED. E Owner/auditor identities and genuine
signed windows are absent. Historical Session02/03 public keys are not candle
permission. Original trust and all scoped inputs preserved; Session03 payloads
unopened and306 sealed metadata entries verified. Actual real market requests,
account calls, orders, alerts, PRIMARY and holdout reads are zero.

Source/Shadow/economic qualifications FALSE; Account UNKNOWN/VETO; S2/S3 disabled.
See README_NATIVE_OPERATOR.md, E4's NON_AUTHORIZING Owner ceremony and E6's manual
accumulation plan. Code-only public packet is prepared; PR12 is not merged or
updated, no deployment or Program F worker started. Controller should independently
review the offline runtime and retain native block until genuine rights/signatures
and a separately qualified host clock allow consideration of one finite diagnostic.
""")
    print(
        json.dumps(
            {
                "status": "E_NATIVE_RUNTIME_OFFLINE_READY_AUTHORITY_BLOCKED",
                "tests": counts,
                "new_E": len(new),
                "preserved": len(inputs["files"]),
                "Session03_metadata": len(inputs["session03_metadata"]),
            }
        )
    )


if __name__ == "__main__":
    main()
