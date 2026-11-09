"""Opt-in swing review V2. Reuse J transport, immutable journal, S1 and renderer."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from pydantic import Field, model_validator

from ..core import fingerprint
from ..native.contract import digest, strict
from ..rc_models import STRATEGY_VERSION, frozen_contract
from ..rc_strategy import compile_s1
from ..qualification.source import causal
from ..swing import INTERVALS, SwingPolicy
from ..reporting import table
from .models import Decision, POLICY, ensure, offset_step, sample
from .product import Product, SourceView
from .source import Collector, project, reference

V2 = strict((Path(__file__).parent / "swing_review_v2.json").read_bytes())
VERSION = V2["schema"]
V2_HASH = digest(V2)
PRODUCT = V2["product"]


def window_minutes(value):
    ensure(type(value) is int and 5 <= value <= 120, "SWING_REVIEW_WINDOW_REQUIRES_5_TO_120_MINUTES")
    return value


def observation(body, wire, ref, trigger, symbol):
    """Keep current partial OHLC separate from completed strategy candles."""
    ensure(
        wire["params"]
        == {
            "symbol": symbol,
            "interval": "4h",
            "startTime": trigger,
            "endTime": trigger + INTERVALS["4H"] - 1,
            "limit": 1,
        },
        "SWING_CURRENT_OBSERVATION_SCOPE",
        "SOURCE_BLOCKED",
    )
    ensure(
        isinstance(body, list) and len(body) == 1 and len(body[0]) == 12,
        "SWING_CURRENT_OBSERVATION_MISSING",
        "SOURCE_BLOCKED",
    )
    row = body[0]
    ensure(
        type(row[0]) is int
        and type(row[6]) is int
        and row[0] == trigger
        and row[6] + 1 == trigger + INTERVALS["4H"],
        "SWING_CURRENT_OBSERVATION_INTERVAL",
        "SOURCE_BLOCKED",
    )
    from decimal import Decimal, InvalidOperation

    try:
        ensure(
            all(type(row[i]) in (str, int, float) for i in (1, 2, 3, 4, 5, 7, 9, 10)),
            "SWING_CURRENT_NUMERIC_TYPES",
            "SOURCE_BLOCKED",
        )
        values = [Decimal(str(row[i])) for i in (1, 2, 3, 4, 5, 7, 9, 10)]
        ensure(all(v.is_finite() for v in values), "SWING_CURRENT_NONFINITE", "SOURCE_BLOCKED")
        o, h, low, c, volume, quote, buy, buy_quote = values
        ensure(
            0 < low <= min(o, c) <= max(o, c) <= h
            and min(volume, quote, buy, buy_quote) >= 0
            and type(row[8]) is int
            and row[8] >= 0,
            "SWING_CURRENT_OHLC_INVALID",
            "SOURCE_BLOCKED",
        )
        import math

        ensure(all(math.isfinite(float(v)) for v in values), "SWING_CURRENT_RANGE", "SOURCE_BLOCKED")
    except InvalidOperation as error:
        raise ValueError("SWING_CURRENT_DECIMAL_INVALID") from error
    stamp = wire["durable_sample"]
    ensure(
        stamp["boot_id"] == ref["boot_id"] and 0 <= ref["at_mono_ms"] - stamp["mono_before_ms"] <= 120000,
        "SWING_OBSERVATION_OUTSIDE_TIME_PROBE_BRACKET",
        "SOURCE_BLOCKED",
    )
    # This observation lies BETWEEN the two probes, before reference.at_mono_ms.
    # project() intentionally only supports forward freshness; bounded interpolation
    # uses the already intersected probe offsets, like J's completed-bar parser.
    lower = ref["offset_lower_ms"] + stamp["mono_before_ms"]
    upper = ref["offset_upper_ms"] + stamp["mono_after_ms"]
    ensure(
        trigger + 120000 <= lower <= upper < row[6] + 1,
        "SWING_CURRENT_OBSERVATION_NOT_CURRENT",
        "SOURCE_BLOCKED",
    )
    return {
        "symbol": symbol,
        "cycle_open_ms": trigger,
        "open": float(o),
        "high": float(h),
        "low": float(low),
        "price": float(c),
        "available_bounds_ms": [lower, upper],
        "wire_ref": [wire["session"], wire["ordinal"]],
        "response_sha256": wire["body_sha256"],
        "source_event_ms": None,
        "source_publication_ms": None,
        "kind": "CURRENT_PARTIAL_4H_NOT_A_COMPLETED_SIGNAL_BAR",
    }


def verify_market(store, snapshot, at_sample):
    market = snapshot["swing_market"]
    wires = {(w["session"], w["ordinal"]): w for w in store.events.values("HTTP_RESPONSE")}

    def wire_body(key):
        w = wires[tuple(key)]
        raw = (store.directory / w["raw_path"]).read_bytes()
        ensure(hashlib.sha256(raw).hexdigest() == w["body_sha256"], "SWING_MARKET_RAW_HASH")
        ensure(
            w["status"] == 200
            and w["route"] in POLICY["routes"]
            and w["tls"]["hostname_verified"] is True
            and w["tls"]["chain"] == "CERT_REQUIRED"
            and w["tls"]["sni"] == "fapi.binance.com",
            "SWING_MARKET_TLS_OR_HTTP",
        )
        return strict(b'{"response":' + raw + b"}")["response"], w

    probes = [wire_body(key) for key in market["time_responses"]]
    ensure(all(w["route"] == "/fapi/v1/time" for _, w in probes), "SWING_TIME_ROUTE")
    ref = reference(*probes)
    ensure(ref == market["reference"], "SWING_MARKET_TIME_LINEAGE")
    lower, upper = project(ref, at_sample, V2["quote_max_age_ms"])
    old_lo, old_hi = project(snapshot["reference"], at_sample, snapshot["reference_max_age_ms"])
    ensure(
        max(lower, old_lo) <= min(upper, old_hi),
        "SWING_VENUE_TIME_REFERENCES_DISAGREE",
        "LIVE_CLOCK_DEGRADED_BLOCKED",
    )
    trigger = lower // INTERVALS["4H"] * INTERVALS["4H"]
    ensure(
        upper // INTERVALS["4H"] * INTERVALS["4H"] == trigger,
        "SWING_CYCLE_BOUNDARY_UNCERTAIN",
        "SOURCE_BLOCKED",
    )
    out = {}
    for recorded in market["observations"]:
        body, w = wire_body(recorded["wire_ref"])
        ensure(
            w["route"] == "/fapi/v1/klines"
            and probes[0][1]["durable_sample"]["mono_after_ms"] <= w["request_sample"]["mono_before_ms"]
            and w["durable_sample"]["mono_after_ms"] <= probes[1][1]["request_sample"]["mono_before_ms"],
            "SWING_OBSERVATION_NOT_BRACKETED",
        )
        rebuilt = observation(body, w, ref, trigger, recorded["symbol"])
        ensure(rebuilt == recorded and recorded["symbol"] not in out, "SWING_OBSERVATION_LINEAGE")
        ensure(
            0 <= upper - recorded["available_bounds_ms"][0] <= V2["quote_max_age_ms"],
            "SWING_CURRENT_PRICE_STALE",
            "SOURCE_BLOCKED",
        )
        out[recorded["symbol"]] = rebuilt
    ensure(set(out) == set(POLICY["symbols"]), "SWING_CURRENT_SYMBOL_MISSING", "SOURCE_BLOCKED")
    return out


class SwingCollector(Collector):
    # Nine requests normally before this hook, seventeen after one reconciliation.
    bars = V2["mandatory_bars"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ensure(self.grace >= 120000, "SWING_GRACE_AT_LEAST_120_SECONDS")

    def finish_snapshot(self, result):
        first = self.get("/fapi/v1/time", {})
        trigger = first[0]["serverTime"] // INTERVALS["4H"] * INTERVALS["4H"]
        bodies = []
        for symbol in POLICY["symbols"]:
            ensure(
                not any(
                    trigger < hi and trigger + INTERVALS["4H"] > lo
                    for lo, hi in self.exclusions["excluded_UTC_ms_ranges"]
                ),
                "LIVE_HOLDOUT_DATE_OVERLAP_FORBIDDEN",
            )
            body, w = self.get(
                "/fapi/v1/klines",
                {
                    "symbol": symbol,
                    "interval": "4h",
                    "startTime": trigger,
                    "endTime": trigger + INTERVALS["4H"] - 1,
                    "limit": 1,
                },
            )
            bodies.append((body, w, symbol))
        last = self.get("/fapi/v1/time", {})
        ref = reference(first, last)
        now = sample()
        ensure(
            not self.jumped and not offset_step(self.last, now),
            "SWING_CLOCK_JUMP_DURING_CURRENT_PRICE_CHECK",
            "LIVE_CLOCK_DEGRADED_BLOCKED",
        )
        ensure(now["mono_after_ms"] <= self.deadline, "LIVE_SESSION_DURATION_EXCEEDED")
        result.update(
            swing_review_policy=VERSION,
            swing_review_policy_sha256=V2_HASH,
            swing_market={
                "reference": ref,
                "time_responses": [[w["session"], w["ordinal"]] for _, w in (first, last)],
                "observations": [observation(b, w, ref, trigger, s) for b, w, s in bodies],
            },
            last_sample=now,
            source_bounds=list(project(result["reference"], now, self.max_age)),
            requests=self.requests,
            request_weight=self.weight,
            response_bytes=self.size,
        )
        verify_market(self.store, result, now)
        return result


class SwingDecision(Decision):
    schema_version: Literal["J_PUBLIC_SWING_DECISION_V2"] = "J_PUBLIC_SWING_DECISION_V2"  # type: ignore[assignment]  # New schema literal; V1 stays exact.
    product_version: Literal["J_PUBLIC_S1_SWING_V2"] = "J_PUBLIC_S1_SWING_V2"  # type: ignore[assignment]  # Deliberate version boundary.
    contract_sha256: str = V2_HASH
    review_window_minutes: int = Field(ge=5, le=120)
    market_observation: dict

    @model_validator(mode="after")
    def integrity(self):
        ensure(self.contract_sha256 == V2_HASH, "SWING_V2_POLICY_CHANGED")
        ensure(fingerprint(list(self.admitted_prefix)) == self.prefix_sha256, "SWING_PREFIX_TAMPER")
        lo, hi = self.review_source_bounds_ms
        ensure(
            self.decision_ms == lo <= hi
            and self.trigger_close_ms + 120000 <= lo
            and hi <= self.trigger_close_ms + self.review_window_minutes * 60000,
            "SWING_ACTUAL_REVIEW_WINDOW",
        )
        ensure(self.scheduled_review_ms == SwingPolicy().next_review(lo), "SWING_SCHEDULED_REVIEW")
        positive = self.market_state in ("WATCH", "ARMED")
        ensure(
            positive == (self.opportunity is not None) == (self.episode_id is not None), "SWING_PLAN_STATE"
        )
        q = self.market_observation
        ensure(
            q["symbol"] == self.symbol
            and q["cycle_open_ms"] == self.trigger_close_ms
            and q["available_bounds_ms"][1] <= lo
            and 0 <= hi - q["available_bounds_ms"][0] <= V2["quote_max_age_ms"],
            "SWING_PRICE_CAUSALITY",
        )
        if self.opportunity:
            p = self.opportunity
            ensure(
                p.setup_close_ms == self.trigger_close_ms
                and p.symbol == self.symbol
                and 4 <= p.holding_hours <= 48
                and p.account_status == "UNKNOWN"
                and p.available_ms <= lo < self.scheduled_review_ms < p.expires_ms
                and p.planned_after_cost_r >= 2,
                "SWING_CAUSAL_GEOMETRY",
            )
            ensure(
                self.episode_id
                == fingerprint(
                    [PRODUCT, STRATEGY_VERSION, self.symbol, self.trigger_close_ms, self.prefix_sha256]
                ),
                "SWING_EPISODE_ID",
            )
            ensure(
                self.eligible_planned_r == tuple(r for r in (2, 3, 4) if r <= p.planned_after_cost_r),
                "SWING_R_LABEL",
            )
            ensure(
                actionability(p, q, hi) is None and self.clock_condition != "CLOCK_DEGRADED_HOLD",
                "SWING_PLAN_NOT_CURRENTLY_ACTIONABLE",
            )
        else:
            ensure(not self.eligible_planned_r, "SWING_NEGATIVE_R_LABEL")
        return self


class SwingObservationCollector(Collector):
    """Preserve J's full 1H forward Shadow path within its 12/23-request budget."""

    def finish_snapshot(self, result):
        result.update(
            swing_review_policy=VERSION, swing_review_policy_sha256=V2_HASH, shadow_observation_only=True
        )
        return result


