from __future__ import annotations

import logging
import os
import time
from collections.abc import Sequence
from typing import Any

from ..data.binance import BinancePublicClient
from .alerting import send_market_watch_alert
from .config import MarketWatchConfig, compute_market_watch_config_hash
from .context import apply_benchmark_context_gate, evaluate_benchmark_context
from .derivatives import apply_derivatives_action_gate, evaluate_derivatives_regime
from .domain import (
    MARKET_WATCH_EVIDENCE_VERSION,
    MARKET_WATCH_POLICY_VERSION,
    BreakoutState,
    ConfidenceBand,
    DerivativesMetrics,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    GridDecision,
    GridPlan,
    MarketSnapshot,
    MarketWatchAlert,
    PlaybookType,
    PriceMetrics,
    RelativePerformance,
    ScanHealth,
    ShadowFillStatus,
    SignalLifecycleState,
    SymbolAssessment,
    extract_setup_key,
    extract_signal_identity,
)
from .entry_quality import calculate_net_risk_reward, evaluate_entry_quality, evaluate_exhaustion
from .grid_policy import evaluate_grid_policy
from .lifecycle import advance_lifecycle_state
from .playbooks import (
    evaluate_breakout_retest,
    evaluate_failed_breakout,
    evaluate_timeframe_alignment,
    evaluate_trend_pullback,
    evaluate_volatility_expansion,
)
from .ranking import (
    calculate_opportunity_score,
    check_fatal_vetoes,
    compute_relative_performances,
)
from .snapshot import compute_snapshot_hash, compute_timeframe_snapshot
from .state import (
    MarketWatchStateStore,
    compute_decision_fingerprint,
    evaluate_alert_emission,
)

logger = logging.getLogger(__name__)


