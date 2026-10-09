"""Independent positive-oracle behavioral re-audit tests for Role A Repair R2 (`2c60b0653d3619eedf457753511a9ecc84c1cd5b`)."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

from scripts.strategy_research.r3_verification.a_repair_r2_reauditor import (
    A_IMMUTABLE_TARGET_SHA,
    A_R2_PARENT_SHA,
    CONTROLLER_DISPATCH_SHA,
    EXPECTED_A_R2_CHANGED_FILES,
    PROMPT_PINNED_SHA,
    TERMINAL_VERDICT_BLOCKED_REPLAN,
    build_repair_r2_independent_report,
    verify_r2_git_lineage_and_scope,
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


def test_r2_git_lineage_scope_and_r1_a01_a02_a04_preserved() -> None:
    """Verify immutable R2 Git lineage, Controller/Prompt SHA bindings, allowlist, and A01/A02/A04 stability."""
    scope = verify_r2_git_lineage_and_scope(REPO_ROOT)
    assert scope["a_target_sha"] == A_IMMUTABLE_TARGET_SHA
    assert scope["a_parent_sha"] == A_R2_PARENT_SHA
    assert scope["a_parent_matches_expected"] is True
    assert scope["controller_dispatch_sha"] == CONTROLLER_DISPATCH_SHA
    assert scope["controller_decision_verified"] is True
    assert scope["prompt_pinned_sha"] == PROMPT_PINNED_SHA
    assert scope["prompt_parent_matches_controller_dispatch"] is True
    assert scope["prompt_pins_controller_sha"] is True
    assert tuple(scope["r2_changed_files"]) == EXPECTED_A_R2_CHANGED_FILES  # type: ignore[arg-type]
    assert scope["r2_changed_files_match_expected_7"] is True
    assert scope["out_of_allowlist_files_r1_to_r2"] == []
    assert scope["out_of_allowlist_files_vs_base"] == []
    assert scope["diff_from_base_count"] == 30
    assert scope["a02_manifest_files_untouched_in_r2"] is True

    report = build_repair_r2_independent_report(REPO_ROOT)
    assert report.terminal_verdict == TERMINAL_VERDICT_BLOCKED_REPLAN
    assert report.live_a_worktree_reads == 0
    assert report.raw_market_body_reads == 0

    r1_on_r2 = report.dynamic_observations["r1_probe_on_r2"]  # type: ignore[index]
    assert r1_on_r2["a01_init_absent"] is True  # type: ignore[index]
    assert r1_on_r2["a02_old_intact"] is True  # type: ignore[index]
    assert r1_on_r2["a02_new_canonical"] is True  # type: ignore[index]
    assert r1_on_r2["candidate_count"] == len(CANDIDATE_REGISTRY_IDS) == 8  # type: ignore[index]
    assert report.dynamic_observations["cost_proxy_verified"] is True


def test_r2_b01_mark_pit_and_out_of_order_replay_engine_drop() -> None:
    """Verify B01 ordered mark ingress repair (0 -> 8) and reproduce out-of-order same-symbol mark drop in ReplayEngine."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b01 = report.dynamic_observations["b01_probes"]  # type: ignore[index]

    # Ordered mark stream: R1 ingested 0 marks across 8 books; R2 ingests 8 marks (1 per book)
    assert b01["r1_replay_marks_ingested_count"] == 0  # type: ignore[index]
    assert b01["r2_replay_marks_ingested_count"] == 8  # type: ignore[index]
    assert b01["future_mark_rejected"] is True  # type: ignore[index]
    assert b01["unavailable_mark_rejected"] is True  # type: ignore[index]
    assert b01["sol_mark_ingested"] is True  # type: ignore[index]

    # Out-of-order same-symbol mark stream in ReplayEngine.run_simulation:
    # M_fresh (close=51000, close_ms=S+60s, avail=S+90s) is overwritten by delayed M_stale (close=49000, close_ms=S, avail=S+120s)
    assert b01["ooo_expected_mark_close"] == "51000"  # type: ignore[index]
    assert b01["ooo_observed_mark_close"] == "49000"  # type: ignore[index]
    assert b01["ooo_observed_mark_close_ms"] < b01["ooo_expected_mark_close_ms"]  # type: ignore[index]


