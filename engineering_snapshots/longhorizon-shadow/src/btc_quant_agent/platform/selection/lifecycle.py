"""Frozen episode lifecycle, response revalidation and synthetic quote-cross execution."""

from __future__ import annotations

from dataclasses import dataclass
from math import floor

from ..core import ExecutableQuote, InstrumentSpec, UserReportedFill, dec, fingerprint, quantize
from .selector import Policy
from .sources import MINUTE, Bar, Observation
from .store import Capital, SelectorStore


@dataclass(frozen=True)
class Monitor:
    bar: Bar
    now: int
    quote: ExecutableQuote | None
    quote_authority: str = "OFFLINE_EXECUTABLE_TOP_OF_BOOK"
    funding: Observation | None = None
    funding_cadence_ms: int | None = None
    next_funding_ts: int | None = None
    healthy: bool = True
    regime: str | None = None
    previous_bar: Bar | None = None
    beta: float | None = None
    beta_available_ts: int | None = None
    # symbol, executable valuation, beta, available timestamp, multiplier, adverse costs per base unit
    portfolio_marks: tuple[tuple[str, float, float, int, float, float], ...] = ()
    mark: Observation | None = None
    cadence_evidence: Observation | None = None
    next_funding_evidence: Observation | None = None
    entry_vetoes: tuple[str, ...] = ()
    setup_known_ts: int | None = None

    def quote_reason(self, policy: Policy) -> str | None:
        if self.quote is None:
            return "MISSING_EXECUTABLE_QUOTE"
        from ..canary.public_data import admitted_public

        public = admitted_public(self.quote.provenance)
        expected = "PUBLIC_READONLY_TOP_OF_BOOK" if public else "OFFLINE_EXECUTABLE_TOP_OF_BOOK"
        if self.quote_authority != expected:
            return "QUOTE_AUTHORITY_INVALID"
        if self.quote.provenance.exposure != "SYNTHETIC" and not public:
            return "BLOCKED_PENDING_OWNER_AUTH"
        return self.quote.reason(self.bar.spec, self.now, policy.quote_max_age_ms)


def funding_risk(monitor: Monitor, side: int, policy: Policy) -> tuple[float | None, str | None]:
    if monitor.bar.spec.market != "PERPETUAL":
        return 0, None
    o, cadence, next_ts = monitor.funding, monitor.funding_cadence_ms, monitor.next_funding_ts
    from ..canary.clock_domain import NativeProvenance

    if any(
        isinstance(e.provenance, NativeProvenance)
        for e in (o, monitor.cadence_evidence, monitor.next_funding_evidence)
        if e is not None
    ):
        return None, "NATIVE_FUNDING_SCHEDULE_CLOCK_UNQUALIFIED"
    if (
        o is None
        or cadence is None
        or cadence <= 0
        or next_ts is None
        or next_ts <= monitor.now
        or monitor.bar.spec.funding_interval_hours is None
        or cadence != monitor.bar.spec.funding_interval_hours * 3_600_000
    ):
        return None, "FUNDING_CADENCE_OR_NEXT_SETTLEMENT_UNKNOWN"
    for evidence, name, value in (
        (monitor.cadence_evidence, "funding_interval_ms", cadence),
        (monitor.next_funding_evidence, "next_funding_ts", next_ts),
    ):
        if (
            evidence is None
            or evidence.field != name
            or evidence.value != value
            or evidence.reason(monitor.bar.spec, monitor.now, MINUTE)
        ):
            return None, "FUNDING_SCHEDULE_PROVENANCE_INCOMPLETE"
    if o.field != "funding_rate":
        return None, "FUNDING_FIELD_MISMATCH"
    reason = o.reason(monitor.bar.spec, monitor.now, MINUTE)
    if reason or monitor.now - o.provenance.exchange_event_ts > policy.funding_max_age_ms:
        return None, "FUNDING_SOURCE_" + (reason or "STALE")
    settlements = max(
        0, floor((monitor.now + policy.funding_review_hours * 3_600_000 - next_ts) / cadence) + 1
    )
    # No favorable funding credit. Stress both sign uncertainty and current adverse rate.
    rate = max(abs(o.value), side * o.value, 0.0001)
    return rate * settlements, None


