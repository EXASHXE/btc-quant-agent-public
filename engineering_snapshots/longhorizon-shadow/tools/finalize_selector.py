"""Consolidate observed test XML, source hashes and read-only preservation evidence."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from btc_quant_agent.platform.core import primitive
from btc_quant_agent.platform.factors import REGISTRY as FACTORS
from btc_quant_agent.platform.reporting import source_identity
from btc_quant_agent.platform.strategies import REGISTRY as STRATEGIES

ROOT = Path(__file__).resolve().parents[1]
assert ROOT.name == "l23-selector-evaluation-01"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def emit(name, value):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(primitive(value), indent=2, sort_keys=True, allow_nan=False) + "\n")


def parse_run(name, xml, command):
    path = ROOT / xml
    cases = []
    for node in ET.parse(path).iter("testcase"):
        outcome = (
            "FAILED"
            if node.find("failure") is not None
            else "ERROR"
            if node.find("error") is not None
            else "SKIPPED"
            if node.find("skipped") is not None
            else "PASSED"
        )
        cases.append(
            {
                "id": node.attrib["classname"] + "::" + node.attrib["name"],
                "status": outcome,
                "seconds": float(node.attrib.get("time", 0)),
            }
        )
    return {
        "name": name,
        "command": command,
        "xml": xml,
        "xml_sha256": sha(path),
        "counts": dict(Counter(c["status"] for c in cases)),
        "cases": cases,
    }


runs = [
    parse_run(
        "reused_platform_bridge_foundation",
        "artifacts/logs/reused_repaired_final.xml",
        "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ../multi-strategy-platform-01/.venv/bin/python tools/offline_pytest.py tests/platform tests/bridge tests/test_advisory_foundation_completion.py tests/test_structure.py -q --tb=short --junitxml=artifacts/logs/reused_repaired_final.xml",
    ),
    parse_run(
        "unchanged_legacy_known_red",
        "artifacts/logs/legacy_known_red_final.xml",
        "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ../multi-strategy-platform-01/.venv/bin/python tools/offline_pytest.py tests/test_advisory_foundation.py tests/test_market_watch.py tests/test_live_v1_decision_e2e.py -q --tb=short --junitxml=artifacts/logs/legacy_known_red_final.xml",
    ),
    parse_run(
        "final_selector_and_bridge",
        "artifacts/logs/acceptance_tests.xml",
        ".venv/bin/python tools/offline_pytest.py -q --tb=short --junitxml=artifacts/logs/acceptance_tests.xml",
    ),
]
latest = {c["id"]: c for run in runs for c in run["cases"]}
known = {
    "test_gated_data_never_attempts_notification",
    "test_r2_01_two_run_scanner_breakout_persist_to_retest_triggered",
    "test_mocked_provider_market_watch_to_durable_approval",
}
failed = [c for c in latest.values() if c["status"] == "FAILED"]
assert {c["id"].split("::")[-1] for c in failed} == known
assert all(c["status"] in {"PASSED", "FAILED"} for c in latest.values())
assert all(c["status"] == "PASSED" for c in runs[-1]["cases"])
assert all(c["status"] == "PASSED" for c in runs[0]["cases"])
assert "All checks passed!" in (ROOT / "artifacts/logs/ruff_acceptance_final.log").read_text()
assert "Success: no issues found" in (ROOT / "artifacts/logs/mypy_acceptance_final.log").read_text()
assert not (ROOT / "artifacts/logs/compile_acceptance_final.log").read_text().strip()

before = json.loads((ROOT / "artifacts/preservation_before.json").read_text())
copy = json.loads((ROOT / "artifacts/copy_manifest.json").read_text())["files"]
projects = {
    "R": ROOT.parent / "research-loop-bootstrap",
    "M": ROOT.parent.parent / "Quant-agent-market-watch",
    "Q": ROOT.parent.parent / "Quant-agent",
}
originals = {}
for name, path in projects.items():
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}

    def git(*args):
        return subprocess.check_output(["git", "-C", str(path), *args], env=env, text=True).strip()

    index = Path(git("rev-parse", "--git-path", "index"))
    if not index.is_absolute():
        index = path / index
    previous = before["original_worktrees"][name]
    current = {
        "head": git("rev-parse", "HEAD"),
        "status": git("status", "--porcelain=v1", "--untracked-files=all"),
        "index_sha256": sha(index) if index.is_file() else None,
        "dirty_allowlisted_hashes": {rel: sha(path / rel) for rel in previous["dirty_allowlisted_hashes"]},
    }
    originals[name] = {
        "path": str(path),
        "before": previous,
        "after": current,
        "unchanged": previous == current,
    }

baseline_expected = {
    "multi-strategy-platform-01": "6b455b662c996e1f6ab3e292ee01bec24a2deb25e2bfaf1f726fa960a7f7fda2",
    "real-market-bridge-01": "930c12169f9de52b7f9edb670893fe134c4f831eaadac422b9996e35ab73de68",
}
baselines = {}
for name, files in before["baselines"].items():
    path = ROOT.parent / name
    modified = [rel for rel, value in files.items() if not (path / rel).is_file() or sha(path / rel) != value]
    identity = source_identity(path / "src/btc_quant_agent")
    baselines[name] = {
        "source_identity": identity,
        "expected_source_identity": baseline_expected[name],
        "checked_files": len(files),
        "changed_recorded_files": modified,
        "unchanged": not modified and identity == baseline_expected[name],
    }

legacy_tests_modified = [
    rel
    for rel, value in copy.items()
    if rel.startswith("tests/") and (not (ROOT / rel).is_file() or sha(ROOT / rel) != value)
]
assert not legacy_tests_modified
preserved = all(x["unchanged"] for x in originals.values()) and all(
    x["unchanged"] for x in baselines.values()
)
coverage_limits = [
    "Preservation checks cover original HEAD/index/status, the initially recorded allowlisted dirty hashes, and both baseline source/config/test/tool/receipt inventories. Protected/runtime/private contents were deliberately not read.",
    "The initial stripped git-status snapshot omitted a content hash for dirty R/README.md. Its dirty status, index and HEAD are unchanged and no L23 operation wrote it; initial-to-final byte equality for that one document is not independently established.",
    "No collector PID continuity assertion is made. No collector/service control operation was performed.",
]
emit(
    "L23_PRESERVATION.json",
    {
        "status": "RECORDED_SCOPE_UNCHANGED" if preserved else "OBSERVED_CHANGES_REQUIRE_REVIEW",
        "original_worktrees": originals,
        "baselines": baselines,
        "legacy_tests_modified": legacy_tests_modified,
        "original_write_operations": 0,
        "collector_control_operations": 0,
        "commits_pushes_deployments": 0,
        "protected_data_or_registry_reads": 0,
        "scope_limits": coverage_limits,
        "initial_worker_check": before["worker_check"],
    },
)

source_files = {str(p.relative_to(ROOT / "src")): sha(p) for p in sorted((ROOT / "src").rglob("*.py"))}
source_sha = hashlib.sha256(
    json.dumps(source_files, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
emit(
    "artifacts/source_sha256.json",
    {
        "algorithm": "SHA256 of UTF-8 canonical JSON of sorted relative-path:SHA256 file map",
        "source_sha256": source_sha,
        "project_source_identity": source_identity(ROOT / "src/btc_quant_agent"),
        "files": source_files,
    },
)
emit(
    "artifacts/canonical_inputs.json",
    {
        "repository": "EXASHXE/btc-quant-agent-public",
        "branch": "docs/engineering",
        "verified_head_at_phase_start": "d284b34cf30834c3e79c8103cb72fba5d402567e",
        "read_paths": [
            "AGENTS.md",
            "docs/project/V070_DOCUMENTATION_BRANCH_POLICY.md",
            "docs/project/V070_ADVISORY_MISSION_AND_SCOPE.md",
            "docs/roles/V070_ADVISORY_AGENT_ROLES.md",
            "docs/project/V070_ADVISORY_ROADMAP.md",
            "docs/project/V070_CURRENT_STATE_AND_HANDOFF.md",
            "docs/project/V070_L12_OFFLINE_MULTISTRATEGY_ADVISORY_MANDATE_20261029.md",
        ],
        "read_via": "Connected GitHub read-only tools at the exact commit",
        "astra_sha256": before["astra_sha256"],
        "canonical_document_changes": 0,
        "local_receipts_are_not_a_new_roadmap": True,
    },
)
emit(
    "artifacts/factor_strategy_matrix.json",
    {
        "factors": primitive(list(FACTORS.values())),
        "strategies": primitive(list(STRATEGIES.values())),
        "v1_enabled": ["trend_pullback", "breakout_retest", "bollinger_reversion"],
        "synthetic_validated_metadata_count": sum(
            str(s.evidence_tier) == "SYNTHETIC_VALIDATED" for s in STRATEGIES.values()
        ),
        "tier_promotions": 0,
    },
)

requirements = {
    "stale_OI_fresh_price": "test_price_cannot_launder_oi[stale]",
    "wrong_symbol_trades": "test_actual_trade_observation_identity_in_shared_frame[symbol]",
    "misaligned_benchmark": "test_frozen_membership_never_shrinks_to_hide_bad_reference",
    "duplicate_momentum": "test_duplicate_momentum_indicators_do_not_gain_votes",
    "opposing_setups": "test_veto_before_opposition_and_no_direction_vote_counting",
    "missing_quote": "test_missing_quote_preserves_watch_then_armed_and_risk",
    "delayed_post_ack_quote": "test_delivery_is_unknown_until_separate_assumption_and_new_quote",
    "positive_later_limit_cross_and_candle_touch_NO_FILL": "test_later_strict_quote_cross_positive_limit_fill_and_candle_touch_no_fill",
    "lost_entry_1_3_5_minutes": "test_lost_entry_at_response_cancels_irreversibly",
    "stop_gap_execution_unknown": "test_replay_and_user_supervisor_exit_parity[gap]",
    "two_simultaneous_capital_reservations": "test_two_processes_cannot_reuse_same_risk_capital",
    "pending_order_uncertainty": "test_reservations_use_equity_signed_beta_and_pending_unknown",
    "notification_replay_crash_restart": "test_genuine_process_restart_dedup_and_unknown_delivery",
    "prepare_state_binding_crash": "test_episode_crash_between_prepare_and_state_binding_is_recoverable",
    "replay_supervisor_exit_parity": "test_replay_and_user_supervisor_exit_parity",
    "past_checkpoint_rejection": "test_regime_checkpoint_cannot_leak_into_a_past_decision",
    "CLI_restart_parity": "test_cli_resume_does_not_replay_a_past_snapshot_into_future_state",
    "duplicate_user_fill_after_close": "test_duplicate_user_report_after_close_cannot_reopen",
}
failures = {
    key: [c["id"] for c in latest.values() if needle in c["id"] and c["status"] == "PASSED"]
    for key, needle in requirements.items()
}
assert all(failures.values())
counts = dict(Counter(c["status"] for c in latest.values()))
by_group = {
    group: dict(Counter(c["status"] for c in latest.values() if predicate(c["id"])))
    for group, predicate in {
        "L23": lambda s: s.startswith("tests.selection."),
        "platform": lambda s: s.startswith("tests.platform."),
        "bridge": lambda s: s.startswith("tests.bridge."),
        "reused_foundation": lambda s: s.startswith(
            ("tests.test_advisory_foundation_completion", "tests.test_structure")
        ),
        "legacy_files": lambda s: s.startswith(
            (
                "tests.test_advisory_foundation::",
                "tests.test_market_watch::",
                "tests.test_live_v1_decision_e2e::",
            )
        ),
    }.items()
}
# Pytest can omit the tests. prefix depending on collection package discovery.
by_group = {key: value for key, value in by_group.items() if value}
replacement = [c["id"] for c in latest.values() if "test_contract_reconciliation" in c["id"]]
assert len(replacement) == 3 and all(latest[key]["status"] == "PASSED" for key in replacement)
static = {
    "ruff": {
        "command": "ruff check src/btc_quant_agent/platform/selection src/btc_quant_agent/platform/data.py src/btc_quant_agent/platform/factors.py src/btc_quant_agent/platform/backtest.py src/btc_quant_agent/platform/strategies.py src/btc_quant_agent/platform/position_management.py src/btc_quant_agent/platform/cli.py tests/selection tools/selector_worker.py tools/demonstrate_selector.py tools/offline_cli.py",
        "observed_exit_code": 0,
        "log": "artifacts/logs/ruff_acceptance_final.log",
    },
    "mypy": {
        "command": "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../multi-strategy-platform-01/.venv/bin/python -m mypy --no-incremental",
        "observed_exit_code": 0,
        "checked_source_files": 11,
        "log": "artifacts/logs/mypy_acceptance_final.log",
    },
    "compile": {
        "command": ".venv/bin/python -m compileall -q src/btc_quant_agent/platform tools/selector_worker.py tools/demonstrate_selector.py tools/offline_cli.py tests/selection",
        "observed_exit_code": 0,
        "log": "artifacts/logs/compile_acceptance_final.log",
    },
}
emit(
    "L23_TEST_MATRIX.json",
    {
        "source_sha256": source_sha,
        "unique_counts": counts,
        "by_group": by_group,
        "runs": runs,
        "known_red": failed,
        "replacement_contract_passes_included_not_added": replacement,
        "required_failure_cases": failures,
        "static_checks": static,
        "deduplication": "Latest listed result per classname::name; bridge overlap counted once",
        "multiprocess": "Four new subprocess test cases execute real independent Python processes against synthetic SQLite, including concurrent claims, killed sender, prepare/binding crash and regime restart",
        "earlier_failed_iteration_logs": "Retained under artifacts/logs; not acceptance passes",
    },
)

evaluation = json.loads((ROOT / "artifacts/final/evaluation/episodes.json").read_text())
position_demo = json.loads((ROOT / "artifacts/final/user-position/receipt.json").read_text())
assert position_demo["actual_ledger_position"]["status"] == "OPEN" and position_demo["fake_sender_calls"] == 1
assert position_demo["delivery"]["delivery"] == "UNKNOWN"
assert evaluation["transport_attempts"] == 0 and evaluation["threshold_fitting_runs"] == 0
scope_status = "ACCEPT" if preserved else "PARTIAL"
limitations = [
    "All prices, provider receipts, execution and delivery assumptions are fabricated.",
    "Three structural episodes generate dependent fault/latency counterfactuals, not independent market evidence.",
    "Regime thresholds and prior-60-bar volatility/shock proxies are engineering hypotheses, not the full Astra daily-percentile estimator.",
    "Only three bounded V1 playbooks are enabled. Shock cessation/entry activation is absent; 21+7 original definitions and evidence tiers are preserved.",
    "Correlation risk uses a conservative common crypto cluster and signed beta; adaptive clustering and endogenous portfolio-return attribution are not implemented.",
    "Quote-cross fills are conservative models with no queue, venue or actual execution proof. Unknown pending capacity requires explicit reconciliation.",
    "Exit comparisons are paired on frozen fills. Unmatched previous-scanner setup geometries receive no invented economics.",
    "Funding is projected for risk. Short held fixtures have no declared settlement due; long-horizon missing funding is not full-net validation.",
    "V1 shared modeled exits support stop-market. Inherited stop-limit simulation is separate.",
    "The whole repository remains KNOWN_RED_3. Replacement safety passes are separate and do not reclassify legacy failures.",
    *coverage_limits,
]
acceptance = {
    "task": "V070-L23-SELECTOR-EVALUATION-01",
    "status": scope_status,
    "scope": "ISOLATED_OFFLINE_ENGINEERING_ONLY",
    "implementation_status": "WORKING_BASELINE",
    "generated_utc": datetime.now(timezone.utc).isoformat(),
    "source_sha256": source_sha,
    "project_source_identity": source_identity(ROOT / "src/btc_quant_agent"),
    "tests": {
        "unique": counts,
        "groups": by_group,
        "replacement_contract_passes": 3,
        "no_skips_or_xfails": True,
        "global_suite_status": "KNOWN_RED_3_UNCHANGED",
    },
    "coverage": {
        "factors_retained": len(FACTORS),
        "directional_strategies_retained": 21,
        "research_only_strategies_retained": 7,
        "v1_playbooks": 3,
        "strategy_tier_promotions": 0,
        "unique_structural_episodes": evaluation["unique_structural_episodes"],
        "scenario_runs": len(evaluation["runs"]),
        "funnel": evaluation["funnel"],
        "modeled_fills_are_not_actual": True,
    },
    "preservation_recorded_scope_unchanged": preserved,
    "activation": "BLOCKED_PENDING_OWNER_AUTH",
    "source_readiness": "artifacts/final/source_readiness.json",
    "network_exchange_calls": 0,
    "orders_accounts_or_real_notifications": 0,
    "protected_dataset_or_PRIMARY_operations": 0,
    "original_integration_commits_deployments": 0,
    "automatic_successor_task": False,
    "limitations": limitations,
    "artifacts": {
        "test_matrix": "L23_TEST_MATRIX.json",
        "preservation": "L23_PRESERVATION.json",
        "source_manifest": "artifacts/source_sha256.json",
        "changes": "artifacts/changed_files.json",
        "evaluation_json": "artifacts/final/evaluation/episodes.json",
        "evaluation_html": "artifacts/final/evaluation/episodes.html",
        "field_history": "artifacts/final/evaluation/source_histories.jsonl",
        "factor_coverage": "artifacts/final/evaluation/factor_coverage.json",
        "factor_strategy_matrix": "artifacts/factor_strategy_matrix.json",
        "user_position": "artifacts/final/user-position/receipt.json",
    },
    "evaluation_sha256": sha(ROOT / "artifacts/final/evaluation/episodes.json"),
}
emit("L23_ACCEPTANCE.json", acceptance)

passed = counts["PASSED"]
rows = "\n".join(f"| {name} | {value['head']} |" for name, value in before["original_worktrees"].items())
coverage_rows = "\n".join(
    f"| {strategy} | V1 bounded implementation | {STRATEGIES[strategy].evidence_tier} |"
    for strategy in ["trend_pullback", "breakout_retest", "bollinger_reversion"]
)
report = (
    f"""# L23 final delivery

