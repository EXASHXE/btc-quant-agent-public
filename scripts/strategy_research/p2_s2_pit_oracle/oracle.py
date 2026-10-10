"""Invented-clock as-of snapshots and scalar funding arithmetic; no reader/engine."""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Context, Decimal, localcontext

D = Decimal
MINUTE = 60000
HOUR = 3600000


def amount(x: Decimal) -> str:
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        return format(x.quantize(D("0.000000000001")), "f")


def result(code: str, reason: str, **values) -> dict:
    return {"code": code, "reason": reason, **values}


def visibility(x: dict) -> dict:
    if any(x.get(k) is None for k in ("event", "available", "observed")):
        return result("SOURCE_UNPROVEN", "Historical event/availability/observation proof missing")
    if x["event"] > x["decision"] or x["available"] > x["decision"]:
        return result("LOOKAHEAD", "Claimed usable input exceeds decision cut")
    if x["available"] < max(x["observed"], x["proof_floor"], x.get("corrected", 0)):
        return result("LOOKAHEAD", "Declared availability precedes its required proof")
    if x.get("max_age") is not None and x["decision"]-x["event"] > x["max_age"]:
        return result("SOURCE_UNPROVEN", "Stale source cannot certify current decision eligibility")
    return result("VISIBLE_SYNTHETIC", "Both event and availability pass declared proof floor")


def mark_asof(x: dict) -> dict:
    if not x.get("rights") or not x.get("physical_monotonic"):
        return result("SOURCE_UNPROVEN", "Rights or raw timestamp monotonicity not established")
    cut = x["decision"]
    visible = []
    for r in x["observations"]:
        if r["available"] is None:
            return result("SOURCE_UNPROVEN", "Mark initial-known-at is absent, not interpolated")
        if r["available"] > cut or r["close"] > cut:
            continue
        if r["kind"] != "MARK_1M" or r["source"] == x["trade_source"]:
            return result("SOURCE_UNPROVEN", "Trade/daily alias is not independent true-minute Mark")
        if r["symbol"] != "BTCUSDT" or D(r["price"]) <= 0:
            return result("SOURCE_UNPROVEN", "This BTC oracle requires matching symbol and positive Mark")
        if r["start"] % MINUTE or r["close"] != r["start"] + MINUTE:
            return result("SOURCE_UNPROVEN", "Not an epoch-UTC exclusive one-minute interval")
        if r["available"] < max(r["close"] + MINUTE, r["observed"], r.get("corrected", 0)):
            return result("LOOKAHEAD", "Mark proof floor or correction knowledge backdated")
        visible.append(r)
    identities = {}
    slots = {}
    for r in visible:
        payload = tuple((k, str(v)) for k, v in sorted(r.items()))
        if r["id"] in identities and identities[r["id"]] != payload:
            return result("CONFLICT_SOURCE_FAIL_CLOSED", "Same immutable ID changes value or clock")
        identities[r["id"]] = payload
        key = (r["source"], r["symbol"], r["close"], r["revision"])
        if key in slots:
            fields = ("price", "available", "observed", "corrected", "supersedes")
            if any(slots[key].get(k) != r.get(k) for k in fields):
                return result("CONFLICT_SOURCE_FAIL_CLOSED", "Contradictory same source-close revision")
        slots[key] = r
    for r in slots.values():
        if r["revision"]:
            parent = next((p for p in slots.values() if p["id"] == r.get("supersedes")), None)
            if not parent or r.get("corrected", 0) < parent["available"]:
                return result("SOURCE_UNPROVEN", "Correction has no immutable visible parent proof")
            if (r["source"], r["symbol"], r["close"]) != (
                    parent["source"], parent["symbol"], parent["close"]):
                return result("SOURCE_UNPROVEN", "Correction changes source identity")
            if r["revision"] != parent["revision"] + 1 or r["available"] < parent["available"]:
                return result("SOURCE_UNPROVEN", "Correction sequence or knowledge regresses")
    prices = {}
    for close in x["expected_closes"]:
        candidates = [r for r in slots.values() if r["close"] == close]
        if len({r["source"] for r in candidates}) > 1:
            return result("METHOD_CONFLICT", "Multiple Mark providers need Controller source choice")
        if not candidates:
            return result("SOURCE_UNPROVEN", "Required admitted minute missing/unknown at cut")
        current = max(candidates, key=lambda r: (r["available"], r["revision"]))
        prices[str(close)] = current["price"]
    if x.get("claimed_prices") is not None and x["claimed_prices"] != prices:
        return result("LOOKAHEAD", "Claimed snapshot substitutes unavailable correction")
    return result("ASOF_SYNTHETIC", "Unique versioned legal observations, no future revisions",
                  prices=prices, unique_minutes=len(prices))