def actionability(plan, quote, upper):
    if upper >= min(plan.expires_ms, plan.review_deadline_ms):
        return "SWING_SETUP_EXPIRED"
    long = plan.direction == "LONG"
    if (
        quote["low"] <= plan.structural_invalidation
        if long
        else quote["high"] >= plan.structural_invalidation
    ):
        return "SWING_PROTECTIVE_PIVOT_INVALIDATED_SINCE_CLOSE"
    if quote["low"] <= plan.buffered_stop if long else quote["high"] >= plan.buffered_stop:
        return "SWING_HARD_STOP_CROSSED_SINCE_CLOSE"
    if quote["high"] >= min(plan.target_zones) if long else quote["low"] <= max(plan.target_zones):
        return "SWING_TARGET_ALREADY_OBSERVED_NO_RETROSPECTIVE_ENTRY"
    if not plan.entry_region[0] <= quote["price"] <= plan.entry_region[1]:
        return "SWING_PRICE_OUTSIDE_FROZEN_ENTRY_REGION_NO_CHASE"
    return None


class SwingSourceView(SourceView):
    intervals = tuple(V2["mandatory_bars"])

    def assess(self, symbol=None, *, review=False):
        q = super().assess(symbol, review=False)
        if q["status"] != "ELIGIBLE":
            return q
        try:
            s = self.store.snapshots()[-1]
            ensure(
                s.get("swing_review_policy_sha256") == V2_HASH, "SWING_V2_SNAPSHOT_REQUIRED", "SOURCE_BLOCKED"
            )
            if s.get("shadow_observation_only") is True:
                ensure(not review, "SWING_FRESH_SCAN_REQUIRED_FOR_NEW_CANDIDATES", "SOURCE_BLOCKED")
                q.update(
                    new_candidate_generation="SOURCE_BLOCKED_SHADOW_OBSERVATION_ONLY",
                    manual_review_policy=VERSION,
                )
                return q
            quotes = verify_market(self.store, s, q["sample"])
            lo, hi = q["source_bounds"]
            limit = self.store.events.values("MANUAL_REVIEW_POLICY")[0]["window_minutes"]
            window_open = (
                max(120000, s["grace_ms"]) <= lo - q["trigger"] and hi - q["trigger"] <= limit * 60000
            )
            q.update(
                manual_review_policy=VERSION,
                review_window_open=window_open,
                new_candidate_generation="REQUIRES_FRESH_MANUAL_REVIEW" if window_open else "SOURCE_BLOCKED",
            )
            if review:
                ensure(window_open, "SWING_REVIEW_HORIZON_EXPIRED_OR_NOT_CONFIRMED", "SOURCE_BLOCKED")
            q["market_observations"] = quotes
            q["review_not_before_ms"] = max(r["available_bounds_ms"][1] for r in quotes.values())
            return q
        except (ValueError, KeyError) as error:
            return {
                "status": getattr(error, "status", "SOURCE_BLOCKED"),
                "reason": str(error),
                "data_status": "DATA_NOT_READY",
                "records": [],
            }


