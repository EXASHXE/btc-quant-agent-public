"""Deterministic surface catalog generator for BTC Quant Agent v0.4.2 A01.

Inspects source modules, tests, persisted surfaces, frozen surfaces,
historical runners, CLI entrypoints, and API routes without touching
operational stores or sealed evidence.
"""

from __future__ import annotations

import argparse
import ast
import glob
import json
import subprocess
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0.0"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def get_git_head_sha() -> str:
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except (subprocess.SubprocessError, OSError):
        return "UNKNOWN"


def count_physical_loc(filepath: Path) -> int:
    with open(filepath, "rb") as f:
        return sum(1 for _ in f)


def find_imports_in_file(filepath: Path) -> list[tuple[str, str | None]]:
    try:
        content = filepath.read_text(encoding="utf-8")
        tree = ast.parse(content)
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    imported: list[tuple[str, str | None]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                imported.append((n.name, None))
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for n in node.names:
                imported.append((mod, n.name))
    return imported


def build_import_graph(
    source_files: list[Path], test_files: list[Path]
) -> dict[str, list[str]]:
    consumers: dict[str, list[str]] = {}
    for p in source_files:
        rel = p.relative_to(REPOSITORY_ROOT).as_posix()
        consumers[rel] = []

    all_inspect_files = source_files + test_files
    for f in all_inspect_files:
        rel_f = f.relative_to(REPOSITORY_ROOT).as_posix()
        imports = find_imports_in_file(f)
        for mod, symbol in imports:
            if mod.startswith("btc_quant_agent."):
                sub = mod[len("btc_quant_agent.") :]
                cand1 = f"src/btc_quant_agent/{sub.replace('.', '/')}.py"
                cand2 = f"src/btc_quant_agent/{sub.replace('.', '/')}/__init__.py"
                if cand1 in consumers and rel_f not in consumers[cand1] and rel_f != cand1:
                    consumers[cand1].append(rel_f)
                if cand2 in consumers and rel_f not in consumers[cand2] and rel_f != cand2:
                    consumers[cand2].append(rel_f)
            elif mod == "btc_quant_agent":
                cand = "src/btc_quant_agent/__init__.py"
                if cand in consumers and rel_f not in consumers[cand] and rel_f != cand:
                    consumers[cand].append(rel_f)
                if symbol:
                    cand_sym = f"src/btc_quant_agent/{symbol}.py"
                    if (
                        cand_sym in consumers
                        and rel_f not in consumers[cand_sym]
                        and rel_f != cand_sym
                    ):
                        consumers[cand_sym].append(rel_f)
            for target_rel in list(consumers.keys()):
                stem = Path(target_rel).stem
                if (
                    mod == stem
                    or mod.endswith(f".{stem}")
                    or (mod.startswith("..") and stem in mod)
                ) and rel_f not in consumers[target_rel] and rel_f != target_rel:
                    consumers[target_rel].append(rel_f)

    for v in consumers.values():
        v.sort()
    return consumers


def get_subsystem(rel_path: str) -> str:
    if rel_path.startswith("src/btc_quant_agent/economic/"):
        return "economic"
    if rel_path.startswith("src/btc_quant_agent/research_contract/"):
        return "research_contract"
    if rel_path.startswith("src/btc_quant_agent/data/"):
        return "data"
    if rel_path in (
        "src/btc_quant_agent/microstructure.py",
        "src/btc_quant_agent/h39_baseline.py",
        "src/btc_quant_agent/h39_input.py",
        "src/btc_quant_agent/h39_statistics.py",
        "src/btc_quant_agent/microstructure_research.py",
    ):
        return "h39_microstructure"
    if rel_path in (
        "src/btc_quant_agent/evidence_epoch.py",
        "src/btc_quant_agent/opportunity_forward.py",
        "src/btc_quant_agent/forward_evidence.py",
        "src/btc_quant_agent/forward_diagnostics.py",
    ):
        return "forward_operations"
    if rel_path in (
        "src/btc_quant_agent/research.py",
        "src/btc_quant_agent/funnel_research.py",
        "src/btc_quant_agent/mechanism_research.py",
        "src/btc_quant_agent/geometry_research.py",
        "src/btc_quant_agent/causal_entry_research.py",
        "src/btc_quant_agent/breakout_edge_research.py",
        "src/btc_quant_agent/directional_architecture_research.py",
        "src/btc_quant_agent/funding_crowding_research.py",
        "src/btc_quant_agent/funding_stability_research.py",
        "src/btc_quant_agent/cross_asset_breadth_research.py",
        "src/btc_quant_agent/range_mean_reversion_research.py",
        "src/btc_quant_agent/spot_perp_flow_research.py",
    ):
        return "historical_runners"
    if rel_path.startswith("src/btc_quant_agent/symbolic_alpha/"):
        return "symbolic_alpha"
    if rel_path in (
        "src/btc_quant_agent/backtest.py",
        "src/btc_quant_agent/shadow.py",
        "src/btc_quant_agent/domain.py",
        "src/btc_quant_agent/features.py",
        "src/btc_quant_agent/indicators.py",
        "src/btc_quant_agent/regime.py",
        "src/btc_quant_agent/structure.py",
        "src/btc_quant_agent/directional_episode.py",
        "src/btc_quant_agent/engine.py",
        "src/btc_quant_agent/strategies.py",
        "src/btc_quant_agent/multifactor.py",
        "src/btc_quant_agent/risk.py",
        "src/btc_quant_agent/funnel.py",
        "src/btc_quant_agent/mechanism.py",
        "src/btc_quant_agent/research_protocol.py",
        "src/btc_quant_agent/research_registry.py",
    ):
        return "legacy_signal_backtest"
    if rel_path in (
        "src/btc_quant_agent/cli.py",
        "src/btc_quant_agent/api.py",
        "src/btc_quant_agent/service.py",
        "src/btc_quant_agent/storage.py",
        "src/btc_quant_agent/config.py",
        "src/btc_quant_agent/explain.py",
        "src/btc_quant_agent/__init__.py",
        "src/btc_quant_agent/__main__.py",
    ):
        return "entry_cli_api"
    if rel_path.startswith("src/btc_quant_agent/execution/"):
        return "execution"
    if rel_path.startswith("src/btc_quant_agent/notify/"):
        return "notify"
    return "unknown"


def get_classification_and_target(rel_path: str) -> tuple[str, str, str]:
    """Returns (classification, reason, future_target)."""
    # 1. Historical research runners -> ARCHIVE_CANDIDATE
    if rel_path in (
        "src/btc_quant_agent/research.py",
        "src/btc_quant_agent/funnel_research.py",
        "src/btc_quant_agent/mechanism_research.py",
        "src/btc_quant_agent/geometry_research.py",
        "src/btc_quant_agent/causal_entry_research.py",
        "src/btc_quant_agent/breakout_edge_research.py",
        "src/btc_quant_agent/directional_architecture_research.py",
        "src/btc_quant_agent/funding_crowding_research.py",
        "src/btc_quant_agent/funding_stability_research.py",
        "src/btc_quant_agent/cross_asset_breadth_research.py",
        "src/btc_quant_agent/range_mean_reversion_research.py",
        "src/btc_quant_agent/spot_perp_flow_research.py",
    ):
        return (
            "ARCHIVE_CANDIDATE",
            ("Historical v0.3.x research family runner; archive once shared mathematical "
            "and statistical helpers are extracted to core and compatibility replay is verified."),
            "archive/v03/historical_runners",
        )

    # 2. Symbolic alpha modules
    if rel_path in (
        "src/btc_quant_agent/symbolic_alpha/ast.py",
        "src/btc_quant_agent/symbolic_alpha/grammar.py",
    ):
        return (
            "MERGE_CANDIDATE",
            ("Formula AST grammar and definitions to preserve as read-only compatibility "
            "formula loader."),
            "contracts/formula_dsl",
        )
    if rel_path.startswith("src/btc_quant_agent/symbolic_alpha/"):
        return (
            "ARCHIVE_CANDIDATE",
            ("Stopped symbolic search, evaluation, and sandbox execution; candidate for "
            "archival after formula loader isolation."),
            "archive/v03/symbolic_alpha",
        )

    # 3. Legacy signal, backtest, and diagnostics
    if rel_path in ("src/btc_quant_agent/backtest.py", "src/btc_quant_agent/shadow.py"):
        return (
            "ARCHIVE_CANDIDATE",
            ("Legacy trade and shadow simulation engine; superseded by formal economics replay loop. "
            "Archival blocked by backtest.FundingEvent imports in data/funding.py."),
            "archive/v03/legacy_backtest",
        )
    if rel_path in ("src/btc_quant_agent/funnel.py", "src/btc_quant_agent/mechanism.py"):
        return (
            "ARCHIVE_CANDIDATE",
            "Historical explanatory diagnostic modules for v0.3.1-v0.3.2 deliverables.",
            "archive/v03/diagnostics",
        )
    if rel_path in (
        "src/btc_quant_agent/domain.py",
        "src/btc_quant_agent/features.py",
        "src/btc_quant_agent/indicators.py",
        "src/btc_quant_agent/regime.py",
        "src/btc_quant_agent/structure.py",
        "src/btc_quant_agent/directional_episode.py",
        "src/btc_quant_agent/engine.py",
        "src/btc_quant_agent/strategies.py",
        "src/btc_quant_agent/multifactor.py",
        "src/btc_quant_agent/risk.py",
        "src/btc_quant_agent/research_protocol.py",
        "src/btc_quant_agent/research_registry.py",
    ):
        return (
            "MERGE_CANDIDATE",
            ("Legacy market/strategy/risk components with active opportunity detection dependencies; "
            "target convergence into contracts/ and features/ without independent economic authority."),
            "contracts/ and features/",
        )

    # 4. Economic subsystem
    if rel_path == "src/btc_quant_agent/economic/benchmarks.py":
        return (
            "PRESERVE_ONLY",
            ("Legacy benchmark formula helper; retained as historical diagnostic reference until "
            "acceptance verification replay fully replaces it."),
            "qualification/legacy_benchmarks",
        )
    if rel_path == "src/btc_quant_agent/economic/qualification.py":
        return (
            "MERGE_CANDIDATE",
            ("Core qualification logic mixed with diagnostic report rendering and duplicate "
            "matching schema checks; target convergence into pure gate evaluator."),
            "qualification/gates",
        )
    if rel_path.startswith("src/btc_quant_agent/economic/"):
        return (
            "CORE",
            "Formal causal economic kernel, cash accounting, fee/funding models, and replay loop.",
            "economics/",
        )

    # 5. Research contract subsystem
    if rel_path.startswith("src/btc_quant_agent/research_contract/"):
        return (
            "CORE",
            "P5 research experiment contracts, canonical hashing, and experiment registry.",
            "contracts/ and qualification/registry",
        )

    # 6. Data subsystem
    if rel_path == "src/btc_quant_agent/data/funding.py":
        return (
            "MERGE_CANDIDATE",
            ("Data funding pipeline currently importing backtest.FundingEvent; needs extraction "
            "to canonical contracts."),
            "data/funding",
        )
    if rel_path.startswith("src/btc_quant_agent/data/"):
        return (
            "CORE",
            "Point-in-time validation, public transport, store transactions, and candle stores.",
            "data/",
        )

    # 7. H39 / Microstructure
    if rel_path == "src/btc_quant_agent/microstructure_research.py":
        return (
            "MERGE_CANDIDATE",
            ("Combines authoritative v0.3.26 H39 boundary logic with deprecated diagnostics "
            "and legacy v0.3.22 report generators."),
            "forward/h39/ and archive/v03/reports",
        )
    if rel_path in (
        "src/btc_quant_agent/microstructure.py",
        "src/btc_quant_agent/h39_baseline.py",
        "src/btc_quant_agent/h39_input.py",
        "src/btc_quant_agent/h39_statistics.py",
    ):
        return (
            "CORE",
            "Microstructure partition store and frozen H39 statistical rules and input contracts.",
            "forward/h39/ and data/microstructure",
        )

    # 8. Forward operations
    if rel_path in (
        "src/btc_quant_agent/forward_diagnostics.py",
        "src/btc_quant_agent/forward_evidence.py",
    ):
        return (
            "MERGE_CANDIDATE",
            "Forward health aggregation and evidence auditing; target unified read-only health model.",
            "diagnostics/health",
        )
    if rel_path in (
        "src/btc_quant_agent/evidence_epoch.py",
        "src/btc_quant_agent/opportunity_forward.py",
    ):
        return (
            "CORE",
            "Forward evidence lifecycle and opportunity forward collection campaign orchestration.",
            "forward/lifecycle and forward/shadow",
        )

    # 9. CLI, API, entrypoints
    if rel_path in ("src/btc_quant_agent/cli.py", "src/btc_quant_agent/api.py"):
        return (
            "MERGE_CANDIDATE",
            ("Monolithic CLI parser / API routers; target thin command handlers and optional "
            "read-only API views."),
            "cli/ and diagnostics/api",
        )
    if rel_path == "src/btc_quant_agent/storage.py":
        return (
            "MERGE_CANDIDATE",
            "Runtime quant.db SQLite repository; target explicit typed schemas and read-only loader.",
            "data/runtime_store",
        )
    if rel_path in (
        "src/btc_quant_agent/__init__.py",
        "src/btc_quant_agent/__main__.py",
        "src/btc_quant_agent/service.py",
        "src/btc_quant_agent/config.py",
        "src/btc_quant_agent/explain.py",
    ):
        return (
            "CORE",
            "Package entrypoints, daemon service loop, configuration loading, and signal explanation.",
            "core/ and cli/",
        )

    # 10. Execution boundary
    if rel_path in (
        "src/btc_quant_agent/execution/binance_client.py",
        "src/btc_quant_agent/execution/binance_public.py",
        "src/btc_quant_agent/execution/binance_signed.py",
    ):
        return (
            "OPTIONAL_ADAPTER",
            "External exchange HTTP transport adapters; signed execution strictly disabled by default.",
            "execution_boundary/adapters",
        )
    if rel_path in (
        "src/btc_quant_agent/execution/__init__.py",
        "src/btc_quant_agent/execution/order_manager.py",
    ):
        return (
            "CORE",
            "Execution order lifecycle management and fail-closed state tracking.",
            "execution_boundary/orders",
        )

    # 11. Notification
    if rel_path.startswith("src/btc_quant_agent/notify/"):
        return (
            "OPTIONAL_ADAPTER",
            "Optional one-way outbound notification webhook adapter.",
            "diagnostics/notify",
        )

    return ("CORE", "General production module.", "core/")


def get_cli_entrypoints() -> list[str]:
    import sys

    sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
    from btc_quant_agent import cli

    parser = cli.build_parser()

    def get_leaves(p: Any, prefix: str = "") -> list[str]:
        leaves: list[str] = []
        subparsers_actions = [
            action
            for action in p._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        if not subparsers_actions:
            leaves.append(prefix.strip())
        else:
            for spa in subparsers_actions:
                for subcmd, subp in spa.choices.items():
                    sub_prefix = f"{prefix} {subcmd}" if prefix else subcmd
                    leaves.extend(get_leaves(subp, sub_prefix))
        return leaves

    return sorted(get_leaves(parser))


def get_api_routes() -> list[dict[str, str]]:
    api_path = REPOSITORY_ROOT / "src/btc_quant_agent/api.py"
    tree = ast.parse(api_path.read_text(encoding="utf-8"))
    routes: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and isinstance(dec.func, ast.Attribute)
                    and dec.func.attr in ("get", "post", "put", "delete", "patch")
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                ):
                    routes.append(
                        {
                            "method": dec.func.attr.upper(),
                            "path": str(dec.args[0].value),
                            "handler": node.name,
                        }
                    )
    routes.sort(key=lambda x: (x["path"], x["method"]))
    return routes


def build_persisted_surfaces() -> list[dict[str, Any]]:
    return [
        {
            "logical_name": "Runtime Operational SQLite",
            "path_pattern": "var/quant.db",
            "owner_module": "src/btc_quant_agent/storage.py",
            "schema_version": "1.0.0",
            "role": "Runtime signals, opportunities, shadow_trades, execution plans/events, decision logs",
            "migration_rule": "Explicit columns, schema versioning, read-only loader for old schemas, fail-closed under test",
            "sealed_or_mutable": "MUTABLE_OPERATIONAL",
        },
        {
            "logical_name": "Forward Derivatives PIT Store",
            "path_pattern": "data/forward/BTCUSDT/derivatives.sqlite3",
            "owner_module": "src/btc_quant_agent/data/forward_store.py",
            "schema_version": "1.0.0",
            "role": "Forward derivative snapshots and collection run records",
            "migration_rule": "Preserve receipt/event/slot/epoch/attempt identities; additive successor schema only",
            "sealed_or_mutable": "MUTABLE_OPERATIONAL",
        },
        {
            "logical_name": "Opportunity Forward Store",
            "path_pattern": "data/forward/BTCUSDT/opportunity_shadow.sqlite3",
            "owner_module": "src/btc_quant_agent/data/opportunity_shadow.py",
            "schema_version": "1.0.0",
            "role": "Forward scan observations, directionless outcome evaluations, integrity audit events",
            "migration_rule": "Preserve campaign identities, unresolved/mature status, and terminal history",
            "sealed_or_mutable": "MUTABLE_OPERATIONAL",
        },
        {
            "logical_name": "Microstructure Raw Partitions",
            "path_pattern": "data/forward/BTCUSDT/microstructure/microstructure-YYYY-MM-DD.sqlite3",
            "owner_module": "src/btc_quant_agent/microstructure.py",
            "schema_version": "1.0.0",
            "role": "High-frequency depth events, agg_trades, book_samples, gaps, sessions, and clocks",
            "migration_rule": "Immutable partition hashes, WAL checkpointing; no in-place schema mutation",
            "sealed_or_mutable": "APPEND_ONLY_OPERATIONAL",
        },
        {
            "logical_name": "Partition Finalization Manifest and Cache",
            "path_pattern": "data/forward/BTCUSDT/microstructure/finalized-partitions.*.json",
            "owner_module": "src/btc_quant_agent/microstructure.py",
            "schema_version": "1.0.0",
            "role": "Cryptographic SHA-256 seal of completed microstructure partitions; stats cache",
            "migration_rule": "Manifest authoritative and crash-safe; stats cache disposable and never an authority",
            "sealed_or_mutable": "FROZEN_MANIFEST",
        },
        {
            "logical_name": "H39 Canonical 1m Candle Store",
            "path_pattern": "data/forward/BTCUSDT/h39_canonical_1m_candles.sqlite3",
            "owner_module": "src/btc_quant_agent/microstructure_research.py",
            "schema_version": "1.0.0",
            "role": "Deterministic Binance 1m klines used for reference price and return computation",
            "migration_rule": "Distinguish causal baseline inputs from future outcomes; diagnostics must not load future ranges",
            "sealed_or_mutable": "APPEND_ONLY_OPERATIONAL",
        },
        {
            "logical_name": "H39 Blind Validation Ledger",
            "path_pattern": "data/research/h39_validation/h39_blind_ledger.sqlite3",
            "owner_module": "src/btc_quant_agent/microstructure_research.py",
            "schema_version": "1.0.0",
            "role": "Blind forward feature rows, eligibility records, and partition provenance without future labels",
            "migration_rule": "Keep eligibility, input contract, source provenance, denominator, and immutable epoch",
            "sealed_or_mutable": "APPEND_ONLY_BLIND",
        },
        {
            "logical_name": "H39 Exactly-Once Registry and Manifests",
            "path_pattern": "data/research/h39_validation/h39_one_shot_execution_registry.sqlite3",
            "owner_module": "src/btc_quant_agent/microstructure_research.py",
            "schema_version": "1.0.0",
            "role": "Enforces single-execution unblind rule, immutable cutoff manifests, and hash binding",
            "migration_rule": "Snapshot hash, Git ancestry, protocol/clarifications, and consumed state preserved together",
            "sealed_or_mutable": "SEALED_AFTER_CONSUMPTION",
        },
        {
            "logical_name": "H39 Frozen Snapshots and Manifests",
            "path_pattern": "data/research/h39_validation/frozen/**",
            "owner_module": "src/btc_quant_agent/microstructure_research.py",
            "schema_version": "1.0.0",
            "role": "Immutable snapshots of validation state and cutoff preregistrations",
            "migration_rule": "Never rewrite frozen snapshots or change committed manifests",
            "sealed_or_mutable": "FROZEN_EVIDENCE",
        },
        {
            "logical_name": "P5 Research Experiment Registry",
            "path_pattern": "configs/research_registry.json (or caller-supplied JSON)",
            "owner_module": "src/btc_quant_agent/research_contract/registry.py",
            "schema_version": "1.0.0",
            "role": "Preregistered hypotheses, experiment revisions, candidate contracts, decision events",
            "migration_rule": "Preserve canonical hashes and event chains; verify CAS; new schemas read old revisions",
            "sealed_or_mutable": "STRUCTURED_EVENT_LOG",
        },
        {
            "logical_name": "P6 Economic Qualification Artifacts",
            "path_pattern": "artifacts/p6/** / caller-supplied qualification JSON",
            "owner_module": "src/btc_quant_agent/economic/qualification.py",
            "schema_version": "1.1.0",
            "role": "Formal candidate run, matched benchmark trials, comparison contracts, qualification verdicts",
            "migration_rule": "Immutable new evidence references; old artifacts viewable, unsupported for new promotion",
            "sealed_or_mutable": "IMMUTABLE_ARTIFACT",
        },
        {
            "logical_name": "Runtime Research and Formula Registries",
            "path_pattern": "configs/formula_registry*.json, configs/research_registry.json",
            "owner_module": "src/btc_quant_agent/research_registry.py",
            "schema_version": "1.0.0",
            "role": "Static research status, execution eligibility catalog, and symbolic formula metadata",
            "migration_rule": "Separate historical research status, execution ceiling, and formula metadata",
            "sealed_or_mutable": "READ_ONLY_CONFIG",
        },
        {
            "logical_name": "Frozen Protocols and Clarifications",
            "path_pattern": "configs/frozen/**, configs/research/**, deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_*.json",
            "owner_module": "src/btc_quant_agent/research_protocol.py",
            "schema_version": "1.0.0",
            "role": "Preregistered scientific research protocols and frozen clarifications 001-004",
            "migration_rule": "Byte-identical preservation; source constants are authoritative for exact locations",
            "sealed_or_mutable": "FROZEN_PROTOCOL",
        },
        {
            "logical_name": "Final Holdout Contract and Partition",
            "path_pattern": "final_holdout/** (partition reference in protocols)",
            "owner_module": "SEALED",
            "schema_version": "1.0.0",
            "role": "Out-of-sample holdout dataset strictly sealed until formal final evaluation",
            "migration_rule": "Strictly sealed; zero read, export, or parameter selection permitted",
            "sealed_or_mutable": "SEALED_FORBIDDEN",
        },
    ]


def build_frozen_surfaces() -> list[dict[str, str]]:
    return [
        {
            "path": "configs/frozen/v0.2.2.toml",
            "description": "Baseline v0.2.2 frozen runtime configuration",
            "role": "Historical baseline reference",
        },
        {
            "path": "configs/research/v0.3.1_funnel_protocol.json",
            "description": "Funnel research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.2_mechanism_protocol.json",
            "description": "Mechanism research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.3_geometry_protocol.json",
            "description": "Geometry research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.4_causal_entry_protocol.json",
            "description": "Causal entry research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.5_breakout_edge_protocol.json",
            "description": "Breakout edge research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.6_directional_architecture_protocol.json",
            "description": "Directional architecture research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.7_funding_crowding_protocol.json",
            "description": "Funding crowding research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.8_funding_stability_protocol.json",
            "description": "Funding stability research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.9_cross_asset_breadth_protocol.json",
            "description": "Cross-asset breadth research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.10_range_mean_reversion_protocol.json",
            "description": "Range mean reversion research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.12_spot_perp_flow_protocol.json",
            "description": "Spot-perp flow research protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.18_symbolic_derivatives_protocol.json",
            "description": "Symbolic alpha exploration protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/v0.3.19_symbolic_derivatives_refinement_protocol.json",
            "description": "Symbolic alpha refinement protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "configs/research/h39_microstructure_alpha_protocol.json",
            "description": "H39 microstructure alpha foundation protocol",
            "role": "Scientific preregistration",
        },
        {
            "path": "deliverables/v0.3.22/H39_PROTOCOL_CLARIFICATION_001.json",
            "description": "H39 Protocol Clarification 001: decision boundary and reference timing",
            "role": "Frozen clarification",
        },
        {
            "path": "deliverables/v0.3.25/H39_PROTOCOL_CLARIFICATION_002.json",
            "description": "H39 Protocol Clarification 002: temporal isolation and gap handling",
            "role": "Frozen clarification",
        },
        {
            "path": "deliverables/v0.3.25/H39_PROTOCOL_CLARIFICATION_003.json",
            "description": "H39 Protocol Clarification 003: sample maturity and wall-clock denominator",
            "role": "Frozen clarification",
        },
        {
            "path": "deliverables/v0.3.26/H39_PROTOCOL_CLARIFICATION_004.json",
            "description": "H39 Protocol Clarification 004: one-shot unblind preregistration binding",
            "role": "Frozen clarification",
        },
    ]


def build_historical_runners(
    consumers: dict[str, list[str]],
) -> list[dict[str, Any]]:
    runners = [
        {
            "name": "research.py",
            "path": "src/btc_quant_agent/research.py",
            "original_deliverable_root": "deliverables/v0.3.0",
            "original_protocol_reference": "configs/frozen/v0.2.2.toml",
            "shared_helper_dependencies_to_extract": [],
            "proposed_future_state": "archive/v03/historical_runners/research.py",
        },
        {
            "name": "funnel_research.py",
            "path": "src/btc_quant_agent/funnel_research.py",
            "original_deliverable_root": "deliverables/v0.3.1",
            "original_protocol_reference": "configs/research/v0.3.1_funnel_protocol.json",
            "shared_helper_dependencies_to_extract": [],
            "proposed_future_state": "archive/v03/historical_runners/funnel_research.py",
        },
        {
            "name": "mechanism_research.py",
            "path": "src/btc_quant_agent/mechanism_research.py",
            "original_deliverable_root": "deliverables/v0.3.2",
            "original_protocol_reference": "configs/research/v0.3.2_mechanism_protocol.json",
            "shared_helper_dependencies_to_extract": [],
            "proposed_future_state": "archive/v03/historical_runners/mechanism_research.py",
        },
        {
            "name": "geometry_research.py",
            "path": "src/btc_quant_agent/geometry_research.py",
            "original_deliverable_root": "deliverables/v0.3.3",
            "original_protocol_reference": "configs/research/v0.3.3_geometry_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "_mfe_mae",
                "_reachability_row",
                "_distribution",
            ],
            "proposed_future_state": "archive/v03/historical_runners/geometry_research.py",
        },
        {
            "name": "causal_entry_research.py",
            "path": "src/btc_quant_agent/causal_entry_research.py",
            "original_deliverable_root": "deliverables/v0.3.4",
            "original_protocol_reference": "configs/research/v0.3.4_causal_entry_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "IndexedOneMinuteSeries",
                "bootstrap_directionality",
                "_percentile",
                "match_controls",
            ],
            "proposed_future_state": "archive/v03/historical_runners/causal_entry_research.py",
        },
        {
            "name": "breakout_edge_research.py",
            "path": "src/btc_quant_agent/breakout_edge_research.py",
            "original_deliverable_root": "deliverables/v0.3.5",
            "original_protocol_reference": "configs/research/v0.3.5_breakout_edge_protocol.json",
            "shared_helper_dependencies_to_extract": ["_spearman", "_pearson"],
            "proposed_future_state": "archive/v03/historical_runners/breakout_edge_research.py",
        },
        {
            "name": "directional_architecture_research.py",
            "path": "src/btc_quant_agent/directional_architecture_research.py",
            "original_deliverable_root": "deliverables/v0.3.6",
            "original_protocol_reference": "configs/research/v0.3.6_directional_architecture_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "movement_label",
                "_pair_bootstrap",
                "_match_episode_pairs",
            ],
            "proposed_future_state": "archive/v03/historical_runners/directional_architecture_research.py",
        },
        {
            "name": "funding_crowding_research.py",
            "path": "src/btc_quant_agent/funding_crowding_research.py",
            "original_deliverable_root": "deliverables/v0.3.7",
            "original_protocol_reference": "configs/research/v0.3.7_funding_crowding_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "opportunity_union",
                "_cluster_bootstrap_median",
                "_permutation_analysis",
                "PRIMARY_HORIZONS",
                "StrictAfterPriceSeries",
            ],
            "proposed_future_state": "archive/v03/historical_runners/funding_crowding_research.py",
        },
        {
            "name": "funding_stability_research.py",
            "path": "src/btc_quant_agent/funding_stability_research.py",
            "original_deliverable_root": "deliverables/v0.3.8",
            "original_protocol_reference": "configs/research/v0.3.8_funding_stability_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "_interaction_analysis",
                "interaction_verdict",
            ],
            "proposed_future_state": "archive/v03/historical_runners/funding_stability_research.py",
        },
        {
            "name": "cross_asset_breadth_research.py",
            "path": "src/btc_quant_agent/cross_asset_breadth_research.py",
            "original_deliverable_root": "deliverables/v0.3.9",
            "original_protocol_reference": "configs/research/v0.3.9_cross_asset_breadth_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "btc_momentum_direction",
                "xab_direction",
            ],
            "proposed_future_state": "archive/v03/historical_runners/cross_asset_breadth_research.py",
        },
        {
            "name": "range_mean_reversion_research.py",
            "path": "src/btc_quant_agent/range_mean_reversion_research.py",
            "original_deliverable_root": "deliverables/v0.3.10",
            "original_protocol_reference": "configs/research/v0.3.10_range_mean_reversion_protocol.json",
            "shared_helper_dependencies_to_extract": [],
            "proposed_future_state": "archive/v03/historical_runners/range_mean_reversion_research.py",
        },
        {
            "name": "spot_perp_flow_research.py",
            "path": "src/btc_quant_agent/spot_perp_flow_research.py",
            "original_deliverable_root": "deliverables/v0.3.12",
            "original_protocol_reference": "configs/research/v0.3.12_spot_perp_flow_protocol.json",
            "shared_helper_dependencies_to_extract": [],
            "proposed_future_state": "archive/v03/historical_runners/spot_perp_flow_research.py",
        },
        {
            "name": "symbolic_alpha",
            "path": "src/btc_quant_agent/symbolic_alpha",
            "original_deliverable_root": "deliverables/v0.3.18, deliverables/v0.3.19",
            "original_protocol_reference": "configs/research/v0.3.18_symbolic_derivatives_protocol.json, configs/research/v0.3.19_symbolic_derivatives_refinement_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "symbolic_alpha/ast.py",
                "symbolic_alpha/grammar.py",
            ],
            "proposed_future_state": "archive/v03/symbolic_alpha; formula DSL preserved in contracts/formula_dsl",
        },
        {
            "name": "legacy_h39_report_generators",
            "path": "src/btc_quant_agent/microstructure_research.py (generate_all_v0322_deliverables, run_h39_pipeline, etc.)",
            "original_deliverable_root": "deliverables/v0.3.22, deliverables/v0.3.23, deliverables/v0.3.24",
            "original_protocol_reference": "configs/research/h39_microstructure_alpha_protocol.json",
            "shared_helper_dependencies_to_extract": [
                "H39ResearchEngine",
                "H39BlindLedger",
            ],
            "proposed_future_state": "archive/v03/reports/h39_report_generator.py; core H39 engine in forward/h39",
        },
    ]

    for r in runners:
        p = r["path"]
        r["current_imports_from_active_source_or_tests"] = consumers.get(p, [])

    return runners


