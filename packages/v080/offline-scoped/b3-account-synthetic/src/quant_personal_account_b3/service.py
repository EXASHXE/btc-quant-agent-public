"""End-to-end B3 offline snapshot collection, overlay publishing, and demo orchestration."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from quant_personal_decision_b2.cli import demo as b2_demo

from .b2_reader import ReadOnlyB2JournalReader
from .client import (
    ROUTE_ACCOUNT,
    ROUTE_ALL_ALGO_ORDERS,
    ROUTE_ALL_ORDERS,
    ROUTE_INCOME,
    ROUTE_OPEN_ALGO_ORDERS,
    ROUTE_OPEN_ORDERS,
    ROUTE_POSITION_RISK,
    ROUTE_USER_TRADES,
    PrivateUserDataClient,
)
from .fixtures import (
    DEFAULT_SYNTHETIC_AS_OF_MS,
    SCENARIO_NAMES,
    build_synthetic_scenario,
)
from .models import (
    DAY_MS,
    SYNTHETIC_BANNER_TEXT,
    AccountB3Error,
    encode,
)
from .normalize import (
    DEFAULT_HISTORY_FRESHNESS_MS,
    DEFAULT_LIVE_FRESHNESS_MS,
    EndpointCoverage,
    NormalizedAccount,
    NormalizedAlgoOrder,
    NormalizedFill,
    NormalizedIncome,
    NormalizedOrder,
    NormalizedPosition,
    PrivateAccountSnapshot,
    build_endpoint_coverage,
    build_snapshot_id,
    compute_overall_snapshot_status,
    normalize_account,
    normalize_algo_orders,
    normalize_orders,
    normalize_positions,
)
from .overlay import build_account_overlay
from .pagination import HistoryPaginator
from .storage import ManualAssociation, OverlayJournal, PrivateAccountStore


def collect_private_snapshot(
    *,
    client: PrivateUserDataClient,
    store: PrivateAccountStore,
    symbol: str,
    as_of_venue_ms: int,
    history_lookback_ms: int = DAY_MS,
    live_freshness_ms: int = DEFAULT_LIVE_FRESHNESS_MS,
    history_freshness_ms: int = DEFAULT_HISTORY_FRESHNESS_MS,
    stale_overrides: dict[str, int] | None = None,
) -> PrivateAccountSnapshot:
    """Collect a NON_ATOMIC multi-endpoint synthetic snapshot and persist it transactionally."""
    stale_map = stale_overrides or {}
    coverage: dict[str, EndpointCoverage] = {}
    notes: list[str] = ["Multi-endpoint snapshot is NON_ATOMIC; each endpoint carries independent timing and status."]

    account: NormalizedAccount | None = None
    positions: tuple[NormalizedPosition, ...] = ()
    open_orders: tuple[NormalizedOrder, ...] = ()
    open_algo_orders: tuple[NormalizedAlgoOrder, ...] = ()

    # 1. GET /fapi/v3/account
    try:
        raw_acc, acc_rcpt = client.get_account()
        account = normalize_account(raw_acc)
        if ROUTE_ACCOUNT in stale_map:
            acc_rcpt = replace(acc_rcpt, venue_time_estimate_ms=as_of_venue_ms - stale_map[ROUTE_ACCOUNT])
        coverage[ROUTE_ACCOUNT] = build_endpoint_coverage(
            endpoint=ROUTE_ACCOUNT,
            symbol=None,
            as_of_venue_ms=as_of_venue_ms,
            receipt=acc_rcpt,
            record_count=1,
            freshness_limit_ms=live_freshness_ms,
        )
    except AccountB3Error as exc:
        coverage[ROUTE_ACCOUNT] = build_endpoint_coverage(
            endpoint=ROUTE_ACCOUNT,
            symbol=None,
            as_of_venue_ms=as_of_venue_ms,
            receipt=None,
            record_count=0,
            freshness_limit_ms=live_freshness_ms,
            error_code=exc.code,
            error_detail=exc.detail,
        )

    # 2. GET /fapi/v3/positionRisk
    try:
        raw_pos, pos_rcpt = client.get_position_risk(symbol=symbol)
        positions = normalize_positions(raw_pos)
        if ROUTE_POSITION_RISK in stale_map:
            pos_rcpt = replace(pos_rcpt, venue_time_estimate_ms=as_of_venue_ms - stale_map[ROUTE_POSITION_RISK])
        coverage[ROUTE_POSITION_RISK] = build_endpoint_coverage(
            endpoint=ROUTE_POSITION_RISK,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=pos_rcpt,
            record_count=len(positions),
            freshness_limit_ms=live_freshness_ms,
        )
    except AccountB3Error as exc:
        coverage[ROUTE_POSITION_RISK] = build_endpoint_coverage(
            endpoint=ROUTE_POSITION_RISK,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=None,
            record_count=0,
            freshness_limit_ms=live_freshness_ms,
            error_code=exc.code,
            error_detail=exc.detail,
        )

    # 3. GET /fapi/v1/openOrders
    try:
        raw_oo, oo_rcpt = client.get_open_orders(symbol=symbol)
        open_orders = normalize_orders(raw_oo, source_endpoint=ROUTE_OPEN_ORDERS)
        if ROUTE_OPEN_ORDERS in stale_map:
            oo_rcpt = replace(oo_rcpt, venue_time_estimate_ms=as_of_venue_ms - stale_map[ROUTE_OPEN_ORDERS])
        coverage[ROUTE_OPEN_ORDERS] = build_endpoint_coverage(
            endpoint=ROUTE_OPEN_ORDERS,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=oo_rcpt,
            record_count=len(open_orders),
            freshness_limit_ms=live_freshness_ms,
        )
    except AccountB3Error as exc:
        coverage[ROUTE_OPEN_ORDERS] = build_endpoint_coverage(
            endpoint=ROUTE_OPEN_ORDERS,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=None,
            record_count=0,
            freshness_limit_ms=live_freshness_ms,
            error_code=exc.code,
            error_detail=exc.detail,
        )

    # 4. GET /fapi/v1/openAlgoOrders
    try:
        raw_oao, oao_rcpt = client.get_open_algo_orders(symbol=symbol)
        open_algo_orders = normalize_algo_orders(raw_oao, source_endpoint=ROUTE_OPEN_ALGO_ORDERS)
        if ROUTE_OPEN_ALGO_ORDERS in stale_map:
            oao_rcpt = replace(oao_rcpt, venue_time_estimate_ms=as_of_venue_ms - stale_map[ROUTE_OPEN_ALGO_ORDERS])
        coverage[ROUTE_OPEN_ALGO_ORDERS] = build_endpoint_coverage(
            endpoint=ROUTE_OPEN_ALGO_ORDERS,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=oao_rcpt,
            record_count=len(open_algo_orders),
            freshness_limit_ms=live_freshness_ms,
        )
    except AccountB3Error as exc:
        coverage[ROUTE_OPEN_ALGO_ORDERS] = build_endpoint_coverage(
            endpoint=ROUTE_OPEN_ALGO_ORDERS,
            symbol=symbol,
            as_of_venue_ms=as_of_venue_ms,
            receipt=None,
            record_count=0,
            freshness_limit_ms=live_freshness_ms,
            error_code=exc.code,
            error_detail=exc.detail,
        )

    # 5-8. Paginated historical endpoints via bounded HistoryPaginator with durable checkpoints.
    paginator = HistoryPaginator(client=client, store=store, freshness_limit_ms=history_freshness_ms)
    win_start = as_of_venue_ms - history_lookback_ms

    trades_res = paginator.sync_user_trades(
        symbol=symbol, start_ms=win_start, end_ms=as_of_venue_ms, as_of_venue_ms=as_of_venue_ms
    )
    all_ord_res = paginator.sync_all_orders(
        symbol=symbol, start_ms=win_start, end_ms=as_of_venue_ms, as_of_venue_ms=as_of_venue_ms
    )
    all_algo_res = paginator.sync_all_algo_orders(
        symbol=symbol, start_ms=win_start, end_ms=as_of_venue_ms, as_of_venue_ms=as_of_venue_ms
    )
    inc_res = paginator.sync_income(
        symbol=None, start_ms=win_start, end_ms=as_of_venue_ms, as_of_venue_ms=as_of_venue_ms
    )

    coverage[ROUTE_USER_TRADES] = trades_res.coverage
    coverage[ROUTE_ALL_ORDERS] = all_ord_res.coverage
    coverage[ROUTE_ALL_ALGO_ORDERS] = all_algo_res.coverage
    coverage[ROUTE_INCOME] = inc_res.coverage

    fills: tuple[NormalizedFill, ...] = trades_res.fills
    all_orders: tuple[NormalizedOrder, ...] = all_ord_res.orders
    all_algo_orders: tuple[NormalizedAlgoOrder, ...] = all_algo_res.algo_orders
    income_rows: tuple[NormalizedIncome, ...] = inc_res.income_rows

    overall = compute_overall_snapshot_status(coverage)
    snap_id = build_snapshot_id(as_of_venue_ms=as_of_venue_ms, symbol_scope=symbol, coverage=coverage)

    snapshot = PrivateAccountSnapshot(
        snapshot_id=snap_id,
        as_of_venue_ms=as_of_venue_ms,
        symbol_scope=symbol,
        account=account,
        positions=positions,
        open_orders=open_orders,
        open_algo_orders=open_algo_orders,
        all_orders=all_orders,
        all_algo_orders=all_algo_orders,
        fills=fills,
        income_rows=income_rows,
        endpoint_coverage=coverage,
        overall_status=overall,
        notes=tuple(notes),
    )
    store.save_snapshot(snapshot)
    return snapshot


def load_synthetic_scenario_into_store(
    *,
    scenario: str,
    private_db: Path,
    symbol: str = "BTCUSDT",
    episode_id: str | None = None,
    as_of_venue_ms: int = DEFAULT_SYNTHETIC_AS_OF_MS,
) -> PrivateAccountSnapshot:
    """Instantiate a synthetic fixture scenario, query via PrivateUserDataClient, and persist to B3 private store."""
    bundle = build_synthetic_scenario(
        scenario,
        symbol=symbol,
        episode_id=episode_id,
        as_of_venue_ms=as_of_venue_ms,
    )
    store = PrivateAccountStore(private_db, create=True)
    stale_overrides = {ep: bundle.stale_age_ms for ep in bundle.stale_endpoints}
    return collect_private_snapshot(
        client=bundle.client,
        store=store,
        symbol=symbol,
        as_of_venue_ms=as_of_venue_ms,
        stale_overrides=stale_overrides,
    )


def generate_and_publish_overlay(
    *,
    b2_journal_path: Path,
    overlay_journal_path: Path,
    private_db_path: Path | None = None,
    card_id: str | None = None,
    episode_id: str | None = None,
    symbol: str | None = None,
    snapshot_id: str | None = None,
) -> dict[str, Any]:
    """Read verified B2 card (strictly read-only), join optional B3 private store, and publish to B3 overlay journal."""
    b2_view = ReadOnlyB2JournalReader(b2_journal_path).load_and_verify()
    card = b2_view.get_card(card_id=card_id, episode_id=episode_id, symbol=symbol)

    snapshot: PrivateAccountSnapshot | None = None
    manual_links: tuple[ManualAssociation, ...] = ()
    if private_db_path is not None:
        store = PrivateAccountStore(private_db_path, create=False)
        snapshot = store.load_snapshot(snapshot_id=snapshot_id)
        manual_links = store.list_manual_associations(b2_episode_id=card.episode_id)

    overlay = build_account_overlay(
        card=card,
        snapshot=snapshot,
        peer_cards=b2_view.cards,
        manual_associations=manual_links,
    )
    journal = OverlayJournal(overlay_journal_path, create=True)
    return journal.publish(overlay)


def run_offline_demo(output_dir: Path, *, existing_b2_journal: Path | None = None) -> dict[str, Any]:
    """Generate a reproducible offline B3 demo suite using accepted B2 contracts and all synthetic scenarios."""
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=False)

    if existing_b2_journal is not None:
        b2_db = existing_b2_journal.resolve()
    else:
        b2_out = output_dir / "b2_demo"
        b2_demo(b2_out)
        b2_db = b2_out / "pullback-long" / "decision.sqlite"

    b2_view = ReadOnlyB2JournalReader(b2_db).load_and_verify()
    # Select the triggered EXECUTABLE card (card_1) from B2 pullback-long!
    exec_cards = [c for c in b2_view.cards if c.market_status == "EXECUTABLE"]
    target_card = exec_cards[0] if exec_cards else b2_view.cards[-1]

    demo_scenarios = (
        "no_position",
        "one_way_protected",
        "hedge_long_short",
        "short_opposite",
        "multiple_position_legs",
        "ordinary_and_algo_protection",
        "partial_protection",
        "no_protection",
        "conflicting_orders",
        "partial_fills_multi_leg",
        "funding_and_commission",
        "funding_and_commission_discrepancy",
        "stale_endpoint",
        "partial_missing_algo",
        "ambiguous_matching",
        "probable_matching",
        "public_only_fallback",
    )
    assert set(demo_scenarios) == set(SCENARIO_NAMES)

    results: list[dict[str, Any]] = []
    for scenario in demo_scenarios:
        case_dir = output_dir / "scenarios" / scenario
        case_dir.mkdir(parents=True, exist_ok=False)
        private_db = case_dir / "private_account.sqlite"
        overlay_db = case_dir / "overlay_journal.sqlite"

        snap = load_synthetic_scenario_into_store(
            scenario=scenario,
            private_db=private_db,
            symbol=target_card.symbol,
            episode_id=target_card.episode_id,
            as_of_venue_ms=max(DEFAULT_SYNTHETIC_AS_OF_MS, target_card.as_of_ms + 80_000),
        )
        overlay = generate_and_publish_overlay(
            b2_journal_path=b2_db,
            overlay_journal_path=overlay_db,
            private_db_path=private_db if scenario != "public_only_fallback" else None,
            card_id=target_card.card_id,
        )
        replay = OverlayJournal(overlay_db).replay()
        replayed_overlay = OverlayJournal(overlay_db).read(overlay_id=overlay["overlay_id"])
        replay_equal = replayed_overlay == overlay and replay["verified"] is True

        (case_dir / "snapshot.json").write_text(json.dumps(snap.to_dict(), indent=2) + "\n", encoding="utf-8")
        (case_dir / "overlay.json").write_text(json.dumps(overlay, indent=2) + "\n", encoding="utf-8")
        (case_dir / "replay.json").write_text(json.dumps(replay, indent=2) + "\n", encoding="utf-8")

        results.append(
            {
                "scenario": scenario,
                "b2_card_id": target_card.card_id,
                "b2_episode_id": target_card.episode_id,
                "market_setup_status": overlay["market_setup_status"],
                "account_context_status": overlay["account_context_status"],
                "position_relation": overlay["position_relation"],
                "protection_status": overlay["protection_status"],
                "signal_trade_match": overlay["signal_trade_match"],
                "reconciliation_status": overlay["accounting_reconciliation"]["reconciliation_cross_check"]["status"],
                "realized_net_r_status": overlay["accounting_reconciliation"]["actual_vs_b2_projected"][
                    "planned_vs_realized_net_r"
                ]["realized_net_r_status"],
                "real_account_connected": overlay["real_account_connected"],
                "replay_equal": replay_equal,
            }
        )

    # Confirm B2 DB remained byte-identical across the entire demo.
    b2_view_after = ReadOnlyB2JournalReader(b2_db).load_and_verify()
    summary = {
        "evidence_banner": SYNTHETIC_BANNER_TEXT,
        "real_account_connected": False,
        "b2_journal_sha256_before": b2_view.db_file_sha256,
        "b2_journal_sha256_after": b2_view_after.db_file_sha256,
        "b2_journal_immutable": b2_view.db_file_sha256 == b2_view_after.db_file_sha256,
        "scenario_count": len(results),
        "all_replays_equal": all(r["replay_equal"] for r in results),
        "scenarios": results,
    }
    (output_dir / "summary.json").write_text(encode(summary) + "\n", encoding="utf-8")
    (output_dir / "summary_pretty.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary
