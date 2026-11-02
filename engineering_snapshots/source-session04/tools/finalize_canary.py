"""Consolidate observed offline tests and allowlisted preservation; never access market payloads."""

from __future__ import annotations
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter

from btc_quant_agent.platform.canary.clocks import Capture, ClockEstimate, NativeClock, Probe
from btc_quant_agent.platform.canary.policy import ROOT, SourceGrant, load_catalog, load_policy, budget_plan
from btc_quant_agent.platform.canary.warmup import contract
from btc_quant_agent.platform.core import primitive
from btc_quant_agent.platform.reporting import source_identity

assert ROOT.name == "l4-readonly-source-canary-01"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def emit(name, value):
    p = ROOT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(primitive(value), sort_keys=True, indent=2, allow_nan=False) + "\n")


def main():
    policy = load_policy(ROOT / "configs/canary/offline.yaml")
    catalog = load_catalog(ROOT / "configs/canary/endpoints.json")
    before = json.loads((ROOT / "artifacts/preservation_before.json").read_text())
    copies = json.loads((ROOT / "artifacts/copy_manifest.json").read_text())["files"]
    baselines = {}
    for name, files in before["baselines"].items():
        changed = [
            p
            for p, s in files.items()
            if not (ROOT.parent / name / p).is_file() or sha(ROOT.parent / name / p) != s
        ]
        baselines[name] = {"recorded_files": len(files), "changed": changed, "unchanged": not changed}
    paths = {
        "R": ROOT.parent / "research-loop-bootstrap",
        "M": ROOT.parent.parent / "Quant-agent-market-watch",
        "Q": ROOT.parent.parent / "Quant-agent",
    }
    originals = {}
    for name, path in paths.items():

        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(path), *args], env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"}, text=True
            ).rstrip("\n")

        idx = Path(git("rev-parse", "--git-path", "index"))
        if not idx.is_absolute():
            idx = path / idx
        previous = before["original_worktrees"][name]
        current = {
            "head": git("rev-parse", "HEAD"),
            "status_porcelain": git("status", "--porcelain=v1", "--untracked-files=all"),
            "index_sha256": sha(idx) if idx.is_file() else None,
            "dirty_allowlisted_hashes": {
                rel: sha(path / rel) for rel in previous["dirty_allowlisted_hashes"]
            },
        }
        originals[name] = {
            "path": str(path),
            "before": previous,
            "after": current,
            "unchanged": previous == current,
        }
    inherited_tests = [p for p in copies if p.startswith("tests/")]
    test_changes = [p for p in inherited_tests if not (ROOT / p).is_file() or sha(ROOT / p) != copies[p]]
    preserved = (
        all(x["unchanged"] for x in baselines.values())
        and all(x["unchanged"] for x in originals.values())
        and not test_changes
    )
    preservation = {
        "task": before["task"],
        "before_receipt": "artifacts/preservation_before.json",
        "original_worktrees": originals,
        "baselines": baselines,
        "inherited_test_sources": {"recorded": len(inherited_tests), "changed": test_changes},
        "pre_creation_worker_check": before["worker_check"],
        "exclusive_workspace": "artifacts/task_ownership.json",
        "recorded_scope_preserved": preserved,
        "collector_control_operations": 0,
        "protected_data_reads": 0,
        "registry_or_PRIMARY_operations": 0,
        "commits_pushes_deployments_integrations": 0,
        "limits": [
            "Only allowlisted source/config/tests/receipts and original HEAD/index/status/recorded dirty source hashes were read.",
            "Private/runtime datasets and collector payloads were deliberately not hashed or opened; external runtime changes are not excluded.",
            "No new L4 worker, daemon, scheduled task or successor was created. Test subprocesses are finite and reaped.",
            "R README has a pre/post dirty-content hash in this receipt; previous L23 missing-first-status-line limitation is not repeated.",
        ],
    }
    emit("L4_PRESERVATION.json", preservation)
    inventory = {}
    for directory in ("src", "tests", "configs", "tools"):
        for p in sorted((ROOT / directory).rglob("*")):
            if (
                p.is_file()
                and p.suffix in (".py", ".yaml", ".yml", ".json", ".toml", ".csv", ".html")
                and "__pycache__" not in p.parts
            ):
                inventory[str(p.relative_to(ROOT))] = sha(p)
    inventory["pyproject.toml"] = sha(ROOT / "pyproject.toml")
    changes = []
    diffs = []
    for p, s in inventory.items():
        if copies.get(p) == s:
            continue
        previous = ROOT.parent / "l23-selector-evaluation-01" / p
        old = previous.read_text().splitlines(True) if p in copies else []
        new = (ROOT / p).read_text().splitlines(True)
        diffs.extend(
            difflib.unified_diff(old, new, fromfile="l23/" + p if old else "/dev/null", tofile="l4/" + p)
        )
        changes.append(
            {
                "path": p,
                "status": "MODIFIED" if p in copies else "ADDED",
                "before_sha256": copies.get(p),
                "after_sha256": s,
            }
        )
    (ROOT / "artifacts/source.diff").write_text("".join(diffs))
    aggregate = hashlib.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    emit(
        "artifacts/source_sha256.json",
        {
            "hash_algorithm": "SHA256",
            "files": inventory,
            "aggregate_sha256": aggregate,
            "project_native_source_identity": source_identity(ROOT),
            "pre_copy": "artifacts/copy_manifest.json",
        },
    )
    emit(
        "artifacts/changed_file_manifest.json",
        {
            "allowlist": [
                "src/**.py",
                "tests/**.py",
                "configs/**.yaml/json",
                "tools/**.py",
                "pyproject.toml",
            ],
            "changes": changes,
            "deleted": sorted(p for p in copies if not (ROOT / p).exists()),
            "source_diff": "artifacts/source.diff",
            "source_diff_sha256": sha(ROOT / "artifacts/source.diff"),
        },
    )
    runs = []
    specs = [
        (
            "L4_L23_bridge",
            "artifacts/logs/l4_l23_bridge_final.xml",
            ".venv/bin/python tools/offline_pytest.py tests/canary tests/selection tests/bridge -q --tb=short --junitxml=artifacts/logs/l4_l23_bridge_final.xml",
        ),
        (
            "platform_foundation",
            "artifacts/logs/platform_foundation.xml",
            "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ../multi-strategy-platform-01/.venv/bin/python tools/offline_pytest.py tests/platform tests/test_advisory_foundation_completion.py tests/test_structure.py -q --tb=short --junitxml=artifacts/logs/platform_foundation.xml",
        ),
        (
            "legacy_known_red",
            "artifacts/logs/legacy_known_red.xml",
            "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:tests ../multi-strategy-platform-01/.venv/bin/python tools/offline_pytest.py tests/test_advisory_foundation.py tests/test_market_watch.py tests/test_live_v1_decision_e2e.py -q --tb=short --junitxml=artifacts/logs/legacy_known_red.xml",
        ),
    ]
    allcases = {}
    for name, rel, cmd in specs:
        cases = []
        for n in ET.parse(ROOT / rel).iter("testcase"):
            outcome = (
                "FAILED"
                if n.find("failure") is not None
                else "ERROR"
                if n.find("error") is not None
                else "SKIPPED"
                if n.find("skipped") is not None
                else "PASSED"
            )
            case = {
                "id": n.attrib["classname"] + "::" + n.attrib["name"],
                "status": outcome,
                "seconds": float(n.attrib.get("time", 0)),
            }
            cases.append(case)
            assert case["id"] not in allcases
            allcases[case["id"]] = case
        runs.append(
            {
                "name": name,
                "command": cmd,
                "xml": rel,
                "xml_sha256": sha(ROOT / rel),
                "counts": dict(Counter(c["status"] for c in cases)),
                "cases": cases,
            }
        )
    counts = dict(Counter(c["status"] for c in allcases.values()))
    failed = [c["id"] for c in allcases.values() if c["status"] == "FAILED"]
    replacements = [c for c in allcases.values() if "test_contract_reconciliation" in c["id"]]
    assert len(failed) == 3 and counts.get("ERROR", 0) == counts.get("SKIPPED", 0) == 0
    assert {x.split("::")[-1] for x in failed} == {
        "test_gated_data_never_attempts_notification",
        "test_r2_01_two_run_scanner_breakout_persist_to_retest_triggered",
        "test_mocked_provider_market_watch_to_durable_approval",
    }
    assert len(replacements) == 3 and all(c["status"] == "PASSED" for c in replacements)
    assert not test_changes and preserved
    static = {}
    for name in ("ruff", "mypy", "compile"):
        content = (ROOT / "artifacts/logs" / f"{name}.log").read_text()
        assert (
            "All checks passed!"
            if name == "ruff"
            else "Success: no issues found"
            if name == "mypy"
            else "COMPILE_OK"
        ) in content
        static_commands = {
            "ruff": ".venv/bin/python -m ruff check src/btc_quant_agent/platform/canary src/btc_quant_agent/platform/selection src/btc_quant_agent/platform/cli.py tests/canary tests/selection tools/canary_worker.py tools/finalize_canary.py",
            "mypy": "env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src ../multi-strategy-platform-01/.venv/bin/python -m mypy --no-incremental --cache-dir /tmp/l4-mypy-last",
            "compile": "Compile 28 scoped source/test/tool files using compile(path.read_bytes(), str(path), 'exec'); no module execution",
        }
        static[name] = {
            "command": static_commands[name],
            "status": "PASSED",
            "log": f"artifacts/logs/{name}.log",
            "sha256": sha(ROOT / "artifacts/logs" / f"{name}.log"),
        }
    emit(
        "L4_TEST_MATRIX.json",
        {
            "unique_counts": counts,
            "runs": runs,
            "static": static,
            "replacement_tests": replacements,
            "known_red_tests": failed,
            "new_L4_passes": sum(
                c["status"] == "PASSED" and c["id"].startswith("tests.canary.") for c in allcases.values()
            ),
            "multiprocess_evidence": [
                c
                for c in allcases.values()
                if any(
                    word in c["id"]
                    for word in ("genuine", "process_restart", "process_reserv", "crash", "sender_failures")
                )
            ],
            "no_skips_xfails_or_assertion_rewrites": True,
            "warnings": ["Inherited sklearn SVC probability deprecation warning; smoke training passed."],
            "source_sha256_aggregate": aggregate,
        },
    )
    report = json.loads((ROOT / "artifacts/final/canary/report.json").read_text())
    plan = budget_plan(policy, catalog)
    endpoint_matrix = {
        "version": "L4-SOURCE-GRANT-MATRIX-1",
        "task": before["task"],
        "status": "OFFLINE_READY_PENDING_AUTH",
        "canonical_docs_head": before["canonical_docs_head"],
        "owner_grant": None,
        "grant_present": False,
        "real_transport_implemented": False,
        "market_transport_network_calls": 0,
        "documentation_network_access": "Documentation only; reviewed 2026-10-29",
        "proposal_2026_11_01_to_2026_11_02_02_UTC": "UNAPPROVED_NOT_SCHEDULED",
        "policy": policy.model_dump(),
        "policy_sha256": policy.hash,
        "endpoint_matrix": list(catalog.values()),
        "budget_preflight": plan,
        "warmup_contract": contract(),
        "exact_future_grant_required": [
            "provider and legal region with confirmed eligible hosts",
            "market and instrument/contract identity",
            "every public endpoint/stream and native fields",
            "symbols: start BTCUSDT/ETHUSDT/SOLUSDT only; separate explicit expansion scope",
            "UTC start/end; no proposed time is approved",
            "endpoint calls, IP weight including retry/repair reserve, WS subscriptions/controls/connections/reconnect budgets",
            "total/symbol/chunk bytes, 36h rolling raw and 7d normalized expiry (24h alternative must declare EARLIEST_RAW_NOT_RETAINED)",
            "isolated output, current documentation fingerprint and explicit permitted-use/terms status",
        ],
        "blocking_dependencies": [
            "BLOCKED_PENDING_OWNER_AUTH: exact public source grant absent",
            "Current endpoint/IP ceilings, Owner legal region, terms and actual deployed schema must be freshly verified",
            "Raw estimate exceeds the fabricated 16 MiB quota; no real acquisition approved under this quota",
            "PremiumIndex time authority/funding cadence, regular kline WS clock and spot/OKX details remain unverified",
            "3-symbol stage cannot support >=10-member ranks; beta needs >=201 aligned bars, strict 288-return reference >=289",
            "No market network implementation exists in Phase A; a grant cannot enable a socket",
        ],
        "retention_contract": {
            "recommendation_raw_hours": 36,
            "normalized_hours": 168,
            "pilot_hours_proposed_only": 26,
            "minimum_earliest_raw_remaining_hours_at_26h": 10,
            "24h_alternative": "Audited immutable prefix manifest retained; expired raw cannot be replayed and is explicitly labeled.",
            "quota_behavior": "Optional DIAGNOSTIC shedding is counted. Essential quota failure closes scripted session with STORAGE_BLOCKED.",
            "atomicity": "fsync -> atomic rename -> SQLite manifest commit; actual subprocess crash recovery tested.",
            "stop": "Explicit UTC equality stop closes scripted subscriptions, audits hashes and replay; no timer, daemon or polling.",
        },
    }
    emit("L4_SOURCE_GRANT_AND_ENDPOINT_MATRIX.json", endpoint_matrix)
    emit("artifacts/final/source_grant.schema.json", SourceGrant.model_json_schema())
    clock_schema = {
        "version": "L4-CLOCK-RECEIPT-1",
        "classes": {
            c.__name__: list(c.__dataclass_fields__) for c in (Capture, NativeClock, Probe, ClockEstimate)
        },
        "wall_time_unit": "UTC epoch milliseconds",
        "monotonic_time_unit": "milliseconds in declared local boot/process clock domain",
        "latency_semantics": [
            "measured_local_elapsed is monotonic",
            "event_to_receive_estimate bounds include conservative clock offset uncertainty",
            "No one-way latency proof; unknown native timestamp cannot be manufactured by probes",
            "native E/T/publish retained separately; L23 event<=receive remains mandatory",
            "Actual delivery/acknowledgement are UNKNOWN unless independently observed; L23 delayed scenarios remain explicitly fabricated assumptions",
        ],
        "source_identity": "provider/host/market/symbol/interval/units plus raw SHA256 and immutable metadata binding",
        "recovery": "1m/5m cursors independent; gap ranges accumulate. Later repairs retain actual availability and never backdate L23 features.",
    }
    emit("artifacts/final/clock_receipt_contract.json", clock_schema)
    feeds = []
    for e in catalog.values():
        feeds.append(
            {
                "id": e.id,
                "matrix_status": e.status,
                "actual_source_status": "SOURCE_CLOCK_BLOCKED"
                if e.timestamp_semantics == "UNKNOWN"
                else "UNVERIFIED_NATIVE",
                "authorization": "BLOCKED_PENDING_OWNER_AUTH",
                "native_observations": 0,
                "source_qualified": False,
                "shadow_advisory_qualified": False,
                "native_timestamp_semantics": e.timestamp_semantics,
                "documentation_reference": e.documentation["reference_url"],
                "synthetic_fixture_class": "FABRICATED_ONLY"
                if e.id
                in (
                    "binance_usdm_exchange_info",
                    "binance_usdm_bbo_ws",
                    "binance_usdm_klines_rest",
                    "binance_usdm_klines_ws",
                    "binance_usdm_oi",
                    "binance_usdm_premium",
                )
                else "SCHEMA_OR_BUDGET_ONLY_NOT_NATIVE_TESTED",
            }
        )
    emit(
        "L4_SOURCE_HEALTH.json",
        {
            "status": "OFFLINE_READY_PENDING_AUTH",
            "feeds": feeds,
            "actual_received_market_payloads": 0,
            "synthetic_demo": {
                "bars": report["decoded_completed_5m_bars"],
                "quotes": report["quotes"],
                "replay": report["finalization"]["replay"],
                "readiness": report["readiness"],
                "report": "artifacts/final/canary/report.json",
            },
            "source_qualified": False,
            "shadow_advisory_qualified": False,
            "economically_validated": False,
            "optional_failure_contract": "Bad OI/funding disables dependent decisions only. Independent valid price can support WATCH/RISK; missing quote/funding/essential risk blocks ACTION.",
        },
    )
    acceptance = {
        "task": before["task"],
        "status": "OFFLINE_READY_PENDING_AUTH",
        "phase_A": "ACCEPT_OFFLINE_ENGINEERING_ONLY",
        "phase_B": "BLOCKED_PENDING_OWNER_AUTH",
        "phase_C": "BLOCKED_PENDING_OWNER_AUTH",
        "source_qualified": False,
        "shadow_advisory_qualified": False,
        "economically_validated": False,
        "unique_test_counts": counts,
        "new_L4_tests": sum(c["id"].startswith("tests.canary.") for c in allcases.values()),
        "three_original_legacy_failures": failed,
        "separate_passing_replacements": len(replacements),
        "source_sha256_aggregate": aggregate,
        "policy_sha256": policy.hash,
        "preserved_recorded_scope": preserved,
        "source_transport_network_calls": 0,
        "external_notifications": 0,
        "orders_or_account_operations": 0,
        "normalization_replay": report["finalization"]["replay"],
        "terminal_behavior": "Exit now; no grant request, wait, standing automation, successor or reviewer chain.",
        "artifacts": {
            "tests": "L4_TEST_MATRIX.json",
            "preservation": "L4_PRESERVATION.json",
            "matrix": "L4_SOURCE_GRANT_AND_ENDPOINT_MATRIX.json",
            "health": "L4_SOURCE_HEALTH.json",
            "source": "artifacts/source_sha256.json",
            "diff": "artifacts/source.diff",
            "manifest": "artifacts/changed_file_manifest.json",
            "json": "artifacts/final/canary/report.json",
            "html": "artifacts/final/canary/report.html",
        },
    }
    emit("L4_ACCEPTANCE.json", acceptance)
    return acceptance


if __name__ == "__main__":
    print(json.dumps(main(), indent=2))