Status: **{scope_status} — isolated offline engineering scope**. This is a working deterministic V1 baseline, not real-market or economic acceptance. Controller 0-C retains the concentrated phase-audit decision.

## Verified baselines and authority

Canonical docs/engineering HEAD: `d284b34cf30834c3e79c8103cb72fba5d402567e`. The seven required canonical documents, both baseline receipts/source/tests and the Astra review were read before implementation. No matching L23 worker was found before the isolated copy.

| Original tree | Verified HEAD |
|---|---|
{rows}

Platform source identity: `{baseline_expected["multi-strategy-platform-01"]}`.
Bridge source identity: `{baseline_expected["real-market-bridge-01"]}`.
Delivered source SHA256 manifest: `{source_sha}`. Algorithm and per-file hashes: `artifacts/source_sha256.json`. Project-native source identity is separately recorded in `L23_ACCEPTANCE.json`.

## Implemented modules

| Module | Status | Result |
|---|---|---|
| selection/sources | FULLY_IMPLEMENTED for offline contracts | Field identity/units/clocks, completed 5m/1m, actual bridge decoder seam, frozen membership, optional data isolation, field-history artifact |
| selection/selector | WORKING_BASELINE | Six explicit regimes, causal hysteresis/revocation/restart, grouped confirmations, side-aware ranks, three enabled playbooks, veto before conflict |
| selection/lifecycle | FULLY_IMPLEMENTED for modeled offline paths | Frozen geometry/trigger IDs, readiness revocation, irreversible expiry/cancel, continuous monitoring, new post-ack quotes, later resting-limit cross |
| selection/store | FULLY_IMPLEMENTED for tested offline contracts | SQLite episodes, atomic signed-risk reservations, user-ledger exposure, commit-before-notify reuse, unknown delivery/pending execution |
| selection/management + existing backtest/supervise | WORKING_BASELINE | Shared stop/gap, frozen mean, optional partial, next-observation trail, funding-review and actual-execution separation |
| selection/evaluation | WORKING_BASELINE / RESEARCH_ONLY outputs | Actual old scanner and resolver comparisons, matched costs/geometries, entry diagnostic, paired exits, complete episode funnel |
| CLI | FULLY_IMPLEMENTED for offline paths | selector validate/scan/evaluate/report-fill/position-replay plus existing CLI; no real-source activation |
| Real transports, verified accounts, real notifications | BLOCKED_PENDING_OWNER_AUTH | No authorization or successful connectivity claimed |