def proposal(anchors: dict, monitor: Monitor, policy: Policy, capital: Capital) -> dict:
    q, spec = monitor.quote, monitor.bar.spec
    if q is None:
        raise ValueError("MISSING_EXECUTABLE_QUOTE")
    sign = 1 if anchors["side"] == "LONG" else -1
    stop, atr = dec(anchors["stop"]), dec(anchors["atr"])
    entry = (
        dec(anchors["anchor"])
        if anchors["entry_mode"] == "resting_limit"
        else quantize(
            (q.ask if sign == 1 else q.bid) * dec(1 + sign * policy.slippage_bps / 10000),
            spec.tick_size,
            up=sign == 1,
        )
    )
    if sign * (entry - dec(anchors["chase_cap"])) > 0:
        raise ValueError("SLIPPAGE_ADJUSTED_CHASE_CAP_EXCEEDED")
    if anchors["entry_mode"] == "market" and not dec(anchors["zone_low"]) <= entry <= dec(
        anchors["zone_high"]
    ):
        raise ValueError("SLIPPAGE_ADJUSTED_ENTRY_REGION_EXCEEDED")
    stressed = stop - dec(sign) * max(2 * spec.tick_size, dec(0.15) * atr)
    if stressed <= 0 or sign * (entry - stop) <= 0:
        raise ValueError("INVALID_STRUCTURAL_STOP")
    funding, reason = funding_risk(monitor, sign, policy)
    if reason:
        raise ValueError(reason)
    fee_rate = dec(policy.fee_bps / 10000)
    # Entry is already executable; do not charge its spread twice.
    exit_slip = abs(stressed) * dec(policy.slippage_bps / 10000)
    unit_loss = spec.multiplier * (
        dec(sign) * (entry - stressed) + exit_slip + fee_rate * (entry + stressed) + entry * dec(funding)
    )
    visible = q.ask_quantity if sign == 1 else q.bid_quantity
    vals, _ = monitor.bar.values(min(monitor.now, monitor.bar.end + 1000))
    if visible is None or visible <= 0 or "quote_volume" not in vals:
        raise ValueError("EXECUTION_CAPACITY_UNKNOWN")
    desired = dec(capital.equity * policy.per_trade_risk) / unit_loss
    occupancy_cap = dec(capital.equity * policy.symbol) / (entry * spec.multiplier)
    quantity = quantize(
        min(desired, visible * dec(0.05), dec(vals["quote_volume"]) * dec(0.005) / entry, occupancy_cap),
        spec.quantity_step,
    )
    notional = quantity * entry * spec.multiplier
    if notional < spec.min_notional:
        raise ValueError("INSUFFICIENT_MINIMUM_NOTIONAL")
    leverage = min(policy.leverage, spec.max_leverage)
    stop_distance = abs(float(entry - stressed) / float(entry))
    if leverage > 1 and stop_distance + 0.05 >= 1 / leverage - spec.maintenance_margin_rate:
        raise ValueError("LIQUIDATION_BUFFER_INSUFFICIENT")
    if (
        monitor.beta is None
        or monitor.beta_available_ts is None
        or monitor.beta_available_ts > monitor.now
        or monitor.now - monitor.beta_available_ts > 2 * 300_000
    ):
        raise ValueError("BETA_EVIDENCE_REQUIRED_FOR_FIRST_POSITION")
    if leverage > 1 and (monitor.mark is None or monitor.mark.reason(spec, monitor.now, MINUTE)):
        raise ValueError("ADMISSIBLE_MARK_PRICE_REQUIRED_FOR_LEVERAGE")
    target = dec(anchors["target"]) if anchors.get("target") is not None else None
    cost = unit_loss / spec.multiplier - dec(sign) * (entry - stressed)
    if target is not None:
        net_reward = dec(sign) * (target - entry) - cost
        if net_reward <= 0 or net_reward / unit_loss * spec.multiplier < dec(1.2):
            raise ValueError("REMAINING_NET_MEAN_GEOMETRY_INSUFFICIENT")
    elif cost > abs(entry - stop) * dec(0.25):
        raise ValueError("FRICTION_TOO_LARGE_FOR_INITIAL_RISK")
    return {
        "episode_id": anchors["id"],
        "symbol": anchors["symbol"],
        "side": sign,
        "beta": monitor.beta,
        "beta_available_ts": monitor.beta_available_ts,
        "cluster": anchors["cluster"],
        "risk": float(quantity * unit_loss),
        "initial_price_risk": float(quantity * abs(entry - stop) * spec.multiplier),
        "notional": float(notional),
        "margin": float(notional) / leverage,
        "quantity": str(quantity),
        "entry": str(entry),
        "funding_stress_rate": funding,
        "funding_status": "PROJECTED_ADVERSE_REVIEW_HORIZON_NOT_REALIZED",
        "unit_loss": str(unit_loss),
        "equity_ts": capital.available_ts,
        "quote_id": fingerprint(q),
        "source": "SIMULATED",
    }


