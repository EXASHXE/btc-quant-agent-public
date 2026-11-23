"""Additional adversarial, boundary, deduplication, realized-R, protection, and roundtrip tests."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
from quant_personal_decision_b2.engine import Engine
from quant_personal_decision_b2.fixtures import (
    AFTER_TRIGGER,
    INITIAL,
    PULLBACK,
    FabricatedMarket,
)
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import DEFAULT_POLICY, MINUTE

from quant_personal_account_b3.accounting import compute_accounting_report
from quant_personal_account_b3.b2_reader import ReadOnlyB2JournalReader
from quant_personal_account_b3.client import (
    ROUTE_ALL_ORDERS,
    ROUTE_INCOME,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
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
from quant_personal_account_b3.models import raw_sha256
from quant_personal_account_b3.normalize import (
    NormalizedAlgoOrder,
    NormalizedOrder,
)
from quant_personal_account_b3.overlay import build_account_overlay
from quant_personal_account_b3.pagination import HistoryPaginator
from quant_personal_account_b3.service import load_synthetic_scenario_into_store
from quant_personal_account_b3.storage import PrivateAccountStore


def test_duplicate_fills_and_income_never_double_count_and_conflicts_flagged(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    exec_card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    snap = load_synthetic_scenario_into_store(
        scenario="partial_fills_multi_leg",
        private_db=tmp_path / "dup.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
    )
    # Feed exact duplicate fills and duplicate income rows -> totals MUST remain identical!
    snap_dup = replace(snap, fills=(*snap.fills, *snap.fills), income_rows=(*snap.income_rows, *snap.income_rows))
    rep_orig = compute_accounting_report(snap, symbol_filter="BTCUSDT")
    rep_dup = compute_accounting_report(snap_dup, symbol_filter="BTCUSDT")
    assert rep_dup.canonical_realized_pnl_by_asset == rep_orig.canonical_realized_pnl_by_asset
    assert rep_dup.canonical_commission_paid_by_asset == rep_orig.canonical_commission_paid_by_asset
    assert rep_dup.canonical_funding_fee_by_asset == rep_orig.canonical_funding_fee_by_asset
    assert rep_dup.reconciliation_status == "RECONCILED"
    assert len(rep_dup.per_trade_view) == len(rep_orig.per_trade_view)

    # Conflicting duplicate fill (same trade_id, altered realized_pnl) MUST trigger DISCREPANCY!
    mutated_fill = replace(snap.fills[0], realized_pnl=Decimal("999.00"))
    snap_conflict = replace(snap, fills=(*snap.fills, mutated_fill))
    rep_conflict = compute_accounting_report(snap_conflict, symbol_filter="BTCUSDT")
    assert rep_conflict.reconciliation_status == "DISCREPANCY"
    assert any(d["type"] == "CONFLICTING_DUPLICATE_FILL" for d in rep_conflict.discrepancies)


def test_realized_net_r_unavailable_and_partial_failure_modes(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    watch_card = b2_view.get_card(card_id=b2_pullback_long_journal["watch_card"]["card_id"])
    exec_card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])

    snap_multi = load_synthetic_scenario_into_store(
        scenario="partial_fills_multi_leg",
        private_db=tmp_path / "r_cases.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
    )
    match_ok = match_episode_to_account(exec_card, snap_multi)

    # 1. WATCH card has only B2_MARKET_PLAN_PREVIEW_V1 (no unit_stop_loss_usdt) -> ACTUAL_R_UNAVAILABLE!
    rep_preview = compute_accounting_report(snap_multi, card=watch_card, match_result=match_ok, symbol_filter="BTCUSDT")
    assert rep_preview.actual_vs_b2_projected is not None
    r_prev = rep_preview.actual_vs_b2_projected["planned_vs_realized_net_r"]
    assert r_prev["realized_net_r_status"] == "ACTUAL_R_UNAVAILABLE"
    assert "MISSING_B2_STOP_RISK_BASIS" in r_prev["reasons"]

    # 2. Missing/partial income coverage -> PARTIAL (never claims full realized net R without funding coverage!).
    partial_inc_cov = replace(snap_multi.endpoint_coverage[ROUTE_INCOME], status="PARTIAL", page_coverage_complete=False)
    snap_no_inc = replace(
        snap_multi,
        endpoint_coverage={**snap_multi.endpoint_coverage, ROUTE_INCOME: partial_inc_cov},
    )
    rep_part_inc = compute_accounting_report(snap_no_inc, card=exec_card, match_result=match_ok, symbol_filter="BTCUSDT")
    assert rep_part_inc.coverage_status == "PARTIAL"
    assert rep_part_inc.actual_vs_b2_projected is not None
    r_part = rep_part_inc.actual_vs_b2_projected["planned_vs_realized_net_r"]
    assert r_part["realized_net_r_status"] == "PARTIAL"
    assert "FUNDING_INCOME_COVERAGE_INCOMPLETE" in r_part["reasons"]

    # 3. Partial exit (only 1 of 2 exit fills present -> exit_qty < entry_qty) -> PARTIAL!
    snap_part_exit = replace(snap_multi, fills=snap_multi.fills[:-1])
    match_part_exit = match_episode_to_account(exec_card, snap_part_exit)
    rep_part_exit = compute_accounting_report(snap_part_exit, card=exec_card, match_result=match_part_exit, symbol_filter="BTCUSDT")
    assert rep_part_exit.actual_vs_b2_projected is not None
    r_pe = rep_part_exit.actual_vs_b2_projected["planned_vs_realized_net_r"]
    assert r_pe["realized_net_r_status"] == "PARTIAL"
    assert "PARTIAL_EXIT_POSITION_STILL_OPEN" in r_pe["reasons"]

    # 4. Unconfirmed PROBABLE_MATCH -> ACTUAL_R_UNAVAILABLE!
    snap_prob = load_synthetic_scenario_into_store(
        scenario="probable_matching",
        private_db=tmp_path / "r_prob.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
    )
    match_prob = match_episode_to_account(exec_card, snap_prob)
    rep_prob = compute_accounting_report(snap_prob, card=exec_card, match_result=match_prob, symbol_filter="BTCUSDT")
    assert rep_prob.actual_vs_b2_projected is not None
    r_pr = rep_prob.actual_vs_b2_projected["planned_vs_realized_net_r"]
    assert r_pr["realized_net_r_status"] == "ACTUAL_R_UNAVAILABLE"
    assert "SIGNAL_MATCH_NOT_CONFIRMED_PROBABLE_MATCH" in r_pr["reasons"]


def test_protection_adversarial_historical_wrong_side_overcoverage_and_orphan(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    exec_card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    snap_base = load_synthetic_scenario_into_store(
        scenario="one_way_protected",
        private_db=tmp_path / "prot_adv.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
    )

    # 1. Historical allAlgoOrders SL MUST NOT count as active protection when openAlgoOrders is empty!
    snap_hist_only = replace(snap_base, open_orders=(), open_algo_orders=())
    ov_hist = build_account_overlay(card=exec_card, snapshot=snap_hist_only)
    assert ov_hist["protection_status"] == "UNPROTECTED"

    # 2. TRIGGERED / FINISHED / EXPIRED Algo order in open_algo_orders MUST NOT count!
    triggered_sl = replace(snap_base.open_algo_orders[0], algo_status="TRIGGERED")
    snap_trig = replace(snap_base, open_orders=(), open_algo_orders=(triggered_sl,))
    ov_trig = build_account_overlay(card=exec_card, snapshot=snap_trig)
    assert ov_trig["protection_status"] == "UNPROTECTED"

    # 3. Wrong-side SL trigger (LONG SL trigger >= markPrice 100.85) -> CONFLICTING!
    wrong_trig_sl = replace(snap_base.open_algo_orders[0], trigger_price=Decimal("105.00"))
    snap_wrong = replace(snap_base, open_orders=(), open_algo_orders=(wrong_trig_sl,))
    ov_wrong = build_account_overlay(card=exec_card, snapshot=snap_wrong)
    assert ov_wrong["protection_status"] == "CONFLICTING"

    # 4. Over-coverage: non-closePosition SL quantity (0.900) exceeds position quantity (0.500) -> CONFLICTING!
    over_sl = replace(snap_base.open_algo_orders[0], close_position=False, quantity=Decimal("0.900"))
    snap_over = replace(snap_base, open_orders=(), open_algo_orders=(over_sl,))
    ov_over = build_account_overlay(card=exec_card, snapshot=snap_over)
    assert ov_over["protection_status"] == "CONFLICTING"

    # 5. Ordinary STOP_MARKET without reduceOnly or closePosition on One-way leg -> CONFLICTING!
    non_ro_ord = NormalizedOrder(
        symbol="BTCUSDT",
        order_id=99001,
        client_order_id="bad-sl",
        side="SELL",
        position_side="BOTH",
        order_type="STOP_MARKET",
        orig_type="STOP_MARKET",
        status="NEW",
        orig_qty=Decimal("0.500"),
        executed_qty=Decimal("0"),
        remaining_qty=Decimal("0.500"),
        price=Decimal("0"),
        avg_price=None,
        stop_price=Decimal("98.72"),
        activate_price=None,
        price_rate=None,
        working_type="MARK_PRICE",
        close_position=False,
        reduce_only=False,
        time_in_force="GTC",
        create_time_ms=DEFAULT_SYNTHETIC_AS_OF_MS,
        update_time_ms=DEFAULT_SYNTHETIC_AS_OF_MS,
        source_endpoint=ROUTE_OPEN_ORDERS,
    )
    snap_non_ro = replace(snap_base, open_orders=(non_ro_ord,), open_algo_orders=())
    ov_non_ro = build_account_overlay(card=exec_card, snapshot=snap_non_ro)
    assert ov_non_ro["protection_status"] == "CONFLICTING"

    # 6. Orphan reduceOnly Algo order when NO_POSITION -> CONFLICTING!
    snap_nopos = load_synthetic_scenario_into_store(
        scenario="no_position",
        private_db=tmp_path / "orphan.sqlite",
        symbol="BTCUSDT",
        episode_id=exec_card.episode_id,
    )
    orphan_algo = NormalizedAlgoOrder(
        symbol="BTCUSDT",
        algo_id=88001,
        client_algo_id="orphan-sl",
        algo_type="CONDITIONAL",
        order_type="STOP_MARKET",
        algo_status="NEW",
        side="SELL",
        position_side="BOTH",
        quantity=Decimal("0.500"),
        trigger_price=Decimal("98.72"),
        price=None,
        activate_price=None,
        callback_rate=None,
        working_type="MARK_PRICE",
        close_position=True,
        reduce_only=True,
        time_in_force="GTC",
        create_time_ms=DEFAULT_SYNTHETIC_AS_OF_MS,
        update_time_ms=DEFAULT_SYNTHETIC_AS_OF_MS,
        trigger_time_ms=None,
        actual_order_id=None,
        actual_price=None,
        trigger_result=None,
        source_endpoint=ROUTE_OPEN_ALGO_ORDERS,
    )
    snap_orphan = replace(snap_nopos, open_algo_orders=(orphan_algo,))
    ov_orphan = build_account_overlay(card=exec_card, snapshot=snap_orphan)
    assert ov_orphan["position_relation"] == "NO_POSITION"
    assert ov_orphan["protection_status"] == "CONFLICTING"


def test_b2_all_market_statuses_preserved_and_snapshot_store_roundtrip(tmp_path: Path) -> None:
    # Build a B2 journal with WATCH, EXECUTABLE, SOURCE_BLOCKED (stale), and INVALID cards!
    feed = FabricatedMarket(tmp_path / "b1_multi.sqlite", PULLBACK, "LONG")
    feed.scan(INITIAL)
    b2_db = tmp_path / "b2_multi.sqlite"
    j = Journal(b2_db, create=True, policy=DEFAULT_POLICY)
    eng = Engine(MarketSnapshotAdapter(feed.path, "fixture"), j)
    c_watch = eng.evaluate("BTCUSDT")
    feed.scan(AFTER_TRIGGER)
    c_exec = eng.evaluate("BTCUSDT")
    s5 = feed.scan(AFTER_TRIGGER + 5 * MINUTE + 1000, "stale")
    c_blocked = eng.evaluate(
        "BTCUSDT",
        scan=s5["scan_id"],
        as_of_ms=s5["decision_as_of_venue_ms"],
        reprice_minutes=5,
        episode_id=c_exec["episode_id"],
    )
    s10 = feed.scan(AFTER_TRIGGER + 10 * MINUTE + 1000, "invalid")
    c_invalid = eng.evaluate(
        "BTCUSDT",
        scan=s10["scan_id"],
        as_of_ms=s10["decision_as_of_venue_ms"],
        reprice_minutes=10,
        episode_id=c_exec["episode_id"],
    )
    assert [c_watch["market_status"], c_exec["market_status"], c_blocked["market_status"], c_invalid["market_status"]] == [
        "WATCH",
        "EXECUTABLE",
        "SOURCE_BLOCKED",
        "INVALID",
    ]
    before_sha = raw_sha256(b2_db.read_bytes())

    priv_db = tmp_path / "roundtrip_priv.sqlite"
    snap = load_synthetic_scenario_into_store(
        scenario="funding_and_commission",
        private_db=priv_db,
        symbol="BTCUSDT",
        episode_id=c_exec["episode_id"],
    )
    # Reload from SQLite and verify exact fidelity (Decimal, unknown fields, unknown enums, coverage).
    reloaded = PrivateAccountStore(priv_db, create=False).load_snapshot(snap.snapshot_id)
    assert reloaded is not None
    assert reloaded.snapshot_id == snap.snapshot_id
    assert reloaded.account is not None and snap.account is not None
    assert reloaded.account.raw_unknown_fields == snap.account.raw_unknown_fields
    assert reloaded.to_dict() == snap.to_dict()

    b2_view = ReadOnlyB2JournalReader(b2_db).load_and_verify()
    for card in b2_view.cards:
        ov_conn = build_account_overlay(card=card, snapshot=reloaded)
        ov_unavail = build_account_overlay(card=card, snapshot=None)
        # B2 market_status is ALWAYS preserved identically regardless of account availability!
        assert ov_conn["market_setup_status"] == card.market_status
        assert ov_unavail["market_setup_status"] == card.market_status

    assert raw_sha256(b2_db.read_bytes()) == before_sha


def test_multipage_all_orders_and_income_overlapping_window_dedup(tmp_path: Path) -> None:
    as_of = DEFAULT_SYNTHETIC_AS_OF_MS
    t0 = as_of - 30_000
    orders_data = [
        {
            "symbol": "BTCUSDT",
            "orderId": 500 + i,
            "clientOrderId": f"ord-{i}",
            "side": "BUY",
            "positionSide": "BOTH",
            "type": "LIMIT",
            "status": "FILLED",
            "origQty": "0.1",
            "executedQty": "0.1",
            "price": "100.5",
            "time": t0 + i * 1000,
            "updateTime": t0 + i * 1000,
        }
        for i in range(1, 6)
    ]
    income_data = [
        {
            "tranId": f"INC-{i}",
            "symbol": "BTCUSDT",
            "incomeType": "FUNDING_FEE",
            "income": "-0.005",
            "asset": "USDT",
            "info": "funding",
            "time": t0 + i * 2000,
        }
        for i in range(1, 5)
    ]

    def handler(req: SignedPrivateRequest) -> TransportResponse:
        params = dict(p.split("=", 1) for p in req.canonical_unsigned_query.split("&") if "=" in p)
        start_t = int(params.get("startTime", "0"))
        end_t = int(params.get("endTime", str(as_of)))
        lim = int(params.get("limit", "2"))
        if req.path == ROUTE_ALL_ORDERS:
            rows = [r for r in orders_data if start_t <= r["updateTime"] <= end_t][:lim]
        else:
            rows = [r for r in income_data if start_t <= r["time"] <= end_t][:lim]
        return TransportResponse(status_code=200, raw_body=json.dumps(rows).encode())

    store = PrivateAccountStore(tmp_path / "mp.sqlite", create=True)
    clk = DeterministicFakeClock(wall_ms=as_of - 500, venue_offset_ms=100)
    client = PrivateUserDataClient(
        transport=OfflineFixtureTransport(handler=handler, clock=clk),
        credentials=FakeCredentialProvider(),
        signer=DeterministicFakeSigner(),
        clock=clk,
    )
    pag = HistoryPaginator(client=client, store=store)
    res_ord = pag.sync_all_orders(symbol="BTCUSDT", start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of, page_limit=2)
    assert res_ord.checkpoint.status == "COMPLETE"
    assert [o.order_id for o in res_ord.orders] == [501, 502, 503, 504, 505]

    # Overlapping window rerun produces exact same deduplicated 5 orders.
    res_ord2 = pag.sync_all_orders(symbol="BTCUSDT", start_ms=t0 - 5000, end_ms=as_of, as_of_venue_ms=as_of, page_limit=2)
    assert [o.order_id for o in res_ord2.orders] == [501, 502, 503, 504, 505]

    res_inc = pag.sync_income(symbol="BTCUSDT", start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of, page_limit=2)
    assert res_inc.checkpoint.status == "COMPLETE"
    assert [r.tran_id for r in res_inc.income_rows] == ["INC-1", "INC-2", "INC-3", "INC-4"]
    # Overlapping income window rerun never double-counts!
    res_inc2 = pag.sync_income(symbol="BTCUSDT", start_ms=t0 - 5000, end_ms=as_of, as_of_venue_ms=as_of, page_limit=2)
    assert [r.tran_id for r in res_inc2.income_rows] == ["INC-1", "INC-2", "INC-3", "INC-4"]