def build_dependency_warnings() -> list[dict[str, Any]]:
    return [
        {
            "blocker_id": "BLOCKER_01_FUNDING_BACKTEST",
            "source_consumer": "src/btc_quant_agent/data/funding.py",
            "imported_symbol": "FundingEvent",
            "target_provider": "src/btc_quant_agent/backtest.py",
            "description": "Core data funding module imports FundingEvent from legacy backtest.py. "
            "Archive of backtest.py is blocked until FundingEvent is extracted to canonical contracts.",
            "remediation": "Extract FundingEvent to contracts/funding.py or economic/events.py.",
        },
        {
            "blocker_id": "BLOCKER_02_CAUSAL_ENTRY_HELPERS",
            "source_consumer": "src/btc_quant_agent/breakout_edge_research.py, directional_architecture_research.py, funding_crowding_research.py, funding_stability_research.py, cross_asset_breadth_research.py",
            "imported_symbol": "IndexedOneMinuteSeries, bootstrap_directionality, _percentile, match_controls",
            "target_provider": "src/btc_quant_agent/causal_entry_research.py",
            "description": "Multiple later research modules directly import indexed bar and bootstrap "
            "routines from causal_entry_research.py.",
            "remediation": "Extract IndexedOneMinuteSeries and bootstrap utilities to shared research helpers before D02 archival.",
        },
        {
            "blocker_id": "BLOCKER_03_BREAKOUT_SPEARMAN",
            "source_consumer": "src/btc_quant_agent/funding_crowding_research.py",
            "imported_symbol": "_spearman",
            "target_provider": "src/btc_quant_agent/breakout_edge_research.py",
            "description": "Funding crowding research imports rank correlation _spearman from breakout_edge_research.py.",
            "remediation": "Extract _spearman and _pearson to shared statistical kernels before D02 archival.",
        },
        {
            "blocker_id": "BLOCKER_04_DIRECTIONAL_MOVEMENT_LABEL",
            "source_consumer": "src/btc_quant_agent/funding_crowding_research.py",
            "imported_symbol": "movement_label",
            "target_provider": "src/btc_quant_agent/directional_architecture_research.py",
            "description": "Funding crowding research imports movement_label from directional_architecture_research.py.",
            "remediation": "Extract movement_label to features/movement.py before D02 archival.",
        },
        {
            "blocker_id": "BLOCKER_05_FUNDING_CROWDING_HELPERS",
            "source_consumer": "src/btc_quant_agent/funding_stability_research.py, cross_asset_breadth_research.py, spot_perp_flow_research.py",
            "imported_symbol": "opportunity_union, _cluster_bootstrap_median, _permutation_analysis, PRIMARY_HORIZONS, StrictAfterPriceSeries",
            "target_provider": "src/btc_quant_agent/funding_crowding_research.py",
            "description": "Funding stability, cross asset breadth, and spot perp flow runners depend on "
            "opportunity union and bootstrap routines from funding_crowding_research.py.",
            "remediation": "Extract shared resampling and funding feature utilities before D03 archival.",
        },
        {
            "blocker_id": "BLOCKER_06_TEST_SUITE_HISTORICAL_RUNNER_IMPORTS",
            "source_consumer": "tests/test_*_research.py (12 test modules)",
            "imported_symbol": "historical audit routines, assert_*_development_only",
            "target_provider": "src/btc_quant_agent/*_research.py",
            "description": "64 historical test cases directly import and exercise the 12 historical runner modules.",
            "remediation": "Preserve tests against archive compatibility package or mapped regression assertions.",
        },
    ]


