"""Materialize the scoped offline acceptance from retained test evidence and source hashes."""
from datetime import datetime, timezone
import ast
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from btc_quant_agent.platform.canary import longhorizon as lh
from btc_quant_agent.platform.core import fingerprint

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/engineering"


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")


suites = ("regression_final", "session02_recovery", "tls_recovery", "longhorizon_final",
          "response_veto_final", "report_final", "quality_supplement_final", "finite_final")
outcomes = {}
attempts = []
for name in suites:
    cases = list(ET.parse(OUT / (name + ".xml")).getroot().iter("testcase"))
    summary = {"suite": name, "cases": len(cases), "pass": 0, "fail": 0, "skip": 0}
    for case in cases:
        key = case.attrib["classname"] + "::" + case.attrib["name"]
        status = "fail" if case.find("failure") is not None or case.find("error") is not None else (
            "skip" if case.find("skipped") is not None else "pass")
        summary[status] += 1
        previous = outcomes.get(key, {}).get("attempts", [])
        outcomes[key] = {"outcome": status, "attempts": previous + [{"suite": name, "outcome": status}]}
    attempts.append(summary)
assert all(v["outcome"] == "pass" for v in outcomes.values()), "Unresolved final test outcome"
new_count = sum(".longhorizon." in k.split("::")[0] for k in outcomes)
write(OUT / "test_matrix.json", {"unique_pass": len(outcomes), "new_unique_pass": new_count,
                               "attempt_summaries": attempts, "cases": outcomes})

hashes = lh.source_hashes()
write(OUT / "source_sha256.json", {"files": hashes, "source_sha256_fingerprint": fingerprint(hashes)})
before = json.loads((OUT / "preservation_before.json").read_text())
delta = []
for name, old in before["source_hashes"].items():
    path = ROOT / name
    new = hashlib.sha256(path.read_bytes()).hexdigest()
    if new != old:
        delta.append({"path": name, "before_sha256": old, "after_sha256": new})
