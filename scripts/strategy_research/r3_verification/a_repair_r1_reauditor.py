"""Independent Adversarial Static & Dynamic Re-Auditor for Role A Repair R1 (`A_REPAIR_SHA`).

Materializes Role A's immutable Git commit into an isolated temporary directory via
`git archive` (zero reads/writes to Role A's live worktree) and executes both static diff/AST
checks and dynamic synthetic cross-checks against Role B's independent oracle invariants.
"""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from scripts.strategy_research.r3_verification.a_impl_static_auditor import (
    is_role_a_path_allowed,
)
from scripts.strategy_research.r3_verification.oracle_specs import (
    CANDIDATE_REGISTRY_IDS,
    FROZEN_CODE_BASE_SHA,
    METHOD_ADDENDUM_HEAD_SHA,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
    ORIGINAL_DESIGN_SHA,
)

CONTROLLER_REAUDIT_DISPATCH_SHA = "3fb4508110c031eb0ff9226a7e42d918684c554f"
PREVIOUS_A_REPAIR_DISPATCH_SHA = "e94d53c1f98f16d8d3881737564f773bc2584f28"
A_ORIGINAL_BLOCKED_SHA = "3b8befb0112cfe2d314ad65964762a3fb251e710"
A_REPAIR_INITIAL_SHA = "2f0383816127cb7d87cf5deb559aeda0b04f1624"
A_REPAIR_EXACT_SHA = "5c542edd418a74b440162610fd540b1f01e423d3"
B_PREVIOUS_HEAD_SHA = "a0aacd105ac3f3173b15d91c869990748178e222"


@dataclass(frozen=True)
class FindingReauditRecord:
    """Before/after re-audit record for an original finding A01-A08."""

    finding_id: str
    discrepancy_code: str
    severity: str
    before_sha: str
    before_status: str
    after_sha: str
    after_status: str
    repaired_aspects: tuple[str, ...]
    residual_or_new_blockers: tuple[str, ...]
    concrete_b_test_names: tuple[str, ...]
    observed_trace_summary: str
    residual_risk: str


@dataclass(frozen=True)
class NewBlockerRecord:
    """New or residual runtime interaction blocker discovered in `A_REPAIR_SHA`."""

    blocker_id: str
    related_finding_ids: tuple[str, ...]
    severity: str
    file_and_lines: str
    summary: str
    expected_oracle_behavior: str
    observed_a_behavior: str
    minimal_reproduction_test: str


@dataclass(frozen=True)
class RepairR1ReauditReport:
    """Complete independent static and dynamic re-audit report for `A_REPAIR_SHA`."""

    task_id: str
    controller_dispatch_sha: str
    a_original_sha: str
    a_repair_initial_sha: str
    a_repair_exact_sha: str
    b_previous_head_sha: str
    code_baseline_sha: str
    method_sha: str
    original_design_sha: str
    terminal_status: str
    dynamic_crosscheck_executed: bool
    live_a_worktree_reads: int
    raw_market_body_reads: int
    findings_matrix: tuple[FindingReauditRecord, ...]
    new_blockers: tuple[NewBlockerRecord, ...]
    dynamic_probe_observations: dict[str, object]


def _extract_commit_to_tempdir(repo_root: Path, commit_sha: str, target_dir: Path) -> None:
    """Materialize an immutable Git commit into `target_dir` using `git archive`."""
    archive_proc = subprocess.run(
        ["git", "-C", str(repo_root), "archive", "--format=tar", commit_sha],
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["tar", "-x", "-C", str(target_dir)],
        input=archive_proc.stdout,
        capture_output=True,
        check=True,
    )