def test_r2_b02_ack_idempotency_2x_3x_stale_and_distinct_orders() -> None:
    """Verify B02 positive oracle invariant: 2x/3x duplicate entry/exit/funding ACKs and stale ACKs after close are idempotent."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b02 = report.dynamic_observations["b02_probes"]  # type: ignore[index]

    # R1 debited duplicate entry fill ACK twice; R2 debits exactly once
    assert Decimal(str(b02["r1_dup_ack_fee_debited_times"])) == Decimal(2)  # type: ignore[index]
    assert Decimal(str(b02["r2_dup_ack_fee_debited_times"])) == Decimal(1)  # type: ignore[index]
    assert b02["b02_3x_trades_count"] == 1  # type: ignore[index]
    assert b02["b02_3x_funding_count"] == 1  # type: ignore[index]
    assert b02["b02_3x_positions_count"] == 0  # type: ignore[index]
    assert b02["b02_3x_cash_reconciled"] is True  # type: ignore[index]


def test_r2_b03_settlement_window_ack_race_and_multi_position_misattribution() -> None:
    """Verify B03 single-SL repair at S and reproduce pre-S Stage 6 exit ACK race + multi-position misattribution."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b03 = report.dynamic_observations["b03_probes"]  # type: ignore[index]

    # Single position entering at S and hitting SL at S: R1 charged 0; R2 charges 0.200000
    assert Decimal(str(b03["r1_sl_at_s_funding_charged"])) == Decimal(0)  # type: ignore[index]
    assert Decimal(str(b03["r2_sl_at_s_funding_charged"])) == Decimal("0.200000")  # type: ignore[index]

    # Defect B03-D1: Position entering at S-60s and hitting Stage 6 SL in minute S-60s (econ_exit = S-1):
    # Stage 1 at S pops exit ACK into completed_trades (total_funding_usdt=0) before Stage 7 at S charges 0.20
    assert Decimal(str(b03["pre_s_sl_funding_on_ledger"])) == Decimal("0.200000")  # type: ignore[index]
    assert Decimal(str(b03["pre_s_sl_funding_on_trade"])) == Decimal(0)  # type: ignore[index]
    assert Decimal(str(b03["pre_s_sl_cash_delta"])) != Decimal(str(b03["pre_s_sl_trade_net_pnl"]))  # type: ignore[index]
    # And Stage 7 at S steals 0.20 from ETHUSDT's 2.00 funding reserve (1.80 vs required 2.00)
    assert Decimal(str(b03["pre_s_sl_rf_after_s"])) == Decimal("1.800000")  # type: ignore[index]
    assert Decimal(str(b03["pre_s_sl_eth_required_rf"])) == Decimal("2.00")  # type: ignore[index]

    # Compare against Role B IndependentBookOracle on the exact same pre-S intraminute SL [S-60s, S-1]:
    s_ms = 1_700_002_800_000
    flt = {
        "BTCUSDT": SymbolFilterSpec(
            symbol="BTCUSDT",
            tick_size=Decimal("0.10"),
            lot_size=Decimal("0.001"),
            min_notional_usdt=Decimal("5.0"),
        )
    }
    oracle_book = IndependentBookOracle(
        book_id="ORACLE_B03_PRE_S",
        cost_scenario=BASE_COST_SCENARIO,
        filters=flt,
    )
    oracle_book.last_available_marks["BTCUSDT"] = (
        Decimal(50000),
        s_ms - 2 * ONE_MINUTE_MS,
        s_ms - ONE_MINUTE_MS,
    )
    oracle_ord = oracle_book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=s_ms - 2 * ONE_MINUTE_MS,
        decision_close=Decimal(50000),
        atr20=Decimal(500),
        raw_stop=Decimal(49000),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=4,
    )
    assert oracle_ord is not None
    oracle_book.step_minute_open(
        s_ms - ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_PRE_S",
                symbol="BTCUSDT",
                open_ms=s_ms - ONE_MINUTE_MS,
                open=Decimal(50000),
                high=Decimal(50050),
                low=Decimal(48500),
                close=Decimal(48800),
            )
        },
        mark_bars_at_open={},
        settlements_to_check=[],
    )
    oracle_step_s = oracle_book.step_minute_open(
        s_ms,
        trade_bars_at_open={},
        mark_bars_at_open={},
        settlements_to_check=[
            SettlementWindow(
                settlement_id="SETTLE_S",
                symbol="BTCUSDT",
                settlement_ms=s_ms,
                settlement_mark_price=Decimal(50000),
                actual_rate=Decimal("0.0004"),
                is_measured_schedule=False,
            )
        ],
    )
    assert len(oracle_step_s["stage7_funding"]) == 1  # type: ignore[arg-type]
    # Advance to S + 2m so all oracle ACKs settle cleanly with 0 residual reserves
    for step_t in (s_ms + ONE_MINUTE_MS, s_ms + 2 * ONE_MINUTE_MS):
        oracle_book.step_minute_open(
            step_t,
            trade_bars_at_open={},
            mark_bars_at_open={},
            settlements_to_check=[],
        )
    assert oracle_book.compute_outstanding_reserves() == (Decimal(0), Decimal(0))

    # Defect B03-D2: Close then reopen at S (POS_1 qty=0.05 closes in Stage 4, POS_2 qty=0.01 opens in Stage 5)
    # Role A R2 charges POS_1 0 and charges POS_2 1.000000 (5x its size!)
    assert Decimal(str(b03["reopen_pos1_funding"])) == Decimal(0)  # type: ignore[index]
    assert Decimal(str(b03["reopen_pos2_funding"])) == Decimal("1.000000")  # type: ignore[index]

    # Defect B03-D3: Disjoint positions where POS_EARLY exited at S-120s (outside window) with delayed ACK
    # Role A R2 charges POS_EARLY 0.400000 and charges POS_AT_S (which owned S) 0!
    assert Decimal(str(b03["disjoint_early_trade_funding"])) == Decimal("0.400000")  # type: ignore[index]
    assert Decimal(str(b03["disjoint_at_s_trade_funding"])) == Decimal(0)  # type: ignore[index]


