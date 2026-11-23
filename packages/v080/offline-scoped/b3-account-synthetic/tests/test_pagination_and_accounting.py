"""Tests for bounded pagination, checkpoints, crash/restart recovery, canonical accounting, and realized net R."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from quant_personal_account_b3.accounting import compute_accounting_report
from quant_personal_account_b3.b2_reader import ReadOnlyB2JournalReader
from quant_personal_account_b3.client import (
    ROUTE_ALL_ALGO_ORDERS,
    ROUTE_ALL_ORDERS,
    ROUTE_INCOME,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
    ROUTE_USER_TRADES,
    DeterministicFakeClock,
    DeterministicFakeSigner,
    FakeCredentialProvider,
    OfflineFixtureTransport,
    PrivateUserDataClient,
    SignedPrivateRequest,
    TransportResponse,
)
from quant_personal_account_b3.fixtures import DEFAULT_SYNTHETIC_AS_OF_MS
from quant_personal_account_b3.matching import match_episode_to_account
from quant_personal_account_b3.models import (
    DAY_MS,
    NINETY_DAYS_MS,
    SEVEN_DAYS_MS,
    PrivateRequestRejectedError,
)
from quant_personal_account_b3.pagination import HistoryPaginator, plan_bounded_windows
from quant_personal_account_b3.service import load_synthetic_scenario_into_store
from quant_personal_account_b3.storage import PrivateAccountStore


def _parse_query(qs: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in qs.split("&"):
        if "=" in part:
            k, v = part.split("=", 1)
            out[k] = v
    return out


def _make_trade_row(trade_id: int, ts: int, *, qty: str = "0.100", rpnl: str = "1.00") -> dict[str, Any]:
    return {
        "symbol": "BTCUSDT",
        "id": trade_id,
        "orderId": 1000 + trade_id,
        "side": "SELL",
        "positionSide": "BOTH",
        "price": "101.00",
        "qty": qty,
        "quoteQty": "10.10",
        "realizedPnl": rpnl,
        "commission": "0.005",
        "commissionAsset": "USDT",
        "time": ts,
        "maker": False,
        "buyer": False,
    }


def test_open_orders_rejected_as_historical_source_and_retention_gaps_tracked() -> None:
    as_of = DEFAULT_SYNTHETIC_AS_OF_MS
    for ep in (ROUTE_OPEN_ORDERS, ROUTE_OPEN_ALGO_ORDERS):
        with pytest.raises(PrivateRequestRejectedError) as exc:
            plan_bounded_windows(endpoint=ep, start_ms=as_of - DAY_MS, end_ms=as_of, as_of_venue_ms=as_of)
        assert exc.value.code == "OPEN_ORDERS_NOT_HISTORICAL_SOURCE"

    # Requesting 100 days ago -> >90d gap explicitly marked, remaining windows strictly <7d for allOrders.
    windows, gaps, warnings = plan_bounded_windows(
        endpoint=ROUTE_ALL_ORDERS,
        start_ms=as_of - 100 * DAY_MS,
        end_ms=as_of,
        as_of_venue_ms=as_of,
    )
    assert len(gaps) == 1
    assert gaps[0]["reason"] == "RETENTION_GAP_90D"
    assert gaps[0]["end_ms"] == as_of - NINETY_DAYS_MS - 1
    assert "CANCELED_UNFILLED_ORDERS_OLDER_THAN_3_DAYS_MAY_DISAPPEAR" in warnings
    assert all((e - s) < SEVEN_DAYS_MS for s, e in windows)

    # Income >3 months -> RETENTION_GAP_3M_INCOME + weight 30 warning.
    inc_windows, inc_gaps, inc_warn = plan_bounded_windows(
        endpoint=ROUTE_INCOME,
        start_ms=as_of - 110 * DAY_MS,
        end_ms=as_of,
        as_of_venue_ms=as_of,
    )
    assert inc_gaps[0]["reason"] == "RETENTION_GAP_3M_INCOME"
    assert "INCOME_WEIGHT_30_USE_INCREMENTAL_POLLING" in inc_warn
    assert all((e - s) <= SEVEN_DAYS_MS for s, e in inc_windows)


def test_pagination_crash_restart_recovery_no_loss_no_double_count(tmp_path: Path) -> None:
    as_of = DEFAULT_SYNTHETIC_AS_OF_MS
    t0 = as_of - 20_000
    # 5 trades across 3 pages (page_limit=2) using fromId pagination.
    dataset = [
        _make_trade_row(101, t0 + 1000),
        _make_trade_row(102, t0 + 2000),
        _make_trade_row(103, t0 + 3000),
        _make_trade_row(104, t0 + 4000),
        _make_trade_row(105, t0 + 5000),
    ]

    def handler(req: SignedPrivateRequest) -> TransportResponse:
        q = _parse_query(req.canonical_unsigned_query)
        from_id = int(q.get("fromId", "0"))
        limit = int(q.get("limit", "2"))
        # Intentionally return page rows out-of-order to verify normalization + ordering!
        matched = [row for row in dataset if row["id"] >= from_id][:limit]
        matched_out_of_order = list(reversed(matched))
        return TransportResponse(status_code=200, raw_body=json.dumps(matched_out_of_order).encode())

    store = PrivateAccountStore(tmp_path / "private.sqlite", create=True)
    clk = DeterministicFakeClock(wall_ms=as_of - 500, venue_offset_ms=100)
    client = PrivateUserDataClient(
        transport=OfflineFixtureTransport(handler=handler, clock=clk),
        credentials=FakeCredentialProvider(),
        signer=DeterministicFakeSigner(),
        clock=clk,
    )
    paginator = HistoryPaginator(client=client, store=store)

    class SimulatedCrash(RuntimeError):
        pass

    # Crash BEFORE committing page 2 -> page 1 committed, page 2 rolled back!
    def crash_on_page_2(page_num: int) -> None:
        if page_num == 2:
            raise SimulatedCrash("simulated process crash before page 2 commit")

    with pytest.raises(SimulatedCrash):
        paginator.sync_user_trades(
            symbol="BTCUSDT",
            start_ms=t0,
            end_ms=as_of,
            as_of_venue_ms=as_of,
            page_limit=2,
            use_from_id=True,
            initial_from_id=101,
            before_page_commit=crash_on_page_2,
        )

    # Verify rollback: only page 1 (trades 101, 102) persisted, checkpoint points at next cursor 103.
    mid_fills = store.load_all_fills(symbol="BTCUSDT")
    assert [f.trade_id for f in mid_fills] == [101, 102]
    cp = store.load_checkpoint(
        endpoint=ROUTE_USER_TRADES, symbol="BTCUSDT", window_start_ms=t0, window_end_ms=as_of
    )
    assert cp is not None
    assert cp.status == "IN_PROGRESS"
    assert cp.last_accepted_id == "102"
    assert cp.pages_completed == 1

    # Resume after restart -> completes cleanly with ALL 5 trades, zero duplicates!
    res = paginator.sync_user_trades(
        symbol="BTCUSDT",
        start_ms=t0,
        end_ms=as_of,
        as_of_venue_ms=as_of,
        page_limit=2,
        use_from_id=True,
        initial_from_id=101,
    )
    assert res.checkpoint.status == "COMPLETE"
    assert res.coverage.status == "OK"
    assert [f.trade_id for f in res.fills] == [101, 102, 103, 104, 105]
    assert [f.trade_id for f in store.load_all_fills(symbol="BTCUSDT")] == [101, 102, 103, 104, 105]

    # Re-running an overlapping time window with duplicate pages never double-counts!
    res_overlap = paginator.sync_user_trades(
        symbol="BTCUSDT",
        start_ms=t0 - 1000,
        end_ms=as_of,
        as_of_venue_ms=as_of,
        page_limit=2,
        use_from_id=True,
        initial_from_id=101,
    )
    assert [f.trade_id for f in res_overlap.fills] == [101, 102, 103, 104, 105]


def test_pagination_handles_repeated_cursor_empty_pages_partial_failure_and_retention_gap(tmp_path: Path) -> None:
    as_of = DEFAULT_SYNTHETIC_AS_OF_MS
    t0 = as_of - 10_000
    store = PrivateAccountStore(tmp_path / "private_edge.sqlite", create=True)
    clk = DeterministicFakeClock(wall_ms=as_of - 500, venue_offset_ms=100)

    # 1. Repeated / non-advancing cursor -> halts bounded and marks PARTIAL with NON_ADVANCING_CURSOR!
    stuck_page = [_make_trade_row(201, t0 + 1000), _make_trade_row(202, t0 + 2000)]

    def stuck_handler(_req: SignedPrivateRequest) -> TransportResponse:
        return TransportResponse(status_code=200, raw_body=json.dumps(stuck_page).encode())

    c_stuck = PrivateUserDataClient(
        transport=OfflineFixtureTransport(handler=stuck_handler, clock=clk),
        credentials=FakeCredentialProvider(),
        signer=DeterministicFakeSigner(),
        clock=clk,
    )
    res_stuck = HistoryPaginator(client=c_stuck, store=store).sync_user_trades(
        symbol="BTCUSDT", start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of, page_limit=2, use_from_id=True, initial_from_id=201
    )
    assert res_stuck.checkpoint.status == "PARTIAL"
    assert res_stuck.coverage.status == "PARTIAL"
    assert any(g["reason"] == "NON_ADVANCING_CURSOR" for g in res_stuck.coverage.gap_windows)

    # 2. Empty page -> completes cleanly with 0 records.
    c_empty = PrivateUserDataClient(
        transport=OfflineFixtureTransport(routes={ROUTE_ALL_ALGO_ORDERS: []}, clock=clk),
        credentials=FakeCredentialProvider(),
        signer=DeterministicFakeSigner(),
        clock=clk,
    )
    res_empty = HistoryPaginator(client=c_empty, store=store).sync_all_algo_orders(
        symbol="ETHUSDT", start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of, page_limit=10
    )
    assert res_empty.checkpoint.status == "COMPLETE"
    assert res_empty.coverage.status == "OK"
    assert res_empty.algo_orders == ()

    # 3. Partial endpoint failure on page 2 -> page 1 saved, status PARTIAL, missing window recorded!
    calls = {"n": 0}

    def fail_page_2(_req: SignedPrivateRequest) -> TransportResponse:
        calls["n"] += 1
        if calls["n"] == 1:
            return TransportResponse(
                status_code=200,
                raw_body=json.dumps([_make_trade_row(301, t0 + 1000), _make_trade_row(302, t0 + 2000)]).encode(),
            )
        return TransportResponse(status_code=429, raw_body=b'{"code":-1003,"msg":"Rate limited"}')

    c_fail = PrivateUserDataClient(
        transport=OfflineFixtureTransport(handler=fail_page_2, clock=clk),
        credentials=FakeCredentialProvider(),
        signer=DeterministicFakeSigner(),
        clock=clk,
    )
    res_fail = HistoryPaginator(client=c_fail, store=store).sync_user_trades(
        symbol="SOLUSDT", start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of, page_limit=2
    )
    assert res_fail.checkpoint.status == "PARTIAL"
    assert res_fail.coverage.status in ("PARTIAL", "RATE_LIMITED")
    assert res_fail.coverage.page_coverage_complete is False
    assert len(res_fail.coverage.gap_windows) >= 1

    # 4. Retention gap (>90 days requested on income) -> remains PARTIAL with RETENTION_GAP_3M_INCOME!
    c_inc = PrivateUserDataClient(
        transport=OfflineFixtureTransport(routes={ROUTE_INCOME: []}, clock=clk),
        credentials=FakeCredentialProvider(),
        signer=DeterministicFakeSigner(),
        clock=clk,
    )
    res_ret = HistoryPaginator(client=c_inc, store=store).sync_income(
        symbol="BTCUSDT",
        start_ms=as_of - 95 * DAY_MS,
        end_ms=as_of,
        as_of_venue_ms=as_of,
    )
    assert res_ret.checkpoint.status == "PARTIAL"
    assert res_ret.coverage.status == "PARTIAL"
    assert any(g["reason"] == "RETENTION_GAP_3M_INCOME" for g in res_ret.coverage.gap_windows)


def test_canonical_accounting_no_double_count_realized_net_r_and_multi_asset_separation(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    exec_card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    as_of = max(DEFAULT_SYNTHETIC_AS_OF_MS, exec_card.as_of_ms + 80_000)

    # 1. Closed multi-leg round-trip (all USDT): exact Decimal reconciliation + realized net R!
    snap_multi = load_synthetic_scenario_into_store(
        scenario="partial_fills_multi_leg",
        private_db=tmp_path / "multi_leg.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    match_multi = match_episode_to_account(exec_card, snap_multi)
    assert match_multi.signal_trade_match == "MATCHED"
    assert len(match_multi.entry_fill_ids) == 3
    assert len(match_multi.exit_fill_ids) == 2

    report = compute_accounting_report(snap_multi, card=exec_card, match_result=match_multi, symbol_filter="BTCUSDT")
    assert report.coverage_status == "COMPLETE"
    assert report.reconciliation_status == "RECONCILED"
    assert report.discrepancies == ()
    # Verify NO double counting of commission or realizedPnl from income rows!
    assert report.canonical_realized_pnl_by_asset == {"USDT": Decimal("3.1750000")}
    assert report.canonical_commission_paid_by_asset == {"USDT": Decimal("0.1023575")}
    assert report.canonical_funding_fee_by_asset == {"USDT": Decimal("-0.0100000")}
    assert report.canonical_net_cashflow_by_asset == {"USDT": Decimal("3.0626425")}
    assert report.single_currency_net_available is True

    # Hand-verify per-order partial fill aggregation (order 30001 had 2 partial fills of 0.300 each = 0.600).
    order_30001 = next(row for row in report.per_order_view if row["order_id"] == 30001)
    assert order_30001["fill_count"] == 2
    assert order_30001["is_partial_fill_aggregate"] is True
    assert Decimal(order_30001["executed_qty"]) == Decimal("0.600")
    assert len(report.per_trade_view) == 5
    assert len(report.per_period_view) >= 1

    # Hand-verify realized net R against B2 unit_stop_loss_usdt (2.319660 * 1.000 base = 2.319660 USDT)!
    assert report.actual_vs_b2_projected is not None
    r_block = report.actual_vs_b2_projected["planned_vs_realized_net_r"]
    assert r_block["realized_net_r_status"] == "AVAILABLE"
    expected_denom = Decimal(str(exec_card.plan["unit_stop_loss_usdt"])) * Decimal("1.000")  # type: ignore[index]
    expected_r = Decimal("3.0626425") / expected_denom
    assert abs(Decimal(r_block["realized_net_r"]) - expected_r) < Decimal("1e-25")

    # 2. Multi-asset commissions (BNB + USDT): NEVER combined, realized net R MUST be ACTUAL_R_UNAVAILABLE!
    snap_fx = load_synthetic_scenario_into_store(
        scenario="funding_and_commission",
        private_db=tmp_path / "multi_asset.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    match_fx = match_episode_to_account(exec_card, snap_fx)
    rep_fx = compute_accounting_report(snap_fx, card=exec_card, match_result=match_fx, symbol_filter="BTCUSDT")
    assert rep_fx.reconciliation_status == "RECONCILED"
    assert rep_fx.single_currency_net_available is False
    assert rep_fx.canonical_commission_paid_by_asset == {
        "BNB": Decimal("0.00010000"),
        "USDT": Decimal("0.02583250"),
    }
    assert rep_fx.canonical_net_cashflow_by_asset["BNB"] == Decimal("-0.00010000")
    assert rep_fx.canonical_net_cashflow_by_asset["USDT"] == Decimal("1.24916750")
    assert "TRANSFER" in rep_fx.other_income_by_type_and_asset
    assert "FUTURE_NEW_INCOME_TYPE_V9" in rep_fx.other_income_by_type_and_asset
    assert rep_fx.actual_vs_b2_projected is not None
    fx_r = rep_fx.actual_vs_b2_projected["planned_vs_realized_net_r"]
    assert fx_r["realized_net_r_status"] == "ACTUAL_R_UNAVAILABLE"
    assert "NON_QUOTE_FEE_OR_FUNDING_ASSET_UNVALUED" in fx_r["reasons"]

    # 3. Discrepancy between userTrades and income[REALIZED_PNL] MUST be surfaced, never netted away!
    snap_disc = load_synthetic_scenario_into_store(
        scenario="funding_and_commission_discrepancy",
        private_db=tmp_path / "disc.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
        as_of_venue_ms=as_of,
    )
    rep_disc = compute_accounting_report(snap_disc, symbol_filter="BTCUSDT")
    assert rep_disc.reconciliation_status == "DISCREPANCY"
    assert any(d["type"] == "REALIZED_PNL_RECONCILIATION_DISCREPANCY" for d in rep_disc.discrepancies)
    rpnl_disc = next(d for d in rep_disc.discrepancies if d["type"] == "REALIZED_PNL_RECONCILIATION_DISCREPANCY")
    assert Decimal(rpnl_disc["delta"]) == Decimal("-0.10000000")