The retained library has **69 factors, 21 directional and seven research-only portfolio strategies**. Formula/parameter/support metadata is in `artifacts/factor_strategy_matrix.json`; actual factor availability is in `artifacts/final/evaluation/factor_coverage.json`. Only the original three entries carry SYNTHETIC_VALIDATED. No tier was promoted.

| Enabled strategy | Coverage | Preserved strategy evidence tier |
|---|---|---|
{coverage_rows}

## Actual validation

**{passed} unique passes, three unchanged legacy failures, zero skipped/xfail/error cases.** Overlapping bridge tests are counted once. Exact commands, XML hashes, case IDs, durations and required failure mappings are in `L23_TEST_MATRIX.json`.

- Final selector/bridge gate: `{runs[-1]["counts"]}`.
- Reused full platform/bridge/Foundation gate: `{runs[0]["counts"]}`; includes 158 platform, 31 bridge and 37 Foundation/structure tests.
- Unchanged legacy files: 175 passed / 3 failed. `tests/test_advisory_foundation.py::test_gated_data_never_attempts_notification`, `tests/test_market_watch.py::test_r2_01_two_run_scanner_breakout_persist_to_retest_triggered`, `tests/test_live_v1_decision_e2e.py::test_mocked_provider_market_watch_to_durable_approval` remain red. They were not skipped, edited or reinterpreted. Three replacement contract passes are included in the bridge count and separately identified.
- Scoped Ruff, compile and mypy passed; mypy checked 11 source files using preinstalled baseline stubs read-only.
- Four new tests execute real subprocesses for concurrent capital, restart deduplication, sender crash and regime/episode recovery. No thread-only approximation is substituted.
- Two bridge OI regressions discovered during integration were repaired using row-relative freshness with actual availability retained. Earlier failed logs remain visible. One inherited sklearn SVM deprecation warning remains; no warning was hidden.