def test_r2_b04_minute_end_sl_tp_causal_ohlc_and_horizons() -> None:
    """Verify B04 minute-end SL/TP timestamps, holding_minutes >= 1, 4h/12h horizons, and cooldown alignment."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b04 = report.dynamic_observations["b04_probes"]  # type: ignore[index]
    e2e = report.dynamic_observations["e2e_replay_engine"]  # type: ignore[index]

    s_ms = 1_700_002_800_000
    assert b04["r1_sl_at_s_exit_ms"] == s_ms  # type: ignore[index]
    assert b04["r2_sl_at_s_exit_ms"] == s_ms + ONE_MINUTE_MS - 1  # type: ignore[index]
    assert b04["r1_sl_at_s_holding_minutes"] == 0  # type: ignore[index]
    assert b04["r2_sl_at_s_holding_minutes"] == 1  # type: ignore[index]
    assert b04["r1_sl_at_s_cooldown_until_ms"] == b04["expected_cooldown_until_ms"] - ONE_MINUTE_MS  # type: ignore[index]
    assert b04["r2_sl_at_s_cooldown_until_ms"] == b04["expected_cooldown_until_ms"]  # type: ignore[index]

    # E2E 4h (240m) and 12h (720m) horizons
    assert e2e["base_04h_trades"] == 1  # type: ignore[index]
    assert e2e["base_04h_holding_minutes"] == 240  # type: ignore[index]
    assert e2e["base_12h_trades"] == 1  # type: ignore[index]
    assert e2e["base_12h_holding_minutes"] == 720  # type: ignore[index]


def test_r2_b05_decision_economic_equity_and_pre_clamp_reserve_algebra() -> None:
    """Verify B05 post-kill reserve fix and reproduce pre-ACK catastrophic loss blindness + premature entry release."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b05 = report.dynamic_observations["b05_probes"]  # type: ignore[index]

    # R1 post-kill reserves went negative (-3.0315125, -5.00); R2 clamps/preserves to 0
    assert Decimal(str(b05["r1_post_kill_cost_commitment_o"])) < Decimal(0)  # type: ignore[index]
    assert Decimal(str(b05["r1_post_kill_funding_reserve_rf"])) < Decimal(0)  # type: ignore[index]
    assert Decimal(str(b05["r2_post_kill_cost_commitment_o"])) == Decimal(0)  # type: ignore[index]
    assert Decimal(str(b05["r2_post_kill_funding_reserve_rf"])) == Decimal(0)  # type: ignore[index]

    # Defect B05-D1: Unacknowledged position suffers -$125 crash (economic_equity ~ 874.12 <= 900 kill threshold),
    # yet decision_equity stays ~998.9995 (>900), killed is False, and Stage 5 already released entry notional so available_capital is ~942.96
    assert Decimal(str(b05["unacked_crash_economic_equity"])) < Decimal(900)  # type: ignore[index]
    assert Decimal(str(b05["unacked_crash_decision_equity"])) == Decimal("998.999500000000")  # type: ignore[index]
    assert b05["unacked_crash_killed"] is False  # type: ignore[index]
    assert Decimal(str(b05["unacked_crash_available_cap"])) > Decimal(900)  # type: ignore[index]