class MarketWatchScanner:
    """Multi-asset operational scanner with PIT-safe snapshots and failure isolation."""

    def __init__(self, config: MarketWatchConfig, client: BinancePublicClient, store: MarketWatchStateStore) -> None:
        self.config = config
        self.client = client
        self.store = store

    def collect_symbol_snapshot(self, symbol: str, now_ms: int) -> tuple[MarketSnapshot | None, ScanHealth, tuple[str, ...]]:
        """Collect market snapshot for one symbol with robust degradation handling."""
        collection_started_at_ms = int(time.time() * 1000)
        symbol = symbol.upper()
        health_reasons: list[str] = []
        health = ScanHealth.OK

        # 1. Core klines (15m, 1h, 4h) - Failure here is FAILED
        try:
            raw_15m = self.client.klines(symbol, "15m", 120)
            raw_1h = self.client.klines(symbol, "1h", 120)
            raw_4h = self.client.klines(symbol, "4h", 120)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Core candle retrieval failed for %s: %s", symbol, exc)
            return None, ScanHealth.FAILED, (f"CORE_CANDLE_ERROR: {exc}",)

        if len(raw_15m) < 30 or len(raw_1h) < 30 or len(raw_4h) < 30:
            return None, ScanHealth.FAILED, ("INSUFFICIENT_CANDLE_HISTORY",)

        # 2. Derivatives collection - Failure here is DEGRADED
        mark_price = None
        index_price = None
        funding_rate = None
        funding_time_ms = None
        open_interest = None
        open_interest_time_ms = None
        oi_1h_change = None
        oi_4h_change = None
        oi_12h_change = None
        taker_ratio = None
        taker_time_ms = None
        basis_rate = None
        basis_time_ms = None
        long_short_ratio = None
        long_short_time_ms = None
        top_pos_ratio = None
        top_acc_ratio = None
        order_book_imbalance = None
        spread_bps = None
        field_avail: dict[str, bool] = {}
        endpoint_errs: dict[str, str] = {}

        candle_avail_timestamps: list[int] = []
        for _tf_name, raw_tf in (("15m", raw_15m), ("1h", raw_1h), ("4h", raw_4h)):
            if raw_tf:
                last_c = raw_tf[-1]
                avail = last_c.available_at_ms if last_c.available_at_ms is not None else last_c.close_time_ms
                if avail and avail > 0:
                    candle_avail_timestamps.append(int(avail))

        deriv_observed_at_ms: int | None = None
        try:
            deriv_collection = self.client.collect_derivatives(symbol, include_order_book=True)
            snap = deriv_collection.snapshot
            deriv_observed_at_ms = snap.observed_at_ms
            mark_price = snap.mark_price
            index_price = snap.index_price
            funding_rate = snap.funding_rate
            funding_time_ms = snap.funding_time_ms
            open_interest = snap.open_interest
            open_interest_time_ms = snap.open_interest_time_ms
            oi_1h_change = snap.open_interest_change_pct
            taker_ratio = snap.taker_buy_sell_ratio
            taker_time_ms = snap.taker_time_ms
            basis_rate = snap.basis_rate
            basis_time_ms = snap.basis_time_ms
            long_short_ratio = snap.long_short_account_ratio
            long_short_time_ms = snap.long_short_time_ms
            order_book_imbalance = snap.order_book_imbalance
            spread_bps = snap.spread_bps
            field_avail = dict(deriv_collection.field_availability)
            if deriv_collection.endpoint_errors:
                health = ScanHealth.DEGRADED
                for ep, err in deriv_collection.endpoint_errors.items():
                    health_reasons.append(f"DERIVATIVES_PARTIAL_ERROR_{ep}: {err}")
                endpoint_errs = dict(deriv_collection.endpoint_errors)
        except Exception as exc:  # noqa: BLE001
            health = ScanHealth.DEGRADED
            health_reasons.append(f"DERIVATIVES_ERROR: {exc}")
            endpoint_errs = {"all": str(exc)}

        # Optional multi-horizon OI history query
        oi_hist_receipt_ms: int | None = None
        try:
            oi_hist = self.client._optional_get(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": "1h", "limit": 13},
            )
            oi_hist_receipt_ms = int(time.time() * 1000)
            if oi_hist and len(oi_hist) >= 2:
                curr_oi = float(oi_hist[-1].get("sumOpenInterest", 0.0))
                if len(oi_hist) >= 2 and oi_1h_change is None:
                    p1 = float(oi_hist[-2].get("sumOpenInterest", 0.0))
                    oi_1h_change = (curr_oi / p1 - 1.0) if p1 > 0 else None
                if len(oi_hist) >= 5:
                    p4 = float(oi_hist[-5].get("sumOpenInterest", 0.0))
                    oi_4h_change = (curr_oi / p4 - 1.0) if p4 > 0 else None
                if len(oi_hist) >= 13:
                    p12 = float(oi_hist[-13].get("sumOpenInterest", 0.0))
                    oi_12h_change = (curr_oi / p12 - 1.0) if p12 > 0 else None
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            logger.debug("OI history parse failed for %s: %s", symbol, exc)

        # Optional top trader position/account ratio queries
        top_pos_receipt_ms: int | None = None
        try:
            top_pos_payload = self.client._optional_get(
                "/futures/data/topLongShortPositionRatio",
                {"symbol": symbol, "period": "1h", "limit": 1},
            )
            top_pos_receipt_ms = int(time.time() * 1000)
            if top_pos_payload and isinstance(top_pos_payload, list) and "longShortRatio" in top_pos_payload[-1]:
                top_pos_ratio = float(top_pos_payload[-1]["longShortRatio"])
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            logger.debug("Top pos ratio parse failed for %s: %s", symbol, exc)

        top_acc_receipt_ms: int | None = None
        try:
            top_acc_payload = self.client._optional_get(
                "/futures/data/topLongShortAccountRatio",
                {"symbol": symbol, "period": "1h", "limit": 1},
            )
            top_acc_receipt_ms = int(time.time() * 1000)
            if top_acc_payload and isinstance(top_acc_payload, list) and "longShortRatio" in top_acc_payload[-1]:
                top_acc_ratio = float(top_acc_payload[-1]["longShortRatio"])
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            logger.debug("Top acc ratio parse failed for %s: %s", symbol, exc)

        # Exchange time and staleness check
        exchange_time_ms = now_ms
        server_time_receipt_ms: int | None = None
        try:
            val = self.client.server_time_ms()
            server_time_receipt_ms = int(time.time() * 1000)
            if isinstance(val, (int, float)):
                exchange_time_ms = int(val)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Failed to fetch server time for %s: %s", symbol, exc)

        if (
            raw_15m
            and isinstance(raw_15m[-1].close_time_ms, (int, float))
            and exchange_time_ms - int(raw_15m[-1].close_time_ms) > 3_600_000
        ):
            health = ScanHealth.DEGRADED
            health_reasons.append("STALE_CANDLE_DATA")

        # 3. 24hr ticker for price metrics
        change_24h = 0.0
        high_24h = raw_15m[-1].close
        low_24h = raw_15m[-1].close
        quote_vol_24h = 0.0
        ticker_receipt_ms: int | None = None
        try:
            ticker = self.client._optional_get("/fapi/v1/ticker/24hr", {"symbol": symbol})
            ticker_receipt_ms = int(time.time() * 1000)
            if ticker and isinstance(ticker, dict):
                change_24h = float(ticker.get("priceChangePercent", 0.0)) / 100.0
                high_24h = float(ticker.get("highPrice", high_24h))
                low_24h = float(ticker.get("lowPrice", low_24h))
                quote_vol_24h = float(ticker.get("quoteVolume", 0.0))
        except (KeyError, ValueError, TypeError) as exc:
            logger.debug("24hr ticker parse failed for %s: %s", symbol, exc)

        last_price = raw_15m[-1].close
        price_metrics = PriceMetrics(
            last_price=last_price,
            mark_price=mark_price,
            change_24h_pct=change_24h,
            high_24h=high_24h,
            low_24h=low_24h,
            quote_volume_24h=quote_vol_24h,
        )

        # 4. Compute TimeframeSnapshots strictly on closed candles
        tf_15m = compute_timeframe_snapshot("15m", raw_15m, None, self.config)
        tf_1h = compute_timeframe_snapshot("1h", raw_1h, None, self.config)
        tf_4h = compute_timeframe_snapshot("4h", raw_4h, None, self.config)

        # 5. Assemble DerivativesMetrics
        basis_bps = (basis_rate * 10_000.0) if basis_rate is not None else None
        deriv_metrics = DerivativesMetrics(
            mark_price=mark_price,
            index_price=index_price,
            funding_rate=funding_rate,
            funding_time_ms=funding_time_ms,
            current_open_interest=open_interest,
            open_interest_time_ms=open_interest_time_ms,
            oi_1h_change=oi_1h_change,
            oi_4h_change=oi_4h_change,
            oi_12h_change=oi_12h_change,
            global_account_long_short_ratio=long_short_ratio,
            long_short_time_ms=long_short_time_ms,
            top_trader_position_ratio=top_pos_ratio,
            top_trader_account_ratio=top_acc_ratio,
            taker_buy_sell_ratio=taker_ratio,
            taker_time_ms=taker_time_ms,
            basis_rate=basis_rate,
            basis_bps=basis_bps,
            basis_time_ms=basis_time_ms,
            spread_bps=spread_bps,
            order_book_imbalance=order_book_imbalance,
            field_availability=field_avail,
            endpoint_errors=endpoint_errs,
        )

        # Evaluate derivatives regime
        d_regime, d_reasons, d_risks = evaluate_derivatives_regime(
            price_change_1h_pct=tf_1h.roc,
            derivatives=deriv_metrics,
            config=self.config,
        )
        deriv_metrics = DerivativesMetrics(
            mark_price=deriv_metrics.mark_price,
            index_price=deriv_metrics.index_price,
            funding_rate=deriv_metrics.funding_rate,
            funding_time_ms=deriv_metrics.funding_time_ms,
            current_open_interest=deriv_metrics.current_open_interest,
            open_interest_time_ms=deriv_metrics.open_interest_time_ms,
            oi_1h_change=deriv_metrics.oi_1h_change,
            oi_4h_change=deriv_metrics.oi_4h_change,
            oi_12h_change=deriv_metrics.oi_12h_change,
            global_account_long_short_ratio=deriv_metrics.global_account_long_short_ratio,
            long_short_time_ms=deriv_metrics.long_short_time_ms,
            top_trader_position_ratio=deriv_metrics.top_trader_position_ratio,
            top_trader_account_ratio=deriv_metrics.top_trader_account_ratio,
            taker_buy_sell_ratio=deriv_metrics.taker_buy_sell_ratio,
            taker_time_ms=deriv_metrics.taker_time_ms,
            basis_rate=deriv_metrics.basis_rate,
            basis_bps=deriv_metrics.basis_bps,
            basis_time_ms=deriv_metrics.basis_time_ms,
            spread_bps=deriv_metrics.spread_bps,
            order_book_imbalance=deriv_metrics.order_book_imbalance,
            field_availability=deriv_metrics.field_availability,
            endpoint_errors=deriv_metrics.endpoint_errors,
            regime=d_regime,
            reasons=d_reasons + d_risks,
        )

        # Strict PIT receipt semantics (R2.1-03):
        # Include latest Candle.available_at_ms for every timeframe,
        # DerivativeCollection.observed_at_ms, and receipt timestamps of all queries.
        # Do not confuse exchange event timestamps with local availability.
        consumed_availability = [
            *candle_avail_timestamps,
            *(
                [int(t)]
                for t in (
                    deriv_observed_at_ms,
                    oi_hist_receipt_ms,
                    top_pos_receipt_ms,
                    top_acc_receipt_ms,
                    ticker_receipt_ms,
                    server_time_receipt_ms,
                )
                if isinstance(t, (int, float)) and t > 0
            ),
        ]
        flat_availability: list[int] = []
        for item in consumed_availability:
            if isinstance(item, list):
                flat_availability.extend(item)
            elif isinstance(item, (int, float)) and item > 0:
                flat_availability.append(int(item))

        collection_completed_ms = int(time.time() * 1000)
        observed_at_ms = max([collection_started_at_ms, *flat_availability])
        decision_time_ms = max(collection_completed_ms, now_ms, observed_at_ms, *flat_availability)

        snap_hash = compute_snapshot_hash(
            symbol=symbol,
            decision_time_ms=decision_time_ms,
            price=price_metrics,
            tf_15m=tf_15m,
            tf_1h=tf_1h,
            tf_4h=tf_4h,
            derivatives=deriv_metrics,
        )

        snapshot = MarketSnapshot(
            symbol=symbol,
            decision_time_ms=decision_time_ms,
            observed_at_ms=observed_at_ms,
            exchange_time_ms=exchange_time_ms,
            collection_started_at_ms=collection_started_at_ms,
            collection_completed_at_ms=collection_completed_ms,
            price=price_metrics,
            tf_15m=tf_15m,
            tf_1h=tf_1h,
            tf_4h=tf_4h,
            derivatives=deriv_metrics,
            snapshot_hash=snap_hash,
            health=health,
            health_reasons=tuple(health_reasons),
        )

        return snapshot, health, tuple(health_reasons)

    def assess_symbol(
        self,
        snapshot: MarketSnapshot,
        prev_state: dict[str, Any] | None,
        btc_snapshot: MarketSnapshot | None,
        eth_snapshot: MarketSnapshot | None,
        relative_perf: RelativePerformance | None,
    ) -> SymbolAssessment:
        """Evaluate directional policy, grid policy, ranking score, and state transitions."""
        symbol = snapshot.symbol
        tf_15m = snapshot.tf_15m
        tf_1h = snapshot.tf_1h
        tf_4h = snapshot.tf_4h
        derivatives = snapshot.derivatives

        # 1. Multi-timeframe alignment
        _alignment_status, tf_reasons = evaluate_timeframe_alignment(tf_4h, tf_1h, tf_15m)

        # 2. Exhaustion & overextension filter
        exhaustion = evaluate_exhaustion(tf_15m, derivatives, self.config)

        # 3. Benchmark Context & evaluation
        bench_context, bench_reasons, bench_risks = evaluate_benchmark_context(
            btc_snapshot=btc_snapshot,
            eth_snapshot=eth_snapshot,
            config=self.config,
        )

        # 4. Playbook evaluation
        pb_candidate = (
            evaluate_trend_pullback(
                tf_4h=tf_4h,
                tf_1h=tf_1h,
                tf_15m=tf_15m,
                derivatives=derivatives,
                exhaustion=exhaustion,
                config=self.config,
            )
            or evaluate_breakout_retest(
                tf_1h=tf_1h,
                tf_15m=tf_15m,
                derivatives=derivatives,
                exhaustion=exhaustion,
                config=self.config,
                prev_state=prev_state,
            )
            or evaluate_failed_breakout(
                tf_1h=tf_1h,
                tf_15m=tf_15m,
                derivatives=derivatives,
                config=self.config,
            )
            or evaluate_volatility_expansion(
                tf_1h=tf_1h,
                tf_15m=tf_15m,
                derivatives=derivatives,
                exhaustion=exhaustion,
                config=self.config,
            )
        )

        if pb_candidate is not None:
            raw_decision = pb_candidate["decision"]
            setup = pb_candidate["setup"]
            entry_low = pb_candidate["entry_low"]
            entry_high = pb_candidate["entry_high"]
            stop_loss = pb_candidate["stop_loss"]
            tp1 = pb_candidate["take_profit_1"]
            tp2 = pb_candidate["take_profit_2"]
            invalidation = pb_candidate["invalidation"]
            confidence = pb_candidate["confidence"]
            bo_state = pb_candidate.get("breakout_state", BreakoutState.NONE)
            bo_level = pb_candidate.get("breakout_level")
            bo_dir = pb_candidate.get("breakout_direction")
            bo_bar_end_ms = pb_candidate.get("breakout_bar_end_ms")
            reasons = list(pb_candidate["reasons"]) + tf_reasons + list(bench_reasons)
            risks = list(pb_candidate["risks"]) + list(bench_risks)
        else:
            raw_decision = DirectionalDecision.WAIT
            setup = PlaybookType.NO_TRADE
            entry_low = 0.0
            entry_high = 0.0
            stop_loss = 0.0
            tp1 = 0.0
            tp2 = 0.0
            invalidation = 0.0
            confidence = ConfidenceBand.LOW
            bo_state = BreakoutState.NONE
            bo_level = None
            bo_dir = None
            bo_bar_end_ms = None
            reasons = ["NO_CONFIRMED_PLAYBOOK_CANDIDATE"] + tf_reasons
            risks = list(bench_risks)

        # 5. Friction and Net Risk/Reward
        entry_mid = (entry_low + entry_high) / 2.0 if (entry_low > 0 and entry_high > 0) else tf_15m.close
        gross_rr, net_rr = calculate_net_risk_reward(
            entry_price=entry_mid,
            stop_loss=stop_loss,
            take_profit=tp1,
            direction=raw_decision,
            config=self.config,
            funding_rate=derivatives.funding_rate,
        )

        # 6. Entry Quality
        entry_quality, eq_reasons, eq_risks = evaluate_entry_quality(
            direction=raw_decision,
            exhaustion=exhaustion,
            net_rr=net_rr,
            tf_15m=tf_15m,
            derivatives=derivatives,
            config=self.config,
        )
        reasons.extend(eq_reasons)
        risks.extend(eq_risks)

        # Gating: Actionable LONG/SHORT requires EntryQuality >= min_action_entry_quality
        min_quality = EntryQuality(self.config.min_action_entry_quality)
        quality_rank = {
            EntryQuality.EXCELLENT: 3,
            EntryQuality.GOOD: 2,
            EntryQuality.MARGINAL: 1,
            EntryQuality.POOR: 0,
        }
        if raw_decision != DirectionalDecision.WAIT and quality_rank[entry_quality] < quality_rank[min_quality]:
            raw_decision = DirectionalDecision.WAIT
            reasons.append("ENTRY_QUALITY_BELOW_MINIMUM_WAIT")

        # 7. Benchmark Context Gate (e.g. BTC risk-off shock)
        gated_decision, bg_reasons, bg_risks = apply_benchmark_context_gate(
            symbol=symbol,
            decision=raw_decision,
            benchmark_context=bench_context,
            relative_perf=relative_perf,
            entry_quality=entry_quality,
            net_rr=net_rr,
            config=self.config,
        )
        reasons.extend(bg_reasons)
        risks.extend(bg_risks)

        # 7b. Derivatives Action Gate (R2)
        gated_decision, deriv_reasons, deriv_risks = apply_derivatives_action_gate(
            decision=gated_decision,
            derivatives=derivatives,
            config=self.config,
        )
        reasons.extend(deriv_reasons)
        risks.extend(deriv_risks)

        # 8. Fatal Vetoes (Enforced before ranking)
        has_fatal_veto, fatal_reasons = check_fatal_vetoes(
            decision=gated_decision,
            exhaustion=exhaustion,
            net_rr=net_rr,
            tf_4h=tf_4h,
            derivatives=derivatives,
            benchmark_context=bench_context,
            config=self.config,
        )
        if has_fatal_veto:
            gated_decision = DirectionalDecision.WAIT
            reasons.extend(fatal_reasons)

        # 9. Opportunity Score
        opp_score = calculate_opportunity_score(
            decision=gated_decision,
            tf_1h=tf_1h,
            tf_15m=tf_15m,
            entry_quality=entry_quality,
            derivatives=derivatives,
            exhaustion=exhaustion,
            relative_perf=relative_perf,
            benchmark_context=bench_context,
            net_rr=net_rr,
            has_fatal_veto=has_fatal_veto,
            config=self.config,
        )

        directional_plan = DirectionalPlan(
            symbol=symbol,
            decision=gated_decision,
            setup=setup,
            regime=tf_1h.regime,
            entry_quality=entry_quality,
            entry_low=round(entry_low, 4),
            entry_high=round(entry_high, 4),
            stop_loss=round(stop_loss, 4),
            take_profit_1=round(tp1, 4),
            take_profit_2=round(tp2, 4),
            invalidation_level=round(invalidation, 4),
            gross_rr=gross_rr,
            net_rr=net_rr,
            confidence_band=confidence,
            opportunity_score=opp_score,
            reason_codes=tuple(sorted(set(reasons))),
            risk_codes=tuple(sorted(set(risks))),
            derivatives_regime=derivatives.regime,
            benchmark_context=bench_context,
            breakout_state=bo_state,
            breakout_level=bo_level,
            breakout_direction=bo_dir,
            breakout_bar_end_ms=bo_bar_end_ms,
        )

        # 10. Grid Policy
        prev_grid = None
        if prev_state is not None and prev_state.get("grid_decision"):
            prev_lb = prev_state.get("grid_lower_bound")
            if prev_lb is None:
                prev_lb = prev_state.get("recent_support")
            prev_ub = prev_state.get("grid_upper_bound")
            if prev_ub is None:
                prev_ub = prev_state.get("recent_resistance")
            prev_grid = GridPlan(
                symbol=symbol,
                decision=GridDecision(prev_state["grid_decision"]),
                lower_bound=prev_lb,
                upper_bound=prev_ub,
            )
        grid_plan = evaluate_grid_policy(
            symbol=symbol,
            tf_1h=tf_1h,
            tf_15m=tf_15m,
            derivatives=derivatives,
            prev_grid=prev_grid,
            config=self.config,
        )

        # 11. Lifecycle State (Keyed by deterministic signal_identity)
        setup_key = extract_setup_key(symbol, directional_plan, snapshot)
        intended_dir = setup_key.split(":")[2] if ":" in setup_key else "NONE"

        prev_lifecycle = (
            SignalLifecycleState(prev_state["lifecycle_state"])
            if (prev_state and prev_state.get("lifecycle_state"))
            else None
        )
        current_bar_end = tf_15m.closed_bar_end_time_ms
        prev_setup_key = prev_state.get("setup_key") if prev_state else None
        prev_instance_started = prev_state.get("setup_instance_started_bar_end_ms") if prev_state else None
        is_same_setup = bool(
            prev_setup_key is not None
            and prev_setup_key == setup_key
            and str(setup.value) != "NO_TRADE"
            and prev_lifecycle not in (SignalLifecycleState.INVALIDATED, SignalLifecycleState.EXPIRED, None)
        )
        if is_same_setup:
            instance_started_ms = prev_instance_started or current_bar_end
        else:
            instance_started_ms = current_bar_end

        sig_id = extract_signal_identity(symbol, directional_plan, snapshot, instance_started_ms)
        prev_sig_id = prev_state.get("signal_identity") if prev_state else None
        prev_bo_level = prev_state.get("breakout_level") if prev_state else None
        curr_bo_level = directional_plan.breakout_level
        bo_level_changed = (
            curr_bo_level is not None
            and prev_bo_level is not None
            and round(curr_bo_level, 2) != round(prev_bo_level, 2)
        )
        prev_bo_dir = prev_state.get("breakout_direction") if prev_state else None
        dir_changed = (
            prev_bo_dir is not None
            and intended_dir not in ("NONE", "")
            and prev_bo_dir != intended_dir
        )

        is_same_signal = (
            prev_sig_id is not None
            and prev_sig_id == sig_id
            and not bo_level_changed
            and not dir_changed
            and str(setup.value) != "NO_TRADE"
        )
        if is_same_signal and prev_state and prev_state.get("created_bar_end_ms"):
            created_bar_end = prev_state["created_bar_end_ms"]
            if current_bar_end >= created_bar_end:
                age_bars = max(0, int((current_bar_end - created_bar_end) / (15 * 60 * 1000)))
            else:
                age_bars = 0
        else:
            created_bar_end = current_bar_end
            age_bars = 0

        has_setup = (setup != PlaybookType.NO_TRADE)
        is_near_ready = (bo_state == BreakoutState.BREAKOUT_CONFIRMED) or (
            has_setup and raw_decision != DirectionalDecision.WAIT
        )

        is_invalid = False
        if (
            prev_lifecycle in (SignalLifecycleState.ARMED, SignalLifecycleState.TRIGGERED)
            and is_same_signal
            and gated_decision == DirectionalDecision.WAIT
            and not is_near_ready
        ):
            is_invalid = True

        lifecycle = advance_lifecycle_state(
            previous_state=prev_lifecycle if is_same_signal else None,
            decision=gated_decision,
            entry_quality=entry_quality,
            is_invalidated=is_invalid,
            has_setup=has_setup,
            is_near_ready=is_near_ready,
            age_bars=age_bars,
            max_age_bars=self.config.thresholds.max_signal_age_bars,
        )

        cfg_hash = compute_market_watch_config_hash(self.config)

        # Temporary assessment to compute stable fingerprint
        temp_assessment = SymbolAssessment(
            symbol=symbol,
            snapshot=snapshot,
            directional=directional_plan,
            grid=grid_plan,
            opportunity_score=opp_score,
            relative_performance=relative_perf,
            exhaustion=exhaustion,
            rank=0,
            veto_reasons=fatal_reasons,
            alert_fingerprint="",
            lifecycle_state=lifecycle,
            policy_version=MARKET_WATCH_POLICY_VERSION,
            config_hash=cfg_hash,
            signal_identity=sig_id,
            setup_key=setup_key,
        )
        fp = compute_decision_fingerprint(temp_assessment, self.config)

        return SymbolAssessment(
            symbol=symbol,
            snapshot=snapshot,
            directional=directional_plan,
            grid=grid_plan,
            opportunity_score=opp_score,
            relative_performance=relative_perf,
            exhaustion=exhaustion,
            rank=0,
            veto_reasons=fatal_reasons,
            alert_fingerprint=fp,
            lifecycle_state=lifecycle,
            policy_version=MARKET_WATCH_POLICY_VERSION,
            config_hash=cfg_hash,
            signal_identity=sig_id,
            setup_key=setup_key,
        )

    def _record_shadow_observations_if_needed(self, a: SymbolAssessment, now_ms: int) -> None:
        prev_st = self.store.get_symbol_state(a.symbol) or {}
        prev_armed_id = prev_st.get("last_shadow_armed_signal_id")
        prev_triggered_id = prev_st.get("last_shadow_triggered_signal_id")
        sig_id = a.signal_identity or extract_signal_identity(a.symbol, a.directional)

        # 1. ARMED shadow observation (SETUP_ARMED) - R2.1-01
        # ARMED and TRIGGERED must not share one dedupe marker.
        if a.lifecycle_state == SignalLifecycleState.ARMED:
            if prev_armed_id != sig_id:
                entry_low = a.directional.entry_low if a.directional.entry_low > 0.0 else a.snapshot.price.last_price
                entry_high = a.directional.entry_high if a.directional.entry_high > 0.0 else a.snapshot.price.last_price
                if entry_low > entry_high:
                    entry_low, entry_high = entry_high, entry_low
                entry_p = entry_high if a.directional.decision == DirectionalDecision.LONG else (
                    entry_low if a.directional.decision == DirectionalDecision.SHORT else a.snapshot.price.last_price
                )
                entry_bars = self.config.thresholds.entry_window_bars
                sig_time = a.snapshot.decision_time_ms
                entry_win_end = sig_time + (entry_bars * 15 * 60 * 1000)

                self.store.record_shadow_observation(
                    timestamp_ms=sig_time,
                    symbol=a.symbol,
                    snapshot_hash=a.snapshot.snapshot_hash,
                    agent_decision=str(a.directional.decision),
                    agent_setup=str(a.directional.setup),
                    entry_quality=str(a.directional.entry_quality),
                    reason_codes=list(a.directional.reason_codes),
                    policy_version=a.policy_version,
                    config_hash=a.config_hash,
                    entry_price=entry_p,
                    stop_loss=a.directional.stop_loss,
                    tp1=a.directional.take_profit_1,
                    tp2=a.directional.take_profit_2,
                    direction=str(a.directional.decision),
                    observation_type="SETUP_ARMED",
                    signal_identity=sig_id,
                    setup_key=a.setup_key,
                    evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
                    entry_window_start_ms=sig_time,
                    signal_time_ms=sig_time,
                    entry_zone_low=entry_low,
                    entry_zone_high=entry_high,
                    entry_window_bars=entry_bars,
                    entry_window_end_ms=entry_win_end,
                    fill_status=ShadowFillStatus.WAITING_FOR_FILL.value,
                )
                self.store.set_last_shadow_signal_ids(a.symbol, armed_id=sig_id)
                self.store.set_last_shadow_recorded_state(a.symbol, "ARMED")

        # 2. TRIGGERED shadow observation (ACTIONABLE_TRIGGERED) - R2.1-01
        # ARMED WAIT observations must not suppress later actionable TRIGGERED records.
        # A TRIGGERED LONG/SHORT must have exactly one eligible shadow observation.
        elif a.lifecycle_state == SignalLifecycleState.TRIGGERED and a.directional.decision in (DirectionalDecision.LONG, DirectionalDecision.SHORT):
            if prev_triggered_id != sig_id:
                entry_low = a.directional.entry_low if a.directional.entry_low > 0.0 else a.snapshot.price.last_price
                entry_high = a.directional.entry_high if a.directional.entry_high > 0.0 else a.snapshot.price.last_price
                if entry_low > entry_high:
                    entry_low, entry_high = entry_high, entry_low
                entry_p = entry_high if a.directional.decision == DirectionalDecision.LONG else (
                    entry_low if a.directional.decision == DirectionalDecision.SHORT else a.snapshot.price.last_price
                )
                entry_bars = self.config.thresholds.entry_window_bars
                sig_time = a.snapshot.decision_time_ms
                entry_win_end = sig_time + (entry_bars * 15 * 60 * 1000)

                self.store.record_shadow_observation(
                    timestamp_ms=sig_time,
                    symbol=a.symbol,
                    snapshot_hash=a.snapshot.snapshot_hash,
                    agent_decision=str(a.directional.decision),
                    agent_setup=str(a.directional.setup),
                    entry_quality=str(a.directional.entry_quality),
                    reason_codes=list(a.directional.reason_codes),
                    policy_version=a.policy_version,
                    config_hash=a.config_hash,
                    entry_price=entry_p,
                    stop_loss=a.directional.stop_loss,
                    tp1=a.directional.take_profit_1,
                    tp2=a.directional.take_profit_2,
                    direction=str(a.directional.decision),
                    observation_type="ACTIONABLE_TRIGGERED",
                    signal_identity=sig_id,
                    setup_key=a.setup_key,
                    evidence_version=MARKET_WATCH_EVIDENCE_VERSION,
                    entry_window_start_ms=sig_time,
                    signal_time_ms=sig_time,
                    entry_zone_low=entry_low,
                    entry_zone_high=entry_high,
                    entry_window_bars=entry_bars,
                    entry_window_end_ms=entry_win_end,
                    fill_status=ShadowFillStatus.WAITING_FOR_FILL.value,
                )
                self.store.set_last_shadow_signal_ids(a.symbol, triggered_id=sig_id)
                self.store.set_last_shadow_recorded_state(a.symbol, "TRIGGERED")

        elif (
            a.lifecycle_state in (SignalLifecycleState.CANDIDATE, SignalLifecycleState.INVALIDATED, SignalLifecycleState.EXPIRED)
            and a.directional.setup == PlaybookType.NO_TRADE
            and (prev_armed_id or prev_triggered_id)
        ):
            self.store.set_last_shadow_signal_ids(a.symbol, armed_id="", triggered_id="")
            self.store.set_last_shadow_recorded_state(a.symbol, "")

    def scan_universe(
        self,
        symbols: Sequence[str] | None = None,
        notify: bool = False,
    ) -> tuple[list[SymbolAssessment], list[MarketWatchAlert]]:
        """Run universe scan with symbol-level failure isolation and state continuity."""
        target_symbols = list(symbols or self.config.symbols)
        now_ms = int(time.time() * 1000)

        # Always include benchmark symbols (BTC, ETH) for cross-asset relative performance and gates
        benchmarks_needed = [b for b in ("BTCUSDT", "ETHUSDT") if b not in target_symbols]
        all_symbols_to_collect = target_symbols + benchmarks_needed

        # 1. Collect snapshots across universe with failure isolation
        snapshots: dict[str, MarketSnapshot] = {}
        for s in all_symbols_to_collect:
            snap, _health, errors = self.collect_symbol_snapshot(s, now_ms)
            if snap is not None:
                snapshots[s] = snap
            else:
                logger.error("Symbol %s collection failed completely: %s", s, errors)

        if not snapshots:
            logger.warning("No symbol snapshots successfully collected.")
            return [], []

        # 2. Compute cross-asset relative performance
        rel_perfs = compute_relative_performances(snapshots, self.config)

        # 3. Retrieve benchmark snapshots
        btc_snap = snapshots.get("BTCUSDT")
        eth_snap = snapshots.get("ETHUSDT")

        # 4. Assess target symbols
        assessments: list[SymbolAssessment] = []
        for s in target_symbols:
            snap = snapshots.get(s)
            if snap is None:
                continue
            prev_st = self.store.get_symbol_state(s)
            item = self.assess_symbol(
                snapshot=snap,
                prev_state=prev_st,
                btc_snapshot=btc_snap,
                eth_snapshot=eth_snap,
                relative_perf=rel_perfs.get(s),
            )
            assessments.append(item)

        # 5. Rank assessments by opportunity score descending
        assessments.sort(key=lambda a: a.opportunity_score, reverse=True)
        ranked_assessments: list[SymbolAssessment] = []
        for rank_num, a in enumerate(assessments, 1):
            ranked_assessments.append(
                SymbolAssessment(
                    symbol=a.symbol,
                    snapshot=a.snapshot,
                    directional=a.directional,
                    grid=a.grid,
                    opportunity_score=a.opportunity_score,
                    relative_performance=a.relative_performance,
                    exhaustion=a.exhaustion,
                    rank=rank_num,
                    veto_reasons=a.veto_reasons,
                    alert_fingerprint=a.alert_fingerprint,
                    lifecycle_state=a.lifecycle_state,
                    policy_version=a.policy_version,
                    config_hash=a.config_hash,
                    signal_identity=a.signal_identity,
                    setup_key=a.setup_key,
                )
            )

        # 6. Evaluate alerts based on state changes & priority
        alerts_to_send: list[MarketWatchAlert] = []
        webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
        secret = os.getenv("FEISHU_WEBHOOK_SECRET")

        for a in ranked_assessments:
            prev_st = self.store.get_symbol_state(a.symbol) or {}
            self._record_shadow_observations_if_needed(a, now_ms)

            emit, severity, _reasons = evaluate_alert_emission(a, prev_st, self.config)

            alert_sent = False
            if emit and len(alerts_to_send) < self.config.max_alert_symbols:
                alert = MarketWatchAlert(
                    symbol=a.symbol,
                    severity=severity,
                    title=f"{a.symbol} {a.directional.decision.value}",
                    directional=a.directional,
                    grid=a.grid,
                    fingerprint=a.alert_fingerprint,
                    evidence=a.directional.reason_codes,
                    risks=a.directional.risk_codes,
                    alert_time_ms=now_ms,
                    last_price=a.snapshot.price.last_price,
                    change_24h_pct=a.snapshot.price.change_24h_pct,
                    atr=a.snapshot.tf_1h.atr,
                    key_support=a.snapshot.tf_1h.recent_swing_low,
                    key_resistance=a.snapshot.tf_1h.recent_swing_high,
                    funding_rate=a.snapshot.derivatives.funding_rate,
                    oi_1h_change=a.snapshot.derivatives.oi_1h_change,
                    oi_12h_change=a.snapshot.derivatives.oi_12h_change,
                    regime_1h=a.snapshot.tf_1h.regime,
                )
                alerts_to_send.append(alert)

                if notify and self.config.feishu_enabled and webhook_url:
                    try:
                        send_market_watch_alert(webhook_url, alert, secret)
                        alert_sent = True
                    except Exception as exc:  # noqa: BLE001
                        logger.error("Feishu alert failed for %s: %s", a.symbol, exc)

            # Persist state to SQLite
            self.store.save_symbol_state(a.symbol, a, now_ms, alert_sent=alert_sent)

        return ranked_assessments, alerts_to_send
