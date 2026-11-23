"""Multi-to-many SignalEpisode-to-account reconciliation without statistical probabilities."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .b2_reader import B2CardRecord
from .models import SCHEMA_MATCH, ZERO, D, decimal_str
from .normalize import (
    NormalizedAlgoOrder,
    NormalizedFill,
    NormalizedOrder,
    NormalizedPosition,
    PrivateAccountSnapshot,
)
from .storage import ManualAssociation

DIRECT_ID_PREFIX_LEN = 12


@dataclass(frozen=True)
class EpisodeMatchResult:
    """Deterministic multi-to-many match result for one B2 card/episode."""

    b2_card_id: str
    b2_episode_id: str | None
    symbol: str
    signal_trade_match: str  # MATCHED | PROBABLE_MATCH | UNMATCHED | AMBIGUOUS
    machine_match_status: str  # MATCHED | PROBABLE_MATCH | UNMATCHED | AMBIGUOUS
    reason_codes: tuple[str, ...]
    evidence_summary: tuple[dict[str, Any], ...]
    matched_order_ids: tuple[int, ...]
    matched_algo_ids: tuple[int, ...]
    matched_trade_ids: tuple[int, ...]
    matched_income_tran_ids: tuple[str, ...]
    linked_position_sides: tuple[str, ...]
    shared_position_episode_ids: tuple[str, ...]
    owner_entered_associations: tuple[dict[str, Any], ...]
    owner_contradictions: tuple[str, ...]
    entry_fill_ids: tuple[int, ...]
    exit_fill_ids: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_MATCH,
            "b2_card_id": self.b2_card_id,
            "b2_episode_id": self.b2_episode_id,
            "symbol": self.symbol,
            "signal_trade_match": self.signal_trade_match,
            "machine_match_status": self.machine_match_status,
            "statistical_match_probability": "NOT_USED_DETERMINISTIC_RULES_ONLY",
            "reason_codes": list(self.reason_codes),
            "evidence_summary": list(self.evidence_summary),
            "matched_order_ids": list(self.matched_order_ids),
            "matched_algo_ids": list(self.matched_algo_ids),
            "matched_trade_ids": list(self.matched_trade_ids),
            "matched_income_tran_ids": list(self.matched_income_tran_ids),
            "linked_position_sides": list(self.linked_position_sides),
            "shared_position_episode_ids": list(self.shared_position_episode_ids),
            "owner_entered_associations": list(self.owner_entered_associations),
            "owner_contradictions": list(self.owner_contradictions),
            "entry_fill_ids": list(self.entry_fill_ids),
            "exit_fill_ids": list(self.exit_fill_ids),
        }


def _entry_side_for_direction(direction: str) -> str:
    return "BUY" if direction == "LONG" else "SELL"


def _exit_side_for_direction(direction: str) -> str:
    return "SELL" if direction == "LONG" else "BUY"


def _position_side_compatible(pos_side: str, direction: str) -> bool:
    return pos_side == "BOTH" or pos_side == direction


def _client_id_matches_episode(client_id: str, episode_id: str) -> bool:
    if not client_id or not episode_id:
        return False
    lowered = client_id.lower()
    ep_lower = episode_id.lower()
    if ep_lower in lowered:
        return True
    prefix = ep_lower[:DIRECT_ID_PREFIX_LEN]
    return len(prefix) == DIRECT_ID_PREFIX_LEN and prefix in lowered


def _entry_price_band(card: B2CardRecord, episode: dict[str, Any]) -> tuple[Decimal, Decimal] | None:
    plan = card.plan
    if plan and plan.get("entry_low") is not None and plan.get("entry_high") is not None:
        lo, hi = D(str(plan["entry_low"])), D(str(plan["entry_high"]))
        return (min(lo, hi), max(lo, hi))
    band = episode.get("entry_band_unrounded")
    if isinstance(band, list) and len(band) == 2:
        lo, hi = D(str(band[0])), D(str(band[1]))
        return (min(lo, hi), max(lo, hi))
    return None


def _price_within_band(price: Decimal, band: tuple[Decimal, Decimal] | None, atr: Decimal) -> bool:
    if band is None or price <= ZERO:
        return False
    lo, hi = band
    # Allow exact entry band with minimal 0.10 ATR tolerance for market slippage; never match far-away prices.
    tol = max(D("0"), atr * D("0.10"))
    return (lo - tol) <= price <= (hi + tol)


def _deduplicate_orders(snapshot: PrivateAccountSnapshot, symbol: str) -> list[NormalizedOrder]:
    by_id: dict[int, NormalizedOrder] = {}
    for order in (*snapshot.all_orders, *snapshot.open_orders):
        if order.symbol != symbol:
            continue
        prev = by_id.get(order.order_id)
        if prev is None or (order.update_time_ms or 0) >= (prev.update_time_ms or 0):
            by_id[order.order_id] = order
    return sorted(by_id.values(), key=lambda o: (o.create_time_ms or o.update_time_ms or 0, o.order_id))


def _deduplicate_algos(snapshot: PrivateAccountSnapshot, symbol: str) -> list[NormalizedAlgoOrder]:
    by_id: dict[int, NormalizedAlgoOrder] = {}
    for algo in (*snapshot.all_algo_orders, *snapshot.open_algo_orders):
        if algo.symbol != symbol:
            continue
        prev = by_id.get(algo.algo_id)
        if prev is None or (algo.update_time_ms or 0) >= (prev.update_time_ms or 0):
            by_id[algo.algo_id] = algo
    return sorted(by_id.values(), key=lambda a: (a.create_time_ms or a.update_time_ms or 0, a.algo_id))


def _order_effective_price(order: NormalizedOrder, fills_by_order: dict[int, list[NormalizedFill]]) -> Decimal:
    order_fills = fills_by_order.get(order.order_id, [])
    if order_fills:
        total_qty = sum((f.qty for f in order_fills), ZERO)
        if total_qty > ZERO:
            return sum((f.price * f.qty for f in order_fills), ZERO) / total_qty
    if order.avg_price is not None and order.avg_price > ZERO:
        return order.avg_price
    if order.price > ZERO:
        return order.price
    return order.stop_price or ZERO


def _order_time_ms(order: NormalizedOrder, fills_by_order: dict[int, list[NormalizedFill]]) -> int:
    if order.create_time_ms is not None and order.create_time_ms > 0:
        return order.create_time_ms
    order_fills = fills_by_order.get(order.order_id, [])
    if order_fills:
        return min(f.trade_time_ms for f in order_fills)
    return order.update_time_ms or 0


def _order_matches_probable_entry(
    order: NormalizedOrder,
    *,
    episode: dict[str, Any],
    card: B2CardRecord,
    fills_by_order: dict[int, list[NormalizedFill]],
) -> bool:
    direction = str(episode["direction"])
    entry_side = _entry_side_for_direction(direction)
    if order.reduce_only or order.close_position:
        return False
    if order.side != entry_side or not _position_side_compatible(order.position_side, direction):
        return False
    ts = _order_time_ms(order, fills_by_order)
    frozen_ms = int(episode["frozen_at_ms"])
    expires_ms = int(episode["expires_at_ms"])
    if ts < frozen_ms or ts > expires_ms:
        return False
    band = _entry_price_band(card, episode)
    atr = D(str(episode["atr14"]))
    eff_price = _order_effective_price(order, fills_by_order)
    if not _price_within_band(eff_price, band, atr):
        return False
    if order.orig_qty <= ZERO and order.executed_qty <= ZERO:
        return False
    return True


def match_episode_to_account(
    card: B2CardRecord,
    snapshot: PrivateAccountSnapshot | None,
    *,
    peer_cards: tuple[B2CardRecord, ...] = (),
    manual_associations: tuple[ManualAssociation, ...] = (),
) -> EpisodeMatchResult:
    """Reconcile a B2 SignalEpisode/MarketPlan against private orders, algos, fills, positions, and income."""
    ep = card.episode_payload
    if snapshot is None:
        return EpisodeMatchResult(
            b2_card_id=card.card_id,
            b2_episode_id=card.episode_id,
            symbol=card.symbol,
            signal_trade_match="UNMATCHED",
            machine_match_status="UNMATCHED",
            reason_codes=("ACCOUNT_CONTEXT_UNAVAILABLE",),
            evidence_summary=(),
            matched_order_ids=(),
            matched_algo_ids=(),
            matched_trade_ids=(),
            matched_income_tran_ids=(),
            linked_position_sides=(),
            shared_position_episode_ids=(),
            owner_entered_associations=(),
            owner_contradictions=(),
            entry_fill_ids=(),
            exit_fill_ids=(),
        )

    if ep is None or card.episode_id is None:
        return EpisodeMatchResult(
            b2_card_id=card.card_id,
            b2_episode_id=None,
            symbol=card.symbol,
            signal_trade_match="UNMATCHED",
            machine_match_status="UNMATCHED",
            reason_codes=("NO_B2_EPISODE_ON_CARD",),
            evidence_summary=(),
            matched_order_ids=(),
            matched_algo_ids=(),
            matched_trade_ids=(),
            matched_income_tran_ids=(),
            linked_position_sides=(),
            shared_position_episode_ids=(),
            owner_entered_associations=(),
            owner_contradictions=(),
            entry_fill_ids=(),
            exit_fill_ids=(),
        )

    episode_id = card.episode_id
    symbol = card.symbol
    direction = str(ep["direction"])
    entry_side = _entry_side_for_direction(direction)
    exit_side = _exit_side_for_direction(direction)
    frozen_ms = int(ep["frozen_at_ms"])
    expires_ms = int(ep["expires_at_ms"])
    band = _entry_price_band(card, ep)
    atr = D(str(ep["atr14"]))

    orders = _deduplicate_orders(snapshot, symbol)
    algos = _deduplicate_algos(snapshot, symbol)
    fills = sorted((f for f in snapshot.fills if f.symbol == symbol), key=lambda f: (f.trade_time_ms, f.trade_id))
    fills_by_order: dict[int, list[NormalizedFill]] = {}
    for fill in fills:
        fills_by_order.setdefault(fill.order_id, []).append(fill)
    orders_by_id = {o.order_id: o for o in orders}
    algos_by_id = {a.algo_id: a for a in algos}
    fills_by_id = {f.trade_id: f for f in fills}

    reasons: list[str] = []
    evidence: list[dict[str, Any]] = []
    matched_order_ids: set[int] = set()
    matched_algo_ids: set[int] = set()
    matched_trade_ids: set[int] = set()
    entry_fill_ids: set[int] = set()
    exit_fill_ids: set[int] = set()
    direct_contradiction = False

    # 1. Direct client ID matching across orders and algo orders.
    direct_orders: list[NormalizedOrder] = []
    for order in orders:
        if _client_id_matches_episode(order.client_order_id, episode_id):
            ts = _order_time_ms(order, fills_by_order)
            consistent_side = (
                (not order.reduce_only and not order.close_position and order.side == entry_side)
                or ((order.reduce_only or order.close_position) and order.side == exit_side)
                or (order.side == exit_side and any(f.realized_pnl != ZERO for f in fills_by_order.get(order.order_id, [])))
            )
            if ts < frozen_ms or not _position_side_compatible(order.position_side, direction) or not consistent_side:
                direct_contradiction = True
                reasons.append("DIRECT_CLIENT_ID_CONTRADICTS_EPISODE_SEMANTICS")
                evidence.append(
                    {
                        "type": "DIRECT_ORDER_CONTRADICTION",
                        "order_id": order.order_id,
                        "client_order_id": order.client_order_id,
                        "side": order.side,
                        "position_side": order.position_side,
                        "time_ms": ts,
                        "episode_frozen_ms": frozen_ms,
                    }
                )
            else:
                direct_orders.append(order)
                matched_order_ids.add(order.order_id)
                evidence.append(
                    {
                        "type": "DIRECT_CLIENT_ORDER_ID",
                        "order_id": order.order_id,
                        "client_order_id": order.client_order_id,
                        "side": order.side,
                        "position_side": order.position_side,
                        "price": decimal_str(_order_effective_price(order, fills_by_order)),
                        "qty": decimal_str(order.orig_qty),
                        "time_ms": ts,
                    }
                )

    direct_algos: list[NormalizedAlgoOrder] = []
    for algo in algos:
        if _client_id_matches_episode(algo.client_algo_id, episode_id):
            ts = algo.create_time_ms or algo.update_time_ms or 0
            if ts < frozen_ms or not _position_side_compatible(algo.position_side, direction):
                direct_contradiction = True
                reasons.append("DIRECT_ALGO_ID_CONTRADICTS_EPISODE_SEMANTICS")
            else:
                direct_algos.append(algo)
                matched_algo_ids.add(algo.algo_id)
                if algo.actual_order_id is not None and algo.actual_order_id in orders_by_id:
                    matched_order_ids.add(algo.actual_order_id)
                evidence.append(
                    {
                        "type": "DIRECT_CLIENT_ALGO_ID",
                        "algo_id": algo.algo_id,
                        "client_algo_id": algo.client_algo_id,
                        "order_type": algo.order_type,
                        "side": algo.side,
                        "position_side": algo.position_side,
                        "trigger_price": decimal_str(algo.trigger_price),
                        "time_ms": ts,
                    }
                )

    machine_status = "UNMATCHED"
    if direct_contradiction:
        machine_status = "AMBIGUOUS"
    elif direct_orders or direct_algos:
        machine_status = "MATCHED"
        reasons.append("DIRECT_EXCHANGE_CLIENT_ID_MATCH")
    else:
        # 2. Multi-field heuristic matching (NEVER confirmed MATCHED; at most PROBABLE_MATCH or AMBIGUOUS).
        candidate_orders = [
            order
            for order in orders
            if _order_matches_probable_entry(order, episode=ep, card=card, fills_by_order=fills_by_order)
        ]

        # Also check standalone fills whose order isn't in openOrders/allOrders.
        known_order_ids = {o.order_id for o in orders}
        orphan_candidate_fills = [
            fill
            for fill in fills
            if fill.order_id not in known_order_ids
            and fill.side == entry_side
            and _position_side_compatible(fill.position_side, direction)
            and frozen_ms <= fill.trade_time_ms <= expires_ms
            and _price_within_band(fill.price, band, atr)
            and fill.qty > ZERO
        ]
        orphan_order_groups = sorted({f.order_id for f in orphan_candidate_fills})

        # Check competing peer episodes on the same symbol that could also claim the same candidate order.
        competing_episodes: list[str] = []
        distinct_peers = {
            p.episode_id: p
            for p in peer_cards
            if p.episode_id is not None and p.episode_id != episode_id and p.symbol == symbol and p.episode_payload is not None
        }
        for cand in candidate_orders:
            for peer_id, peer_card in distinct_peers.items():
                assert peer_card.episode_payload is not None
                if _order_matches_probable_entry(
                    cand, episode=peer_card.episode_payload, card=peer_card, fills_by_order=fills_by_order
                ):
                    competing_episodes.append(peer_id)

        # Symbol+time-only candidates whose price does NOT fall near entry band -> explicitly NOT matched.
        symbol_time_only = [
            order
            for order in orders
            if not order.reduce_only
            and not order.close_position
            and order.side == entry_side
            and frozen_ms <= _order_time_ms(order, fills_by_order) <= expires_ms
            and order not in candidate_orders
        ]

        total_candidate_groups = len(candidate_orders) + len(orphan_order_groups)
        if competing_episodes:
            machine_status = "AMBIGUOUS"
            reasons.append("COMPETING_EPISODES_CLAIM_SAME_CANDIDATE_ORDER")
            for cand in candidate_orders:
                matched_order_ids.add(cand.order_id)
                evidence.append(
                    {
                        "type": "AMBIGUOUS_COMPETING_EPISODES",
                        "order_id": cand.order_id,
                        "competing_episode_ids": sorted(set(competing_episodes)),
                    }
                )
        elif total_candidate_groups > 1:
            machine_status = "AMBIGUOUS"
            reasons.append("MULTIPLE_PLAUSIBLE_UNLABELLED_ENTRY_ORDERS")
            for cand in candidate_orders:
                matched_order_ids.add(cand.order_id)
                evidence.append(
                    {
                        "type": "AMBIGUOUS_MULTI_ORDER_CANDIDATE",
                        "order_id": cand.order_id,
                        "price": decimal_str(_order_effective_price(cand, fills_by_order)),
                        "time_ms": _order_time_ms(cand, fills_by_order),
                    }
                )
            for oid in orphan_order_groups:
                matched_order_ids.add(oid)
                evidence.append({"type": "AMBIGUOUS_ORPHAN_FILL_ORDER", "order_id": oid})
        elif total_candidate_groups == 1:
            machine_status = "PROBABLE_MATCH"
            reasons.append("MULTI_FIELD_CORROBORATED_WITHOUT_DIRECT_ID")
            for cand in candidate_orders:
                matched_order_ids.add(cand.order_id)
                evidence.append(
                    {
                        "type": "PROBABLE_MULTI_FIELD_ORDER",
                        "order_id": cand.order_id,
                        "side": cand.side,
                        "position_side": cand.position_side,
                        "price": decimal_str(_order_effective_price(cand, fills_by_order)),
                        "qty": decimal_str(cand.orig_qty),
                        "time_ms": _order_time_ms(cand, fills_by_order),
                    }
                )
            for oid in orphan_order_groups:
                matched_order_ids.add(oid)
                evidence.append({"type": "PROBABLE_MULTI_FIELD_FILL_GROUP", "order_id": oid})
        else:
            machine_status = "UNMATCHED"
            if symbol_time_only:
                reasons.append("SYMBOL_AND_TIME_ALONE_INSUFFICIENT_PRICE_OUTSIDE_BAND")
            else:
                reasons.append("NO_ADEQUATE_CANDIDATE")

    # 3. Evaluate explicit OWNER_ENTERED manual associations (immutable, separate, never overriding contradictions).
    owner_entries: list[dict[str, Any]] = []
    owner_contradictions: list[str] = []
    owner_verified_any = False

    relevant_manual = [m for m in manual_associations if m.b2_episode_id == episode_id]
    for assoc in relevant_manual:
        status_flag = "VERIFIED_AGAINST_EXCHANGE"
        contradiction_reason: str | None = None

        if assoc.symbol != symbol:
            contradiction_reason = "OWNER_LINK_SYMBOL_MISMATCH"
        elif assoc.target_type == "ORDER":
            oid = int(assoc.target_id) if assoc.target_id.isdigit() else -1
            order_opt = orders_by_id.get(oid)
            if order_opt is None:
                status_flag = "TARGET_NOT_FOUND_IN_SNAPSHOT"
            else:
                ts = _order_time_ms(order_opt, fills_by_order)
                if ts < frozen_ms:
                    contradiction_reason = "OWNER_LINK_PREDATES_EPISODE_FREEZE"
                elif not _position_side_compatible(order_opt.position_side, direction):
                    contradiction_reason = "OWNER_LINK_POSITION_SIDE_CONTRADICTION"
                elif not order_opt.reduce_only and not order_opt.close_position and order_opt.side != entry_side:
                    contradiction_reason = "OWNER_LINK_ENTRY_SIDE_CONTRADICTION"
                else:
                    matched_order_ids.add(order_opt.order_id)
                    owner_verified_any = True
        elif assoc.target_type == "ALGO_ORDER":
            aid = int(assoc.target_id) if assoc.target_id.isdigit() else -1
            algo_opt = algos_by_id.get(aid)
            if algo_opt is None:
                status_flag = "TARGET_NOT_FOUND_IN_SNAPSHOT"
            else:
                ts = algo_opt.create_time_ms or algo_opt.update_time_ms or 0
                if ts < frozen_ms:
                    contradiction_reason = "OWNER_LINK_PREDATES_EPISODE_FREEZE"
                elif not _position_side_compatible(algo_opt.position_side, direction):
                    contradiction_reason = "OWNER_LINK_POSITION_SIDE_CONTRADICTION"
                else:
                    matched_algo_ids.add(algo_opt.algo_id)
                    if algo_opt.actual_order_id is not None:
                        matched_order_ids.add(algo_opt.actual_order_id)
                    owner_verified_any = True
        elif assoc.target_type == "TRADE":
            tid = int(assoc.target_id) if assoc.target_id.isdigit() else -1
            fill_opt = fills_by_id.get(tid)
            if fill_opt is None:
                status_flag = "TARGET_NOT_FOUND_IN_SNAPSHOT"
            else:
                if fill_opt.trade_time_ms < frozen_ms:
                    contradiction_reason = "OWNER_LINK_PREDATES_EPISODE_FREEZE"
                elif not _position_side_compatible(fill_opt.position_side, direction):
                    contradiction_reason = "OWNER_LINK_POSITION_SIDE_CONTRADICTION"
                else:
                    matched_trade_ids.add(fill_opt.trade_id)
                    matched_order_ids.add(fill_opt.order_id)
                    owner_verified_any = True

        if contradiction_reason is not None:
            status_flag = "CONTRADICTS_EXCHANGE_EVIDENCE"
            owner_contradictions.append(f"{assoc.operator_id}:{contradiction_reason}")
        owner_entries.append(
            {
                **assoc.to_dict(),
                "verification_status": status_flag,
                "contradiction_reason": contradiction_reason,
            }
        )

    # Combine machine match status and OWNER_ENTERED associations without erasing contradiction.
    final_status = machine_status
    if owner_contradictions:
        final_status = "AMBIGUOUS"
        reasons.append("OWNER_ENTERED_LINK_CONTRADICTS_EXCHANGE_EVIDENCE")
    elif owner_verified_any and machine_status in ("UNMATCHED", "PROBABLE_MATCH"):
        final_status = "MATCHED"
        reasons.append("OWNER_ENTERED_EXPLICIT_LINK_VERIFIED")

    # 4. Expand matched_order_ids -> fills (supporting partial fills and multi-leg entries/exits) and income rows.
    for oid in sorted(matched_order_ids):
        for fill in fills_by_order.get(oid, ()):
            matched_trade_ids.add(fill.trade_id)
    for tid in sorted(matched_trade_ids):
        fill_opt = fills_by_id.get(tid)
        if fill_opt is None:
            continue
        if fill_opt.side == entry_side:
            entry_fill_ids.add(tid)
        elif fill_opt.side == exit_side:
            exit_fill_ids.add(tid)

    # Link income rows via explicit tradeId / orderId references, or funding rows during matched holding span.
    matched_income_ids: set[str] = set()
    str_trade_ids = {str(t) for t in matched_trade_ids}
    str_order_ids = {str(o) for o in matched_order_ids}
    matched_fill_times = [fills_by_id[t].trade_time_ms for t in matched_trade_ids if t in fills_by_id]
    min_fill_t = min(matched_fill_times) if matched_fill_times else None
    max_fill_t = max(matched_fill_times) if matched_fill_times else None

    # Identify active position legs compatible with this episode's direction.
    active_legs: list[NormalizedPosition] = [
        p
        for p in snapshot.positions
        if p.symbol == symbol and p.is_open and p.effective_direction == direction
    ]
    linked_pos_sides = tuple(sorted({p.position_side for p in active_legs}))

    # Detect multi-episode shared position legs (many-to-one).
    shared_eps: set[str] = set()
    if active_legs:
        for peer in peer_cards:
            if (
                peer.episode_id is not None
                and peer.episode_id != episode_id
                and peer.symbol == symbol
                and peer.episode_payload is not None
                and peer.episode_payload.get("direction") == direction
                and peer.market_status in ("EXECUTABLE", "WATCH")
            ):
                shared_eps.add(peer.episode_id)

    for inc in snapshot.income_rows:
        if inc.symbol and inc.symbol != symbol:
            continue
        if (inc.trade_id and inc.trade_id in str_trade_ids) or (inc.order_id and inc.order_id in str_order_ids):
            matched_income_ids.add(inc.tran_id)
        elif (
            inc.income_type == "FUNDING_FEE"
            and inc.symbol == symbol
            and min_fill_t is not None
            and inc.time_ms >= min_fill_t
            and (active_legs or (max_fill_t is not None and inc.time_ms <= max_fill_t))
        ):
            # Only attribute funding cashflow directly if position is not shared across multiple episodes.
            if not shared_eps:
                matched_income_ids.add(inc.tran_id)

    return EpisodeMatchResult(
        b2_card_id=card.card_id,
        b2_episode_id=episode_id,
        symbol=symbol,
        signal_trade_match=final_status,
        machine_match_status=machine_status,
        reason_codes=tuple(dict.fromkeys(reasons)),
        evidence_summary=tuple(evidence),
        matched_order_ids=tuple(sorted(matched_order_ids)),
        matched_algo_ids=tuple(sorted(matched_algo_ids)),
        matched_trade_ids=tuple(sorted(matched_trade_ids)),
        matched_income_tran_ids=tuple(sorted(matched_income_ids)),
        linked_position_sides=linked_pos_sides,
        shared_position_episode_ids=tuple(sorted(shared_eps)),
        owner_entered_associations=tuple(owner_entries),
        owner_contradictions=tuple(owner_contradictions),
        entry_fill_ids=tuple(sorted(entry_fill_ids)),
        exit_fill_ids=tuple(sorted(exit_fill_ids)),
    )