## Demonstrations and artifacts

```bash
.venv/bin/python tools/offline_cli.py factors list
.venv/bin/python tools/offline_cli.py strategies list
.venv/bin/python tools/offline_cli.py selector validate --config configs/selector/v1.yaml
.venv/bin/python tools/offline_cli.py selector scan --config configs/selector/v1.yaml --output artifacts/another-scan
.venv/bin/python tools/offline_cli.py selector evaluate --config configs/selector/v1.yaml --output artifacts/another-evaluation
.venv/bin/python tools/demonstrate_selector.py --evaluation artifacts/another-evaluation --output artifacts/another-user-position
.venv/bin/python tools/offline_pytest.py -q
```

Use new evaluation output paths; old evidence is not overwritten. Existing final examples are `artifacts/final/evaluation/episodes.json` and `episodes.html`, with {len(evaluation["runs"])} scenario rows built from {evaluation["unique_structural_episodes"]} structural episodes. Funnel: `{evaluation["funnel"]}`. Clean 1/3/5-minute responses produce nine modeled fills across the three playbooks. The common lost-region path disappears after the first response scenario but before later responses; separate unit cases prove cancellation at every 1/3/5-minute response endpoint. 10/15-minute total-latency stress is separate.

`source_histories.jsonl` retains fabricated field receipts and dependency clocks. `factor_coverage.json` explicitly marks unavailable depth/tape features. `user-position/receipt.json` proves HOLD/TIGHTEN_STOP/PARTIAL_EXIT/EXIT, one fake sender call, UNKNOWN delivery and an actual isolated ledger still OPEN. Its user report is fabricated input, not a claim that the Owner filled a real order.

The previous-source scan uses the same three enabled strategies and identical history/costs. The old setup/rank/regime logic is retained; only matched canonical episode geometries receive controlled economics. Contradictory/duplicate/vetoed setup slates isolate conflict behavior. Paired exit comparisons use frozen identical fills. Alternative responses, fault cases and paired exits are dependent counterfactuals, not additive portfolio trades.

## Limits and unfinished capabilities

"""
    + "\n".join("- " + s for s in limitations)
    + """

Source-qualified shock entry, adaptive correlation clustering, endogenous portfolio-return evaluation, real settlement continuity, genuine execution verification and real notification delivery are not completed or claimed. Real-world schemas, source-time authority, size semantics and forward continuity remain unverified. These limits do not turn synthetic PnL into Alpha.

## Preservation and separately authorized integration

`L23_PRESERVATION.json` verifies unchanged original HEAD/index/status and recorded allowlisted dirty hashes, both delivered baseline inventories/source identities, and every inherited test source. No destructive Git operation, commit, merge, push, collector control, registry access, protected-data read, service restart or deployment occurred. Its explicit preservation coverage limits apply; it does not claim to hash private/runtime contents or the initially unhashed R README.

`artifacts/changed_files.json` is the allowlisted patch manifest. Future integration requires a separately authorized original-tree patch review, application and regression gate; nothing was merged. `artifacts/final/source_readiness.json` gives provider/symbol/endpoint/field/frequency/UTC-window/retention requirements for any future public-source grant. The proposed window is not an authorization or scheduled activity. Private accounts/orders remain excluded. No automatic successor task is created.
"""
)
(ROOT / "L23_FINAL_DELIVERY.md").write_text(report)
(ROOT / "L23_CHECKPOINT.md").write_text(f"""# L23 implementation checkpoint