added = {}
for folder in ("src", "tests/longhorizon", "configs/longhorizon", "tools"):
    for p in (ROOT / folder).rglob("*"):
        rel = str(p.relative_to(ROOT))
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc" and rel not in before["source_hashes"]:
            added[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
write(OUT / "source_delta.json", {"modified": delta, "added": added,
    "l23_selector_lifecycle_management_strategy_parameters_unchanged": all(
        not x["path"].startswith("src/btc_quant_agent/platform/selection/") for x in delta),
    "baseline_modified": False})

proposal = json.loads((ROOT / "LONGHORIZON_SOURCE_GRANT_PROPOSAL.json").read_text())
proposal["unsigned_contract_template"]["source_sha256_fingerprint"] = fingerprint(hashes)
write(ROOT / "LONGHORIZON_SOURCE_GRANT_PROPOSAL.json", proposal)
write(OUT / "default_deny_requirements.json", lh.requirements())

parse_files = list((ROOT / "src/btc_quant_agent/platform/canary").glob("*.py"))
parse_files += list((ROOT / "tests/longhorizon").glob("*.py"))
parse_files += [ROOT / "tools" / name for name in ("launch_longhorizon.py", "demo_longhorizon.py",
    "verify_longhorizon_preservation.py", "prepare_longhorizon_regression.py", "finalize_longhorizon.py")]
for p in parse_files:
    ast.parse(p.read_text(), filename=str(p))
(OUT / "compile_final.log").write_text(f"PASS: AST parse of {len(parse_files)} affected Python files; no bytecode writes.\n")
assert "All checks passed!" in (OUT / "ruff_final.log").read_text()
assert "Success: no issues found in 33 source files" in (OUT / "mypy_final.log").read_text()
preservation = json.loads((OUT / "preservation_after.json").read_text())
assert preservation["unchanged"]
assert not lh.OUTPUT.exists()
assert not json.loads(lh.TRUST.read_text())["keys"]

write(OUT / "iteration_notes.json", {
    "initial_quality_run": {"pass": 13, "fail": 2, "cause": [
        "Test used 1m bar with default 5m FrozenUniverse; corrected the test interval",
        "Test used nonexistent CanaryStore.path; corrected the test's explicit SQLite path"],
        "assertions_removed_or_weakened": False},
    "initial_finite_soak_run": {"pass": 27, "fail": 1, "cause":
        "Overfast simulated producer correctly triggered bounded backpressure; simulation pacing changed from 4ms to 20ms, no production queue/rate limit relaxed",
        "log": "iteration_quality_runtime.log"},
    "inherited_initial_failures": {"count": 9, "cause": "6 AF_UNIX TLS getsockopt sandbox restrictions; 3 absent simulated predecessor markers",
        "recovered": True, "old_tests_modified": False, "log": "regression_final.log"},
    "tls_execution": "Exactly six unchanged tests passed over owned AF_UNIX socket pairs with fabricated certs in controlled host execution; external DNS/connect remained blocked",
    "scope_exclusion": "One old sealed-native-payload replay case deliberately deselected: this phase's implementation tests are simulated-only",
    "static_iterations": "Initial mypy/unused-import failures were repaired; final 33-file mypy, Ruff and AST pass. Initial mypy log retained."})

commands = [
    {"cwd": "artifacts/engineering/regression", "command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python tools/offline_pytest.py tests/canary_public tests/canary tests/selection tests/bridge -q --tb=short -k 'not sealed_native_legacy_replay' --junitxml=../regression_final.xml", "result": "417 pass, 9 initial fixture/environment fail, 1 deselected; failed cases all recovered below"},
    {"cwd": "artifacts/engineering/regression", "command": "L4_SEALED_NATIVE_RUN=<workspace>/artifacts/engineering/synthetic_previous_session PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python tools/offline_pytest.py tests/canary_public/test_session02.py::test_finite_clock_only_replay_isolated_and_no_action -q --junitxml=../session02_recovery.xml", "result": "3 pass"},
    {"cwd": "artifacts/engineering/regression", "command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python tools/offline_pytest.py tests/canary_public/test_egress_integration.py::test_both_clients_verify_original_target_over_preconnected_tunnel -q --junitxml=../tls_recovery.xml", "result": "6 pass; controlled host execution for local socket pairs only"},
    {"cwd": ".", "command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python tools/offline_pytest.py tests/longhorizon -q --junitxml=artifacts/engineering/longhorizon_final.xml", "result": "59 pass before supplemental cases; includes accelerated 48h control-plane soak and 201-bar L23 pipeline"},
    {"cwd": ".", "command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python tools/offline_pytest.py tests/longhorizon/test_quality.py tests/longhorizon/test_response_vetoes.py -q --junitxml=artifacts/engineering/quality_supplement_final.xml", "result": "20 pass, includes added retention/response veto/preflight-bypass cases and final report branch"},
    {"cwd": ".", "command": "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests python tools/offline_pytest.py tests/longhorizon/test_runtime.py::test_finite_foreground_source_shadow_closes_and_seals -q --junitxml=artifacts/engineering/finite_final.xml", "result": "3 pass on final runtime session identity/fsync/seal changes"},
    {"cwd": ".", "command": "python -m mypy --follow-imports=silent --ignore-missing-imports --check-untyped-defs --disable-error-code import-untyped src/btc_quant_agent/platform/core.py src/btc_quant_agent/platform/config.py src/btc_quant_agent/platform/selection src/btc_quant_agent/platform/canary", "result": "33 source files pass"},
    {"cwd": ".", "command": "PYTHONDONTWRITEBYTECODE=1 python tools/verify_longhorizon_preservation.py", "result": "318 baseline files, 134 baseline receipts, recorded R/M/Q metadata/source unchanged"}]
acceptance = {
    "status": "OFFLINE_IMPLEMENTED_TESTED_CONTROLLER_REVIEW_READY",
    "created_utc": datetime.now(timezone.utc).isoformat(), "controller": "0-C",
    "owner_decision": {"offline_review": "GO", "native_acquisition": "NO_GO_NATIVE_SOURCE"},
    "workspace": str(ROOT), "baseline": before["baseline"], "canonical_head": lh.HEAD,
    "source_sha256_fingerprint": fingerprint(hashes), "fingerprinted_source_files": len(hashes),
    "tests": {"unique_pass": len(outcomes), "new_unique_pass_included": new_count,
        "inherited_unique_pass": len(outcomes) - new_count, "unresolved_current_failures": 0,
        "skips_or_xfails": 0, "explicitly_deselected_native_payload_replay": 1,
        "initial_inherited_failures_retained": 9, "count_semantics": "Union by JUnit classname/name; repeated checks and recoveries count once; historical 1053/427 counts are excluded",
        "historical_known_red_not_rerun_or_claimed_fixed": [
            "tests.test_advisory_foundation::test_gated_data_never_attempts_notification",
            "tests.test_live_v1_decision_e2e::test_mocked_provider_market_watch_to_durable_approval",
            "tests.test_market_watch::test_r2_01_two_run_scanner_breakout_persist_to_retest_triggered"]},
    "static": {"ruff": "PASS", "mypy": "PASS_33_SOURCE_FILES", "ast": "PASS", "ast_files": len(parse_files)},
    "coverage": {
        "P0": "Separate signed <=48h UTC grant, one foreground exclusive claim, native default deny, nine source IDs, native clock prerequisite, frozen source/route/storage limits",
        "P1": "REST/WS native-shaped lifecycle, 5s quote lease, 1m/5m continuity and bounded causal repair, explicit derivative UNKNOWN, sticky clock faults, probe refresh, outage/retry/reconnect/backpressure limits, 8/4GiB caps, conservative 36h/168h retention, incomplete early-raw replay status",
        "P2": "Unchanged three V1 L23 playbooks/parameters, 66/201/289 bar contracts, WATCH/ARMED/ENTRY vetoes, structure/risk/trailing inherited checks, post-ack native-shaped observed quote validation and 1/3/5m modeled responses",
        "P3": "Per-symbol field/source health, structure, coverage/funnel/vetoes, conditional response survival with UNKNOWN/censoring, missing account-risk gates, local HTML/JSON reports, no fills/PnL/Alpha",
        "P4": "Socket/DNS-denied simulated tests; focused/integration/48h accelerated control-plane/fault injection, local TLS checks, static checks, scoped preservation"},
    "unresolved_blockers": [
        "NO_GO_NATIVE_SOURCE: no established native Session02 Clock V2 qualification",
        "No distinct Owner-signed long-horizon grant, exact future UTC start/end or new verified public trust key",
        "Current authorized route/TLS, native schema/IP caps, storage and actual long-duration source quality remain unobserved",
        "Three-symbol scope cannot satisfy >=10-symbol ranking; ENTRY_ELIGIBLE remains blocked",
        "Current account equity, margin, portfolio exposures and account-specific tiers MISSING; native funding schedule and OI units unqualified"],
    "qualification": {"source_qualified": False, "shadow_advisory_qualified": False, "economically_validated": False,
        "actual_fills_claimed": False, "executable_net_pnl_claimed": False, "alpha_claimed": False,
        "prospective_profitability_claimed": False, "actual_48h_native_soak_performed": False},
    "actions": {"native_market_acquisition_requests": 0, "external_alerts": 0, "account_or_order_operations": 0,
        "scheduler_created": False, "background_collector_started": False, "automatic_successor": False,
        "native_output_created": False, "longhorizon_owner_grant_signed": False,
        "owner_or_exchange_private_keys_read_or_created": False,
        "test_keys": "Ephemeral in-memory Ed25519 and temporary fabricated TLS keys only; no native authority",
        "protected_history_or_holdout_read": False, "original_integration_or_commit": False},
    "preservation": {"unchanged": True, "baseline_files": 318, "baseline_receipts": 134,
        "old_sealed_compressed_chunks_verified_against_manifest": 10, "R_M_Q": "UNCHANGED_WITHIN_RECORDED_SCOPE",
        "old_session02_key_store_and_outputs_modified": False},
    "prototype": {"report": "artifacts/engineering/synthetic_demo/report.json",
        "dashboard": "artifacts/engineering/synthetic_demo/dashboard_final.html", "exposure": "SYNTHETIC",
        "real_native_observations_in_demo": False},
    "commands": commands,
    "evidence": ["artifacts/engineering/test_matrix.json", "artifacts/engineering/source_sha256.json",
        "artifacts/engineering/source_delta.json", "artifacts/engineering/preservation_after.json",
        "artifacts/engineering/iteration_notes.json", "artifacts/engineering/canonical_review.json",
        "artifacts/engineering/accepted_receipt_review.json", "artifacts/engineering/old_sealed_chunk_verification.json"]}
write(ROOT / "LONGHORIZON_TEST_ACCEPTANCE.json", acceptance)
seal_files = [ROOT / name for name in ("LONGHORIZON_IMPLEMENTATION.md", "LONGHORIZON_SOURCE_GRANT_PROPOSAL.json",
                                      "LONGHORIZON_TEST_ACCEPTANCE.json", "LONGHORIZON_OPERATOR_RUNBOOK.md")]
seal_files += [p for p in OUT.iterdir() if p.is_file() and p.name != "delivery_seal.json"]
seal_files += [p for p in (OUT / "synthetic_demo").rglob("*") if p.is_file()]
write(OUT / "delivery_seal.json", {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(seal_files)})
print(json.dumps({"unique_pass": len(outcomes), "new_unique_pass": new_count,
    "source_fingerprint": fingerprint(hashes), "native_decision": "NO_GO_NATIVE_SOURCE"}))
