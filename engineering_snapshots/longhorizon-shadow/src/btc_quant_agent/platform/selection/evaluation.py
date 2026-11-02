"""Offline candidate-episode evaluation; matched sources/costs, no outcome-driven fitting."""

from __future__ import annotations

import html
import json
import hashlib
from collections import Counter
from dataclasses import replace
from pathlib import Path

from btc_quant_agent.economic.fee_model import FeeModel

from ..advisory import gate as previous_gate, scan as previous_scan
from ..backtest import manage_episode
from ..config import EntryConfig, ExecutionConfig, FactorConfig, PlatformConfig, StrategyConfig
from ..core import (
    DataProvenance,
    Candle,
    DerivativeSnapshot,
    ExecutableQuote,
    Lifecycle,
    MarketEvent,
    PositionState,
    SourceAdmission,
    StrategyCandidate,
    dec,
    fingerprint,
    primitive,
    quantize,
)
from ..execution_model import exit_price
from ..strategies import resolve as previous_resolve
from ..factors import REGISTRY as FACTORS
from .fixtures import BASE, bar, history, market_event, monitor, structural_bars
from .lifecycle import advance, place_resting_limit, simulated_fill
from .management import ExitPolicy
from .selector import Policy, Setup, resolve_setups, scan
from .sources import MINUTE, STRUCTURE
from .store import Capital, SelectorStore


def legacy_candidate(setup: Setup) -> StrategyCandidate:
    a = setup.anchors
    return StrategyCandidate(
        a["id"],
        a["symbol"],
        a["side"],
        a["strategy"],
        a["strategy_version"],
        a["setup_ts"],
        Lifecycle.WATCH,
        setup.ranking.get("opportunity") or 0,
        json.dumps({"close": float(a["anchor"]), "episode_id": a["id"]}),
        (),
        dec(a["zone_low"]),
        dec(a["zone_high"]),
        dec(a["chase_cap"]),
        a["expiry"],
        dec(a["stop"]),
        dec(a["stop"]),
        dec(a["target"]) if a["target"] else None,
        "FROZEN_MEAN" if a["target"] else "TRAIL",
        a["regime"],
        DataProvenance(
            "offline_fixture",
            "FABRICATED:COMMON_EPISODE",
            a["setup_ts"],
            a["setup_ts"] + 10,
            a["setup_ts"] + 100,
        ),
        setup.vetoes,
    )


def legacy_config(policy: Policy) -> PlatformConfig:
    return PlatformConfig(
        universe=list(policy.symbols),
        benchmark=policy.benchmark,
        strategies=[StrategyConfig(id=s, group=s, priority=0) for s in policy.enabled],
        interval_seconds=60,
        entry=EntryConfig(aggregation="vote", confirmation_bars=2),
        execution=ExecutionConfig(fee_bps=policy.fee_bps, slippage_bps=policy.slippage_bps, delay_minutes=1),
    )


def previous_source_scan(snapshot, policy):
    """Run the actual inherited discovery/ranking/kernel on the same completed source snapshot."""
    cfg = legacy_config(policy).model_copy(
        update={
            "interval_seconds": 300,
            "factors": [
                FactorConfig(id="ADX"),
                FactorConfig(id="RELATIVE_STRENGTH"),
                FactorConfig(id="RELATIVE_VOLUME"),
            ],
        }
    )
    events = []
    now = snapshot.universe.decision_ts
    for symbol, df in snapshot.frames.items():
        b = next(b for b in snapshot.bars if b.spec.symbol == symbol and b.end == snapshot.universe.cutoff)
        v, _ = b.values(now)
        price_source = next(o.provenance for o in b.fields if o.field == "close")
        c = Candle(
            symbol,
            "5m",
            b.start,
            b.end - 1,
            v["open"],
            v["high"],
            v["low"],
            v["close"],
            v["volume"],
            v["quote_volume"],
            closed=True,
            available_at_ms=price_source.available_ts,
        )
        qp = DataProvenance(
            b.spec.provider,
            "FABRICATED:COMMON_STRUCTURAL_TOP_OF_BOOK:" + symbol,
            b.end + 500,
            b.end + 600,
            b.end + 700,
        )
        q = ExecutableQuote(
            symbol,
            quantize(v["close"] - 0.01, b.spec.tick_size),
            quantize(v["close"] + 0.01, b.spec.tick_size, up=True),
            qp,
            dec(10000),
            dec(10000),
        )
        events.append(MarketEvent(b.spec, c, price_source, now, q))
    indices = {s: len(df) - 1 for s, df in snapshot.frames.items()}
    raw = previous_scan(snapshot.pipeline, events, indices, cfg, resolve_conflicts=False)
    selected = previous_scan(snapshot.pipeline, events, indices, cfg)
    return cfg, raw, selected