Current phase: terminal offline delivery; status {scope_status}.

Authority: V070-L23-SELECTOR-EVALUATION-01. Workspace only; no automatic successor task.

Completed: strict field histories and actual offline provider-decoder seam; frozen universe; six-state persistent deterministic regime; three bounded playbooks; immutable episode/trigger clocks and terminal states; post-ack quote revalidation; resting-limit cross model; atomic capacity and user-ledger risk; shared management; complete episode funnel and controlled old/new comparisons; CLI, source/factor history and JSON/HTML reports.

Important decisions: see L23_SOURCE_SELECTOR_CONTRACT.md. Thresholds are engineering hypotheses; shock remains non-actionable. Original registries, tiers, legacy tests and durable outbox are retained. Future checkpoints cannot leak into past decisions. Recommendations never execute or close actual positions.

Changed files: artifacts/changed_files.json. Source SHA256: {source_sha}.

Verified: {passed} unique tests passed, exactly three unchanged legacy assertions failed, no skips/xfails/errors. Three replacement passes are separate and included in counts. Scoped Ruff/compile/mypy passed. Exact commands/XML/cases are in L23_TEST_MATRIX.json. Real subprocess restart/reservation tests passed. Final CLI/user-position artifacts are under artifacts/final.

Open defects: no additional failing tested engineering case. Known legacy assertions remain red. Real transport/accounts/notifications/integration/deployment are blocked pending separate authority. Limits and preservation coverage qualifications are in the final report and receipts.