def funding_floor(s: int) -> int:
    last_intersecting_end = ((s + 15000) // MINUTE + 1) * MINUTE
    return max(s + MINUTE, last_intersecting_end + MINUTE)


def settlement_count(start: int, end: int, times: list[int]) -> int:
    if start > end or len(times) != len(set(times)):
        raise ValueError("Duplicate settlement ID/time or reversed synthetic interval")
    return sum(start <= s + 15000 and end >= s - 15000 for s in times)


def funding(x: dict) -> dict:
    if x.get("rate_available") is None or not x.get("clock_proven"):
        return result("SOURCE_UNPROVEN", "Rate publication/initial-known-at unproven")
    if x["rate_available"] < x["rate_observed"]:
        return result("LOOKAHEAD", "Rate is declared available before original observation")
    if x.get("rate_corrected", 0) is None:
        return result("SOURCE_UNPROVEN", "Funding revision knowledge provenance missing")
    if x["rate_available"] < x.get("rate_corrected", 0):
        return result("LOOKAHEAD", "Corrected funding rate knowledge cannot be backdated")
    if x["purpose"] not in ("FEATURE", "CASH"):
        return result("METHOD_CONFLICT", "Unspecified use needs an explicit scientific purpose")
    if x["purpose"] == "FEATURE":
        v = visibility({"event": x["rate_event"], "available": x["rate_available"],
                        "observed": x["rate_observed"], "proof_floor": x["rate_event"],
                        "decision": x["decision"]})
        if v["code"] != "VISIBLE_SYNTHETIC":
            return v
        if x["rate_kind"] == "SETTLED_ACTUAL" and x["settlement"] > x["decision"]:
            return result("LOOKAHEAD", "Eventual settled rate cannot choose an earlier entry")
        return result("PREDICTION_VISIBLE_NOT_SETTLED" if x["rate_kind"] == "PREDICTED" else
                      "SETTLED_RATE_VISIBLE_SYNTHETIC", "Known forecast is not settlement cash")
    if x["rate_kind"] != "SETTLED_ACTUAL":
        return result("SOURCE_UNPROVEN", "Forecast rate cannot certify a settled account payment")
    if x["rate_event"] < x["settlement"] or x["rate_available"] < x["rate_event"]:
        return result("LOOKAHEAD", "Final rate clock backdated before settlement/publication")
    floor = funding_floor(x["settlement"])
    if x.get("ownership_proof") is None:
        return result("SOURCE_UNPROVEN", "S+/-15s intersecting-minute ownership proof missing")
    if x["ownership_proof"] < floor or x["final_at"] < max(floor, x["rate_available"]):
        return result("LOOKAHEAD", "Funding FINAL precedes legal ownership/rate proof")
    ack_floor = max(x["final_at"], x["ownership_proof"], x["rate_available"],
                    x["settlement"] + MINUTE, x.get("extra_delay_until", 0))
    if x["ack_at"] < ack_floor:
        return result("LOOKAHEAD", "Cash ACK precedes finalized source proof")
    if x["knowledge"] < x["final_at"]:
        return result("SOURCE_UNPROVEN", "At this cut ownership is still conditional, not FINAL")
    if x["side"] not in (-1, 1):
        raise ValueError("Invalid signed direction")
    if D(x["notional"]) <= 0 or D(x["mark_multiplier"]) <= 0 or D(x.get("owed_fee", "0")) < 0:
        raise ValueError("Invalid monetary domain")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        cashflow = -D(x["side"]) * D(x["notional"]) * D(x["mark_multiplier"])
        cashflow *= D(x["rate_bp"]) / D(10000)
        paid = x["knowledge"] >= x["ack_at"]
        liability = D(0) if paid else max(D(0), -cashflow)
        # This projection has exactly one finalized settlement, no future events.
        # A known credit has no debit cover; this obligation's ACK releases cover.
        cover = D(0) if paid or cashflow >= 0 else (
            D("1.10") * D(x["notional"]) * abs(D(x["rate_bp"])) / D(10000))
        shortfall = max(D(0), liability - cover)
        owed_fee = D(x.get("owed_fee", "0"))
        if x.get("paid_but_still_claimed"):
            return result("ACCOUNTING_CONTRADICTION", "Already ACKed obligation cannot remain liable")
        if x.get("terminal_clear_claim") and (liability > 0 or owed_fee > 0 or not paid):
            return result("UNPAID_TERMINAL", "Funding/fee/unacknowledged credit not terminally clear")
        return result("FUNDING_SYNTHETIC", "Static cash/owed projection, no financial state transition",
                      cashflow=amount(cashflow), acknowledged_cash=amount(cashflow if paid else D(0)),
                      liability=amount(liability), reserve=amount(cover), shortfall=amount(shortfall),
                      owed_fee=amount(owed_fee), final_floor=floor, ack_floor=ack_floor)


def geometry(x: dict) -> dict:
    if D(x["tick_bound"]) < 0 or D(x["stop_bp"]) <= 0:
        raise ValueError("Invalid adverse tick bound or stop")
    if not x.get("filters_proven") or not x.get("fee_proven"):
        return result("COST_UNKNOWN", "Historical tick/lot/fee applicability missing")
    if x["cadence"] == "UNKNOWN" and x.get("assume_eight_hours"):
        return result("METHOD_CONFLICT", "Unknown actual cadence cannot silently become verified8h")
    if x["cadence"] not in ("UNKNOWN", "KNOWN_SYNTHETIC_8H"):
        return result("METHOD_CONFLICT", "Unsupported cadence needs Controller choice")
    n = settlement_count(x["start"], x["end"], x["synthetic_times"])
    if x["cadence"] == "UNKNOWN":
        first = (x["start"]-15000+HOUR-1)//HOUR
        last = (x["end"]+15000)//HOUR
        expected = [i*HOUR for i in range(first, last+1)]
        actual = sorted(s for s in x["synthetic_times"]
                        if x["start"] <= s+15000 and x["end"] >= s-15000)
        if actual != expected:
            return result("METHOD_CONFLICT", "Unknown cadence requires full declared hourly proxy grid")
    with localcontext(Context(prec=50, rounding=ROUND_HALF_EVEN)):
        c = D(44) + D(8)*n + D(x["tick_bound"])
        minimum = max(D(30), 2*c)
        eligible = minimum <= D(x["stop_bp"]) <= D(250)
        return result("GEOMETRY_POSSIBLE_CONDITIONAL" if eligible else
                      "STRESS_COST_GEOMETRY_INELIGIBLE", "Proxy geometry, not measured expectancy",
                      events=n, stress_cost_bp=amount(c), minimum_stop_bp=amount(minimum),
                      base_cost_bp=amount(D(22)+D(4)*n+D(x["tick_bound"])),
                      cadence_proof="SYNTHETIC_ONLY" if x["cadence"] != "UNKNOWN" else "UNKNOWN_REAL")


def semantic(x: dict) -> dict:
    if x["kind"] == "BTC_POSITIVE" and x["single_asset_fraction"] > .60:
        return result("METHOD_CONFLICT", "BTC-only100% cannot inherit original<=60% positive screen")
    if x["kind"] == "SUPPORT" and min(x["fold_counts"]) < 100:
        return result("INSUFFICIENT_SUPPORT", "Per-fold support cannot be repaired by pooling")
    if x["kind"] == "MULTIPLICITY" and x["comparisons"] != 16:
        return result("METHOD_CONFLICT", "Original eight higher-cost net/incremental retain16 endpoints")
    if x["kind"] == "OOS" and x["exposed"] and x["blind_claim"]:
        return result("METHOD_CONFLICT", "Exposed development is not blind OOS")
    if x["kind"] == "METHOD" and x["R11_equal_R12"]:
        return result("METHOD_CONFLICT", "Prospective proof-floor amendment has distinct identity")
    if x["kind"] == "PRICE_COST" and not x["impact_proven"]:
        return result("COST_UNKNOWN", "22/44bp proxies do not authenticate spread/impact")
    if x["kind"] == "SCOPE" and x["claimed_real_body_access"]:
        return result("METHOD_CONFLICT", "This synthetic task grants zero real-body access")
    return result("DIAGNOSTIC_DESIGN_ONLY", "No source, prereg or positive historical admission")


def evaluate(case: dict) -> dict:
    routes = {"visibility": visibility, "mark": mark_asof, "funding": funding,
              "geometry": geometry, "semantic": semantic}
    return routes[case["op"]](case["input"])