def new_post_ack_quote(m):
    if m.quote is None:
        return replace(m, now=m.now + 1000)
    p = m.quote.provenance
    return replace(
        m,
        now=m.now + 1000,
        quote=replace(
            m.quote,
            provenance=replace(
                p,
                exchange_event_ts=p.exchange_event_ts + 1000,
                received_ts=p.received_ts + 1000,
                available_ts=p.available_ts + 1000,
            ),
        ),
    )


def manage_fill(a, fill, policy: Policy, *, mode="favorable_then_gap", management="v1") -> dict:
    """Use the existing economic execution model and the supervisor's common management kernel."""
    quantity, entry = dec(fill["quantity"]), dec(fill["price"])
    position = PositionState(
        fill["id"],
        a["symbol"],
        a["side"],
        entry,
        quantity,
        dec(a["stop"]),
        dec(a["original_stop"]),
        policy.leverage,
        "ISOLATED",
        1,
        "OPEN",
        "SIMULATED",
        fill["decision_ts"],
    )
    side = 1 if a["side"] == "LONG" else -1
    cfg = legacy_config(policy)
    pending_stop, previous = None, float(entry)
    rows, actions, gross, exit_fees = [], [], 0.0, 0.0
    spread_cost, slip_cost = (
        fill.get("entry_spread_attribution", 0.0),
        fill.get("entry_slippage_attribution", 0.0),
    )
    equity_curve, peak, max_dd = [], 10000.0, 0.0
    fees = FeeModel(taker_fee_rate=policy.fee_bps / 10000)
    high_close = low_close = entry
    last_mark = entry
    for i in range(1, 13):
        if pending_stop is not None:
            position = replace(position, stop=pending_stop)
            pending_stop = None
        gain_r = min(i * 0.25, 2) if i < 9 else (-1.8 if mode == "favorable_then_gap" else 1)
        price = float(entry) + side * gain_r * abs(float(entry - position.initial_stop))
        minute = int((fill["decision_ts"] - a["setup_ts"]) // MINUTE) + i
        m = monitor(a, minute, price=price)
        # Entire OHLC path is fabricated explicitly; quote remains independently timestamped.
        opening = price if i == 9 and mode == "favorable_then_gap" else previous
        m = replace(
            m,
            bar=bar(
                m.bar.spec,
                m.bar.start,
                opening,
                max(opening, price) + 0.01,
                min(opening, price) - 0.01,
                price,
                interval=MINUTE,
            ),
        )
        event = market_event(m)
        if event.quote is None:
            raise ValueError("FIXTURE_EXECUTABLE_QUOTE_MISSING")
        high_close, low_close = max(high_close, dec(price)), min(low_close, dec(price))
        ep = ExitPolicy(
            atr=a["atr"] if management == "v1" else None,
            target=dec(a["target"]) if a["target"] else None,
            highest_completed_close=high_close,
            lowest_completed_close=low_close,
        )
        action = manage_episode(position, event, ep)
        actions.append(primitive(action))
        last_mark = event.quote.bid if side == 1 else event.quote.ask
        if action.action == "TIGHTEN_STOP":
            pending_stop = action.suggested_stop  # Becomes active only on the next observation.
        if action.action in {"EXIT", "PARTIAL_EXIT"}:
            amount = (
                position.quantity if action.action == "EXIT" else position.quantity * dec(action.fraction)
            )
            reference = None
            if action.reason in {"STOP_GAP", "STOP_BREACHED"}:
                reference = (
                    min(event.candle.open, float(position.stop))
                    if side == 1
                    else max(event.candle.open, float(position.stop))
                )
            execution = exit_price(event, a["side"], cfg, reference)
            if execution is None:
                continue
            actual, mid, spread, slip = execution
            realized = side * (actual - float(entry)) * float(amount)
            fee = fees.calculate_fee(float(amount) * actual)
            gross += realized
            exit_fees += fee
            spread_cost += spread * float(amount)
            slip_cost += slip * float(amount)
            rows.append(
                {
                    "source": "SIMULATED",
                    "quantity": str(amount),
                    "price": actual,
                    "gross_executable_pnl": realized,
                    "fee": fee,
                    "spread_attribution": spread * float(amount),
                    "slippage_attribution": slip * float(amount),
                    "reason": action.reason,
                }
            )
            left = position.quantity - amount
            position = replace(
                position,
                quantity=left,
                status="CLOSED" if left == 0 else "OPEN",
                partial_closes=position.partial_closes + int(left > 0),
            )
            if left == 0:
                equity = 10000 + gross - fill["fee"] - exit_fees
                peak = max(peak, equity)
                max_dd = max(max_dd, (peak - equity) / peak)
                equity_curve.append({"ts": event.decision_ts, "equity": equity})
                break
        equity = (
            10000
            + gross
            - fill["fee"]
            - exit_fees
            + float(position.quantity * dec(side) * (last_mark - entry))
        )
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak)
        equity_curve.append({"ts": event.decision_ts, "equity": equity})
        previous = price
    # The declared next funding settlement is outside this short fixture window.
    # No current-rate snapshot is mislabeled as realized funding.
    funding_known = fill.get("next_funding_ts") is not None and event.decision_ts < fill["next_funding_ts"]
    return {
        "initial_R": fill["initial_R"],
        "gross_executable_pnl": gross,
        "fees": fill["fee"] + exit_fees,
        "funding_cashflow": 0.0 if funding_known else None,
        "funding_status": "NO_SETTLEMENT_DUE_IN_DECLARED_SHORT_FIXTURE_WINDOW"
        if funding_known
        else "UNRESOLVED_SETTLEMENT",
        "net_complete_within_declared_model": funding_known,
        "modeled_net_realized": gross - fill["fee"] - exit_fees,
        "net_label": "MODELED_NET_WITH_DECLARED_COSTS" if funding_known else "MODELED_EX_FUNDING_INCOMPLETE",
        "spread_attribution": spread_cost,
        "slippage_attribution": slip_cost,
        "cost_semantics": "Executable PnL already includes spread/slippage; attributions are not subtracted twice",
        "unrealized_executable_pnl": float(position.quantity * dec(side) * (last_mark - entry)),
        "return_R": (gross - fill["fee"] - exit_fees) / fill["initial_R"] if fill["initial_R"] else None,
        "terminal": position.status,
        "actions": actions,
        "exits": rows,
        "maximum_drawdown_fraction": max_dd,
        "equity_curve": equity_curve,
        "holding_minutes": (event.decision_ts - fill["decision_ts"]) / MINUTE,
        "evaluation_cutoff_open_quantity": str(position.quantity),
        "management_policy": management,
    }