Exact next step: Controller 0-C may audit this one milestone. No authorized implementation continuation or source activation is scheduled. Any real acquisition must receive a separate explicit grant matching source_readiness.json.
""")

allowed = {}
for top, extensions in {
    "src": {".py"},
    "tests": {".py"},
    "configs": {".yaml", ".json", ".toml"},
    "tools": {".py"},
}.items():
    for path in sorted((ROOT / top).rglob("*")):
        if (
            path.is_file()
            and not path.is_symlink()
            and "__pycache__" not in path.parts
            and path.suffix in extensions
        ):
            allowed[str(path.relative_to(ROOT))] = sha(path)
for name in ["pyproject.toml", "README.md"]:
    allowed[name] = sha(ROOT / name)
changed = [
    {
        "path": rel,
        "status": "MODIFIED" if rel in copy else "NEW",
        "sha256": value,
        "baseline_sha256": copy.get(rel),
    }
    for rel, value in sorted(allowed.items())
    if copy.get(rel) != value
]
deleted = [rel for rel in copy if not (ROOT / rel).exists()]
assert not deleted
emit(
    "artifacts/changed_files.json",
    {
        "baseline": "real-market-bridge-01",
        "files": changed,
        "deleted_files": deleted,
        "unchanged_inherited_test_sources": True,
        "engineering_receipts": {
            name: sha(ROOT / name)
            for name in [
                "L23_FINAL_DELIVERY.md",
                "L23_CHECKPOINT.md",
                "L23_SOURCE_SELECTOR_CONTRACT.md",
                "L23_ACCEPTANCE.json",
                "L23_TEST_MATRIX.json",
                "L23_PRESERVATION.json",
            ]
        },
        "excluded_from_source_copy": "Credentials, protected/private datasets, runtime stores, caches, original artifacts and virtual environments",
    },
)
print(
    json.dumps(
        {
            "status": scope_status,
            "unique_tests": counts,
            "groups": by_group,
            "source_sha256": source_sha,
            "preserved_recorded_scope": preserved,
            "changed_files": len(changed),
        }
    )
)