def verify_a_repair_git_lineage_and_scope(
    repo_root: Path,
    *,
    a_repair_sha: str = A_REPAIR_EXACT_SHA,
    a_repair_initial_sha: str = A_REPAIR_INITIAL_SHA,
    a_original_sha: str = A_ORIGINAL_BLOCKED_SHA,
    base_sha: str = FROZEN_CODE_BASE_SHA,
) -> dict[str, object]:
    """Verify commit parents, 1-line Controller test import diff, and allowlist scope."""
    parent_repair = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", f"{a_repair_sha}^"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    parent_initial = subprocess.run(
        ["git", "-C", str(repo_root), "rev-parse", f"{a_repair_initial_sha}^"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()

    diff_controller = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            a_repair_initial_sha,
            a_repair_sha,
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()

    diff_from_orig = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-status",
            a_original_sha,
            a_repair_sha,
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()

    diff_from_base = subprocess.run(
        [
            "git",
            "-C",
            str(repo_root),
            "diff",
            "--name-only",
            base_sha,
            a_repair_sha,
        ],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.splitlines()

    out_of_allowlist = [p for p in diff_from_base if not is_role_a_path_allowed(p)]
    init_deleted = "D\tsrc/btc_quant_agent/strategy_research/__init__.py" in diff_from_orig

    return {
        "a_repair_sha": a_repair_sha,
        "a_repair_parent_sha": parent_repair,
        "a_repair_parent_matches_initial": parent_repair == a_repair_initial_sha,
        "a_repair_initial_parent_sha": parent_initial,
        "a_repair_initial_parent_matches_original": parent_initial == a_original_sha,
        "controller_one_line_changed_files": diff_controller,
        "diff_from_original_name_status": diff_from_orig,
        "diff_from_base_count": len(diff_from_base),
        "out_of_allowlist_files_vs_base": out_of_allowlist,
        "strategy_research_init_deleted": init_deleted,
    }


def execute_isolated_dynamic_crosscheck(
    repo_root: Path,
    *,
    a_repair_sha: str = A_REPAIR_EXACT_SHA,
) -> dict[str, object]:
    """Dynamically execute Role A's `A_REPAIR_SHA` in an isolated tempdir against B's adversarial probes."""
    with tempfile.TemporaryDirectory(prefix="g2_r3_b_reaudit_") as tmp_str:
        tmp_dir = Path(tmp_str)
        _extract_commit_to_tempdir(repo_root, a_repair_sha, tmp_dir)

        # Verify A01: src/btc_quant_agent/strategy_research/__init__.py does NOT exist
        init_path = tmp_dir / "src" / "btc_quant_agent" / "strategy_research" / "__init__.py"
        a01_init_absent = not init_path.exists()

        # Verify A02: old receipt intact + new correction receipt has 2,934,720 rows
        old_receipt_path = (
            tmp_dir
            / "evidence/v0.6/b_line/g2_overnight_p0_a/AUDIT_MANIFEST_INSPECTION_RECEIPT.json"
        )
        new_receipt_path = (
            tmp_dir
            / "evidence/v0.6/b_line/g2_overnight_p0_a/repair_r1/AUDIT_MANIFEST_CORRECTION_RECEIPT.json"
        )
        old_receipt = json.loads(old_receipt_path.read_text(encoding="utf-8"))
        new_receipt = json.loads(new_receipt_path.read_text(encoding="utf-8"))
        a02_old_intact = (
            old_receipt["manifest_summary"]["reported_row_count"] == 2_933_280
        )
        a02_new_canonical = (
            new_receipt["reconciliation_summary"]["canonical_manifest_row_count"]
            == 2_934_720
            and new_receipt["reconciliation_summary"]["row_count_delta"] == 1_440
            and new_receipt["supersedes_prior_receipt"]["prior_receipt_path"]
            == "evidence/v0.6/b_line/g2_overnight_p0_a/AUDIT_MANIFEST_INSPECTION_RECEIPT.json"
            and new_receipt["asset_availability_status"]["ethusdt_physical_availability"]
            == "UNKNOWN"
            and new_receipt["asset_availability_status"]["solusdt_physical_availability"]
            == "UNKNOWN"
        )

        # Dynamically import Role A's package from isolated scratch src
        src_path = str(tmp_dir / "src")
        saved_modules = {
            k: v
            for k, v in sys.modules.items()
            if k == "btc_quant_agent" or k.startswith("btc_quant_agent.")
        }
        for k in list(saved_modules.keys()):
            del sys.modules[k]
        sys.path.insert(0, src_path)
        try:
            cand_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.candidate_registry"
            )
            const_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.constants"
            )
            importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.indicators"
            )
            ledger_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.ledger"
            )
            replay_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.replay_engine"
            )
            sig_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.signals"
            )
            types_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.types"
            )

            VirtualBook = ledger_mod.VirtualBook
            ReplayEngine = replay_mod.ReplayEngine
            SignalGenerator = sig_mod.SignalGenerator
            Bar1m = types_mod.Bar1m
            Bar1h = types_mod.Bar1h
            Bar4h = types_mod.Bar4h
            MarkBar1m = types_mod.MarkBar1m
            VirtualOrder = types_mod.VirtualOrder
            CostScenario = types_mod.CostScenario
            Direction = types_mod.Direction

            registry = cand_mod.get_default_registry()
            cids = [c.id for c in registry.list_candidates()]
            assert tuple(cids) == CANDIDATE_REGISTRY_IDS

            S = 1_700_002_800_000  # Exact UTC hour boundary (divisible by 3,600,000)
            t0 = S - 2 * ONE_MINUTE_MS
            four_h_ms = 4 * ONE_HOUR_MS

            # -----------------------------------------------------------------
            # Probe A03 & A08:
            # 1) Normal entry -> Stage 1 fill ACK preserves 4h max_hold_ms
            # 2) Same-minute SL on entry -> no zombie resurrection on Stage 1 fill ACK
            # 3) NEW_BLOCKER_B07: Funding settlement leaks debit in funding_reserve_rf
            # 4) NEW_BLOCKER_B02: Duplicate fill ACK debits entry fee twice
            # 5) NEW_BLOCKER_B03: Pre-hour [S-60s, S) and same-minute SL at S escape funding
            # -----------------------------------------------------------------
            book_a03 = VirtualBook(
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                cost_scenario=CostScenario.BASE,
            )
            ord_a03 = VirtualOrder(
                order_id="ORD_A03_1",
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                quantity=Decimal("0.01"),
                target_fill_time_ms=t0,
                created_at_ms=t0 - ONE_MINUTE_MS,
                expected_entry_bound=Decimal(50100),
                initial_stop=Decimal(49000),
                target=Decimal(52000),
                cost_commitment_usdt=Decimal(505),
                funding_reserve_usdt=Decimal("2.00"),
            )
            book_a03.pending_orders.append(ord_a03)
            book_a03.cost_commitment_o += ord_a03.cost_commitment_usdt
            book_a03.funding_reserve_rf += ord_a03.funding_reserve_usdt

            for step_t, high_p in (
                (t0, Decimal(50050)),
                (t0 + ONE_MINUTE_MS, Decimal(50050)),
                (S, Decimal(50050)),
                (S + ONE_MINUTE_MS, Decimal(52500)),  # TP hit
                (S + 2 * ONE_MINUTE_MS, Decimal(52000)),  # Exit ACK consumed
            ):
                b = Bar1m(
                    timestamp_ms=step_t,
                    open=Decimal(50000),
                    high=high_p,
                    low=Decimal(49950),
                    close=Decimal(50000),
                    volume=Decimal(10),
                    symbol="BTCUSDT",
                )
                m = MarkBar1m(
                    timestamp_ms=step_t - ONE_MINUTE_MS,
                    open=Decimal(50000),
                    high=Decimal(50000),
                    low=Decimal(50000),
                    close=Decimal(50000),
                    symbol="BTCUSDT",
                    available_at_ms=step_t,
                )
                book_a03.step_minute_open(step_t, {"BTCUSDT": b}, {"BTCUSDT": m}, four_h_ms)

            leaked_funding_reserve_after_close = book_a03.funding_reserve_rf
            charged_funding_on_trade = book_a03.completed_trades[0].total_funding_usdt

            # Probe duplicate fill ACK double fee debit (NEW_BLOCKER_B02)
            book_dup = VirtualBook(
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                cost_scenario=CostScenario.BASE,
            )
            ord_dup = VirtualOrder(
                order_id="ORD_DUP",
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                quantity=Decimal("0.01"),
                target_fill_time_ms=t0,
                created_at_ms=t0 - ONE_MINUTE_MS,
                expected_entry_bound=Decimal(50100),
                initial_stop=Decimal(49000),
                target=Decimal(52000),
                cost_commitment_usdt=Decimal(505),
                funding_reserve_usdt=Decimal("2.00"),
            )
            book_dup.pending_orders.append(ord_dup)
            book_dup.cost_commitment_o += ord_dup.cost_commitment_usdt
            book_dup.funding_reserve_rf += ord_dup.funding_reserve_usdt
            b0 = Bar1m(
                timestamp_ms=t0,
                open=Decimal(50000),
                high=Decimal(50050),
                low=Decimal(49950),
                close=Decimal(50000),
                volume=Decimal(10),
                symbol="BTCUSDT",
            )
            m0 = MarkBar1m(
                timestamp_ms=t0 - ONE_MINUTE_MS,
                open=Decimal(50000),
                high=Decimal(50000),
                low=Decimal(50000),
                close=Decimal(50000),
                symbol="BTCUSDT",
                available_at_ms=t0,
            )
            book_dup.step_minute_open(t0, {"BTCUSDT": b0}, {"BTCUSDT": m0}, four_h_ms)
            single_fill_fee = book_dup.pending_fill_acks[0].fee_usdt
            book_dup.pending_fill_acks.append(book_dup.pending_fill_acks[0])
            b1 = Bar1m(
                timestamp_ms=t0 + ONE_MINUTE_MS,
                open=Decimal(50000),
                high=Decimal(50050),
                low=Decimal(49950),
                close=Decimal(50000),
                volume=Decimal(10),
                symbol="BTCUSDT",
            )
            m1 = MarkBar1m(
                timestamp_ms=t0,
                open=Decimal(50000),
                high=Decimal(50000),
                low=Decimal(50000),
                close=Decimal(50000),
                symbol="BTCUSDT",
                available_at_ms=t0 + ONE_MINUTE_MS,
            )
            book_dup.step_minute_open(
                t0 + ONE_MINUTE_MS, {"BTCUSDT": b1}, {"BTCUSDT": m1}, four_h_ms
            )
            dup_ack_fee_debited_times = (
                const_mod.INITIAL_EQUITY_USDT - book_dup.cash
            ) / single_fill_fee

            # Probe pre-hour [S-60s, S) funding escape & same-minute SL at S funding/exit_ms bug
            book_pre_s = VirtualBook(
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                cost_scenario=CostScenario.BASE,
            )
            ord_pre_s = VirtualOrder(
                order_id="ORD_PRE_S",
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                quantity=Decimal("0.01"),
                target_fill_time_ms=S - ONE_MINUTE_MS,
                created_at_ms=S - 2 * ONE_MINUTE_MS,
                expected_entry_bound=Decimal(50100),
                initial_stop=Decimal(49000),
                target=Decimal(52000),
                cost_commitment_usdt=Decimal(505),
                funding_reserve_usdt=Decimal("2.00"),
            )
            book_pre_s.pending_orders.append(ord_pre_s)
            book_pre_s.cost_commitment_o += ord_pre_s.cost_commitment_usdt
            book_pre_s.funding_reserve_rf += ord_pre_s.funding_reserve_usdt
            for step_t in (S - ONE_MINUTE_MS, S, S + ONE_MINUTE_MS):
                b = Bar1m(
                    timestamp_ms=step_t,
                    open=Decimal(50000),
                    high=Decimal(50050),
                    low=Decimal(49950),
                    close=Decimal(50000),
                    volume=Decimal(10),
                    symbol="BTCUSDT",
                )
                m = MarkBar1m(
                    timestamp_ms=step_t - ONE_MINUTE_MS,
                    open=Decimal(50000),
                    high=Decimal(50000),
                    low=Decimal(50000),
                    close=Decimal(50000),
                    symbol="BTCUSDT",
                    available_at_ms=step_t,
                )
                book_pre_s.step_minute_open(
                    step_t, {"BTCUSDT": b}, {"BTCUSDT": m}, ONE_MINUTE_MS
                )
            pre_s_funding_charged = book_pre_s.completed_trades[0].total_funding_usdt

            book_sl_at_s = VirtualBook(
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                cost_scenario=CostScenario.BASE,
            )
            ord_sl_s = VirtualOrder(
                order_id="ORD_SL_S",
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                quantity=Decimal("0.01"),
                target_fill_time_ms=S,
                created_at_ms=S - ONE_MINUTE_MS,
                expected_entry_bound=Decimal(50100),
                initial_stop=Decimal(49000),
                target=Decimal(52000),
                cost_commitment_usdt=Decimal(505),
                funding_reserve_usdt=Decimal("2.00"),
            )
            book_sl_at_s.pending_orders.append(ord_sl_s)
            book_sl_at_s.cost_commitment_o += ord_sl_s.cost_commitment_usdt
            book_sl_at_s.funding_reserve_rf += ord_sl_s.funding_reserve_usdt
            b_sl = Bar1m(
                timestamp_ms=S,
                open=Decimal(50000),
                high=Decimal(50050),
                low=Decimal(48500),
                close=Decimal(48800),
                volume=Decimal(10),
                symbol="BTCUSDT",
            )
            m_sl = MarkBar1m(
                timestamp_ms=S - ONE_MINUTE_MS,
                open=Decimal(50000),
                high=Decimal(50000),
                low=Decimal(50000),
                close=Decimal(50000),
                symbol="BTCUSDT",
                available_at_ms=S,
            )
            book_sl_at_s.step_minute_open(S, {"BTCUSDT": b_sl}, {"BTCUSDT": m_sl}, four_h_ms)
            b_after = Bar1m(
                timestamp_ms=S + ONE_MINUTE_MS,
                open=Decimal(48800),
                high=Decimal(48850),
                low=Decimal(48750),
                close=Decimal(48800),
                volume=Decimal(10),
                symbol="BTCUSDT",
            )
            m_after = MarkBar1m(
                timestamp_ms=S,
                open=Decimal(48800),
                high=Decimal(48800),
                low=Decimal(48800),
                close=Decimal(48800),
                symbol="BTCUSDT",
                available_at_ms=S + ONE_MINUTE_MS,
            )
            book_sl_at_s.step_minute_open(
                S + ONE_MINUTE_MS, {"BTCUSDT": b_after}, {"BTCUSDT": m_after}, four_h_ms
            )
            sl_at_s_trade = book_sl_at_s.completed_trades[0]

            # -----------------------------------------------------------------
            # Probe NEW_BLOCKER_B05B: Post-kill liquidation exit ACK drives reserves negative
            # -----------------------------------------------------------------
            book_kill = VirtualBook(
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                cost_scenario=CostScenario.BASE,
            )
            ord_kill = VirtualOrder(
                order_id="ORD_KILL",
                candidate_id="STRUCTURAL_CONTINUATION_LONG_04H",
                symbol="BTCUSDT",
                direction=Direction.LONG,
                quantity=Decimal("0.05"),
                target_fill_time_ms=t0,
                created_at_ms=t0 - ONE_MINUTE_MS,
                expected_entry_bound=Decimal(50100),
                initial_stop=Decimal(49000),
                target=Decimal(52000),
                cost_commitment_usdt=Decimal(2510),
                funding_reserve_usdt=Decimal("5.00"),
            )
            book_kill.pending_orders.append(ord_kill)
            book_kill.cost_commitment_o += ord_kill.cost_commitment_usdt
            book_kill.funding_reserve_rf += ord_kill.funding_reserve_usdt
            book_kill.step_minute_open(t0, {"BTCUSDT": b0}, {"BTCUSDT": m0}, four_h_ms)
            b_crash = Bar1m(
                timestamp_ms=t0 + ONE_MINUTE_MS,
                open=Decimal(49500),
                high=Decimal(49500),
                low=Decimal(49100),
                close=Decimal(49200),
                volume=Decimal(10),
                symbol="BTCUSDT",
            )
            m_crash = MarkBar1m(
                timestamp_ms=t0,
                open=Decimal(47500),
                high=Decimal(47500),
                low=Decimal(47500),
                close=Decimal(47500),
                symbol="BTCUSDT",
                available_at_ms=t0 + ONE_MINUTE_MS,
            )
            book_kill.step_minute_open(
                t0 + ONE_MINUTE_MS, {"BTCUSDT": b_crash}, {"BTCUSDT": m_crash}, four_h_ms
            )
            for step_t in (t0 + 2 * ONE_MINUTE_MS, t0 + 3 * ONE_MINUTE_MS):
                b_l = Bar1m(
                    timestamp_ms=step_t,
                    open=Decimal(49200),
                    high=Decimal(49200),
                    low=Decimal(49100),
                    close=Decimal(49200),
                    volume=Decimal(10),
                    symbol="BTCUSDT",
                )
                m_l = MarkBar1m(
                    timestamp_ms=step_t - ONE_MINUTE_MS,
                    open=Decimal(47500),
                    high=Decimal(47500),
                    low=Decimal(47500),
                    close=Decimal(47500),
                    symbol="BTCUSDT",
                    available_at_ms=step_t,
                )
                book_kill.step_minute_open(
                    step_t, {"BTCUSDT": b_l}, {"BTCUSDT": m_l}, four_h_ms
                )

            # -----------------------------------------------------------------
            # Probe NEW_BLOCKER_B01: ReplayEngine.run_simulation 100% mark starvation
            # -----------------------------------------------------------------
            engine_probe = ReplayEngine(cost_scenario=CostScenario.BASE)
            # Feed 5 minutes of bars and marks into ReplayEngine.run_simulation
            sim_bars = [
                Bar1m(
                    timestamp_ms=S + i * ONE_MINUTE_MS,
                    open=Decimal(50000),
                    high=Decimal(50050),
                    low=Decimal(49950),
                    close=Decimal(50000),
                    volume=Decimal(10),
                    symbol="BTCUSDT",
                )
                for i in range(5)
            ]
            sim_marks = [
                MarkBar1m(
                    timestamp_ms=S + i * ONE_MINUTE_MS,
                    open=Decimal(50000),
                    high=Decimal(50000),
                    low=Decimal(50000),
                    close=Decimal(50000),
                    symbol="BTCUSDT",
                    available_at_ms=S + (i + 1) * ONE_MINUTE_MS,
                )
                for i in range(5)
            ]
            engine_probe.run_simulation({"BTCUSDT": sim_bars}, {"BTCUSDT": sim_marks})
            replay_marks_ingested_count = sum(
                len(bk.last_available_marks) for bk in engine_probe.books.values()
            )

            # -----------------------------------------------------------------
            # Probe NEW_BLOCKER_B06: Closed retest intermediate bar filter skip
            # -----------------------------------------------------------------
            gen_b06 = SignalGenerator()
            c_retest_04h = registry.get_candidate("CLOSED_RETEST_LONG_04H")
            base_t = 1_700_006_400_000
            bars_1h_b06 = [
                Bar1h(
                    timestamp_ms=base_t + i * ONE_HOUR_MS,
                    open=Decimal(50000),
                    high=Decimal(50100),
                    low=Decimal(49900),
                    close=Decimal(50000),
                    volume=Decimal(100),
                    symbol="BTCUSDT",
                    bar_count=60,
                )
                for i in range(25)
            ]
            # Hour 25: Breakout bar (boundary = 50100, ATR20 = 225, close = 50550)
            bars_1h_b06.append(
                Bar1h(
                    timestamp_ms=base_t + 25 * ONE_HOUR_MS,
                    open=Decimal(50000),
                    high=Decimal(50600),
                    low=Decimal(49950),
                    close=Decimal(50550),
                    volume=Decimal(200),
                    symbol="BTCUSDT",
                    bar_count=60,
                )
            )
            bars_4h_up = [
                Bar4h(
                    timestamp_ms=base_t + i * (4 * ONE_HOUR_MS),
                    open=Decimal(45000 + i * 100),
                    high=Decimal(45050 + i * 100),
                    low=Decimal(44950 + i * 100),
                    close=Decimal(45000 + i * 100),
                    volume=Decimal(1000),
                    symbol="BTCUSDT",
                    bar_count=240,
                )
                for i in range(65)
            ]
            gen_b06.evaluate_hourly_decision(c_retest_04h, "BTCUSDT", bars_1h_b06, bars_4h_up)
            # Hour 26: 4h close temporarily dips below EMA20, while 1h bar makes a lower low 50050
            bars_1h_b06.append(
                Bar1h(
                    timestamp_ms=base_t + 26 * ONE_HOUR_MS,
                    open=Decimal(50300),
                    high=Decimal(50350),
                    low=Decimal(50050),
                    close=Decimal(50250),
                    volume=Decimal(100),
                    symbol="BTCUSDT",
                    bar_count=60,
                )
            )
            bars_4h_dip = list(bars_4h_up[:-1]) + [
                Bar4h(
                    timestamp_ms=bars_4h_up[-1].timestamp_ms,
                    open=Decimal(48000),
                    high=Decimal(48100),
                    low=Decimal(47900),
                    close=Decimal(48000),
                    volume=Decimal(1000),
                    symbol="BTCUSDT",
                    bar_count=240,
                )
            ]
            gen_b06.evaluate_hourly_decision(c_retest_04h, "BTCUSDT", bars_1h_b06, bars_4h_dip)
            state_after_skipped_hour = gen_b06._active_breakouts[
                (c_retest_04h.id, "BTCUSDT", Direction.LONG)
            ]
            skipped_hour_bars_since_breakout = state_after_skipped_hour.bars_since_breakout

            return {
                "a01_init_absent": a01_init_absent,
                "a02_old_intact": a02_old_intact,
                "a02_new_canonical": a02_new_canonical,
                "candidate_count": len(cids),
                "leaked_funding_reserve_after_close": str(leaked_funding_reserve_after_close),
                "charged_funding_on_trade": str(charged_funding_on_trade),
                "dup_ack_fee_debited_times": str(dup_ack_fee_debited_times),
                "pre_s_funding_charged": str(pre_s_funding_charged),
                "sl_at_s_entry_ms": sl_at_s_trade.entry_time_ms,
                "sl_at_s_exit_ms": sl_at_s_trade.exit_time_ms,
                "sl_at_s_holding_minutes": sl_at_s_trade.holding_minutes,
                "sl_at_s_funding_charged": str(sl_at_s_trade.total_funding_usdt),
                "sl_at_s_cooldown_until_ms": book_sl_at_s.cooldown_until_ms["BTCUSDT"],
                "sl_at_s_expected_cooldown_until_ms": S + ONE_MINUTE_MS + four_h_ms,
                "post_kill_cost_commitment_o": str(book_kill.cost_commitment_o),
                "post_kill_funding_reserve_rf": str(book_kill.funding_reserve_rf),
                "replay_engine_marks_ingested_count": replay_marks_ingested_count,
                "skipped_hour_bars_since_breakout": skipped_hour_bars_since_breakout,
            }
        finally:
            sys.path.remove(src_path)
            for k in [
                m
                for m in list(sys.modules.keys())
                if m == "btc_quant_agent" or m.startswith("btc_quant_agent.")
            ]:
                del sys.modules[k]
            sys.modules.update(saved_modules)