def replay_episode(
    setup: Setup, policy: Policy, path: Path, *, delay=1, fault=None, mode="normal", latency_stress=False
) -> dict:
    a = setup.anchors
    store = SelectorStore(path)
    if a.get("regime_evidence"):
        store.save_regime(a["symbol"], a["regime_evidence"])
    store.create_episode(a, a["setup_ts"] + 1000)
    funnel = ["discovered", "ranked", "setup"]
    observations, triggered = [], None
    for i in range(1, 5):
        m = monitor(a, i)
        episode = advance(store, a["id"], m, policy)
        observations.append({"decision_ts": m.now, **episode["state"]})
        if episode["state"]["trigger_ids"]:
            triggered = i
            funnel.append("triggered")
            break
    if triggered is None:
        return {"id": a["id"], "funnel": funnel + ["NO_FILL"], "reason": "NOT_TRIGGERED"}
    delivered = monitor(a, triggered).now
    event = store.notify_episode(a["id"], delivered, lambda wire: None)
    funnel.append("notification_attempted")
    if fault != "delivery_unknown":
        ack = a["setup_ts"] + delay * MINUTE if latency_stress else delivered + delay * MINUTE
        store.delivery(event, delivered_ts=delivered, acknowledged_ts=ack)
        funnel.extend(["notified_assumption", "acknowledged"])
    response_minute = delay if latency_stress else triggered + delay
    # Every intervening completed minute is replayed; a delayed response cannot erase its price path.
    for minute in range(triggered + 1, response_minute):
        advance(store, a["id"], monitor(a, minute, mode=mode), policy, require_ack=True)
    response = new_post_ack_quote(
        monitor(
            a,
            response_minute,
            fault=fault,
            quote=fault != "missing_quote",
            mode="lost" if mode == "lost" else "normal",
        )
    )
    episode = advance(
        store, a["id"], response, policy, require_ack=True, capital=Capital(10000, 10000, response.now)
    )
    funnel.append("revalidated")
    fill = None
    if episode["state"]["status"] == "ENTRY_ELIGIBLE":
        if a["entry_mode"] == "resting_limit":
            place_resting_limit(store, a["id"], response.now)
            cross = monitor(
                a, response_minute + 1, price=float(a["anchor"]) - (0.04 if a["side"] == "LONG" else -0.04)
            )
            episode = advance(
                store, a["id"], cross, policy, require_ack=True, capital=Capital(10000, 10000, cross.now)
            )
            fill = simulated_fill(store, a["id"], cross, policy)
        else:
            fill = simulated_fill(store, a["id"], response, policy)
    funnel.append("modeled_fill" if fill else "NO_FILL")
    managed = manage_fill(a, fill, policy) if fill else None
    if managed:
        funnel.extend(["managed", "terminal" if managed["terminal"] == "CLOSED" else "open"])
        if managed["terminal"] == "CLOSED":
            store.reservation_status(a["id"], "RELEASED_CONFIRMED", execution_confirmed=True)
    state = store.episode(a["id"])["state"]
    if not managed:
        funnel.append("terminal" if state["status"] in {"CANCELLED", "EXPIRED"} else "open")
    occupied = sum(p["risk"] for p in store.reservations() if p["status"] != "RELEASED_CONFIRMED")
    return {
        "id": a["id"],
        "cluster_id": a["structural_setup_id"],
        "strategy": a["strategy"],
        "source": "OFFLINE_SYNTHETIC",
        "policy_hash": policy.hash,
        "delay_minutes": delay,
        "latency_kind": "END_TO_END_STRESS" if latency_stress else "OWNER_RESPONSE_AFTER_SIMULATED_DELIVERY",
        "funnel": funnel,
        "confirmation_lag_ms": triggered * MINUTE,
        "source_availability": "INJECTED_FAILURE" if fault else "FABRICATED_ADMITTED",
        "fault": fault,
        "quote_freshness_ms": response.now - response.quote.provenance.exchange_event_ts
        if response.quote
        else None,
        "state": state["status"],
        "reasons": state["reasons"],
        "fill": fill,
        "management": managed,
        "occupied_risk": occupied,
        "occupied_risk_peak": max((p["risk"] for p in store.reservations()), default=0),
        "reservation_status": store.reservations(),
        "observations": observations,
        "missed_entry": fill is None,
        "funding_uncertainty": fault == "funding_unknown",
        "delivery_status": store.delivery(event)["delivery"],
        "database": path.name,
    }


