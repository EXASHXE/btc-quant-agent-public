"""Hermetic tests for Static Manifest Schema Checker, v0.3 Holdout Conflict, Negatives & A_IMPL_SHA Audit."""

from __future__ import annotations

import copy
import json
from decimal import Decimal
from pathlib import Path

import pytest

from scripts.strategy_research.r3_verification.a_impl_static_auditor import (
    audit_a_impl_file_map,
)
from scripts.strategy_research.r3_verification.manifest_and_boundary_oracle import (
    EXPECTED_BTC_DATASET_SHA256,
    EXPECTED_BTC_FUNDING_ROW_COUNT,
    EXPECTED_BTC_FUNDING_SHA256,
    EXPECTED_BTC_MANIFEST_RELPATH,
    EXPECTED_BTC_MONTH_COUNT,
    EXPECTED_BTC_ROW_COUNT,
    check_HoldoutWindowOverlap,
    check_source_and_product_boundary,
    verify_static_btc_data_manifest,
)
from scripts.strategy_research.r3_verification.oracle_specs import (
    CANDIDATE_REGISTRY_IDS,
    MAX_MARK_EVENT_AGE_MS,
    ONE_HOUR_MS,
    ONE_MINUTE_MS,
    REQUIRED_SOURCE_DATA_GRADE,
    STRESS_COST_SCENARIO,
)
from scripts.strategy_research.r3_verification.two_clock_accounting_oracle import (
    IndependentBookOracle,
    MarketBarMessage,
    SymbolFilterSpec,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_static_btc_data_manifest_schema_and_lineage_verification() -> None:
    """Verify static BTC data_manifest.json (67 months, 2,934,720 rows, 0 gaps, funding & mark lineage)."""
    manifest_path = REPO_ROOT / EXPECTED_BTC_MANIFEST_RELPATH
    res = verify_static_btc_data_manifest(manifest_path)

    assert res.valid is True
    assert res.errors == ()
    assert res.symbol == "BTCUSDT"
    assert res.market == "USD-M PERPETUAL"
    assert res.timeframe == "1m"
    assert res.month_count == EXPECTED_BTC_MONTH_COUNT == 67
    assert res.row_count == EXPECTED_BTC_ROW_COUNT == 2_934_720
    assert res.expected_bars == 2_934_720
    assert res.missing_count == 0
    assert res.duplicate_count == 0
    assert res.out_of_order_count == 0
    assert res.invalid_ohlc_count == 0
    assert res.negative_volume_count == 0
    assert res.known_gaps_count == 0
    assert res.largest_gap_missing_bars == 0
    assert res.zero_volume_count == 367
    assert res.dataset_checksum_sha256 == EXPECTED_BTC_DATASET_SHA256
    assert res.funding_checksum_sha256 == EXPECTED_BTC_FUNDING_SHA256
    assert res.funding_row_count == EXPECTED_BTC_FUNDING_ROW_COUNT == 6_114
    assert res.funding_missing_mark_prices == 0
    assert res.monthly_kline_archive_count == 67
    assert res.monthly_mark_archive_count == 67
    assert res.monthly_funding_archive_count == 67
    assert res.daily_mark_archive_count == 9
    assert res.source_data_grade == REQUIRED_SOURCE_DATA_GRADE
    assert res.prior_exposures_remain_exposed is True
    assert res.blind_oos_claim_permitted is False
    assert res.parquet_or_zip_reads == 0


def test_manifest_schema_checker_rejects_corrupted_metadata_and_raw_bodies() -> None:
    """Manifest checker must fail closed on row/hash/gap corruption, blind OOS claims, or raw file extensions."""
    manifest_path = REPO_ROOT / EXPECTED_BTC_MANIFEST_RELPATH
    raw_dict = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Mutate row count, add gap, corrupt funding hash, and claim blind OOS
    corrupted = copy.deepcopy(raw_dict)
    corrupted["row_count"] = 2_934_719
    corrupted["missing_count"] = 1
    corrupted["funding"]["checksum_sha256"] = "0" * 64

    res_bad = verify_static_btc_data_manifest(
        corrupted,
        declared_source_grade="LIVE_PIT_CERTIFIED",
        claim_blind_oos=True,
    )
    assert res_bad.valid is False
    assert any("ROW_COUNT_MISMATCH" in e for e in res_bad.errors)
    assert any("NON_ZERO_GAP_OR_CORRUPTION_COUNTERS" in e for e in res_bad.errors)
    assert any("FUNDING_SHA256_MISMATCH" in e for e in res_bad.errors)
    assert any("INVALID_DECLARED_SOURCE_GRADE" in e for e in res_bad.errors)
    assert any("FORBIDDEN_BLIND_OOS_CLAIM" in e for e in res_bad.errors)

    # Passing a .parquet or .zip path or final_holdout path must raise ValueError before any file I/O
    with pytest.raises(ValueError, match="FORBIDDEN_RAW_DATA_BODY_PATH"):
        verify_static_btc_data_manifest("artifacts/research/trades.parquet")
    with pytest.raises(ValueError, match="FORBIDDEN_RAW_DATA_BODY_PATH"):
        verify_static_btc_data_manifest("BTCUSDT-1m-2026-01.zip")
    with pytest.raises(ValueError, match="FORBIDDEN_DENYLIST_PATH"):
        verify_static_btc_data_manifest("data/final_holdout/manifest.json")


def test_v03_holdout_overlap_conflict_and_pre2026_calendar_proposals() -> None:
    """Verify v0.3 BTC final holdout [2026-02-01, 2026-08-01) blocks R3 Feb-Apr 2026 and proposes pre-2026 calendar options."""
    report = check_HoldoutWindowOverlap()
    assert report.conflict_detected is True
    assert report.status == "HOLDOUT_OVERLAP_BLOCKED"
    assert report.silent_reclassification_permitted is False
    assert report.return_based_date_selection_permitted is False
    # Feb (28d) + Mar (31d) + Apr (30d) = 89 days = 128,160 minutes
    assert len(report.overlapping_r3_folds) == 3
    assert report.total_overlapping_minutes_per_symbol == 128_160
    assert len(report.eligible_exposed_pre2026_btc_months) == 60
    assert report.eligible_exposed_pre2026_btc_months[0] == "2021-01"
    assert report.eligible_exposed_pre2026_btc_months[-1] == "2025-12"

    for opt in report.proposed_calendar_only_substitute_options:
        assert opt["v03_holdout_overlap_minutes"] == 0
        assert opt["returns_inspected"] is False
        assert opt["source_data_grade"] == REQUIRED_SOURCE_DATA_GRADE


def test_negative_cases_stale_mark_and_corrupted_missing_mark() -> None:
    """Stale mark (>120s) vetoes entry and queues delayed exit; corrupted/missing mark blocks book."""
    t0 = 1_767_225_600_000
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
    book = IndependentBookOracle(
        book_id="BOOK_NEG_MARK",
        cost_scenario=STRESS_COST_SCENARIO,
        filters=flt,
    )
    # Mark event is 180,000 ms old (> 120,000 ms MAX_MARK_EVENT_AGE_MS)
    stale_decision_ms = t0 + MAX_MARK_EVENT_AGE_MS + ONE_MINUTE_MS
    book.last_available_marks["BTCUSDT"] = (Decimal("50000.0"), t0, t0 + ONE_MINUTE_MS)

    order = book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=stale_decision_ms,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("500.0"),
        raw_stop=Decimal("49200.0"),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=4,
    )
    assert order is None
    assert book.wait_and_veto_log[-1]["reason"] == "STALE_MARK_VETO"

    # Now enter with fresh mark, acknowledge position, then let mark become stale -> queues STALE_MARK_EXIT
    book.last_available_marks["BTCUSDT"] = (
        Decimal("50000.0"),
        stale_decision_ms - ONE_MINUTE_MS,
        stale_decision_ms,
    )
    ord_ok = book.size_and_reserve_entry(
        symbol="BTCUSDT",
        direction=1,
        decision_at_ms=stale_decision_ms,
        decision_close=Decimal("50000.0"),
        atr20=Decimal("500.0"),
        raw_stop=Decimal("49200.0"),
        max_hold_ms=4 * ONE_HOUR_MS,
        settlement_events_in_hold=4,
    )
    assert ord_ok is not None

    open_entry = stale_decision_ms + ONE_MINUTE_MS
    book.step_minute_open(
        open_entry,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_S1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_S1",
                symbol="BTCUSDT",
                open_ms=open_entry,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
                is_mark=True,
            )
        },
    )
    # Consume FILL_ACK at open_entry + 60000; mark is now 180s old (>120s), so Stage 2 queues STALE_MARK_EXIT
    step_ack_and_stale = book.step_minute_open(
        open_entry + ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_S2",
                symbol="BTCUSDT",
                open_ms=open_entry + ONE_MINUTE_MS,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
            )
        },
    )
    assert "BTCUSDT" in book.acknowledged_positions
    assert "BTCUSDT" in step_ack_and_stale["stage2_risk"]["stale_symbols"]  # type: ignore[index]
    assert any(o.kind == "STALE_MARK_EXIT" for o in book.due_orders)

    # At open_entry + 4 minutes, the due STALE_MARK_EXIT executes in Stage 4
    stale_check_open = open_entry + 4 * ONE_MINUTE_MS
    book.step_minute_open(
        stale_check_open,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_S3",
                symbol="BTCUSDT",
                open_ms=stale_check_open,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
            )
        },
    )
    assert len(book.completed_trades) == 1
    assert book.completed_trades[0].exit_reason == "STALE_OR_MISSING_MARK_DELAYED_EXIT"

    # Corrupted mark bar triggers SOURCE_BLOCKED hard stop
    book.step_minute_open(
        stale_check_open + ONE_MINUTE_MS,
        trade_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="TB_S4",
                symbol="BTCUSDT",
                open_ms=stale_check_open + ONE_MINUTE_MS,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal("50000.0"),
            )
        },
        mark_bars_at_open={
            "BTCUSDT": MarketBarMessage(
                source_id="MB_CORRUPT",
                symbol="BTCUSDT",
                open_ms=stale_check_open + ONE_MINUTE_MS,
                open=Decimal("50000.0"),
                high=Decimal("50100.0"),
                low=Decimal("49900.0"),
                close=Decimal(0),
                is_mark=True,
                corrupted=True,
            )
        },
    )
    assert book.source_blocked is True
    assert "INVALID_MARK_BAR_AT_CLOSE" in (book.source_blocked_reason or "")