def test_r2_b06_retest_elapsed_hours_cooldown_freeze_and_third_bar_expiry() -> None:
    """Verify B06 intermediate filter fix when not in cooldown and reproduce cooldown clock freeze + 3rd-bar expiry bug."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b06 = report.dynamic_observations["b06_probes"]  # type: ignore[index]

    # R1 left bars_since_breakout at 0 when 4h EMA dipped; R2 advances to 1 when last_exit_time_ms is None
    assert b06["r1_skipped_hour_bars_since_breakout"] == 0  # type: ignore[index]
    assert b06["r2_skipped_hour_bars_since_breakout"] == 1  # type: ignore[index]

    # Defect B06-D1: When last_exit_time_ms places H_26..H_29 in 4h cooldown after breakout at H_25,
    # signals.py:L124-L127 returns None before _advance_active_breakout at L131, so H_30 (5 elapsed hours!)
    # increments bars_since_breakout from 0 to 1 and confirms a stale 5th-hour retest!
    assert b06["stale_5th_hour_elapsed_hours"] == 5  # type: ignore[index]
    assert b06["stale_5th_hour_bars_counter"] == 1  # type: ignore[index]
    assert b06["stale_5th_hour_confirmed"] is True  # type: ignore[index]

    # Defect B06-D2: After 3 unconfirmed post-breakout bars (H_26, H_27, H_28), Breakout 1 stays canceled=False
    # and suppresses registration of the new 24h breakout on H_28
    assert b06["h3_canceled_flag"] is False  # type: ignore[index]
    assert b06["h3_breakout_hour_ms"] < b06["h3_expected_new_breakout_hour_ms"]  # type: ignore[index]


def test_r2_b07_funding_reserve_exhaustion_and_ack_permutation_conservation() -> None:
    """Verify B07 single-trade reserve fix and reproduce reserve-exhaustion aggregate deficit + pre-clamp negative."""
    report = build_repair_r2_independent_report(REPO_ROOT)
    b07 = report.dynamic_observations["b07_probes"]  # type: ignore[index]

    # Single trade with sufficient reserve (2.00 >= 0.20): R1 leaked 0.200000; R2 reaches 0
    assert Decimal(str(b07["r1_leaked_funding_reserve_after_close"])) == Decimal("0.200000")  # type: ignore[index]
    assert Decimal(str(b07["r2_leaked_funding_reserve_after_close"])) == Decimal(0)  # type: ignore[index]

    # Defect B07-D1: When POS_BTC has remaining funding_reserves_usdt=0.40 < debit=1.00 and POS_ETH has 2.00,
    # sum(pos.funding_reserves_usdt) is 2.00, but book.funding_reserve_rf drops to 1.40 (-0.60 deficit),
    # and single-book pre-clamp is 0.40 - 1.00 = -0.60 < 0
    assert Decimal(str(b07["exhaust_sum_position_rf"])) == Decimal("2.00")  # type: ignore[index]
    assert Decimal(str(b07["exhaust_aggregate_rf"])) == Decimal("1.400000")  # type: ignore[index]
    assert Decimal(str(b07["single_pre_clamp_rf"])) == Decimal("-0.60")  # type: ignore[index]


def test_r2_evidence_artifacts_and_controller_handoff_synchronized() -> None:
    """Verify R2 JSON evidence artifacts and B_R2_FINAL_CONTROLLER_HANDOFF.md match live report."""
    report = build_repair_r2_independent_report(REPO_ROOT)

    matrix_path = (
        REPO_ROOT
        / "evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/B01_B07_R2_INDEPENDENT_BEHAVIOR_MATRIX.json"
    )
    receipt_path = (
        REPO_ROOT
        / "evidence/v0.6/b_line/g2_overnight_p0_b/repair_r2/R2_B_INDEPENDENT_SYNTHETIC_EXECUTION_RECEIPT.json"
    )
    handoff_path = (
        REPO_ROOT
        / "docs/strategy_research/g2_r3/prep_b/repair_r2/B_R2_FINAL_CONTROLLER_HANDOFF.md"
    )

    assert matrix_path.is_file()
    assert receipt_path.is_file()
    assert handoff_path.is_file()

    matrix_data = json.loads(matrix_path.read_text(encoding="utf-8"))
    receipt_data = json.loads(receipt_path.read_text(encoding="utf-8"))
    handoff_text = handoff_path.read_text(encoding="utf-8")

    assert matrix_data["a_immutable_target_sha"] == A_IMMUTABLE_TARGET_SHA
    assert matrix_data["a_r2_parent_sha"] == A_R2_PARENT_SHA
    assert matrix_data["controller_dispatch_sha"] == CONTROLLER_DISPATCH_SHA
    assert matrix_data["prompt_pinned_sha"] == PROMPT_PINNED_SHA
    assert matrix_data["terminal_verdict"] == report.terminal_verdict
    assert matrix_data["summary_counts"] == {
        "total_b_items": 7,
        "PASS": 2,
        "BLOCKED": 5,
        "INCOMPLETE": 0,
    }

    assert receipt_data["a_immutable_target_sha"] == A_IMMUTABLE_TARGET_SHA
    assert receipt_data["terminal_verdict"] == report.terminal_verdict
    assert receipt_data["authority_guards"]["live_a_worktree_reads"] == 0
    assert receipt_data["authority_guards"]["raw_market_body_reads"] == 0
    assert receipt_data["coverage_summary"]["b01_b07_verdicts"] == {
        "B01": "BLOCKED",
        "B02": "PASS",
        "B03": "BLOCKED",
        "B04": "PASS",
        "B05": "BLOCKED",
        "B06": "BLOCKED",
        "B07": "BLOCKED",
    }

    assert A_IMMUTABLE_TARGET_SHA in handoff_text
    assert CONTROLLER_DISPATCH_SHA in handoff_text
    assert PROMPT_PINNED_SHA in handoff_text
    assert report.terminal_verdict in handoff_text
