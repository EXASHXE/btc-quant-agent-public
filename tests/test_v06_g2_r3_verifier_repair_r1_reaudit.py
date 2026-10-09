"""Independent adversarial re-audit tests for Role A Repair R1 (`5c542edd418a74b440162610fd540b1f01e423d3`)."""

from __future__ import annotations

import importlib
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from scripts.strategy_research.r3_verification.a_repair_r1_reauditor import (
    A_ORIGINAL_BLOCKED_SHA,
    A_REPAIR_EXACT_SHA,
    A_REPAIR_INITIAL_SHA,
    _extract_commit_to_tempdir,
    build_repair_r1_reaudit_report,
    verify_a_repair_git_lineage_and_scope,
)
from scripts.strategy_research.r3_verification.oracle_specs import (
    BASE_COST_SCENARIO,
    CANDIDATE_REGISTRY_IDS,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
)
from scripts.strategy_research.r3_verification.two_clock_accounting_oracle import (
    IndependentBookOracle,
    MarketBarMessage,
    SettlementWindow,
    SymbolFilterSpec,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_reaudit_a01_and_a02_scope_and_manifest_supersession() -> None:
    """Verify A01 (deleted __init__.py, allowlist scope, PEP 420 import) and A02 (manifest 2,934,720 supersession)."""
    git_scope = verify_a_repair_git_lineage_and_scope(REPO_ROOT)
    assert git_scope["a_repair_sha"] == A_REPAIR_EXACT_SHA
    assert git_scope["a_repair_parent_sha"] == A_REPAIR_INITIAL_SHA
    assert git_scope["a_repair_parent_matches_initial"] is True
    assert git_scope["a_repair_initial_parent_sha"] == A_ORIGINAL_BLOCKED_SHA
    assert git_scope["a_repair_initial_parent_matches_original"] is True
    assert git_scope["controller_one_line_changed_files"] == [
        "tests/test_strategy_research_r3_repair_regressions.py"
    ]
    assert git_scope["strategy_research_init_deleted"] is True
    assert git_scope["out_of_allowlist_files_vs_base"] == []
    assert git_scope["diff_from_base_count"] == 26

    report = build_repair_r1_reaudit_report(REPO_ROOT)
    assert report.terminal_status == "P0_B_REPAIR_DISCREPANCY_BLOCKED"
    assert report.live_a_worktree_reads == 0
    assert report.raw_market_body_reads == 0

    by_id = {f.finding_id: f for f in report.findings_matrix}
    assert by_id["A01"].after_status == "REPAIRED_VERIFIED"
    assert by_id["A02"].after_status == "REPAIRED_VERIFIED"


def test_reaudit_a04_candidate_isolation_and_permutation_invariance() -> None:
    """Verify A04 per-candidate retest state isolation, permutation invariance, and BASE/STRESS hash repeatability."""
    with tempfile.TemporaryDirectory(prefix="g2_r3_b_a04_") as tmp_str:
        tmp_dir = Path(tmp_str)
        _extract_commit_to_tempdir(REPO_ROOT, A_REPAIR_EXACT_SHA, tmp_dir)
        src_path = str(tmp_dir / "src")
        saved = {
            k: v
            for k, v in sys.modules.items()
            if k == "btc_quant_agent" or k.startswith("btc_quant_agent.")
        }
        for k in list(saved.keys()):
            del sys.modules[k]
        sys.path.insert(0, src_path)
        try:
            cand_mod = importlib.import_module(
                "btc_quant_agent.strategy_research.r3_overnight.candidate_registry"
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

            reg = cand_mod.get_default_registry()
            c_04h = reg.get_candidate("CLOSED_RETEST_LONG_04H")
            c_12h = reg.get_candidate("CLOSED_RETEST_LONG_12H")
            assert tuple(c.id for c in reg.list_candidates()) == CANDIDATE_REGISTRY_IDS

            base_t = 1_700_006_400_000
            bars_1h = [
                types_mod.Bar1h(
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
            # Hour 25: Breakout bar (boundary = 50100, ATR20 = 225)
            bars_1h.append(
                types_mod.Bar1h(
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
            # Hour 26: Confirmation bar (low = 50080 inside [50043.75, 50156.25], close = 50180 >= 50122.5)
            bars_1h_confirm = list(bars_1h) + [
                types_mod.Bar1h(
                    timestamp_ms=base_t + 26 * ONE_HOUR_MS,
                    open=Decimal(50100),
                    high=Decimal(50220),
                    low=Decimal(50080),
                    close=Decimal(50180),
                    volume=Decimal(150),
                    symbol="BTCUSDT",
                    bar_count=60,
                )
            ]
            bars_4h = [
                types_mod.Bar4h(
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

            # Order (04H, 12H) vs (12H, 04H) on a shared SignalGenerator
            gen_fwd = sig_mod.SignalGenerator()
            gen_fwd.evaluate_hourly_decision(c_04h, "BTCUSDT", bars_1h, bars_4h)
            gen_fwd.evaluate_hourly_decision(c_12h, "BTCUSDT", bars_1h, bars_4h)
            sig_04_fwd = gen_fwd.evaluate_hourly_decision(
                c_04h, "BTCUSDT", bars_1h_confirm, bars_4h
            )
            sig_12_fwd = gen_fwd.evaluate_hourly_decision(
                c_12h, "BTCUSDT", bars_1h_confirm, bars_4h
            )

            gen_rev = sig_mod.SignalGenerator()
            gen_rev.evaluate_hourly_decision(c_12h, "BTCUSDT", bars_1h, bars_4h)
            gen_rev.evaluate_hourly_decision(c_04h, "BTCUSDT", bars_1h, bars_4h)
            sig_12_rev = gen_rev.evaluate_hourly_decision(
                c_12h, "BTCUSDT", bars_1h_confirm, bars_4h
            )
            sig_04_rev = gen_rev.evaluate_hourly_decision(
                c_04h, "BTCUSDT", bars_1h_confirm, bars_4h
            )

            assert sig_04_fwd is not None and sig_12_fwd is not None
            assert sig_04_rev is not None and sig_12_rev is not None
            assert sig_04_fwd.proposed_stop == sig_04_rev.proposed_stop
            assert sig_12_fwd.proposed_stop == sig_12_rev.proposed_stop

            # Deterministic receipt hash invariance across BASE and STRESS
            eng_b1 = replay_mod.ReplayEngine(cost_scenario=types_mod.CostScenario.BASE)
            eng_b2 = replay_mod.ReplayEngine(cost_scenario=types_mod.CostScenario.BASE)
            eng_s1 = replay_mod.ReplayEngine(cost_scenario=types_mod.CostScenario.STRESS)
            eng_s2 = replay_mod.ReplayEngine(cost_scenario=types_mod.CostScenario.STRESS)
            assert (
                eng_b1.compute_deterministic_receipt_hash()
                == eng_b2.compute_deterministic_receipt_hash()
            )
            assert (
                eng_s1.compute_deterministic_receipt_hash()
                == eng_s2.compute_deterministic_receipt_hash()
            )
        finally:
            sys.path.remove(src_path)
            for k in [
                m
                for m in list(sys.modules.keys())
                if m == "btc_quant_agent" or m.startswith("btc_quant_agent.")
            ]:
                del sys.modules[k]
            sys.modules.update(saved)


def test_reaudit_a05_retest_band_stop_and_intermediate_bar_skip_bug() -> None:
    """Verify A05 band/stop fix and reproduce NEW_BLOCKER_B06 (skipped intermediate hour when 4h EMA dips)."""
    report = build_repair_r1_reaudit_report(REPO_ROOT)
    dyn = report.dynamic_probe_observations["dynamic_probes"]  # type: ignore[index]
    # After 1 elapsed hour post-breakout where 4h EMA temporarily dipped, Role A left bars_since_breakout at 0
    assert dyn["skipped_hour_bars_since_breakout"] == 0  # type: ignore[index]
    assert any(b.blocker_id == "NEW_BLOCKER_B06" for b in report.new_blockers)


def test_reaudit_a06_replay_engine_mark_starvation_and_unacked_valuation() -> None:
    """Reproduce NEW_BLOCKER_B01 (ReplayEngine 0 marks ingested) and NEW_BLOCKER_B05A (unacked position valued)."""
    report = build_repair_r1_reaudit_report(REPO_ROOT)
    dyn = report.dynamic_probe_observations["dynamic_probes"]  # type: ignore[index]
    assert dyn["replay_engine_marks_ingested_count"] == 0  # type: ignore[index]
    assert any(b.blocker_id == "NEW_BLOCKER_B01" for b in report.new_blockers)


def test_reaudit_a03_and_a07_funding_escape_and_intraminute_exit_timestamp() -> None:
    """Reproduce NEW_BLOCKER_B03 (funding escape at S) and NEW_BLOCKER_B04 (intraminute exit_time_ms=O)."""
    report = build_repair_r1_reaudit_report(REPO_ROOT)
    dyn = report.dynamic_probe_observations["dynamic_probes"]  # type: ignore[index]

    # Role A charged 0 funding on [S-60s, S) and on same-minute SL at S
    assert dyn["pre_s_funding_charged"] == "0"  # type: ignore[index]
    assert dyn["sl_at_s_funding_charged"] == "0"  # type: ignore[index]
    assert dyn["sl_at_s_holding_minutes"] == 0  # type: ignore[index]
    assert (
        dyn["sl_at_s_cooldown_until_ms"]  # type: ignore[index]
        == dyn["sl_at_s_expected_cooldown_until_ms"] - ONE_MINUTE_MS  # type: ignore[index]
    )

    # Compare against Role B's IndependentBookOracle on the exact same [S, S+60s) intraminute SL + settlement S
    s_ms = int(dyn["sl_at_s_entry_ms"])  # type: ignore[index]
    flt = {
        "BTCUSDT": SymbolFilterSpec(
            symbol="BTCUSDT",
            tick_size=Decimal("0.10"),
            lot_size=Decimal("0.001"),
            min_notional_usdt=Decimal("5.0"),
        )
    }
    oracle_book = IndependentBookOracle(
        book_id="ORACLE_B03_B04",
        cost_scenario=BASE_COST_SCENARIO,
        filters=flt,
    )
    oracle_book.last_available_marks["BTCUSDT"] = (
        Decimal(50000),
        s_ms - ONE_MINUTE_MS,
        s_ms,
    )
    oracle_ord = oracle_book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=s_ms - ONE_MINUTE_MS,
        decision_close=Decimal(50000),
        atr20=Decimal(500),
        raw_stop=Decimal(49000),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=4,
    )
    assert oracle_ord is not None
    oracle_step = oracle_book.step_minute_open(
        s_ms,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_SL_S",
                symbol="BTCUSDT",
                open_ms=s_ms,
                open=Decimal(50000),
                high=Decimal(50050),
                low=Decimal(48500),
                close=Decimal(48800),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_SL_S",
                symbol="BTCUSDT",
                open_ms=s_ms,
                open=Decimal(50000),
                high=Decimal(50000),
                low=Decimal(50000),
                close=Decimal(50000),
                is_mark=True,
            )
        },
        settlements_to_check=[
            SettlementWindow(
                settlement_id="SETTLE_AT_S",
                symbol="BTCUSDT",
                settlement_ms=s_ms,
                settlement_mark_price=Decimal(50000),
                actual_rate=Decimal("0.0004"),
                is_measured_schedule=False,
            )
        ],
    )
    # Role B oracle charges funding for settlement S because position entered at S (inside [S-15s, S+15s])
    # and records exit_at_ms = S + 59,999 (bar close_ms) with cooldown_until = S + 60,000 + 4h upon Stage 1 exit ACK
    assert len(oracle_step["stage7_funding"]) == 1  # type: ignore[arg-type]
    assert oracle_book.completed_trades[0].exit_at_ms == s_ms + ONE_MINUTE_MS - 1
    oracle_book.step_minute_open(
        s_ms + ONE_MINUTE_MS,
        trade_bars_at_open={},
        mark_bars_at_open={},
        settlements_to_check=[],
    )
    oracle_book.step_minute_open(
        s_ms + 2 * ONE_MINUTE_MS,
        trade_bars_at_open={},
        mark_bars_at_open={},
        settlements_to_check=[],
    )
    assert (
        oracle_book.cooldown_until_ms["BTCUSDT"]
        == s_ms + ONE_MINUTE_MS + 4 * ONE_HOUR_MS
    )


def test_reaudit_a03_and_a08_duplicate_ack_and_funding_reserve_leak() -> None:
    """Reproduce NEW_BLOCKER_B02 (dup ACK double fee), NEW_BLOCKER_B05B (negative reserves), and NEW_BLOCKER_B07 (leaked R_f)."""
    report = build_repair_r1_reaudit_report(REPO_ROOT)
    dyn = report.dynamic_probe_observations["dynamic_probes"]  # type: ignore[index]

    # 1. Duplicate fill ACK debited entry fee twice in Role A
    assert Decimal(str(dyn["dup_ack_fee_debited_times"])) == Decimal(2)  # type: ignore[index]

    # 2. Funding reserve leaked 0.200000 USDT after all positions closed in Role A
    assert Decimal(str(dyn["leaked_funding_reserve_after_close"])) == Decimal("0.200000")  # type: ignore[index]
    assert (
        dyn["leaked_funding_reserve_after_close"]  # type: ignore[index]
        == dyn["charged_funding_on_trade"]  # type: ignore[index]
    )

    # 3. Post-kill exit ACK drove cost_commitment_o and funding_reserve_rf negative in Role A
    assert Decimal(str(dyn["post_kill_cost_commitment_o"])) < Decimal(0)  # type: ignore[index]
    assert Decimal(str(dyn["post_kill_funding_reserve_rf"])) < Decimal(0)  # type: ignore[index]