def test_negative_cases_source_denylist_protected_dates_and_wrong_symbol_product() -> None:
    """Verify boundary checker blocks RC2 symbols, wrong products, denylist paths, and v0.3 holdout dates."""
    # 1. RC2 protected symbols
    for rc2_sym in ("ZECUSDT", "HYPEUSDT", "ORCAUSDT", "PUMPUSDT", "NMRUSDT", "BRUSDT", "RLCUSDT", "QNTUSDT"):
        r = check_source_and_product_boundary(
            symbol=rc2_sym, market_product="BINANCE_USDT_M_PERPETUAL"
        )
        assert r.allowed is False
        assert any("RC2_PROTECTED_SYMBOL_FORBIDDEN" in v for v in r.violations)

    # 2. Wrong symbol & wrong product
    r_wrong = check_source_and_product_boundary(
        symbol="DOGEUSDT", market_product="BINANCE_SPOT"
    )
    assert r_wrong.allowed is False
    assert any("UNALLOWLISTED_SYMBOL" in v for v in r_wrong.violations)
    assert any("WRONG_PRODUCT_OR_MARKET" in v for v in r_wrong.violations)

    # 3. Source denylist paths & live/testnet endpoints
    for bad_src in (
        "data/final_holdout/btc.parquet",
        "data/forward/mark.db",
        "data/research/h39_validation/sample.csv",
        "var/quant.db",
        "https://fapi.binance.com/fapi/v1/premiumIndex",
        "https://testnet.binancefuture.com/fapi/v1/order",
    ):
        r_src = check_source_and_product_boundary(
            symbol="BTCUSDT",
            market_product="BINANCE_USDT_M_PERPETUAL",
            source_path_or_url=bad_src,
        )
        assert r_src.allowed is False

    # 4. Historical v0.3 protected dates [2026-02-01, 2026-08-01)
    r_date = check_source_and_product_boundary(
        symbol="BTCUSDT",
        market_product="BINANCE_USDT_M_PERPETUAL",
        window_start_ms=1_769_904_000_000,  # 2026-02-01T00:00:00Z
        window_end_ms=1_772_323_200_000,    # 2026-03-01T00:00:00Z
    )
    assert r_date.allowed is False
    assert any("V03_PROTECTED_HOLDOUT_DATE_OVERLAP" in v for v in r_date.violations)