class SwingProduct(Product):
    source_view = SwingSourceView
    decision_model = SwingDecision
    metadata_fields = (*Product.metadata_fields, "review_window_minutes", "market_observation")

    def existing_review(self, decision, assessment):
        """A frozen card cannot become a fresh actionable signal by mere replay."""
        reason, disposition = None, "FROZEN_DECISION_REVALIDATED_NOT_REISSUED"
        if decision.opportunity:
            episode = self.episode(decision.episode_id)
            state = episode["state"]["status"]
            if state not in ("WATCH", "ARMED", "READY_FOR_REVIEW", "ENTRY_ZONE_ACTIVE"):
                reason, disposition = "SWING_EPISODE_TERMINAL_NO_REACTIVATION", state
            else:
                reason = actionability(
                    decision.opportunity,
                    assessment["market_observations"][decision.symbol],
                    assessment["source_bounds"][1],
                )
                if reason:
                    disposition = (
                        "EXPIRED"
                        if "EXPIRED" in reason
                        else "INVALIDATED"
                        if "PIVOT" in reason or "STOP" in reason
                        else "NO_CHASE"
                    )
                    self.transition(
                        decision.episode_id,
                        episode["revision"],
                        disposition,
                        assessment["source_bounds"][0],
                        reason,
                    )
        event = {
            "episode_id": decision.episode_id,
            "original_decision_sha256": digest(decision.model_dump(mode="json")),
            "review_local": assessment["sample"],
            "review_source_bounds_ms": assessment["source_bounds"],
            "snapshot_sha256": assessment["snapshot_sha256"],
            "candidate_disposition": disposition,
            "reason": reason,
            "new_decision_created": False,
        }
        self.events.append("MANUAL_REVALIDATION", event)
        if reason:
            return {
                "status": "NO_SETUP",
                "candidate_disposition": disposition,
                "reason": reason,
                "frozen_episode_id": decision.episode_id,
                "new_candidate": False,
                "original_decision_sha256": event["original_decision_sha256"],
            }
        return decision

    def decision_metadata(self, assessment, symbol):
        return {
            "review_window_minutes": self.events.values("MANUAL_REVIEW_POLICY")[0]["window_minutes"],
            "market_observation": assessment["market_observations"][symbol],
        }

    def snapshot(self):
        value = super().snapshot()
        value.update(
            schema_version="J_PUBLIC_SWING_DASHBOARD_V2",
            manual_review_policy=VERSION,
            manual_revalidations=self.events.values("MANUAL_REVALIDATION"),
        )
        value.pop("snapshot_sha256")
        value["snapshot_sha256"] = digest(value)
        return value

    def compile(self, symbol, trigger, lower, records, holding, metadata):
        policy = SimpleNamespace(
            max_availability_delay_ms=metadata["review_window_minutes"] * 60000,
            minimum_history_bars=60,
            next_review=SwingPolicy().next_review,
        )

        def factory(**kw):
            diagnostics = kw["diagnostics"]
            diagnostics.update(
                hypothetical_costs_bps=frozen_contract()["strategy"]["costs_bps"],
                review_policy=VERSION,
                actual_review_delay_ms=lower - trigger,
                price_observation_kind=metadata["market_observation"]["kind"],
                signal_issued_at_close=False,
                acquisition_freshness_not_trade_timestamp=True,
            )
            if kw.get("opportunity"):
                reason = actionability(
                    kw["opportunity"], metadata["market_observation"], metadata["review_source_bounds_ms"][1]
                )
                if reason:
                    kw.update(
                        market_state="NO_SETUP",
                        reasons=(*kw["reasons"], reason),
                        opportunity=None,
                        episode_id=None,
                        eligible_planned_r=(),
                    )
                    diagnostics["candidate_disposition"] = "EXPIRED" if "EXPIRED" in reason else "NO_SETUP"
                else:
                    kw["reasons"] = (*kw["reasons"], "SWING_CURRENT_CYCLE_REVALIDATED_NO_CHASE")
            return SwingDecision(**kw, **metadata)

        return compile_s1(
            symbol=symbol,
            trigger_ms=trigger,
            decision_ms=lower,
            receipts=records,
            holding_hours=holding,
            asof_reader=causal,
            decision_factory=factory,
            product_id=PRODUCT,
            bar_policy=policy,
            source_reason="PUBLIC_HTTPS_UNSIGNED_OPERATIONAL_ONLY_ACCOUNT_VETO",
            cost_label="HYPOTHETICAL_UNCALIBRATED_FEE_SPREAD_SLIPPAGE_FUNDING_NOT_FILL_OR_RETURN",
        )

    def decisions(self):
        values = super().decisions()
        snapshots = {digest(s): s for s in self.store.snapshots()}
        for d in values:
            quotes = verify_market(self.store, snapshots[d.snapshot_sha256], d.review_local.model_dump())
            ensure(quotes[d.symbol] == d.market_observation, "SWING_FROZEN_PRICE_NOT_IN_SOURCE_SNAPSHOT")
            ensure(
                d.review_window_minutes == self.events.values("MANUAL_REVIEW_POLICY")[0]["window_minutes"],
                "SWING_FROZEN_WINDOW_CHANGED",
            )
        return values

    def dashboard(self, output=None):
        result = super().dashboard(output)
        path = self.store.directory / "dashboard/latest.html"
        extra = table(
            [
                {
                    "Review policy": VERSION,
                    "Signal issued at candle close": False,
                    "Actual review UTC bounds ms": d.review_source_bounds_ms,
                    "Actual local review wall ms": d.review_local.wall_ms,
                    "Actual local review monotonic bracket ms": [
                        d.review_local.mono_before_ms,
                        d.review_local.mono_after_ms,
                    ],
                    "Frozen decision warning": "Historical card, not a refreshed signal. Check current source and window status.",
                    "Delay since 4H close (minutes)": (d.decision_ms - d.trigger_close_ms) / 60000,
                    "Current observed price": d.market_observation["price"],
                    "Actionability": "HYPOTHETICAL ONLY; NO CHASE; ACCOUNT VETO",
                    "Quote freshness": "HTTPS acquisition only; no exchange last-trade timestamp",
                    "Window ceiling minutes": d.review_window_minutes,
                }
                for d in self.decisions()
            ]
        )
        extra += table(
            [
                {
                    "Manual re-review": e["review_source_bounds_ms"],
                    "Original plan": e["original_decision_sha256"],
                    "Current disposition": e["candidate_disposition"],
                    "Reason": e["reason"],
                    "New signal issued": False,
                }
                for e in self.events.values("MANUAL_REVALIDATION")
            ]
        )
        path.write_text(path.read_text().replace("</html>", extra + "</html>"), encoding="utf-8")
        return result


def product_for(store, requested=None, minutes=None):
    modes = store.events.values("MANUAL_REVIEW_POLICY")
    if modes:
        ensure(
            len(modes) == 1 and modes[0]["policy"] == VERSION and modes[0]["sha256"] == V2_HASH,
            "SWING_REVIEW_MODE_TAMPER",
        )
        ensure(requested in (None, VERSION), "SWING_REVIEW_MODE_IMMUTABLE")
        ensure(minutes is None or minutes == modes[0]["window_minutes"], "SWING_WINDOW_IMMUTABLE")
        return SwingProduct(store)
    if requested == VERSION:
        ensure(
            not store.snapshots()
            and not store.events.values("DECISION")
            and not store.events.values("SESSION_START"),
            "SWING_V2_REQUIRES_FRESH_OUTPUT_NO_V1_MIGRATION",
        )
        store.events.append(
            "MANUAL_REVIEW_POLICY",
            {
                "policy": VERSION,
                "sha256": V2_HASH,
                "window_minutes": window_minutes(120 if minutes is None else minutes),
            },
        )
        return SwingProduct(store)
    ensure(minutes is None, "SWING_WINDOW_CONFIGURATION_REQUIRES_V2")
    return Product(store)