def advance(
    store: SelectorStore,
    identity: str,
    m: Monitor,
    policy: Policy,
    *,
    require_ack: bool = False,
    capital: Capital | None = None,
    exposures: tuple[dict, ...] = (),
) -> dict:
    episode = store.episode(identity)
    a, s = episode["anchors"], dict(episode["state"])
    if s["status"] in {"CANCELLED", "EXPIRED"}:
        return episode
    if s.get("execution") in {"SIMULATED_FILLED", "USER_REPORTED"}:
        return episode
    if m.now < episode["updated_ts"]:
        raise ValueError("EPISODE_TIME_REGRESSION")
    if (
        a["symbol"] != m.bar.spec.symbol
        or a["policy_hash"] != policy.hash
        or a["instrument_hash"] != fingerprint(m.bar.spec)
    ):
        raise ValueError("EPISODE_MONITOR_IDENTITY_OR_POLICY_MISMATCH")
    if not m.healthy:
        store.revoke_regime(a["symbol"], m.now, a["setup_ts"])
    persisted_regime = store.regime(a["symbol"])
    from ..canary.clock_domain import NativeProvenance, native_before, expired, post_setup

    native_p = next((o.provenance for o in m.bar.fields if isinstance(o.provenance, NativeProvenance)), None)
    regime_future = (
        not native_before(native_p, persisted_regime["cutoff"], m.now)
        if native_p
        else persisted_regime["cutoff"] > m.now
    )
    persisted_mismatch = (
        persisted_regime["cutoff"] < a["setup_ts"]
        or regime_future
        or persisted_regime["state"] != a["regime"]
    )
    vals, errors = m.bar.values(min(m.now, m.bar.end + 1000))
    seen = dict(s.get("observation_hashes", {}))
    if m.bar.id in seen and seen[m.bar.id] != fingerprint(m.bar):
        raise ValueError("IMMUTABLE_MONITOR_OBSERVATION_CONFLICT")
    seen[m.bar.id] = fingerprint(m.bar)
    s["observation_hashes"] = seen
    bar_clock_valid = (
        native_p.reason(m.now, MINUTE) is None and native_before(native_p, m.bar.end, m.now)
        if native_p
        else m.bar.end <= m.now and m.now - m.bar.end <= MINUTE
    )
    bar_valid = (
        m.bar.interval_ms == MINUTE
        and bar_clock_valid
        and m.bar.end >= s.get("last_monitor_end", 0)
        and all(k in vals for k in ("low", "high", "close", "open"))
    )
    path_gap = bar_valid and m.bar.start > s.get("last_monitor_end", a["setup_ts"])
    if bar_valid:
        s["last_monitor_end"] = m.bar.end
    side = 1 if a["side"] == "LONG" else -1
    qreason = m.quote_reason(policy)
    quote_valid = qreason is None
    # Unknown clocks/identity never manufacture a structural cancellation.
    stop = dec(a["stop"])
    if bar_valid and (
        (side == 1 and vals["low"] <= float(stop)) or (side == -1 and vals["high"] >= float(stop))
    ):
        s.update(status="CANCELLED", reasons=["FROZEN_STRUCTURE_BREACHED"])
    elif (
        quote_valid
        and m.quote is not None
        and a["target"] is not None
        and side * float((m.quote.bid if side == 1 else m.quote.ask) - dec(a["target"])) >= 0
    ):
        s.update(status="CANCELLED", reasons=["OBSERVED_TARGET_CONSUMED"])
    elif expired(a, m.now):
        s.update(status="EXPIRED", reasons=["ORIGINAL_EXPIRY_REACHED"])
    elif path_gap:
        s.update(status="CANCELLED", reasons=["UNOBSERVED_ENTRY_PATH"])
    elif not m.healthy or not bar_valid:
        s.update(
            status="ARMED" if s["trigger_ids"] else "WATCH",
            reasons=["MONITOR_SOURCE_UNAVAILABLE", *sorted(set(errors.values()))],
        )
    elif m.regime not in {"TREND_UP", "TREND_DOWN", "RANGE"} or m.regime != a["regime"] or persisted_mismatch:
        s.update(status="ARMED" if s["trigger_ids"] else "WATCH", reasons=["REGIME_REVOKES_READINESS"])
    else:
        anchor, atr = float(a["anchor"]), a["atr"]
        confirmed = False
        if m.bar.end > a["setup_ts"] and post_setup(m.bar, a, m.setup_known_ts):
            if a["strategy"] == "breakout_retest":
                confirmed = (
                    vals["low"] <= anchor + 0.15 * atr
                    and vals["high"] >= anchor - 0.15 * atr
                    and (side * (vals["close"] - anchor) >= 0.05 * atr)
                )
            elif a["strategy"] == "trend_pullback" and m.previous_bar is not None:
                prev, _ = m.previous_bar.values(min(m.now, m.previous_bar.end + 1000))
                confirmed = (
                    m.previous_bar.end == m.bar.start
                    and m.previous_bar.interval_ms == MINUTE
                    and (
                        "high" in prev
                        and "low" in prev
                        and (vals["close"] > prev["high"] if side == 1 else vals["close"] < prev["low"])
                    )
                )
            elif a["strategy"] == "bollinger_reversion":
                confirmed = side * (vals["close"] - anchor) > 0
        if not s["trigger_ids"] and m.bar.id not in s["confirmation_ids"]:
            if confirmed:
                if s["confirmation_ids"] and s.get("last_confirmation_end") != m.bar.start:
                    s["confirmation_ids"] = []
                s["confirmation_ids"] = [*s["confirmation_ids"], m.bar.id]
                s["last_confirmation_end"] = m.bar.end
            elif s["confirmation_ids"]:
                s["confirmation_ids"] = []
            if len(s["confirmation_ids"]) >= policy.independent_confirmations:
                s["trigger_ids"] = list(s["confirmation_ids"])
                s["trigger_ts"] = m.bar.end
        s.update(status="ARMED" if s["trigger_ids"] else "WATCH", reasons=[])
        if not s["trigger_ids"]:
            s["reasons"] = ["DISTINCT_COMPLETED_CONFIRMATIONS_PENDING"]
        else:
            reasons = list(m.entry_vetoes)
            if qreason:
                reasons.append(qreason)
            if quote_valid and m.quote is not None:
                q = m.quote
                entry = q.ask if side == 1 else q.bid
                cap, low, high = dec(a["chase_cap"]), dec(a["zone_low"]), dec(a["zone_high"])
                spread = float((q.ask - q.bid) / ((q.ask + q.bid) / 2)) * 10000
                if spread > policy.max_spread_bps:
                    reasons.append("SPREAD_TOO_HIGH")
                if spread > policy.max_spread_bps:
                    pass  # Raw liquidity veto revokes readiness; it does not reset/fabricate a setup.
                elif side * (entry - cap) > 0:
                    s.update(status="CANCELLED", reasons=["CHASE_CAP_EXCEEDED"])
                elif (side == 1 and entry < low) or (side == -1 and entry > high):
                    s.update(status="CANCELLED", reasons=["ENTRY_REGION_LOST"])
                elif a["entry_mode"] == "market" and not low <= entry <= high:
                    reasons.append("OUTSIDE_MARKET_ENTRY_REGION")
            _, funding_reason = funding_risk(m, side, policy)
            if funding_reason:
                reasons.append(funding_reason)
            if require_ack:
                notice = s.get("notification_event")
                delivery: dict = store.delivery(notice) if notice else {"delivery": "UNKNOWN"}
                ack = delivery.get("acknowledged_ts")
                if delivery["delivery"] == "UNKNOWN" or type(ack) is not int:
                    reasons.append("ACTUAL_DELIVERY_OR_ACK_UNKNOWN")
                elif m.now < ack:
                    reasons.append("OWNER_RESPONSE_PENDING")
                elif m.quote is not None and isinstance(m.quote.provenance, NativeProvenance):
                    # L4 models response time with a frozen monotonic anchor in
                    # PublicEngine; a raw-wall delivery row is not a native ack proof.
                    reasons.append("NATIVE_ACK_CLOCK_EVIDENCE_REQUIRED")
                elif (
                    not quote_valid
                    or m.quote is None
                    or m.quote.provenance.exchange_event_ts < ack
                    or (m.quote.provenance.received_ts < ack or m.quote.provenance.available_ts < ack)
                ):
                    reasons.append("NEW_POST_ACK_QUOTE_REQUIRED")
            else:
                reasons.append("OWNER_ACK_REQUIRED")
            if s["status"] not in {"CANCELLED", "EXPIRED"}:
                if not reasons and capital is not None:
                    try:
                        p = proposal(a, m, policy, capital)
                        marks = {
                            s: (price, beta, ts, mult, cost)
                            for s, price, beta, ts, mult, cost in m.portfolio_marks
                        }
                        if m.quote is not None and m.beta is not None and m.beta_available_ts is not None:
                            stress = float(
                                dec(p["unit_loss"]) / m.bar.spec.multiplier
                                - dec(p["side"]) * (dec(p["entry"]) - dec(a["stop"]))
                            )
                            marks[a["symbol"]] = (
                                float((m.quote.bid + m.quote.ask) / 2),
                                m.beta,
                                m.beta_available_ts,
                                float(m.bar.spec.multiplier),
                                stress,
                            )
                        ledger = store.ledger_exposures(marks, m.now)
                        limits = policy.model_dump(
                            include={"total_risk", "cluster_risk", "gross", "symbol", "net_beta"}
                        )
                        s["reservation"] = store.reserve(p, capital, m.now, limits, (*ledger, *exposures))
                    except ValueError as exc:
                        reasons.append(str(exc))
                elif capital is None and not reasons:
                    reasons.append("CURRENT_CAPITAL_REQUIRED")
                s.update(status="ARMED" if reasons else "ENTRY_ELIGIBLE", reasons=reasons)
                if not reasons and m.quote is not None:
                    s.update(
                        validated_quote_id=fingerprint(m.quote),
                        validated_ts=m.now,
                        validated_book_side=str(m.quote.ask if side == 1 else m.quote.bid),
                        entry_action="RESTING_LIMIT_ELIGIBLE"
                        if a["entry_mode"] == "resting_limit"
                        else "MARKET_ENTRY_ELIGIBLE",
                    )
    return store.transition(identity, episode["revision"], s, m.now)