def test_a_impl_static_auditor_waiting_pass_and_discrepancy_states() -> None:
    """Verify static auditor handles waiting, clean remote commit, and discrepant remote commit."""
    # 1. Waiting state when A has not pushed yet
    res_wait = audit_a_impl_file_map(a_impl_sha=None, file_contents={})
    assert res_wait.terminal_status == "P0_B_READY_WAITING_A_IMPL_SHA"
    assert res_wait.passed is True
    assert res_wait.live_a_worktree_reads == 0

    # 2. Clean synthetic A commit
    clean_sha = "a" * 40
    all_cids_str = "\n".join(f'"{cid}"' for cid in CANDIDATE_REGISTRY_IDS)
    clean_files = {
        "src/btc_quant_agent/strategy_research/r3_overnight/engine.py": (
            f"CANDIDATES = [\n{all_cids_str}\n]\n"
        ),
        "tests/test_strategy_research_r3_engine.py": "def test_ok():\n    assert True\n",
        "evidence/v0.6/b_line/g2_overnight_p0_a/RECEIPT.json": json.dumps(
            {
                "real_funds_write_authority": "NONE",
                "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
            }
        ),
    }
    res_clean = audit_a_impl_file_map(a_impl_sha=clean_sha, file_contents=clean_files)
    assert res_clean.passed is True
    assert res_clean.terminal_status == "P0_B_ORACLE_READY_FOR_CONTROLLER"
    assert len(res_clean.candidate_ids_verified) == 8

    # 3. Discrepant A commit (forbidden import, out-of-scope file, missing 12h candidate, semantic bugs)
    bad_files = {
        "src/btc_quant_agent/cli.py": "import urllib.request\n",
        "src/btc_quant_agent/strategy_research/r3_overnight/engine.py": (
            'CANDIDATES = ["STRUCTURAL_CONTINUATION_LONG_04H"]\n'
        ),
        "src/btc_quant_agent/strategy_research/r3_overnight/ledger.py": (
            "def _stage_1_available_messages(self, open_time_ms: int) -> None:\n"
            "    self.positions[fill.symbol] = Position(max_hold_ms=0)\n"
        ),
        "evidence/v0.6/b_line/g2_overnight_p0_a/AUDIT_MANIFEST_INSPECTION_RECEIPT.json": json.dumps(
            {
                "real_funds_write_authority": "NONE",
                "manifest_summary": {"reported_row_count": 2933280},
            }
        ),
    }
    res_bad = audit_a_impl_file_map(a_impl_sha=clean_sha, file_contents=bad_files)
    assert res_bad.passed is False
    assert res_bad.terminal_status == "P0_B_DISCREPANCY_BLOCKED"
    assert any("ROLE_A_PATH_OUTSIDE_ALLOWLIST" in d for d in res_bad.discrepancies)
    assert any("FORBIDDEN_IMPORT" in d for d in res_bad.discrepancies)
    assert any("MISSING_FROZEN_CANDIDATE_ID" in d for d in res_bad.discrepancies)
    assert any("DISCREPANCY_A02_MANIFEST_ROW_COUNT_MISMATCH" in d for d in res_bad.discrepancies)
    assert any(
        "DISCREPANCY_A03_STAGE1_FILL_ACK_OVERWRITES_POSITION_MAX_HOLD_MS_ZERO" in d
        for d in res_bad.discrepancies
    )