def evaluate(policy: Policy, output: Path) -> dict:
    if (output / "episodes.json").exists() or (output / "scan.sqlite").exists():
        raise ValueError("EVALUATION_OUTPUT_EXISTS")
    output.mkdir(parents=True, exist_ok=True)
    store = SelectorStore(output / "scan.sqlite")
    bars = structural_bars(symbols=tuple(sorted(policy.symbols)))
    scan(history(bars, BASE + 304 * STRUCTURE, policy), store, policy)
    snapshot = history(bars, BASE + 305 * STRUCTURE, policy)
    source_path = output / "source_histories.jsonl"
    with source_path.open("w") as stream:
        for b in sorted(bars, key=lambda b: (b.spec.symbol, b.end)):
            stream.write(json.dumps(primitive(b), sort_keys=True, allow_nan=False) + "\n")
    coverage = {
        symbol: {
            id: primitive(snapshot.pipeline.result(symbol, id, len(df) - 1, snapshot.universe.decision_ts))
            for id in FACTORS
        }
        for symbol, df in snapshot.frames.items()
    }
    (output / "factor_coverage.json").write_text(json.dumps(coverage, indent=2, sort_keys=True) + "\n")
    scanning = scan(snapshot, store, policy)
    slate = [Setup(c["anchors"], c["ranking"], tuple(c["vetoes"])) for c in scanning["candidates"]]
    selected, rejected = resolve_setups(slate)
    cfg = legacy_config(policy)
    prior_source_config, prior_source_raw, prior_source_selected = previous_source_scan(snapshot, policy)
    previous_ids = {c.id for c in previous_resolve([legacy_candidate(s) for s in slate], cfg)}
    selected_ids = {s.anchors["id"] for s in selected}
    runs = []
    for s in selected:
        for delay in policy.response_minutes:
            path = output / f"episode-{s.anchors['id'][:12]}-response-{delay}.sqlite"
            runs.append(replay_episode(s, policy, path, delay=delay))
        for delay in policy.latency_stress_minutes:
            path = output / f"episode-{s.anchors['id'][:12]}-stress-{delay}.sqlite"
            runs.append(replay_episode(s, policy, path, delay=delay, latency_stress=True))
    faults = (
        "missing_quote",
        "stale_quote",
        "invalid_authority",
        "source_clock",
        "high_spread",
        "funding_unknown",
        "outage",
        "delivery_unknown",
    )
    baseline = next((s for s in selected if s.anchors["strategy"] == "trend_pullback"), None)
    if baseline:
        for fault in faults:
            runs.append(replay_episode(baseline, policy, output / f"fault-{fault}.sqlite", fault=fault))
        for delay in policy.response_minutes:
            runs.append(
                replay_episode(baseline, policy, output / f"lost-{delay}.sqlite", delay=delay, mode="lost")
            )
    controlled_slates = []
    if baseline:
        a = baseline.anchors
        opposing = Setup(
            {
                **a,
                "id": fingerprint([a["id"], "OPPOSING_SYNTHETIC_HYPOTHESIS"]),
                "side": "SHORT",
                "stop": str(dec(a["anchor"]) + 1),
                "mechanism": "TREND_RETEST",
                "strategy": "breakout_retest",
            },
            baseline.ranking,
        )
        clone = Setup(
            {**a, "id": fingerprint([a["id"], "DUPLICATE_MOMENTUM_REPRESENTATION"])}, baseline.ranking
        )
        for name, cards in [
            ("unresolved_opposing_with_duplicate_momentum", [baseline, clone, opposing]),
            ("vetoed_opponent", [baseline, replace(opposing, vetoes=("STALE_SOURCE",))]),
        ]:
            new_cards, vetoes = resolve_setups(cards)
            old_cards = previous_resolve([legacy_candidate(c) for c in cards], cfg)
            controlled_slates.append(
                {
                    "case": name,
                    "source": "FABRICATED_CONTRADICTORY_SETUP_HYPOTHESES",
                    "common_input_hash": fingerprint(cards),
                    "previous_ids": [c.id for c in old_cards],
                    "v1_ids": [c.anchors["id"] for c in new_cards],
                    "v1_vetoes": vetoes,
                    "economic_pnl": None,
                    "semantics": "Selection safety diagnostic; no fabricated return attribution",
                }
            )
    standard = [
        r
        for r in runs
        if not r.get("fault")
        and r.get("latency_kind") != "END_TO_END_STRESS"
        and "lost-" not in r.get("database", "")
    ]

    def summary(ids):
        items = [r for r in standard if r["id"] in ids]
        managed = [r["management"] for r in items if r["management"]]
        return {
            "episodes": len(ids),
            "response_scenarios": len(items),
            "fills": sum(r["fill"] is not None for r in items),
            "gross_executable_pnl": sum(r["gross_executable_pnl"] for r in managed),
            "fees": sum(r["fees"] for r in managed),
            "funding": sum(r["funding_cashflow"] for r in managed),
            "modeled_net_realized": sum(r["modeled_net_realized"] for r in managed),
            "warning": "Alternative response scenarios are not independent trades or an investable portfolio",
        }

    prior_source_keys = {(c.symbol, c.direction, c.strategy_id) for c in prior_source_selected}
    matched_prior_source_ids = {
        s.anchors["id"]
        for s in slate
        if (s.anchors["symbol"], s.anchors["side"], s.anchors["strategy"]) in prior_source_keys
    }

    # A common frozen filled sample isolates management, with identical entry and quantity.
    exits = [
        {
            "id": r["id"],
            "fill_hash": fingerprint(r["fill"]),
            "v1": r["management"],
            "frozen_stop_only": manage_fill(
                next(s.anchors for s in selected if s.anchors["id"] == r["id"]),
                r["fill"],
                policy,
                management="frozen_stop_only",
            ),
        }
        for r in standard
        if r["fill"] and r["delay_minutes"] == policy.response_minutes[0]
    ]
    entry_filter = []
    for s in selected:
        # Evaluate the actual inherited gate on the same early completed observation.
        m = monitor(s.anchors, 2)
        event = market_event(m)
        if m.funding is None:
            raise ValueError("FIXTURE_FUNDING_MISSING")
        event = replace(
            event, derivatives=DerivativeSnapshot(m.funding.provenance, funding_rate=m.funding.value)
        )
        admission = SourceAdmission(fingerprint(event), cfg.hash, event.decision_ts, ())
        old = previous_gate(
            legacy_candidate(s), event, cfg, [], beta=s.anchors["beta"], source_admission=admission
        )
        entry_filter.append(
            {
                "episode_id": s.anchors["id"],
                "common_observation_hash": fingerprint(event),
                "previous_gate_action": old.action,
                "previous_gate_reasons": list(old.veto_reasons),
                "v1_required_distinct_completed_observations": policy.independent_confirmations,
                "semantics": "Timing diagnostic; common-risk economic comparison uses post-ack replay only",
            }
        )
    funnel = Counter(stage for r in runs for stage in r["funnel"])
    report = {
        "task": "V070-L23-SELECTOR-EVALUATION-01",
        "source": "OFFLINE_SYNTHETIC",
        "transport_attempts": 0,
        "config_hash": policy.hash,
        "threshold_fitting_runs": 0,
        "source_fingerprint": fingerprint(bars),
        "field_history_artifact": source_path.name,
        "field_history_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "factor_coverage_artifact": "factor_coverage.json",
        "unique_structural_episodes": len(slate),
        "source_field_errors": dict(
            Counter(reason for errors in snapshot.errors.values() for reason in errors.values())
        ),
        "universe_hash": snapshot.universe.hash,
        "scan": scanning,
        "funnel": dict(funnel),
        "runs": runs,
        "response_losses": {
            str(d): {
                "clean_scenarios": sum(r["delay_minutes"] == d for r in standard),
                "clean_missed_entries": sum(r["missed_entry"] for r in standard if r["delay_minutes"] == d),
                "injected_lost_region_missed_entries": sum(
                    r["missed_entry"]
                    for r in runs
                    if r["delay_minutes"] == d and r["database"].startswith("lost-")
                ),
            }
            for d in policy.response_minutes
        },
        "rejections": dict(Counter(reason for r in runs for reason in r["reasons"])),
        "selector_comparison": {
            "source_hash_identical": True,
            "cost_hash": fingerprint(cfg.execution),
            "previous": summary(previous_ids),
            "v1": summary(selected_ids),
            "selection_changed_ids": sorted(previous_ids ^ selected_ids),
            "rejected": rejected,
            "controlled_failure_slates": controlled_slates,
            "previous_source_scan": {
                "implementation": "btc_quant_agent.platform.advisory.scan",
                "config_hash": prior_source_config.hash,
                "cost_hash_identical": fingerprint(prior_source_config.execution)
                == fingerprint(cfg.execution),
                "discovery_candidates": primitive(prior_source_raw),
                "selected": primitive(prior_source_selected),
                "matched_common_episode_ids": sorted(matched_prior_source_ids),
                "common_episode_economics": summary(matched_prior_source_ids),
                "unmatched_geometry_economics": None,
                "semantics": "Same three enabled strategies and source history; old factor ranks/regime/setup logic retained. Economics use only matched frozen episode geometries.",
            },
            "semantics": "Actual inherited resolve versus V1 on identical setup cards, with common safe entry/risk/exit logic",
        },
        "entry_filter_comparison": entry_filter,
        "exit_management_comparison": exits,
        "occupancy": {
            "semantics": "Each response is an isolated counterfactual; reservations are real SQLite claims",
            "simultaneous_capacity_evidence": "tests/selection/test_capacity_management_restart.py",
            "endogenous_portfolio_return": None,
        },
        "limitations": [
            "All provider receipts, prices and paths are fabricated; no Alpha or live readiness claim",
            "No retrospective regime oracle, threshold fitting or PRIMARY trial registration",
            "Ranks and model-free scores are not calibrated probabilities",
            "No queue/latency/venue fill proof; strict synthetic top-of-book cross only",
            "No Sharpe or significance claim from dependent synthetic response scenarios",
            "Funding stress is projected; actual missing settlements are not replaced with zero",
            "Open positions are censored at the evaluation cutoff; recommendations do not close user positions",
        ],
    }
    (output / "episodes.json").write_text(
        json.dumps(primitive(report), indent=2, sort_keys=True, allow_nan=False) + "\n"
    )
    rows = "".join(
        f"<tr><td>{html.escape(r['strategy'])}</td><td>{r['delay_minutes']}</td>"
        f"<td>{html.escape(r['latency_kind'])}</td><td>{html.escape(str(r['fault']))}</td>"
        f"<td>{html.escape(r['state'])}</td><td>{'SIMULATED' if r['fill'] else 'NO_FILL'}</td>"
        f"<td>{html.escape(', '.join(r['reasons']))}</td></tr>"
        for r in runs
    )
    chart = "".join(
        f'<rect x="190" y="{i * 24}" width="{n * 8}" height="18" fill="#177f8f"/>'
        f'<text x="0" y="{i * 24 + 14}">{html.escape(k)}: {n}</text>'
        for i, (k, n) in enumerate(funnel.items())
    )
    (output / "episodes.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        "<title>L23 offline episode evaluation</title><style>body{font:15px system-ui;margin:2rem}"
        "td,th{padding:.5rem;border:1px solid #ccc}table{border-collapse:collapse}svg{font:13px system-ui}</style>"
        "<h1>L23 OFFLINE SYNTHETIC evaluation</h1><p>Fabricated receipts. No market Alpha or real-source activation.</p>"
        f'<p>Policy: {policy.hash}</p><svg width="700" height="{len(funnel) * 24}">{chart}</svg>'
        "<table><tr><th>Strategy</th><th>Delay minutes</th><th>Latency kind</th><th>Injected fault</th>"
        "<th>State</th><th>Fill source</th><th>Reasons</th></tr>" + rows + "</table></html>"
    )
    return report