def generate_catalog() -> dict[str, Any]:
    git_sha = get_git_head_sha()

    src_files = sorted(
        Path(p)
        for p in glob.glob(
            str(REPOSITORY_ROOT / "src/btc_quant_agent/**/*.py"), recursive=True
        )
    )
    test_files = sorted(
        Path(p)
        for p in glob.glob(str(REPOSITORY_ROOT / "tests/**/*.py"), recursive=True)
    )

    import_graph = build_import_graph(src_files, test_files)

    source_inventory: list[dict[str, Any]] = []
    subsystem_counts: dict[str, dict[str, int]] = {}
    classification_counts: dict[str, dict[str, int]] = {}

    for p in src_files:
        rel = p.relative_to(REPOSITORY_ROOT).as_posix()
        sub = get_subsystem(rel)
        loc = count_physical_loc(p)
        classification, reason, target = get_classification_and_target(rel)
        consumers = import_graph.get(rel, [])

        source_inventory.append(
            {
                "path": rel,
                "subsystem": sub,
                "physical_loc": loc,
                "classification": classification,
                "reason": reason,
                "active_importers_or_consumers": consumers,
                "future_target": target,
            }
        )

        if sub not in subsystem_counts:
            subsystem_counts[sub] = {"files": 0, "loc": 0}
        subsystem_counts[sub]["files"] += 1
        subsystem_counts[sub]["loc"] += loc

        if classification not in classification_counts:
            classification_counts[classification] = {"files": 0, "loc": 0}
        classification_counts[classification]["files"] += 1
        classification_counts[classification]["loc"] += loc

    source_inventory.sort(key=lambda x: str(x["path"]))

    persisted_surfaces = build_persisted_surfaces()
    frozen_surfaces = build_frozen_surfaces()
    historical_runners = build_historical_runners(import_graph)
    cli_entrypoints = get_cli_entrypoints()
    api_routes = get_api_routes()
    dependency_warnings = build_dependency_warnings()

    total_src_loc = sum(x["physical_loc"] for x in source_inventory)
    total_test_loc = sum(count_physical_loc(p) for p in test_files)

    summary = {
        "source_files_count": len(src_files),
        "source_physical_loc": total_src_loc,
        "test_files_count": len(test_files),
        "test_physical_loc": total_test_loc,
        "pytest_collected_cases": 813,
        "cli_leaf_count": len(cli_entrypoints),
        "api_routes_count": len(api_routes),
        "subsystem_breakdown": subsystem_counts,
        "classification_breakdown": classification_counts,
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_from_git_sha": git_sha,
        "source_inventory": source_inventory,
        "persisted_surfaces": persisted_surfaces,
        "frozen_surfaces": frozen_surfaces,
        "historical_runners": historical_runners,
        "cli_entrypoints": cli_entrypoints,
        "api_routes": api_routes,
        "dependency_warnings": dependency_warnings,
        "summary": summary,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate v0.4.2 A01 surface catalog"
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=REPOSITORY_ROOT
        / "reviews/v0.4/V0.4.2_A01_SURFACE_CATALOG.json",
        help="Path to output catalog JSON",
    )
    args = parser.parse_args()

    catalog = generate_catalog()
    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Generated catalog with {len(catalog['source_inventory'])} source files to {out_path}"
    )
    print(
        f"Summary: {catalog['summary']['source_files_count']} source files ({catalog['summary']['source_physical_loc']} LOC), "
        f"{catalog['summary']['test_files_count']} test files ({catalog['summary']['test_physical_loc']} LOC), "
        f"{catalog['summary']['cli_leaf_count']} CLI leaves, {catalog['summary']['api_routes_count']} API routes"
    )


if __name__ == "__main__":
    main()