def place_resting_limit(store: SelectorStore, identity: str, now: int) -> dict:
    episode = store.episode(identity)
    a, s = episode["anchors"], dict(episode["state"])
    if a["entry_mode"] != "resting_limit" or s["status"] != "ENTRY_ELIGIBLE" or now >= a["expiry"]:
        raise ValueError("RESTING_LIMIT_NOT_ELIGIBLE")
    if s["limit_placed_ts"] is None:
        side = 1 if a["side"] == "LONG" else -1
        if now != s.get("validated_ts") or side * (dec(s["validated_book_side"]) - dec(a["anchor"])) <= 0:
            raise ValueError("LIMIT_NOT_RESTING_AT_VALIDATED_QUOTE")
        s.update(limit_placed_ts=now, execution="SIMULATED_PENDING_ORDER")
        store.reservation_status(identity, "PENDING_ORDER")
        return store.transition(identity, episode["revision"], s, now)
    return episode


def simulated_fill(store: SelectorStore, identity: str, m: Monitor, policy: Policy) -> dict | None:
    episode = store.episode(identity)
    a, s = episode["anchors"], dict(episode["state"])
    if (
        s.get("execution") not in {"NOT_REPORTED", "SIMULATED_PENDING_ORDER"}
        or s["status"] != "ENTRY_ELIGIBLE"
        or m.now >= a["expiry"]
    ):
        return None
    if m.quote is None or m.quote_reason(policy) or not s.get("reservation"):
        return None
    if s.get("validated_quote_id") != fingerprint(m.quote) or s.get("validated_ts") != m.now:
        return None
    sign = 1 if a["side"] == "LONG" else -1
    if a["entry_mode"] == "resting_limit":
        placed = s.get("limit_placed_ts")
        if placed is None or m.quote.provenance.exchange_event_ts <= placed:
            return None
        limit = dec(a["anchor"])
        if not (m.quote.ask < limit if sign == 1 else m.quote.bid > limit):
            return None  # Candle touch, equality and earlier quote are insufficient.
        price = limit
    else:
        # The exact new quote bound into the capacity reservation is mandatory.
        if fingerprint(m.quote) != s["reservation"]["quote_id"]:
            return None
        price = dec(s["reservation"]["entry"])
    visible = m.quote.ask_quantity if sign == 1 else m.quote.bid_quantity
    vals, _ = m.bar.values(min(m.now, m.bar.end + 1000))
    if visible is None or "quote_volume" not in vals:
        return None
    qty = quantize(
        min(
            dec(s["reservation"]["quantity"]),
            visible * dec(0.05),
            dec(vals["quote_volume"]) * dec(0.005) / price,
        ),
        m.bar.spec.quantity_step,
    )
    if qty * price * m.bar.spec.multiplier < m.bar.spec.min_notional:
        return None
    fill = {
        "id": fingerprint([identity, m.quote, price, qty]),
        "episode_id": identity,
        "symbol": a["symbol"],
        "side": a["side"],
        "price": str(price),
        "quantity": str(qty),
        "decision_ts": m.now,
        "quote_event_ts": m.quote.provenance.exchange_event_ts,
        "source": "SIMULATED",
        "fee": float(qty * price * m.bar.spec.multiplier) * policy.fee_bps / 10000,
        "initial_R": float(qty * abs(price - dec(a["original_stop"])) * m.bar.spec.multiplier),
        "next_funding_ts": m.next_funding_ts,
        "funding_cadence_ms": m.funding_cadence_ms,
        "funding_evidence": [m.funding, m.cadence_evidence, m.next_funding_evidence],
        "entry_spread_attribution": float(
            abs((m.quote.ask if sign == 1 else m.quote.bid) - (m.quote.ask + m.quote.bid) / 2)
            * qty
            * m.bar.spec.multiplier
        ),
        "entry_slippage_attribution": max(
            0.0,
            float(
                dec(sign)
                * (price - (m.quote.ask if sign == 1 else m.quote.bid))
                * qty
                * m.bar.spec.multiplier
            ),
        ),
        "fill_semantics": "Modeled quote cross with capacity haircut; no queue or exchange execution proof",
    }
    s.update(execution="SIMULATED_FILLED", simulated_fill=fill)
    store.transition(identity, episode["revision"], s, m.now)
    store.reservation_status(identity, "OPEN")
    return fill


