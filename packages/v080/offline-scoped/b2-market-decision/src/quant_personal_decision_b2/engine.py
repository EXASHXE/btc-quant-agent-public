"""Integrated B2 observation, market decision, episode transitions and action-time repricing."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from decimal import Context, localcontext
from typing import Any

from .adapter import MarketSnapshotAdapter
from .journal import Journal
from .model import (
    ACCOUNT,
    CARD,
    DEFAULT_POLICY,
    FEATURES,
    MINUTE,
    STRATEGY,
    SYNTHETIC,
    D,
    DecisionError,
    Market,
    Policy,
    check,
    digest,
    encode,
    integer,
)
from .risk import filters, market_plan, prices
from .strategy import axis, regime, setup_candidates, trigger

TRANSITIONS = {
    "CANDIDATE": frozenset({"CANDIDATE", "TRIGGERED", "EXECUTABLE", "INVALID"}),
    "TRIGGERED": frozenset({"TRIGGERED", "EXECUTABLE", "INVALID"}),
    "EXECUTABLE": frozenset({"EXECUTABLE", "TRIGGERED", "INVALID"}),
    "INVALID": frozenset({"INVALID"}),
}

NEXT_ACTION = {
    "SOURCE_BLOCKED": "Refresh qualified public evidence before making a decision.",
    "NOT_EVALUATED": "Wait for enough consecutive closed bars or explicitly run the offline strategy.",
    "NO_SETUP": "Wait for a new closed setup candle.",
    "WATCH": "Wait for independent confirmation or recheck the displayed market blocker.",
    "INVALID": "Close this candidate in the journal. Any future setup needs a new signal candle.",
    "EXECUTABLE": "Synthetic check only. For any future genuine signal, verify exposure, protection and booked costs manually.",
}


def base_card(symbol: str, now: int, receipt: dict[str, Any] | None, **extra: Any) -> dict[str, Any]:
    return {
        "schema": CARD, "symbol": symbol, "evaluated_ms": now, "evidence": SYNTHETIC, **ACCOUNT,
        "strategy": STRATEGY, "features": FEATURES, "evaluation_receipt": receipt,
        "market_status": "NOT_EVALUATED", "strategy_evaluated": False, "data_ready": False,
        "feature_warmup_ready": False, "episode_id": None, "episode_state": None,
        "episode": None, "trigger": None, "first_trigger_evaluation_ms": None, "first_targets": None,
        "frame_end_ms": {}, "plan": None, "card_context": {}, "reasons": [], "reprice": None, **extra,
    }


def market_card(market: Market) -> dict[str, Any]:
    return base_card(market.symbol, market.evaluated_ms, market.source, data_ready=True,
                     feature_warmup_ready=market.warm, reasons=["EXPLICIT_STRATEGY_EVALUATION_REQUIRED"],
                     frame_end_ms={name: bars[-1].end_ms for name, bars in market.bars.items()},
                     card_context=market.context)


def active(db: sqlite3.Connection, symbol: str) -> dict[str, Any] | None:
    return Journal.unpack(db.execute(
        "SELECT payload,payload_sha FROM cards WHERE symbol=? AND episode_id IS NOT NULL "
        "ORDER BY as_of DESC LIMIT 1", (symbol,),
    ).fetchone())


def set_state(card: dict[str, Any], status: str, state: str, reason: str, previous: str | None) -> None:
    if previous is not None:
        check(state in TRANSITIONS[previous], "ILLEGAL_EPISODE_TRANSITION")
    card.update(market_status=status, episode_state=state, reasons=[reason])


def preview(card: dict[str, Any], episode: dict[str, Any], market: Market) -> None:
    spec = filters(market.context["instrument"]["values"])
    lo, hi, stop = prices(episode, spec)
    card["plan"] = {"schema": "B2_MARKET_PLAN_PREVIEW_V1", "entry_low": lo, "entry_high": hi,
                    "hard_stop": stop, "obstacles": episode["obstacles"],
                    "targets": [{"label": f"TP{i}", "status": "UNESTABLISHED", "price": None,
                                 "reason": "PENDING_CONFIRMED_FEASIBILITY"} for i in range(1, 4)]}


def crossed_levels(market: Market, episode: dict[str, Any],
                   prior: dict[str, Any] | None) -> tuple[bool, bool]:
    sign = episode["sign"]
    stop = prices(episode, filters(market.context["instrument"]["values"]))[2]
    invalid = sign * D(episode["structural_invalidation"])
    cut = episode["frozen_at_ms"]
    candidates = [axis(bar, sign) for bar in market.bars["5m"] if bar.open_ms >= cut]
    visible = market.context["quote"]["values"]
    exit_side = D(visible["bidPrice"] if sign > 0 else visible["askPrice"])
    mark = D(market.context["mark"]["values"]["markPrice"])
    if prior is not None:
        carried_plan = prior.get("first_hard_stop")
        if carried_plan is not None:
            stop = D(carried_plan)
    hit_stop = (min(sign * exit_side, sign * mark, *(p[2] for p in candidates)) <= max(sign * stop, invalid)
                if candidates else min(sign * exit_side, sign * mark) <= max(sign * stop, invalid))
    first = (prior or {}).get("first_targets")
    if not first or first[0]["price"] is None:
        return hit_stop, False
    tp1 = sign * D(first[0]["price"])
    initial = prior["first_trigger_evaluation_ms"] if prior else cut
    highs = [axis(bar, sign)[1] for bar in market.bars["5m"] if bar.open_ms >= initial]
    return hit_stop, max([sign * exit_side, *highs]) >= tp1


class Engine:
    def __init__(self, adapter: MarketSnapshotAdapter, journal: Journal,
                 policy: Policy = DEFAULT_POLICY) -> None:
        check(journal.policy_json == encode(policy.data()), "JOURNAL_POLICY_CONFLICT")
        self.adapter, self.journal, self.policy = adapter, journal, policy

    def evaluate(self, symbol: str, *, scan: int | None = None, as_of_ms: int | None = None,
                 reprice_minutes: int | None = None, episode_id: str | None = None,
                 before_commit: Callable[[], None] | None = None) -> dict[str, Any]:
        check((reprice_minutes is None) == (episode_id is None) and reprice_minutes in (None, 5, 10),
              "INVALID_REPRICE_SELECTOR")
        market = None
        source_error = None
        try:
            market = self.adapter.read(symbol, scan=scan, as_of_ms=as_of_ms)
        except DecisionError as exc:
            if as_of_ms is None or exc.code == "UNQUALIFIED_SYMBOL":
                raise
            source_error = exc
        if market is not None:
            now = market.evaluated_ms
        else:
            now = integer(as_of_ms, "as_of_ms", minimum=1)
        receipt = market.source if market is not None else None
        uid = digest([symbol, now, receipt, source_error.data() if source_error else None, reprice_minutes, episode_id])
        with self.journal.connect(write=True) as db:
            cached = Journal.unpack(db.execute("SELECT payload,payload_sha FROM cards WHERE id=?", (uid,)).fetchone())
            if cached:
                return cached
            latest = db.execute("SELECT MAX(as_of) FROM cards WHERE symbol=?", (symbol,)).fetchone()[0]
            check(latest is None or now > latest, "BACKDATED_OR_CONFLICTING_EVALUATION")
            lineage = db.execute("SELECT lineage FROM cards WHERE symbol=? AND lineage IS NOT NULL "
                                 "ORDER BY as_of DESC LIMIT 1", (symbol,)).fetchone()
            if receipt is not None and lineage is not None:
                check(receipt.get("source_lineage") == lineage[0], "SOURCE_LINEAGE_CONFLICT")
            prior = active(db, symbol)
            reprice = None
            if reprice_minutes is not None:
                check(prior is not None, "REPRICE_EPISODE_UNKNOWN")
                assert prior is not None
                check(prior["episode_id"] == episode_id and prior["first_trigger_evaluation_ms"] is not None,
                      "REPRICE_EPISODE_UNKNOWN")
                expected = prior["first_trigger_evaluation_ms"] + reprice_minutes * MINUTE
                check(now >= expected, "REPRICE_BEFORE_TARGET_TIME")
                reprice = {"requested_delay_minutes": reprice_minutes, "scheduled_venue_ms": expected,
                           "observed_venue_ms": now, "lateness_ms": now - expected}
            card = market_card(market) if market is not None else base_card(symbol, now, None)
            card.update(card_id=uid, reprice=reprice, policy=self.policy.data(),
                        journal_recorded_wall_ms=time.time_ns() // 1_000_000)
            events: list[tuple[str, dict[str, Any]]] = [("OBSERVATION", {"source_scan": scan,
                "input_error": source_error.data() if source_error else None,
                "receipt_sha256": digest(receipt) if receipt is not None else None})]
            if prior:
                for key in ("episode_id", "episode_state", "episode", "trigger", "first_trigger_evaluation_ms",
                            "first_targets", "first_hard_stop"):
                    card[key] = prior.get(key)
            if source_error is not None:
                card.update(market_status="SOURCE_BLOCKED", reasons=[source_error.code], source_issue=source_error.data(),
                            rejected_publication=self.adapter.rejected_reference(scan=scan, as_of_ms=now))
                events.append(("SOURCE_BLOCKED", source_error.data()))
            elif market is not None and market.warm:
                with localcontext(Context(prec=40)):
                    self.decide(db, card, prior, market, events)
            else:
                card["reasons"] = ["FEATURE_WARMUP"]
            if reprice is not None:
                events.append(("REPRICE", {**reprice, "status": card["market_status"], "reasons": card["reasons"]}))
            card["next_human_action"] = NEXT_ACTION[card["market_status"]]
            events.append(("PUBLICATION", {"status": card["market_status"], "evaluated_venue_ms": now,
                                           "recorded_wall_ms": card["journal_recorded_wall_ms"]}))
            saved = self.journal.publish(db, card, events)
            if before_commit is not None:
                before_commit()
            return saved

    def decide(self, db: sqlite3.Connection, card: dict[str, Any], prior: dict[str, Any] | None,
               market: Market, events: list[tuple[str, dict[str, Any]]]) -> None:
        card["strategy_evaluated"] = True
        now = market.evaluated_ms
        prev = prior["episode_state"] if prior else None
        episode = prior["episode"] if prior and prev != "INVALID" else None
        if prev == "INVALID" and card["reprice"] is not None:
            card.update(market_status="INVALID", reasons=["TERMINAL_EPISODE"])
            return
        if episode is None:
            tick = filters(market.context["instrument"]["values"]).tick
            try:
                candidates, diag = setup_candidates(market, tick, self.policy)
            except DecisionError as exc:
                card.update(market_status="NOT_EVALUATED", strategy_evaluated=False,
                            feature_warmup_ready=False, reasons=[exc.code])
                return
            card["features_view"] = diag
            if not candidates:
                card.update(market_status="NO_SETUP", episode_id=None, episode_state=None, episode=None,
                            trigger=None, first_trigger_evaluation_ms=None, first_targets=None,
                            reasons=[diag["screen"]])
                return
            pick = candidates[0]
            old = db.execute("SELECT id FROM episodes WHERE group_id=?", (pick["group_id"],)).fetchone()
            if old:
                card.update(market_status="INVALID", reasons=["TERMINAL_EPISODE"])
                return
            episode = pick
            self.journal.add_episode(db, episode)
            prev = None
            events.append(("CANDIDATE", {"family": episode["family"], "group_id": episode["group_id"],
                                          "frozen_at_ms": episode["frozen_at_ms"]}))
            card.update(episode_id=episode["episode_id"], episode=episode, trigger=None,
                        first_trigger_evaluation_ms=None, first_targets=None, first_hard_stop=None)
        else:
            check(episode == self.journal.episode(db, episode["episode_id"]), "EPISODE_IMMUTABILITY_MISMATCH")
        preview(card, episode, market)
        if card.get("first_hard_stop") is not None:
            card["plan"]["hard_stop"] = card["first_hard_stop"]
        else:
            card["first_hard_stop"] = card["plan"]["hard_stop"]
        if now >= episode["expires_at_ms"] or (card["trigger"] is None and now > episode["trigger_deadline_ms"]):
            reason = "EPISODE_EXPIRED" if now >= episode["expires_at_ms"] else "TRIGGER_DEADLINE_PASSED"
            set_state(card, "INVALID", "INVALID", reason, prev)
            events.append(("EXPIRED", {"reason": reason, "expires_at_ms": episode["expires_at_ms"]}))
            return
        stop_hit, target_hit = crossed_levels(market, episode, card)
        if stop_hit or target_hit:
            reason = "STRUCTURAL_INVALIDATION" if stop_hit else "MISSED_NO_CHASE"
            set_state(card, "INVALID", "INVALID", reason, prev)
            events.append(("INVALIDATED", {"reason": reason}))
            return
        current_regime = regime(market.bars["4h"])
        card["current_regime_4h"] = current_regime
        if current_regime["direction"] == -episode["sign"]:
            set_state(card, "INVALID", "INVALID", "OPPOSING_4H_REGIME", prev)
            events.append(("INVALIDATED", {"reason": "OPPOSING_4H_REGIME"}))
            return
        if not current_regime["direction"]:
            set_state(card, "WATCH", "TRIGGERED" if card["trigger"] else "CANDIDATE", "4H_REGIME_PAUSED", prev)
            return
        if card["trigger"] is None:
            confirmed, reason = trigger(episode, market)
            if not confirmed:
                set_state(card, "WATCH", "CANDIDATE", reason, prev)
                quote = market.context["quote"]["values"]
                side = quote["askPrice"] if episode["sign"] > 0 else quote["bidPrice"]
                distance = abs(D(side) - D(episode["confirmation_line"]))
                card["watch_proximity_usdt"] = distance
                card["watch_near_confirmation"] = distance <= D(episode["atr14"]) * D("0.50")
                return
            card["trigger"] = confirmed
            card["first_trigger_evaluation_ms"] = now
            events.append(("TRIGGER", {"bar_end_ms": confirmed["end_ms"], "receipt_id": confirmed["source"]["receipt_id"]}))
        else:
            frozen = card["trigger"]
            current = next((b for b in market.bars["15m"] if b.open_ms == frozen["open_ms"]), None)
            if current is not None and current.source["source_row_sha256"] != frozen["source"]["source_row_sha256"]:
                set_state(card, "WATCH", "TRIGGERED", "TRIGGER_REVISION_CHANGED", prev)
                return
        if filters(market.context["instrument"]["values"]).tick != D(episode["entry_tick"]):
            set_state(card, "WATCH", "TRIGGERED", "INSTRUMENT_TICK_CHANGED", prev)
            return
        pinned = {**episode, "hard_stop_unrounded": card["first_hard_stop"]}
        try:
            plan, reasons = market_plan(market, pinned, self.policy, card["first_targets"])
        except DecisionError as exc:
            set_state(card, "WATCH", "TRIGGERED", exc.code, prev)
            return
        card["plan"] = plan
        if card["first_targets"] is None:
            card["first_targets"] = [{key: target[key] for key in ("label", "price", "status", "reason")}
                                     for target in plan["targets"]]
        if "MISSED_NO_CHASE" in reasons:
            set_state(card, "INVALID", "INVALID", "MISSED_NO_CHASE", prev)
            events.append(("INVALIDATED", {"reason": "MISSED_NO_CHASE"}))
        elif reasons:
            set_state(card, "WATCH", "TRIGGERED", reasons[0], prev)
            card["reasons"] = reasons
        else:
            set_state(card, "EXECUTABLE", "EXECUTABLE", "MARKET_SIDE_ELIGIBLE_SYNTHETIC", prev)
