"""Deterministic Offline Runner for G2 R3 Role B (`GEMINI_B`) Independent Synthetic Oracle."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from scripts.strategy_research.r3_verification.a_impl_static_auditor import (
    audit_remote_a_impl_commit,
)
from scripts.strategy_research.r3_verification.manifest_and_boundary_oracle import (
    EXPECTED_BTC_MANIFEST_RELPATH,
    check_HoldoutWindowOverlap,
    check_source_and_product_boundary,
    verify_static_btc_data_manifest,
)
from scripts.strategy_research.r3_verification.oracle_specs import (
    BASE_COST_SCENARIO,
    CANDIDATE_REGISTRY_IDS,
    CONTROLLER_DISPATCH_SHA,
    EMPIRICAL_EXECUTION_AUTHORITY,
    FROZEN_CODE_BASE_SHA,
    METHOD_ADDENDUM_HEAD_SHA,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
    ORIGINAL_DESIGN_SHA,
    REAL_FUNDS_WRITE_AUTHORITY,
    REQUIRED_SOURCE_DATA_GRADE,
    ROLE_BRANCH,
    ROLE_DIR,
    ROLE_ID,
    SOURCE_AUDIT_SHA,
    STRESS_COST_SCENARIO,
    TASK_ID,
    decimal_context,
)
from scripts.strategy_research.r3_verification.pit_bar_and_signal_oracle import (
    Bar1m,
    aggregate_completed_bars,
    evaluate_stress_cost_geometry,
)
from scripts.strategy_research.r3_verification.two_clock_accounting_oracle import (
    IndependentBookOracle,
    MarketBarMessage,
    SettlementWindow,
    SymbolFilterSpec,
)

REPO_ROOT = Path(__file__).resolve().parents[3]


def run_synthetic_invariant_suite() -> dict[str, object]:
    """Execute deterministic synthetic invariant checks across PIT, Fill, Cost, Funding, and Risk."""
    with decimal_context():
        # 1. Completed 1m vs unfinished 1h/4h & t+60s availability
        base_open = 1_767_225_600_000  # 2026-01-01T00:00:00Z
        bars_1m = [
            Bar1m(
                symbol="BTCUSDT",
                open_ms=base_open + i * ONE_MINUTE_MS,
                open=Decimal(50000),
                high=Decimal(50100),
                low=Decimal(49900),
                close=Decimal(50050),
                volume=Decimal(10),
            )
            for i in range(90)
        ]
        # At 01:01:00Z (base_open + 3660000), first 1h bar [00:00, 01:00) is available (avail=01:01:00Z),
        # while second 1h bar [01:00, 02:00) is unfinished and must be dropped.
        agg_1h = aggregate_completed_bars(
            bars_1m,
            timeframe_ms=ONE_HOUR_MS,
            decision_at_ms=base_open + ONE_HOUR_MS + ONE_MINUTE_MS,
        )

        # 2. 12h vs 4h stress cost geometry across all 8 frozen candidates
        geom_results = {}
        for cid in CANDIDATE_REGISTRY_IDS:
            hold_h = 12 if cid.endswith("_12H") else 4
            geom = evaluate_stress_cost_geometry(
                candidate_id=cid,
                max_holding_hours=hold_h,
                actual_stop_bps=Decimal(180),
            )
            geom_results[cid] = {
                "eligible": geom.eligible,
                "status": geom.status,
                "claim_class": geom.claim_class,
                "required_min_stop_bps": str(geom.required_min_stop_bps),
                "stress_cost_bps_cs": str(geom.stress_cost_bps_cs),
                "registry_preserved": geom.registry_preserved,
            }

        # 3. Two-clock book check (base 22bp vs stress 44bp, 5% buffer, SL-first, TP cap, funding window)
        flt = {
            "BTCUSDT": SymbolFilterSpec(
                symbol="BTCUSDT",
                tick_size=Decimal("0.1"),
                lot_size=Decimal("0.001"),
                min_notional_usdt=Decimal("5.0"),
            ),
            "ETHUSDT": SymbolFilterSpec(
                symbol="ETHUSDT",
                tick_size=Decimal("0.01"),
                lot_size=Decimal("0.01"),
                min_notional_usdt=Decimal("5.0"),
            ),
            "SOLUSDT": SymbolFilterSpec(
                symbol="SOLUSDT",
                tick_size=Decimal("0.01"),
                lot_size=Decimal("0.1"),
                min_notional_usdt=Decimal("5.0"),
            ),
        }
        book_stress = IndependentBookOracle(
            book_id="ORACLE_STRESS",
            cost_scenario=STRESS_COST_SCENARIO,
            filters=flt,
        )
        book_stress.last_available_marks["BTCUSDT"] = (
            Decimal("50000.0"),
            base_open,
            base_open + ONE_MINUTE_MS,
        )
        entry_order = book_stress.size_and_reserve_entry(
            symbol="BTCUSDT",
            direction=1,
            decision_at_ms=base_open + ONE_MINUTE_MS,
            decision_close=Decimal("50000.0"),
            atr20=Decimal("500.0"),
            raw_stop=Decimal("49250.0"),
            max_hold_ms=4 * ONE_HOUR_MS,
            settlement_events_in_hold=4,
        )
        assert entry_order is not None

        # Execute entry at base_open + 120000 (next-minute open), then test intraminute SL-first collision
        entry_open_ms = base_open + 2 * ONE_MINUTE_MS
        tbar = MarketBarMessage(
            source_id="TBAR_COLLISION_1",
            symbol="BTCUSDT",
            open_ms=entry_open_ms,
            open=Decimal("50000.0"),
            high=Decimal("52500.0"),  # Touches TP
            low=Decimal("49000.0"),   # Also touches SL -> SL must win!
            close=Decimal("51000.0"),
            volume=Decimal("25.0"),
        )
        mbar = MarketBarMessage(
            source_id="MBAR_COLLISION_1",
            symbol="BTCUSDT",
            open_ms=entry_open_ms,
            open=Decimal("50000.0"),
            high=Decimal("52000.0"),
            low=Decimal("49100.0"),
            close=Decimal("50000.0"),
            is_mark=True,
        )
        settlement = SettlementWindow(
            settlement_id="SETTLE_SYNTH_01",
            symbol="BTCUSDT",
            settlement_ms=entry_open_ms + 30_000,
            settlement_mark_price=Decimal("50000.0"),
            actual_rate=Decimal("-0.0005"),  # Negative rate for LONG -> 0 benefit in stress!
            is_measured_schedule=False,
        )
        step_out = book_stress.step_minute_open(
            entry_open_ms,
            trade_bars_at_open={"BTCUSDT": tbar},
            mark_bars_at_open={"BTCUSDT": mbar},
            settlements_to_check=[settlement],
        )

        # 4. Boundary negative checks
        neg_rc2 = check_source_and_product_boundary(
            symbol="ZECUSDT",
            market_product="BINANCE_USDT_M_PERPETUAL",
        )
        neg_spot = check_source_and_product_boundary(
            symbol="BTCUSDT",
            market_product="BINANCE_SPOT",
        )
        neg_holdout_path = check_source_and_product_boundary(
            symbol="BTCUSDT",
            market_product="BINANCE_USDT_M_PERPETUAL",
            source_path_or_url="data/final_holdout/BTCUSDT.parquet",
        )

        return {
            "pit_aggregation_check": {
                "completed_1h_count": len(agg_1h.completed_bars),
                "dropped_unfinished_1h_count": len(agg_1h.dropped_unfinished_buckets),
                "validation_errors": list(agg_1h.validation_errors),
            },
            "cost_scenarios": {
                "base_round_trip_bps": str(BASE_COST_SCENARIO.round_trip_one_time_bps),
                "stress_round_trip_bps": str(STRESS_COST_SCENARIO.round_trip_one_time_bps),
            },
            "stress_geometry_by_candidate": geom_results,
            "sl_first_and_funding_check": {
                "executed_entries": step_out["stage5_entries"],
                "intrabar_exit_reason": (
                    book_stress.completed_trades[0].exit_reason
                    if book_stress.completed_trades
                    else None
                ),
                "funding_charges_count": len(step_out["stage7_funding"]),  # type: ignore[arg-type]
                "funding_debit_usdt": (
                    str(step_out["stage7_funding"][0]["funding_debit_usdt"])  # type: ignore[index]
                    if step_out["stage7_funding"]
                    else "0"
                ),
            },
            "negative_boundary_checks": {
                "rc2_symbol_blocked": not neg_rc2.allowed,
                "spot_product_blocked": not neg_spot.allowed,
                "holdout_parquet_path_blocked": not neg_holdout_path.allowed,
            },
        }


def run_full_oracle_report(
    *,
    repo_root: Path = REPO_ROOT,
    a_impl_sha: str | None = None,
) -> dict[str, object]:
    """Run synthetic oracle checks, static manifest check, holdout conflict analysis, and A_IMPL_SHA check."""
    manifest_path = repo_root / EXPECTED_BTC_MANIFEST_RELPATH
    manifest_res = verify_static_btc_data_manifest(manifest_path)
    holdout_res = check_HoldoutWindowOverlap()
    synth_res = run_synthetic_invariant_suite()
    a_audit_res = audit_remote_a_impl_commit(repo_root, a_impl_sha=a_impl_sha)

    if not manifest_res.valid:
        terminal_status = "P0_BLOCKED_IDENTITY_OR_SCOPE"
    elif a_audit_res.audit_performed and not a_audit_res.passed:
        terminal_status = "P0_B_DISCREPANCY_BLOCKED"
    elif a_audit_res.a_impl_sha is not None and a_audit_res.passed:
        terminal_status = "P0_B_ORACLE_READY_FOR_CONTROLLER"
    else:
        terminal_status = "P0_B_READY_WAITING_A_IMPL_SHA"

    return {
        "schema_version": "V06_G2_R3_P0_B_ORACLE_REPORT_V1",
        "task_id": TASK_ID,
        "role": ROLE_ID,
        "role_dir": ROLE_DIR,
        "role_branch": ROLE_BRANCH,
        "controller_dispatch_sha": CONTROLLER_DISPATCH_SHA,
        "frozen_code_base_sha": FROZEN_CODE_BASE_SHA,
        "method_addendum_head_sha": METHOD_ADDENDUM_HEAD_SHA,
        "original_design_sha": ORIGINAL_DESIGN_SHA,
        "source_audit_sha": SOURCE_AUDIT_SHA,
        "real_funds_write_authority": REAL_FUNDS_WRITE_AUTHORITY,
        "empirical_execution_authority": EMPIRICAL_EXECUTION_AUTHORITY,
        "source_data_grade": REQUIRED_SOURCE_DATA_GRADE,
        "raw_market_body_reads": 0,
        "protected_data_reads": 0,
        "external_network_calls": 0,
        "synthetic_invariants": synth_res,
        "manifest_verification": {
            "valid": manifest_res.valid,
            "manifest_relpath": manifest_res.manifest_relpath,
            "month_count": manifest_res.month_count,
            "row_count": manifest_res.row_count,
            "dataset_checksum_sha256": manifest_res.dataset_checksum_sha256,
            "funding_checksum_sha256": manifest_res.funding_checksum_sha256,
            "funding_row_count": manifest_res.funding_row_count,
            "monthly_kline_archive_count": manifest_res.monthly_kline_archive_count,
            "monthly_mark_archive_count": manifest_res.monthly_mark_archive_count,
            "monthly_funding_archive_count": manifest_res.monthly_funding_archive_count,
            "daily_mark_archive_count": manifest_res.daily_mark_archive_count,
            "parquet_or_zip_reads": manifest_res.parquet_or_zip_reads,
            "errors": list(manifest_res.errors),
        },
        "v03_holdout_conflict": {
            "conflict_detected": holdout_res.conflict_detected,
            "status": holdout_res.status,
            "v03_holdout_start_ms": holdout_res.v03_holdout_start_ms,
            "v03_holdout_end_ms": holdout_res.v03_holdout_end_ms,
            "total_overlapping_minutes_per_symbol": (
                holdout_res.total_overlapping_minutes_per_symbol
            ),
            "overlapping_r3_folds": list(holdout_res.overlapping_r3_folds),
            "eligible_exposed_pre2026_btc_months_count": len(
                holdout_res.eligible_exposed_pre2026_btc_months
            ),
            "proposed_calendar_only_substitute_options": list(
                holdout_res.proposed_calendar_only_substitute_options
            ),
        },
        "a_impl_static_audit": {
            "a_impl_sha": a_audit_res.a_impl_sha,
            "remote_branch": a_audit_res.remote_branch,
            "audit_performed": a_audit_res.audit_performed,
            "passed": a_audit_res.passed,
            "terminal_status": a_audit_res.terminal_status,
            "changed_files_count": a_audit_res.changed_files_count,
            "changed_files": list(a_audit_res.changed_files),
            "candidate_ids_verified": list(a_audit_res.candidate_ids_verified),
            "discrepancies": list(a_audit_res.discrepancies),
            "live_a_worktree_reads": a_audit_res.live_a_worktree_reads,
        },
        "terminal_status": terminal_status,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run G2 R3 Role B Independent Synthetic Oracle & Static Verifier"
    )
    parser.add_argument(
        "--a-impl-sha",
        default=None,
        help="Optional explicit immutable remote commit SHA for Role A",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Optional JSON file path to write the verification report",
    )
    args = parser.parse_args(argv)

    report = run_full_oracle_report(a_impl_sha=args.a_impl_sha)
    formatted = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).write_text(formatted, encoding="utf-8")
    sys.stdout.write(formatted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