def record_user_fill(store: SelectorStore, identity: str, fill: UserReportedFill, spec: InstrumentSpec):
    episode = store.episode(identity)
    a = episode["anchors"]
    if fill.symbol != a["symbol"] or fill.direction != a["side"] or fingerprint(spec) != a["instrument_hash"]:
        raise ValueError("USER_FILL_EPISODE_IDENTITY_MISMATCH")
    # Late actual reports are recorded as facts even after an advisory episode became terminal.
    position = store.report(fill, spec, stop=dec(a["original_stop"]), accept_breached_stop=True)
    late = fill.user_action_ts >= a["expiry"] or episode["state"]["status"] in {"EXPIRED", "CANCELLED"}
    evidence = {
        "source": "USER_REPORTED",
        "late_or_terminal_report": late,
        "requires_reconciliation": late,
        "report_id": fill.report_id,
    }
    with store._connect() as db:
        import json

        db.execute(
            "INSERT OR IGNORE INTO selector_position_bindings VALUES (?,?,?)",
            (position.id, identity, json.dumps(evidence, sort_keys=True)),
        )
    if (
        episode["state"]["status"] not in {"CANCELLED", "EXPIRED"}
        and episode["state"].get("execution") != "USER_REPORTED"
    ):
        store.transition(
            identity,
            episode["revision"],
            {**episode["state"], "execution": "USER_REPORTED"},
            fill.received_ts,
        )
    return position, evidence
