"""Independent closed-1H geometry, 15m confirmation, and ephemeral readiness."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from math import ceil

from .schema import Card, MINUTE, Policy, Snapshot, digest
from .source import SourceError, SourceLedger


def regime(bars):
    change = bars[-1].close - bars[-4].close
    return "UP" if change > 0 else "DOWN" if change < 0 else "RANGE"


def atr(bars):
    return sum(max(b.high - b.low, abs(b.high - p.close), abs(b.low - p.close))
               for p, b in zip(bars[-15:-1], bars[-14:])) / 14


def pivots(bars):
    """One full bar on either side; availability of the right bar proves the pivot."""
    result = []
    for left, b, right in zip(bars, bars[1:], bars[2:]):
        for kind, price, confirmed in (("HIGH", b.high, b.high > max(left.high, right.high)),
                                       ("LOW", b.low, b.low < min(left.low, right.low))):
            if confirmed:
                result.append({"kind": kind, "price": price, "interval": b.interval,
                               "pivot_open_ms": b.open_ms, "confirmed_end_ms": right.end_ms,
                               "available_ms": max(b.available_ms, right.available_ms)})
    return result


# Conservative paper scenarios in bps; adverse funding uses full planned extension.
COSTS = {
    "conservative": {"fee_each_side": 6, "spread_round_trip": 8, "slippage_each_side": 6,
                     "adverse_funding_per_8h": 4},
    "stress": {"fee_each_side": 10, "spread_round_trip": 20, "slippage_each_side": 15,
               "adverse_funding_per_8h": 12},
}


def economics(plan, policy, spread_bps=0, capacity=None):
    entry, stop = plan["worst_entry"], plan["hard_stop"]
    risk = abs(entry - stop)
    hours = policy.planned_extension_hours or policy.holding_hours
    funding_windows = ceil(hours / 8)
    scenarios = {}
    for name, c in COSTS.items():
        costs = []
        for target in plan["targets"]:
            ceiling = max(entry, target)
            cost = (ceiling * (2 * (c["fee_each_side"] + c["slippage_each_side"]))
                    + entry * (max(spread_bps, c["spread_round_trip"])
                               + c["adverse_funding_per_8h"] * funding_windows)) / 10_000
            costs.append(cost)
        scenarios[name] = {
            "assumptions_bps": dict(c, spread_round_trip=max(spread_bps, c["spread_round_trip"])),
            "adverse_funding_windows": funding_windows,
            "cost_per_unit_by_tp": costs,
            "planned_after_cost_r_by_tp": [(abs(t - entry) - cost) / (risk + cost)
                                             for t, cost in zip(plan["targets"], costs)],
        }
    risk_multiplier = 0.5 if "DAILY_COUNTERTREND_RISK" in plan["warnings"] else 1.0
    stress_stop_cost = max(scenarios["stress"]["cost_per_unit_by_tp"])
    paper_risk = policy.paper_equity * policy.risk_fraction * risk_multiplier
    risk_quantity = paper_risk / (risk + stress_stop_cost)
    paper_quantity = min(risk_quantity, policy.paper_notional_cap / entry)
    if capacity is not None:
        paper_quantity = min(paper_quantity, capacity)
    return {
        "planned_gross_r_by_tp": [abs(t - entry) / risk for t in plan["targets"]],
        "scenarios": scenarios,
        "realized_r": None,
        "paper_risk_budget": paper_risk,
        "paper_quantity_upper_bound": paper_quantity,
        "capacity_quantity_bound": capacity,
        "capacity_status": "UNKNOWN_5M_VOLUME_IS_NOT_DEPTH" if capacity is None else "TOP_OF_BOOK_ONLY_UNCERTAIN",
        "account_authorization": "UNKNOWN_OFFLINE_NO_ACCOUNT",
        "execution_claim": False,
    }


@dataclass
class Candidate:
    identity: str
    setup_end_ms: int
    created_ms: int
    plan: dict
    consumed_15m_end: int = 0
    control_used: bool = False
    terminal: str | None = None
    terminal_reason: str | None = None


def build_candidate(s, groups, policy):
    hourly = groups["1H"]
    previous, trigger = hourly[-2:]
    long = trigger.low <= previous.close and trigger.close > previous.high
    short = trigger.high >= previous.close and trigger.close < previous.low
    if not (long or short):
        return None, "NO_CLOSED_1H_RECOVERY_OR_REJECTION"
    sign = 1 if long else -1
    side = "LONG" if long else "SHORT"
    hourly_pivots = pivots(hourly)
    protective = [p for p in hourly_pivots if p["kind"] == ("LOW" if long else "HIGH")]
    if not protective:
        return None, "NO_CONFIRMED_1H_PROTECTIVE_STRUCTURE"
    structure = protective[-1]
    volatility = atr(hourly)
    if volatility <= 0:
        return None, "NO_POSITIVE_ATR"
    zone = (trigger.close - 0.15 * volatility, trigger.close + 0.15 * volatility)
    entry = zone[1] if long else zone[0]
    buffer = policy.atr_buffer * volatility
    stop = structure["price"] - sign * buffer
    if stop <= 0 or sign * (entry - stop) <= 0:
        return None, "INVALID_STRUCTURAL_GEOMETRY"
    levels = [p for p in hourly_pivots + pivots(groups["4H"])
              if p["kind"] == ("HIGH" if long else "LOW") and sign * (p["price"] - entry) > 0]
    prices = sorted({p["price"] for p in levels}, reverse=not long)[:3]
    if len(prices) < 2:
        return None, "TWO_OBSERVABLE_TARGETS_REQUIRED"
    if (trigger.low <= stop if long else trigger.high >= stop):
        return None, "SETUP_BAR_ALREADY_STOPPED"
    if (trigger.high >= prices[0] if long else trigger.low <= prices[0]):
        return None, "SETUP_BAR_ALREADY_TARGET_TOUCHED"
    warnings = []
    daily, four = regime(groups["1D"]), regime(groups["4H"])
    opposing = "DOWN" if long else "UP"
    if daily == opposing:
        warnings.append("DAILY_COUNTERTREND_RISK")
    if four == opposing:
        warnings.append("FOUR_HOUR_CONFLICT_VETO_READY")
    plan = {
        "direction": side, "setup_end_ms": trigger.end_ms,
        "setup_available_ms": trigger.available_ms,
        "entry_region": list(zone), "worst_entry": entry,
        "confirmation_level": trigger.close,
        "structural_invalidation": structure["price"], "structure_evidence": structure,
        "atr14_1h": volatility, "atr_buffer": buffer, "hard_stop": stop,
        "targets": prices,
        "target_evidence": [p for p in levels if p["price"] in prices],
        "tp3_optional": len(prices) == 3,
        "entry_expires_ms": trigger.end_ms + policy.entry_lifetime_minutes * MINUTE,
        "holding_hours_from_hypothetical_fill": policy.holding_hours,
        "planned_extension_hours": policy.planned_extension_hours,
        "absolute_holding_deadline_ms": None,  # no fill, so no invented hold clock
        "warnings": warnings, "daily_regime": daily, "four_hour_regime": four,
        "four_hour_atr14": atr(groups["4H"]),
        "four_hour_structure": pivots(groups["4H"]),
        "economics": None,
    }
    plan["economics"] = economics(plan, policy)
    identity = digest({"version": "S1_INTRADAY_MTF_V2", "symbol": s.symbol,
                       "primary_bar": asdict(trigger), "geometry": plan, "policy": asdict(policy)})
    return Candidate(identity, trigger.end_ms, s.asof_ms, plan), None


def terminal_hit(candidate, groups, quote, arm):
    p = candidate.plan
    long = p["direction"] == "LONG"
    intervals = ("1H", "15m", "5m") if arm == "MTF_15M" else ("1H", "5m")
    for interval in intervals:
        for b in groups.get(interval, ()):
            if b.end_ms <= candidate.setup_end_ms:
                continue
            if (b.low <= p["hard_stop"] if long else b.high >= p["hard_stop"]):
                return "HARD_STOP_TOUCHED_OR_CROSSED"
            if (b.high >= p["targets"][0] if long else b.low <= p["targets"][0]):
                return "TARGET_ALREADY_TOUCHED_BEFORE_ENTRY"
    if quote is not None and quote.exchange_ms >= candidate.setup_end_ms:
        if (quote.bid <= p["hard_stop"] if long else quote.ask >= p["hard_stop"]):
            return "QUOTE_STOP_CROSSED"
        if (quote.ask >= p["targets"][0] if long else quote.bid <= p["targets"][0]):
            return "QUOTE_TARGET_ALREADY_TOUCHED"
    return None


def refresh_context(plan, groups, policy, asof_ms):
    """Late but causal context receipts can update risk, never fixed 1H geometry."""
    opposing = "DOWN" if plan["direction"] == "LONG" else "UP"
    daily, four = regime(groups["1D"]), regime(groups["4H"])
    warnings = []
    if daily == opposing:
        warnings.append("DAILY_COUNTERTREND_RISK")
    if four == opposing:
        warnings.append("FOUR_HOUR_CONFLICT_VETO_READY")
    plan.update(warnings=warnings, daily_regime=daily, four_hour_regime=four,
                four_hour_atr14=atr(groups["4H"]), four_hour_structure=pivots(groups["4H"]),
                context_review_ms=asof_ms,
                context_evidence={i: {"end_ms": groups[i][-1].end_ms,
                                      "available_ms": groups[i][-1].available_ms}
                                  for i in ("1D", "4H")})
    plan["economics"] = economics(plan, policy)


def confirmation(b, candidate):
    p = candidate.plan
    lo, hi = p["entry_region"]
    # A completed rejection/recovery or break/retest must close inside the fixed 1H zone.
    level = p["confirmation_level"]
    if p["direction"] == "LONG":
        return lo <= b.close <= hi and b.low <= b.open <= level < b.close
    return lo <= b.close <= hi and b.high >= b.open >= level > b.close


class Engine:
    def __init__(self, policy=None, arm="MTF_15M"):
        if arm not in ("MTF_15M", "CONTROL_1H_ONLY"):
            raise ValueError("UNKNOWN_ARM")
        self.policy = policy or Policy()
        self.arm = arm
        self.source = SourceLedger()
        self.candidates = {}
        self.seen_primary = {}

    def review(self, s):
        if not isinstance(s, Snapshot) or type(s.symbol) is not str or not s.symbol:
            return Card("UNKNOWN", 0, self.arm, "UNKNOWN", ("UNRECOGNIZED_SNAPSHOT_SCHEMA",))
        candidate = self.candidates.get(s.symbol)

        def card(state, reason, diagnostics=None, plan=None):
            review_ms = s.asof_ms if type(s.asof_ms) is int and s.asof_ms >= 0 else 0
            return Card(s.symbol, review_ms, self.arm, state, (reason,),
                        candidate.identity if candidate else None,
                        deepcopy(plan if plan is not None else candidate.plan) if candidate else None,
                        diagnostics)

        try:
            groups = self.source.admit(s)
        except SourceError as error:
            # Readiness is never cached, including source failures.
            return card("SOURCE_BLOCKED" if error.global_veto else "DATA_UNAVAILABLE", error.code)
        primary = groups["1H"][-1].end_ms
        # A newer primary bar supersedes the prior candidate; same bar cannot resurrect a killed setup.
        if primary != self.seen_primary.get(s.symbol):
            self.seen_primary[s.symbol] = primary
            candidate, reason = build_candidate(s, groups, self.policy)
            if candidate is None:
                self.candidates.pop(s.symbol, None)
                return card("NO_SETUP", reason)
            self.candidates[s.symbol] = candidate
            is_new = True
        else:
            is_new = False
        if candidate is None:
            return card("NO_SETUP", "UNCHANGED_1H_NO_SETUP")
        refresh_context(candidate.plan, groups, self.policy, s.asof_ms)
        if candidate.terminal:
            return card(candidate.terminal, candidate.terminal_reason)
        hit = terminal_hit(candidate, groups, s.quote, self.arm)
        if hit:
            candidate.terminal, candidate.terminal_reason = "INVALIDATED", hit
            return card("INVALIDATED", hit)
        if s.asof_ms >= candidate.plan["entry_expires_ms"]:
            candidate.terminal, candidate.terminal_reason = "EXPIRED", "ENTRY_LIFETIME_ENDED"
            return card("EXPIRED", "ENTRY_LIFETIME_ENDED")
        if is_new:
            return card("WATCH", "FINISHED_1H_SETUP_REGISTERED")
        p = candidate.plan
        if "FOUR_HOUR_CONFLICT_VETO_READY" in p["warnings"]:
            return card("WATCH", "FOUR_HOUR_CONFLICT_VETO_READY")
        if self.arm == "MTF_15M":
            new = [b for b in groups.get("15m", ())
                   if b.open_ms >= candidate.setup_end_ms and b.end_ms > candidate.created_ms
                   and b.end_ms > candidate.consumed_15m_end]
            if not new:
                return card("WATCH", "NO_NEW_MATCHING_15M_CONFIRMATION")
            candidate.consumed_15m_end = new[-1].end_ms
            latest = new[-1]
            if s.asof_ms - latest.end_ms > 2 * MINUTE:
                return card("WATCH", "CONFIRMATION_TOO_OLD_FOR_NEW_READY")
            if not confirmation(latest, candidate):
                return card("WATCH", "15M_FALSE_TRIGGER_OR_NO_RECOVERY")
        else:
            if candidate.control_used:
                return card("WATCH", "CONTROL_PRIMARY_ALREADY_CONSUMED")
            candidate.control_used = True
        required_window = self.policy.response_minutes * MINUTE
        # Both the entry lifetime and confirmation lifetime must cover the declared response.
        confirmation_deadline = (candidate.consumed_15m_end + 15 * MINUTE
                                 if self.arm == "MTF_15M" else p["entry_expires_ms"])
        deadline = min(p["entry_expires_ms"], confirmation_deadline)
        if deadline - s.asof_ms < required_window:
            return card("WATCH", "INSUFFICIENT_5_TO_10_MINUTE_RESPONSE_WINDOW")
        # Cover the path since setup with contiguous smaller bars before permitting action.
        monitoring_groups = [(groups.get("5m", ()), 5 * MINUTE + MINUTE)]
        if self.arm == "MTF_15M":
            monitoring_groups.append((groups.get("15m", ()), 15 * MINUTE + 2 * MINUTE))
        monitoring = any(rows and rows[0].open_ms <= candidate.setup_end_ms
                         and rows[-1].end_ms >= s.asof_ms - max_age
                         for rows, max_age in monitoring_groups)
        if not monitoring:
            return card("WATCH", "POST_SETUP_PATH_UNPROVEN")
        q, capacity, spread = s.quote, None, 0
        if q is not None:
            if s.asof_ms - q.exchange_ms > MINUTE:
                return card("WATCH", "STALE_VENUE_QUOTE")
            price = q.ask if p["direction"] == "LONG" else q.bid
            spread = (q.ask - q.bid) / price * 10_000
            capacity = 0.10 * min(q.bid_size, q.ask_size)
            if capacity <= 0:
                return card("WATCH", "ZERO_VISIBLE_CAPACITY")
            action_source = "FRESH_VENUE_QUOTE_PRICE_ONLY"
        else:
            bars = groups.get("5m", ())
            if not bars or s.asof_ms - bars[-1].end_ms > MINUTE:
                return card("WATCH", "STALE_OR_MISSING_5M_ACTIONABILITY")
            price = bars[-1].close
            action_source = "COMPLETED_5M_PRICE_ONLY_CAPACITY_UNKNOWN"
        if not p["entry_region"][0] <= price <= p["entry_region"][1]:
            return card("WATCH", "NO_CHASE_PRICE_OUTSIDE_1H_ZONE")
        updated = deepcopy(p)
        updated["economics"] = economics(p, self.policy, spread, capacity)
        if updated["economics"]["scenarios"]["stress"]["planned_after_cost_r_by_tp"][0] <= 0:
            return card("WATCH", "NONPOSITIVE_STRESS_PLANNED_R", plan=updated)
        updated["review_actionability"] = {
            "price": price, "source": action_source, "review_ms": s.asof_ms,
            "response_minutes": self.policy.response_minutes,
            "respond_by_ms": s.asof_ms + required_window, "ready_valid_until_ms": deadline,
            "future_price_guaranteed": False,
            "instruction": "RECHECK_ZONE_STOP_TARGET_SOURCE_AT_RESPONSE_NO_CHASE",
        }
        return card("ENTRY_READY", "NEW_SIGNAL_AND_PLAUSIBLE_HUMAN_RESPONSE_WINDOW", plan=updated)


class PairedComparison:
    """Same ordered snapshots, same geometry/cost policy; only 15m entry filter differs."""
    def __init__(self, policy=None):
        self.mtf = Engine(policy, "MTF_15M")
        self.control = Engine(policy, "CONTROL_1H_ONLY")

    def review(self, snapshot):
        mtf, control = self.mtf.review(snapshot), self.control.review(snapshot)
        return {
            "pair_id": digest({"symbol": snapshot.symbol, "asof_ms": snapshot.asof_ms,
                               "candidate": mtf.candidate_id}),
            "mtf": mtf.to_dict(), "control": control.to_dict(),
            "same_candidate": mtf.candidate_id == control.candidate_id,
            "comparison": "DECISION_ELIGIBILITY_ONLY_NO_FORWARD_OUTCOMES",
            "forward_outcomes": None, "realized_r_delta": None,
        }