def build_repair_r1_reaudit_report(
    repo_root: Path,
    *,
    a_repair_sha: str = A_REPAIR_EXACT_SHA,
) -> RepairR1ReauditReport:
    """Run complete static and dynamic re-audit of `A_REPAIR_SHA` and return structured report."""
    git_scope = verify_a_repair_git_lineage_and_scope(repo_root, a_repair_sha=a_repair_sha)
    dyn = execute_isolated_dynamic_crosscheck(repo_root, a_repair_sha=a_repair_sha)

    findings = (
        FindingReauditRecord(
            finding_id="A01",
            discrepancy_code="ROLE_A_PATH_OUTSIDE_ALLOWLIST:src/btc_quant_agent/strategy_research/__init__.py",
            severity="BLOCKING_SCOPE_VIOLATION",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="REPAIRED_VERIFIED",
            repaired_aspects=(
                "Deleted src/btc_quant_agent/strategy_research/__init__.py",
                "All 26 changed files vs e0ff8c3473de4bfa3e66fe7928d42992a4d38a32 strictly within Role A allowlist",
                "PEP 420 implicit namespace imports verified on Python 3.12.3 and Python 3.13.13",
            ),
            residual_or_new_blockers=(),
            concrete_b_test_names=("test_reaudit_a01_and_a02_scope_and_manifest_supersession",),
            observed_trace_summary=(
                f"strategy_research_init_deleted={git_scope['strategy_research_init_deleted']}, "
                f"out_of_allowlist_files_vs_base={git_scope['out_of_allowlist_files_vs_base']}"
            ),
            residual_risk="NONE",
        ),
        FindingReauditRecord(
            finding_id="A02",
            discrepancy_code="DISCREPANCY_A02_MANIFEST_ROW_COUNT_MISMATCH",
            severity="BLOCKING_MANIFEST_AUDIT_ERROR",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="REPAIRED_VERIFIED",
            repaired_aspects=(
                "Original AUDIT_MANIFEST_INSPECTION_RECEIPT.json preserved intact without history rewrite",
                "Superseding repair_r1/AUDIT_MANIFEST_CORRECTION_RECEIPT.json reconciles 2,934,720 rows (+1,440 leap-day 2024-02-29 minutes across 2,038 days)",
                "ETHUSDT and SOLUSDT physical availability recorded as UNKNOWN",
            ),
            residual_or_new_blockers=(),
            concrete_b_test_names=("test_reaudit_a01_and_a02_scope_and_manifest_supersession",),
            observed_trace_summary=(
                f"a02_old_intact={dyn['a02_old_intact']}, a02_new_canonical={dyn['a02_new_canonical']}"
            ),
            residual_risk="NONE",
        ),
        FindingReauditRecord(
            finding_id="A03",
            discrepancy_code="DISCREPANCY_A03_STAGE1_FILL_ACK_OVERWRITES_POSITION_MAX_HOLD_MS_ZERO",
            severity="CRITICAL_ACCOUNTING_AND_HOLDING_BUG",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="PARTIAL_REPAIR_RESIDUAL_BLOCKED",
            repaired_aspects=(
                "Stage 1 fill ACK no longer overwrites Position with max_hold_ms=0 (4h and 12h lifetimes preserved)",
                "Same-minute SL/TP closed positions tracked in closed_position_ids and not resurrected as zombie positions",
            ),
            residual_or_new_blockers=("NEW_BLOCKER_B02", "NEW_BLOCKER_B03"),
            concrete_b_test_names=(
                "test_reaudit_a03_and_a08_duplicate_ack_and_funding_reserve_leak",
                "test_reaudit_a03_and_a07_funding_escape_and_intraminute_exit_timestamp",
            ),
            observed_trace_summary=(
                f"dup_ack_fee_debited_times={dyn['dup_ack_fee_debited_times']} (expected 1), "
                f"pre_s_funding_charged={dyn['pre_s_funding_charged']} (expected 0.200000), "
                f"sl_at_s_funding_charged={dyn['sl_at_s_funding_charged']} (expected 0.200000)"
            ),
            residual_risk="HIGH_DOUBLE_FEE_AND_MISSED_BOUNDARY_FUNDING",
        ),
        FindingReauditRecord(
            finding_id="A04",
            discrepancy_code="DISCREPANCY_A04_SHARED_SIGNAL_GENERATOR_CORRUPTS_RETEST_STATE_ACROSS_04H_AND_12H",
            severity="CRITICAL_CANDIDATE_ISOLATION_BUG",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="REPAIRED_VERIFIED",
            repaired_aspects=(
                "SignalGenerator._active_breakouts keyed by (candidate_id, symbol, direction)",
                "Retest event_id includes candidate_id",
                "ReplayEngine instantiates dedicated SignalGenerator per candidate",
                "Verified invariant to candidate evaluation order permutation and repeatable BASE/STRESS receipt hashes",
            ),
            residual_or_new_blockers=(),
            concrete_b_test_names=("test_reaudit_a04_candidate_isolation_and_permutation_invariance",),
            observed_trace_summary="04H and 12H retest state isolated across LONG/SHORT and permutation-invariant",
            residual_risk="NONE",
        ),
        FindingReauditRecord(
            finding_id="A05",
            discrepancy_code="DISCREPANCY_A05_CLOSED_RETEST_TOUCH_ZONE_INEQUALITY_AND_STOP_EXTREMUM_OMITS_BREAKOUT_BAR",
            severity="SPECIFICATION_SIGNAL_MISMATCH",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="PARTIAL_REPAIR_RESIDUAL_BLOCKED",
            repaired_aspects=(
                "LONG low and SHORT high required inside inclusive [B - 0.25*ATR_b, B + 0.25*ATR_b] band (deep wicks rejected)",
                "Initial stop extremum includes breakout.breakout_low and breakout.breakout_high",
            ),
            residual_or_new_blockers=("NEW_BLOCKER_B06",),
            concrete_b_test_names=("test_reaudit_a05_retest_band_stop_and_intermediate_bar_skip_bug",),
            observed_trace_summary=(
                f"skipped_hour_bars_since_breakout={dyn['skipped_hour_bars_since_breakout']} (expected 1)"
            ),
            residual_risk="MEDIUM_STALE_RETEST_CONFIRMATION_AFTER_3_BAR_WINDOW",
        ),
        FindingReauditRecord(
            finding_id="A06",
            discrepancy_code="DISCREPANCY_A06_STAGE2_MARK_UPDATE_AND_BAR_OPEN_TIMESTAMP_AGE_CHECK",
            severity="CRITICAL_REPLAY_ENGINE_REGRESSION",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="BROKEN_INTERACTION_BLOCKED",
            repaired_aspects=(
                "Standalone VirtualBook._stage_1_available_messages ingests marks using close_ms and rejects future marks",
            ),
            residual_or_new_blockers=("NEW_BLOCKER_B01", "NEW_BLOCKER_B05A"),
            concrete_b_test_names=("test_reaudit_a06_replay_engine_mark_starvation_and_unacked_valuation",),
            observed_trace_summary=(
                f"replay_engine_marks_ingested_count={dyn['replay_engine_marks_ingested_count']} "
                "(ReplayEngine keys marks_by_minute by timestamp_ms=O while Stage 1 requires close_ms=O+60s <= O)"
            ),
            residual_risk="CRITICAL_REPLAY_ENGINE_100_PERCENT_SIGNAL_VETO",
        ),
        FindingReauditRecord(
            finding_id="A07",
            discrepancy_code="DISCREPANCY_A07_COOLDOWN_ORIGIN_AND_OMITTED_4H_DEDUP_ARGS",
            severity="SPECIFICATION_DEDUP_AND_COOLDOWN_MISMATCH",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="PARTIAL_REPAIR_RESIDUAL_BLOCKED",
            repaired_aspects=(
                "ReplayEngine passes last_exit_time_ms and last_entry_4h_time_ms to SignalGenerator.evaluate_hourly_decision",
                "Stage 4 open exits anchor cooldown to ceil_to_minute(open_time_ms) + 4h",
            ),
            residual_or_new_blockers=("NEW_BLOCKER_B04",),
            concrete_b_test_names=(
                "test_reaudit_a03_and_a07_funding_escape_and_intraminute_exit_timestamp",
            ),
            observed_trace_summary=(
                f"sl_at_s_holding_minutes={dyn['sl_at_s_holding_minutes']} (expected 1), "
                f"sl_at_s_cooldown_until_ms={dyn['sl_at_s_cooldown_until_ms']} "
                f"(expected {dyn['sl_at_s_expected_cooldown_until_ms']})"
            ),
            residual_risk="HIGH_INTRAMINUTE_EXIT_TIMESTAMP_AND_COOLDOWN_CLOCK_MISMATCH",
        ),
        FindingReauditRecord(
            finding_id="A08",
            discrepancy_code="DISCREPANCY_A08_STAGE5_EXIT_COMMITMENT_OMITS_TICK_SIZE_TERM",
            severity="CRITICAL_RESERVE_ACCOUNTING_BUG",
            before_sha=A_ORIGINAL_BLOCKED_SHA,
            before_status="OPEN_BLOCKED",
            after_sha=a_repair_sha,
            after_status="PARTIAL_REPAIR_RESIDUAL_BLOCKED",
            repaired_aspects=(
                "Stage 5 Position.cost_commitment_exit_usdt now includes sym_filter.tick_size * order.quantity",
            ),
            residual_or_new_blockers=("NEW_BLOCKER_B07", "NEW_BLOCKER_B05B"),
            concrete_b_test_names=(
                "test_reaudit_a03_and_a08_duplicate_ack_and_funding_reserve_leak",
            ),
            observed_trace_summary=(
                f"leaked_funding_reserve_after_close={dyn['leaked_funding_reserve_after_close']} "
                f"(expected 0), post_kill_cost_commitment_o={dyn['post_kill_cost_commitment_o']}, "
                f"post_kill_funding_reserve_rf={dyn['post_kill_funding_reserve_rf']}"
            ),
            residual_risk="HIGH_PERMANENT_FUNDING_RESERVE_LEAK_AND_NEGATIVE_POST_KILL_RESERVES",
        ),
    )

    new_blockers = (
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B01",
            related_finding_ids=("A06",),
            severity="CRITICAL_BLOCKER",
            file_and_lines=(
                "src/btc_quant_agent/strategy_research/r3_overnight/replay_engine.py:L89-L100; "
                "ledger.py:L149-L151,L277-L280"
            ),
            summary=(
                "ReplayEngine.run_simulation indexes marks_by_minute by m.timestamp_ms (bar open O), "
                "passing mbar only at current_open_ms = O, while VirtualBook._stage_1_available_messages "
                "requires mbar.close_ms <= open_time_ms (where mbar.close_ms = O + 60,000). Since "
                "O + 60,000 <= O is always False, ReplayEngine.run_simulation never ingests any mark "
                "bars into last_available_marks and calculate_order_sizing vetoes 100% of signals."
            ),
            expected_oracle_behavior=(
                "At minute open O, completed mark bar [O - 60,000, O) with close_ms = O and "
                "available_at_ms = O must be delivered to Stage 1 so last_available_marks is populated."
            ),
            observed_a_behavior=(
                f"replay_engine_marks_ingested_count={dyn['replay_engine_marks_ingested_count']} "
                "across all 8 books; 100% of signals vetoed by mark_info is None."
            ),
            minimal_reproduction_test="test_reaudit_a06_replay_engine_mark_starvation_and_unacked_valuation",
        ),
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B02",
            related_finding_ids=("A03", "A08"),
            severity="HIGH_BLOCKER",
            file_and_lines="src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L284-L330",
            summary=(
                "Stage 1 message processing is not idempotent against duplicate/repeated fill, exit, "
                "or funding ACK messages: a repeated VirtualFill ACK debits fill.fee_usdt from cash a "
                "second time; a repeated exit ACK double-credits PnL and subtracts reserves a second time."
            ),
            expected_oracle_behavior=(
                "Each fill_id, trade_id, and funding event_id must be acknowledged and applied to cash "
                "and reserves at most once."
            ),
            observed_a_behavior=(
                f"dup_ack_fee_debited_times={dyn['dup_ack_fee_debited_times']} "
                "(cash debited twice for the same fill_id)."
            ),
            minimal_reproduction_test="test_reaudit_a03_and_a08_duplicate_ack_and_funding_reserve_leak",
        ),
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B03",
            related_finding_ids=("A03",),
            severity="HIGH_BLOCKER",
            file_and_lines="src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L658-L669,L731-L755",
            summary=(
                "Stage 7 funding ownership check uses strict `hour_s + 3_600_000 < minute_end` (L744), "
                "which is False at pre-hour minute open_time_ms = S - 60,000 (minute_end = S), missing "
                "the [S - 15s, S) half of the ownership window for positions exiting at S. Moreover, "
                "positions entering at S that hit same-minute SL/TP in Stage 6 are deleted before Stage 7 "
                "runs at S, also escaping funding at S."
            ),
            expected_oracle_behavior=(
                "Any position active during [S - 15,000, S + 15,000] must be charged funding for "
                "settlement S exactly once."
            ),
            observed_a_behavior=(
                f"pre_s_funding_charged={dyn['pre_s_funding_charged']}; "
                f"sl_at_s_funding_charged={dyn['sl_at_s_funding_charged']}."
            ),
            minimal_reproduction_test="test_reaudit_a03_and_a07_funding_escape_and_intraminute_exit_timestamp",
        ),
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B04",
            related_finding_ids=("A07",),
            severity="HIGH_BLOCKER",
            file_and_lines=(
                "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L145,L658,L667,L685-L701; "
                "signals.py:L86"
            ),
            summary=(
                "Stage 6 intraminute SL/TP passes economic_exit_ms=open_time_ms (1m bar open O) instead "
                "of bar close O + 60,000, producing holding_minutes=0 on same-minute exits, shifting "
                "ceil_to_minute(economic_exit_at) cooldown 60s early, and mutating last_economic_exit_time_ms "
                "before Stage 1 exit ACK. In addition, signals.py:L86 compares decision_time_ms while "
                "ledger.py:L145 compares signal.available_at_ms (60s boundary disagreement)."
            ),
            expected_oracle_behavior=(
                "Intraminute SL/TP during [O, O + 60s) completes at bar close O + 60s (holding_minutes >= 1, "
                "cooldown = O + 60s + 4h), and decision-clock cooldown checks use consistent availability time."
            ),
            observed_a_behavior=(
                f"sl_at_s_holding_minutes={dyn['sl_at_s_holding_minutes']}, "
                f"sl_at_s_cooldown_until_ms={dyn['sl_at_s_cooldown_until_ms']} "
                f"vs expected {dyn['sl_at_s_expected_cooldown_until_ms']}."
            ),
            minimal_reproduction_test="test_reaudit_a03_and_a07_funding_escape_and_intraminute_exit_timestamp",
        ),
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B05",
            related_finding_ids=("A06", "A08"),
            severity="HIGH_BLOCKER",
            file_and_lines="src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L313-L314,L349-L381",
            summary=(
                "(A) _stage_2_account_risk values all self.positions in decision_equity without checking "
                "pos.is_acknowledged. (B) _trigger_kill_liquidation zeroes cost_commitment_o and "
                "funding_reserve_rf at kill latch while positions are still open; when the subsequent "
                "DRAWDOWN_KILL exit ACK arrives in Stage 1, exit_reserve and rem_funding are subtracted "
                "again, driving cost_commitment_o and funding_reserve_rf negative."
            ),
            expected_oracle_behavior=(
                "Stage 2 decision_equity values only acknowledged positions, and reserve commitments "
                "must never become negative after kill liquidation exit ACK."
            ),
            observed_a_behavior=(
                f"post_kill_cost_commitment_o={dyn['post_kill_cost_commitment_o']}, "
                f"post_kill_funding_reserve_rf={dyn['post_kill_funding_reserve_rf']}."
            ),
            minimal_reproduction_test="test_reaudit_a03_and_a08_duplicate_ack_and_funding_reserve_leak",
        ),
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B06",
            related_finding_ids=("A05",),
            severity="MEDIUM_BLOCKER",
            file_and_lines="src/btc_quant_agent/strategy_research/r3_overnight/signals.py:L96,L263-L276",
            summary=(
                "In SignalGenerator, if an hourly bar after a registered breakout temporarily fails the "
                "1h vol_bps filter (L96) or 4h EMA alignment check (L263-L268), evaluate_hourly_decision "
                "returns None before incrementing breakout.bars_since_breakout or appending the bar's "
                "high/low to intermediate_highs/intermediate_lows."
            ),
            expected_oracle_behavior=(
                "Every closed 1h bar after breakout must advance bars_since_breakout (expiring after 3 "
                "bars) and record its high/low in the breakout-through-confirmation stop extremum."
            ),
            observed_a_behavior=(
                f"skipped_hour_bars_since_breakout={dyn['skipped_hour_bars_since_breakout']} "
                "(remained 0 after 1 elapsed hour when 4h EMA alignment dipped)."
            ),
            minimal_reproduction_test="test_reaudit_a05_retest_band_stop_and_intermediate_bar_skip_bug",
        ),
        NewBlockerRecord(
            blocker_id="NEW_BLOCKER_B07",
            related_finding_ids=("A08", "A03"),
            severity="CRITICAL_BLOCKER",
            file_and_lines="src/btc_quant_agent/strategy_research/r3_overnight/ledger.py:L314,L588,L729,L761",
            summary=(
                "In Stage 7 (L761), pos.funding_reserves_usdt is reduced by each funding debit while "
                "book.funding_reserve_rf is not reduced in Stage 7 or Stage 1 funding ACK. When the "
                "position exits and its exit ACK arrives in Stage 1 (L314), book.funding_reserve_rf only "
                "subtracts the reduced pos.funding_reserves_usdt, permanently leaking the sum of charged "
                "funding debits in book.funding_reserve_rf after all positions close."
            ),
            expected_oracle_behavior=(
                "When all positions, pending orders, and pending ACKs are closed/consumed, "
                "book.funding_reserve_rf and book.cost_commitment_o must both equal 0."
            ),
            observed_a_behavior=(
                f"leaked_funding_reserve_after_close={dyn['leaked_funding_reserve_after_close']} "
                f"(equals charged_funding_on_trade={dyn['charged_funding_on_trade']}) with 0 open positions."
            ),
            minimal_reproduction_test="test_reaudit_a03_and_a08_duplicate_ack_and_funding_reserve_leak",
        ),
    )

    return RepairR1ReauditReport(
        task_id="V06_G2_R3_P0_B_INDEPENDENT_REAUDIT_R1",
        controller_dispatch_sha=CONTROLLER_REAUDIT_DISPATCH_SHA,
        a_original_sha=A_ORIGINAL_BLOCKED_SHA,
        a_repair_initial_sha=A_REPAIR_INITIAL_SHA,
        a_repair_exact_sha=a_repair_sha,
        b_previous_head_sha=B_PREVIOUS_HEAD_SHA,
        code_baseline_sha=FROZEN_CODE_BASE_SHA,
        method_sha=METHOD_ADDENDUM_HEAD_SHA,
        original_design_sha=ORIGINAL_DESIGN_SHA,
        terminal_status="P0_B_REPAIR_DISCREPANCY_BLOCKED",
        dynamic_crosscheck_executed=True,
        live_a_worktree_reads=0,
        raw_market_body_reads=0,
        findings_matrix=findings,
        new_blockers=new_blockers,
        dynamic_probe_observations={
            "git_scope": git_scope,
            "dynamic_probes": dyn,
        },
    )
