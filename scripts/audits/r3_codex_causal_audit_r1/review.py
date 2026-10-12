"""Offline, exact-Git-blob accounting probes. All inputs are SYNTHETIC_ONLY.

Passing a defect probe means its observation matched the frozen baseline; it
does not mean the application invariant passed. No xfail, skip, or transport.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

BASE = "632d2e37f28b8c3efbd2b818ecdb74783f0df238"
B_SHA = "51cdd4e17503fbd18ad22aaeeaba3580f5efacf8"
C_SHA = "91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b"
BRANCH = "feature/v06-bline-codex-r3-independent-causal-audit-r1"
NS = "r3_codex_causal_audit_r1"
ROOT = Path(__file__).resolve().parents[3]
TEST_NAMES = (
    "c_composite_g1", "depth_ladder_l2", "pit_clock_mark_last",
    "settled_funding_ledger", "stress_and_security",
)
R2_FILES = [
    f"scripts/integration/market_event_bridge_r2/{n}.py"
    for n in ("__init__", "bridge_engine", "funding_adapter", "mark_aggregator",
              "c_composite_bar", "book_ladder")
] + [
    f"scripts/market_data/forward_public_feed_r1/{n}.py"
    for n in ("__init__", "order_book", "contracts")
] + [f"tests/test_v06_market_event_bridge_r2_{n}.py" for n in TEST_NAMES]
B_FILES = [f"scripts/strategy_research/forward_shadow_research_r1/{n}.py"
           for n in ("__init__", "adapter", "contract", "execution", "account",
                     "registry", "signals")]
C_FILES = ["scripts/g1g3_offline_ports_r1/__init__.py",
           "scripts/g1g3_offline_ports_r1/market_pit_port.py",
           "scripts/g1_offline_preview_r1/model.py",
           "scripts/g1_offline_preview_r1/fixtures.py"]
EXPECTED_BUGS = {
    "delay_200", "delay_30000", "delay_10800000", "correct_c_receipt",
    "mark_missing", "mark_stale", "mark_after_settlement", "mark_route_switch",
    "mark_infinity", "mark_nan", "dedupe_equivalent_rate", "missing_rate",
    "legacy_imports",
}
CASES = [
    "delay_200", "delay_30000", "delay_10800000", "correct_c_receipt",
    "mark_missing", "mark_stale", "mark_after_settlement", "mark_route_switch",
    "mark_infinity", "mark_nan", "decimal_long_positive", "decimal_short_positive",
    "decimal_long_negative", "decimal_short_negative", "decimal_rounding",
    "dedupe_identical", "dedupe_equivalent_rate", "missing_rate",
    "pinned_import_identity", "legacy_imports",
]


def git(*args: str) -> bytes:
    p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True)
    if p.returncode:
        raise RuntimeError("DEPENDENCY_UNAVAILABLE: git " + " ".join(args))
    return p.stdout


def prepare_sources(destination: Path) -> list[dict]:
    """Stage only named public code blobs, never a working-tree fallback."""
    manifest = []
    for sha, paths in ((BASE, R2_FILES), (B_SHA, B_FILES), (C_SHA, C_FILES)):
        resolved = git("rev-parse", f"{sha}^{{commit}}").decode().strip()
        if resolved != sha:
            raise RuntimeError("PINNED_SOURCE_IDENTITY_MISMATCH")
        for path in paths:
            raw = git("show", f"{sha}:{path}")
            output = destination / path
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(raw)
            manifest.append({"revision": sha, "path": path,
                             "sha256": hashlib.sha256(raw).hexdigest()})
    (destination / "source_manifest.json").write_text(json.dumps(manifest))
    return manifest


def run_case(stage: Path, case: str) -> dict:
    p = subprocess.run(
        [sys.executable, "-I", str(Path(__file__).resolve()), "--worker", str(stage), case],
        capture_output=True, text=True, timeout=30,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if p.returncode:
        raise RuntimeError(f"PROBE_EXECUTION_FAILED {case}: {p.stderr[-2000:]}")
    return json.loads(p.stdout)


def verify_origin(stage: Path, file: Path, by_path: dict) -> dict:
    try:
        relative = file.resolve().relative_to(stage.resolve()).as_posix()
    except ValueError as exc:
        raise RuntimeError("PINNED_IMPORT_ORIGIN_MISMATCH") from exc
    if relative not in by_path:
        raise RuntimeError("PINNED_IMPORT_ORIGIN_MISMATCH")
    source = by_path[relative]
    digest = hashlib.sha256(file.read_bytes()).hexdigest()
    if digest != source["sha256"]:
        raise RuntimeError("PINNED_IMPORT_HASH_MISMATCH")
    return {"path": relative, "revision": source["revision"], "sha256": digest}


def assert_baseline_observation(result: dict) -> None:
    """Require the specific witness, not merely any unsuccessful invariant."""
    case = result["case_id"]
    observed = result["observed"]
    assert result["BUG_REPRODUCED"] == (case in EXPECTED_BUGS), result
    assert result["INVARIANT_PASSED"] == (case not in EXPECTED_BUGS), result
    if case.startswith("delay_"):
        delay = int(case.split("_")[1])
        assert observed["c_status"] == "ACCEPTED", result
        assert observed["b_ingress"] == observed["b_accounting_receive_time"] == observed["entry_known_at"] == 180_000 + delay, result
        assert observed["c_ingress"] == observed["c_available"] == observed["c_feature_known"] == 180_000, result
        assert observed["earlier_decision_rejected"] is False, result
    elif case == "correct_c_receipt":
        assert observed["corrected_receipt_envelope"] == "FUNDING_PIT_INVALID", result
    elif case == "mark_missing":
        assert observed["entry"] is None and observed["bridge_status"] == "INGESTED", result
        assert not observed["dispatched_b"] and not observed["dispatched_c"], result
    elif case in ("mark_stale", "mark_after_settlement", "mark_route_switch"):
        assert observed["entry"]["quality"] == "VERIFIED", result
        assert observed["dispatched_b"] and observed["dispatched_c"], result
        assert observed["cash_long_1btc"] == ("-9.00000000" if case == "mark_after_settlement" else "-6.00000000"), result
        assert observed["entry"]["parent_event_sha256"] == [], result
        if case == "mark_route_switch":
            assert observed["route_epoch"] == "route-epoch-1" and observed["entry"]["route_epoch"] == "route-epoch-0", result
    elif case == "mark_infinity":
        assert observed["uncaught_exception"] == "ValueError" and observed["journal_entries"] == 1, result
        assert observed["journal"][0]["mark_price"] == "Infinity" and observed["journal"][0]["quality"] == "VERIFIED", result
        assert observed["b_cash_callbacks"] == observed["c_envelopes_received"] == 0, result
    elif case == "mark_nan":
        assert observed["uncaught_exception"] == "InvalidOperation" and observed["journal_entries"] == 0, result
    elif case == "dedupe_equivalent_rate":
        assert observed["journal_entries"] == 2 and observed["sum_long_cash"] == "-12.00000000", result
    elif case == "missing_rate":
        assert observed == {"accepted": True, "rate": "0.0", "quality": "VERIFIED", "cash": "-0E-8"}, result
    elif case == "legacy_imports":
        assert observed["collection_permission_errors"] == 5, result
        assert all(x["absolute_path_lines"] for x in observed["modules"]), result


def worker(stage: Path, case: str) -> dict:
    # -I subprocess prevents prior scripts.* imports/sys.path from deciding origin.
    sys.path.insert(0, str(stage))
    sys.dont_write_bytecode = True
    import copy
    from decimal import Decimal, InvalidOperation
    import importlib
    from unittest.mock import patch

    # Any unexpected network attempt fails the probe, even if introduced later.
    import socket
    def denied(*args, **kwargs):
        raise AssertionError("OFFLINE_NETWORK_FORBIDDEN")
    socket.socket.connect = denied
    socket.create_connection = denied
    socket.getaddrinfo = denied

    bridge_mod = importlib.import_module("scripts.integration.market_event_bridge_r2.bridge_engine")
    fund_mod = importlib.import_module("scripts.integration.market_event_bridge_r2.funding_adapter")
    b_mod = importlib.import_module("scripts.strategy_research.forward_shadow_research_r1.adapter")
    c_mod = importlib.import_module("scripts.g1g3_offline_ports_r1.market_pit_port")
    manifests = json.loads((stage / "source_manifest.json").read_text())
    by_path = {x["path"]: x for x in manifests}
    origins = []
    for name, module in list(sys.modules.items()):
        if name.startswith("scripts.") and getattr(module, "__file__", None):
            file = Path(module.__file__).resolve()
            origins.append({"module": name, **verify_origin(stage, file, by_path)})

    T = 180_000  # invented milliseconds, not a real market record
    rate_record = {"symbol": "BTCUSDT", "fundingRate": "0.0001", "fundingTime": T}
    class EngineSink:
        def __init__(self):
            self.receipts = []
        def on_funding_settled(self, funding, received):
            self.receipts.append((funding, received))
    class CRecorder:
        def __init__(self):
            self.port = c_mod.MarketPitPort()
            self.envelopes = []
            self.results = []
        def ingest_envelope(self, env):
            self.envelopes.append(copy.deepcopy(env))
            result = self.port.ingest_envelope(env)
            self.results.append(result)
            return result
    sink = EngineSink()
    b_adapter = b_mod.PublicFeedAdapter(sink)
    c = CRecorder()
    bridge = bridge_mod.MarketEventBridgeR2(b_adapter=b_adapter, c_port=c)
    def mark(price="60000", provider=T, received=T):
        bridge.ingest_frame({"e": "markPriceUpdate", "E": provider, "s": "BTCUSDT", "p": price},
                            received, 100, raw_manifest_sha256="synthetic-mark-source")
    def funding(received=T, mono=200):
        return bridge.ingest_frame(rate_record, received, mono,
                                   raw_manifest_sha256="synthetic-funding-source")
    passed = False
    if case.startswith("delay_") or case == "correct_c_receipt":
        delay = int(case.split("_")[1]) if case.startswith("delay_") else 200
        mark()
        result = funding(T + delay)
        env = c.envelopes[-1]
        if case == "correct_c_receipt":
            env["observed_wall_utc_ms"] = T + delay
            env["available_at_ms"] = T + delay
            try:
                c_mod.MarketPitPort().ingest_envelope(env)
                code = "ACCEPTED"
            except c_mod.SafetyViolation as exc:
                code = exc.code
            expected = {"corrected_receipt_envelope": "ACCEPTED", "available_at_ms": T + delay}
            observed = {"corrected_receipt_envelope": code, "available_at_ms": env["available_at_ms"]}
            passed = code == "ACCEPTED"
        else:
            c.port.validate_decision_pit(T + delay - 1)
            expected = {"b_ingress": T + delay, "c_ingress": T + delay,
                        "c_available": T + delay, "earlier_decision_rejected": True}
            observed = {"b_ingress": b_adapter.last_wall_utc_ms,
                        "b_accounting_receive_time": sink.receipts[-1][1],
                        "c_ingress": env["observed_wall_utc_ms"],
                        "c_available": env["available_at_ms"],
                        "c_feature_known": c.results[-1]["feature_known_at_ms"],
                        "earlier_decision_rejected": False,
                        "c_status": c.results[-1]["status"],
                        "entry_known_at": result["settled_funding"]["feature_known_at_ms"]}
            passed = env["available_at_ms"] == T + delay
    elif case.startswith("mark_"):
        received = T
        if case == "mark_missing":
            pass
        elif case == "mark_stale":
            mark(provider=T - 60_000, received=T - 60_000)
        elif case == "mark_after_settlement":
            received = T + 10_800_000
            mark(price="90000", provider=received, received=received)
        elif case == "mark_route_switch":
            mark()
            bridge.switch_route_node("route-epoch-1")
        elif case == "mark_infinity":
            mark("Infinity")
        elif case == "mark_nan":
            mark("NaN")
        try:
            result = funding(received)
            entry = result.get("settled_funding")
            observed = {"bridge_status": result["status"], "entry": entry,
                        "route_epoch": bridge.route_epoch,
                        "cached_mark": str(bridge.last_mark_tick_price),
                        "dispatched_b": result["emitted_to_b"],
                        "dispatched_c": result["emitted_to_c"]}
            if entry:
                try:
                    observed["cash_long_1btc"] = str(next(iter(bridge.funding_ledger.journal.values())).calculate_cash_flow(Decimal("1")))
                except InvalidOperation:
                    observed["cash_error"] = "InvalidOperation"
            passed = entry is None and result["status"] in ("NO_REALIZED_CASH_BASIS", "UNKNOWN", "COST_INCOMPLETE")
        except (InvalidOperation, ValueError) as exc:
            observed = {"uncaught_exception": type(exc).__name__,
                        "journal_entries": len(bridge.funding_ledger.journal),
                        "journal": [e.to_dict() for e in bridge.funding_ledger.journal.values()],
                        "b_cash_callbacks": len(sink.receipts),
                        "c_envelopes_received": len(c.envelopes)}
        expected = {"entry_quality": "not VERIFIED", "explicit_status": "NO_REALIZED_CASH_BASIS / UNKNOWN / COST_INCOMPLETE",
                    "cash_basis": "finite positive settlement-time mark with ingress/source/epoch provenance"}
    elif case.startswith("decimal_"):
        ledger = fund_mod.SettledFundingLedger()
        if case == "decimal_rounding":
            row = {**rate_record, "fundingRate": "0.000000015"}
            entry = ledger.ingest_settled_funding(row, "1", T)
            cf = entry.calculate_cash_flow(Decimal("1"))
            expected = {"cash": "-0.00000002", "rounding": "ROUND_HALF_EVEN"}
            observed = {"cash": str(cf), "rounding": "ROUND_HALF_EVEN"}
            passed = cf == Decimal("-0.00000002")
        else:
            short = "short" in case
            negative = case.endswith("negative")
            quantity = Decimal("-1.5" if short else "1.5")
            rate = Decimal("-0.0001" if negative else "0.0001")
            entry = ledger.ingest_settled_funding({**rate_record, "fundingRate": str(rate)}, "60000", T)
            cash = entry.calculate_cash_flow(quantity)
            oracle = (-quantity * rate * Decimal("60000")).quantize(Decimal("0.00000001"))
            expected = {"cash": str(oracle), "units": "USDT", "quantity_btc": str(quantity), "rate_fraction": str(rate)}
            observed = {"cash": str(cash), "units": "USDT", "opposite_quantity_cash": str(entry.calculate_cash_flow(-quantity))}
            passed = cash == oracle and cash + entry.calculate_cash_flow(-quantity) == 0
    elif case.startswith("dedupe_"):
        ledger = fund_mod.SettledFundingLedger()
        first = ledger.ingest_settled_funding(rate_record, "60000", T)
        second_row = dict(rate_record)
        if case == "dedupe_equivalent_rate":
            second_row["fundingRate"] = "0.00010000"
        second = ledger.ingest_settled_funding(second_row, "60000", T + 200)
        expected = {"journal_entries": 1, "same_entry": True, "duplicate_count": 1}
        observed = {"journal_entries": len(ledger.journal), "same_entry": first is second,
                    "duplicate_count": ledger.duplicate_count,
                    "sum_long_cash": str(sum((e.calculate_cash_flow(Decimal("1")) for e in ledger.journal.values()), Decimal("0")))}
        passed = len(ledger.journal) == 1 and first is second and ledger.duplicate_count == 1
    elif case == "missing_rate":
        ledger = fund_mod.SettledFundingLedger()
        entry = ledger.ingest_settled_funding({"symbol": "BTCUSDT", "fundingTime": T}, "60000", T)
        expected = {"accepted": False, "cash_basis": "incomplete rate"}
        observed = {"accepted": entry is not None, "rate": str(entry.funding_rate) if entry else None,
                    "quality": entry.quality if entry else None,
                    "cash": str(entry.calculate_cash_flow(Decimal("1"))) if entry else None}
        passed = entry is None
    elif case == "pinned_import_identity":
        # An altered source and a foreign module origin must fail verification.
        target = Path(c_mod.__file__)
        correct = target.read_bytes()
        target.write_bytes(correct + b"\n# synthetic tamper\n")
        try:
            verify_origin(stage, target, by_path)
            wrong_hash_rejected = False
        except RuntimeError as exc:
            wrong_hash_rejected = str(exc) == "PINNED_IMPORT_HASH_MISMATCH"
        finally:
            target.write_bytes(correct)
        try:
            verify_origin(stage, stage.parent / "foreign_module.py", by_path)
            wrong_origin_rejected = False
        except RuntimeError as exc:
            wrong_origin_rejected = str(exc) == "PINNED_IMPORT_ORIGIN_MISMATCH"
        expected = {"wrong_hash_rejected": True, "wrong_origin_rejected": True,
                    "b_revision": B_SHA, "c_revision": C_SHA}
        observed = {**expected, "wrong_hash_rejected": wrong_hash_rejected,
                    "wrong_origin_rejected": wrong_origin_rejected,
                    "executed_modules": origins}
        passed = wrong_hash_rejected and wrong_origin_rejected
    elif case == "legacy_imports":
        # Execute each existing module's filesystem import preamble against a fake
        # runner filesystem. No actual development directory is inspected.
        import ast
        results = []
        for suffix in TEST_NAMES:
            path = f"tests/test_v06_market_event_bridge_r2_{suffix}.py"
            raw = (stage / path).read_text()
            tree = ast.parse(raw)
            absolute_lines = [n.lineno for n in ast.walk(tree)
                              if isinstance(n, ast.Constant) and isinstance(n.value, str)
                              and n.value.startswith("/root/")]
            def fake_exists(p):
                if str(p).startswith("/root/"):
                    raise PermissionError("SYNTHETIC_RUNNER_DENIES_DEVELOPMENT_ROOT")
                return True
            path_names = {"_SCRIPTS_DIR", "_C_DIR", "_B_DIR", "B_DIR", "C_DIR"}
            def is_preamble(n):
                if isinstance(n, ast.Import):
                    return all(x.name == "sys" for x in n.names)
                if isinstance(n, ast.ImportFrom):
                    return n.module == "pathlib"
                if isinstance(n, ast.Assign):
                    return any(isinstance(x, ast.Name) and x.id in path_names for x in n.targets)
                if isinstance(n, ast.If):
                    return any(isinstance(x, ast.Name) and x.id in path_names for x in ast.walk(n.test))
                return False
            top = ast.Module(body=[n for n in tree.body if is_preamble(n)], type_ignores=[])
            saved_path = list(sys.path)
            try:
                with patch.object(Path, "exists", fake_exists):
                    exec(compile(top, path, "exec"), {"__file__": str(stage / path), "__name__": "audit_legacy_probe"})
                outcome = "COLLECTED"
            except PermissionError:
                outcome = "PermissionError"
            finally:
                sys.path[:] = saved_path
            results.append({"path": path, "absolute_path_lines": absolute_lines, "observed": outcome})
        expected = {"development_machine_paths": 0, "collection_permission_errors": 0}
        observed = {"modules": results, "collection_permission_errors": sum(x["observed"] == "PermissionError" for x in results),
                    "simulation": "SYNTHETIC runner filesystem import preambles; no host development directory stat"}
        passed = observed["collection_permission_errors"] == 0
    else:
        raise ValueError(case)
    return {"case_id": case, "input_label": "SYNTHETIC_ONLY",
            "BUG_REPRODUCED": not passed, "INVARIANT_PASSED": passed,
            "expected": expected, "observed": observed,
            "source_baseline": BASE, "B_source": B_SHA, "C_source": C_SHA}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", nargs=2, metavar=("STAGE", "CASE"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.worker:
        print(json.dumps(worker(Path(args.worker[0]), args.worker[1]), allow_nan=False))
        return
    with tempfile.TemporaryDirectory(prefix="accounting-review-") as temporary:
        stage = Path(temporary)
        manifest = prepare_sources(stage)
        results = [run_case(stage, case) for case in CASES]
    for result in results:
        assert_baseline_observation(result)
    expected_observations = True
    report = {"scope": "Focused offline Python accounting and import review; no release authority",
              "baseline": BASE, "baseline_parent": git("show", "-s", "--format=%P", BASE).decode().strip(),
              "audit_branch": BRANCH, "python": sys.version.split()[0],
              "reference_revisions": {"B": B_SHA, "C": C_SHA},
              "harness_commit": git("rev-parse", "HEAD").decode().strip(),
              "harness_files": [{"path": p, "sha256": hashlib.sha256((ROOT / p).read_bytes()).hexdigest()}
                                for p in ("scripts/audits/" + NS + "/review.py",
                                          "tests/test_v06_" + NS + "_focused.py")],
              "source_files": manifest, "cases": results,
              "summary": {"cases_run": len(results), "BUG_REPRODUCED": sum(r["BUG_REPRODUCED"] for r in results),
                          "INVARIANT_PASSED": sum(r["INVARIANT_PASSED"] for r in results),
                          "BASELINE_OBSERVATION_MATCHED": expected_observations},
              "determinations": ["FUNDING_TIMESTAMP_CORRECTION_REQUIRED",
                                 "FUNDING_REFERENCE_PRICE_CORRECTION_REQUIRED", "TEST_IMPORTS_REPAIR_REQUIRED"],
              "network_attempts_in_probes": 0, "protected_data_accessed": 0,
              "original_actions_run": {"id": "38252226915", "verification": "USER_REPORTED_NOT_FETCHED_OFFLINE"}}
    output = args.output or ROOT / "evidence/v0.6/b_line" / NS / "REVIEW_RESULTS.json"
    allowed = ROOT / "evidence/v0.6/b_line" / NS
    if not output.resolve().is_relative_to(allowed.resolve()):
        raise ValueError("Output must remain in audit evidence namespace")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps(report["summary"]))
    if not expected_observations:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
