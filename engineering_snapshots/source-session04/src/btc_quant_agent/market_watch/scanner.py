from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, replace
from typing import Any

from ..data.binance import BinancePublicClient
from .alerting import NotificationNotSent, send_market_watch_alert
from .config import (
    MarketWatchConfig,
    compute_market_watch_config_hash,
    compute_required_closed_bars,
    compute_required_fetch_bars,
)
from .context import apply_benchmark_context_gate, evaluate_benchmark_context
from .derivatives import apply_derivatives_action_gate, evaluate_derivatives_regime
from .domain import (
    DIRECTIONAL_OUTCOME_PROFILE_VERSION,
    HEURISTIC_RULE_QUALITY_BAND_VERSION,
    MARKET_SNAPSHOT_SCHEMA_VERSION,
    MARKET_WATCH_EVIDENCE_VERSION,
    PLAYBOOK_SELECTION_VERSION,
    REFERENCE_UNIVERSE_VERSION,
    RETURN_FEATURE_SEMANTICS_VERSION,
    RULE_SCORE_SEMANTICS_VERSION,
    TACTICAL_POLICY_VERSION,
    AlertSeverity,
    BreakoutState,
    ConfidenceBand,
    DerivativesMetrics,
    DirectionalDecision,
    DirectionalPlan,
    EntryQuality,
    GridDecision,
    GridPlan,
    InputClock,
    MarketSnapshot,
    MarketWatchAlert,
    PlaybookType,
    PriceMetrics,
    RelativePerformance,
    ScanHealth,
    ShadowExecutionPathModel,
    ShadowFillStatus,
    SignalLifecycleState,
    SymbolAssessment,
    TacticalSemanticIdentity,
    extract_setup_key,
    extract_signal_identity,
    source_json_value,
)
from .entry_quality import calculate_net_risk_reward, evaluate_entry_quality, evaluate_exhaustion
from .evidence import (
    PolicyDecisionTrace,
    PolicyGateStageTrace,
    TacticalEvidenceConflictError,
    TacticalFeatureEvidenceV2,
    build_tactical_feature_evidence,
)
from .foundation import (
    actionable_reasons,
    increment,
    metadata_map,
    positive,
    reference_reasons,
    timestamp,
)
from .grid_policy import evaluate_grid_policy
from .lifecycle import advance_lifecycle_state
from .playbooks import (
    evaluate_all_playbook_candidates,
    evaluate_timeframe_alignment,
    select_playbook_candidate,
)
from .ranking import (
    calculate_rule_score_breakdown,
    check_fatal_vetoes,
    compute_relative_performances,
)
from .shadow_evidence import get_playbook_evaluation_profile
from .snapshot import (
    ReturnAvailability,
    compute_return_observation,
    compute_snapshot_hash,
    compute_timeframe_snapshot,
)
from .state import (
    MarketWatchStateStore,
    compute_decision_fingerprint,
    evaluate_alert_emission,
)

logger = logging.getLogger(__name__)


class MarketWatchScanner:
    """Multi-asset operational scanner with PIT-safe snapshots and failure isolation."""

    def __init__(self, config: MarketWatchConfig, client: BinancePublicClient,
                 store: MarketWatchStateStore, *, clock_ms: Callable[[], int] | None = None,
                 symbol_filters: dict[str, dict[str, float]] | None = None) -> None:
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.symbol_filters = symbol_filters or {}
        self.config = config
        self.client = client
        self.store = store
        self._last_evidences: dict[str, TacticalFeatureEvidenceV2] = {}

    def get_last_evidence(self, symbol: str) -> TacticalFeatureEvidenceV2 | None:
        """Get the latest in-memory TacticalFeatureEvidenceV2 built for symbol."""
        return self._last_evidences.get(symbol.upper())

    def collect_symbol_snapshot(self, symbol: str, now_ms: int) -> tuple[MarketSnapshot | None, ScanHealth, tuple[str, ...]]:
        """Collect market snapshot for one symbol with robust degradation handling."""
        collection_started_at_ms = self.clock_ms()
        symbol = symbol.upper()
        health_reasons: list[str] = []
        health = ScanHealth.OK

        # 1. Core klines (15m, 1h, 4h) - Failure here is FAILED
        fetch_bars = compute_required_fetch_bars(self.config)
        try:
            raw_15m = self.client.klines(symbol, "15m", fetch_bars)
            raw_1h = self.client.klines(symbol, "1h", fetch_bars)
            raw_4h = self.client.klines(symbol, "4h", fetch_bars)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Core candle retrieval failed for %s: %s", symbol, exc)
            return None, ScanHealth.FAILED, (f"CORE_CANDLE_ERROR: {exc}",)

        raw_15m = [c for c in raw_15m if c.closed]
        raw_1h = [c for c in raw_1h if c.closed]
        raw_4h = [c for c in raw_4h if c.closed]
        if len(raw_15m) < 30 or len(raw_1h) < 30 or len(raw_4h) < 30:
            return None, ScanHealth.FAILED, ("INSUFFICIENT_CANDLE_HISTORY",)

        # 2. Derivatives collection - Failure here is DEGRADED
        mark_price = None
        index_price = None
        funding_rate = None
        funding_time_ms = None
        premium_index_time_ms = None
        next_funding_time_ms = None
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
                avail = last_c.available_at_ms
                if avail and avail > 0:
                    candle_avail_timestamps.append(int(avail))

        def _to_opt_int(v: Any) -> int | None:
            return int(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None

        deriv_observed_at_ms: int | None = None
        try:
            deriv_collection = self.client.collect_derivatives(symbol, include_order_book=True)
            snap = deriv_collection.snapshot
            deriv_observed_at_ms = self.clock_ms()
            mark_price = getattr(snap, "mark_price", None)
            index_price = getattr(snap, "index_price", None)
            funding_rate = getattr(snap, "funding_rate", None)
            funding_time_ms = _to_opt_int(getattr(snap, "funding_time_ms", None))
            premium_index_time_ms = _to_opt_int(getattr(snap, "premium_index_time_ms", None))
            next_funding_time_ms = _to_opt_int(getattr(snap, "next_funding_time_ms", None))
            open_interest = getattr(snap, "open_interest", None)
            open_interest_time_ms = _to_opt_int(getattr(snap, "open_interest_time_ms", None))
            oi_1h_change = getattr(snap, "open_interest_change_pct", None)
            taker_ratio = getattr(snap, "taker_buy_sell_ratio", None)
            taker_time_ms = _to_opt_int(getattr(snap, "taker_time_ms", None))
            basis_rate = getattr(snap, "basis_rate", None)
            basis_time_ms = _to_opt_int(getattr(snap, "basis_time_ms", None))
            long_short_ratio = getattr(snap, "long_short_account_ratio", None)
            long_short_time_ms = _to_opt_int(getattr(snap, "long_short_time_ms", None))
            order_book_imbalance = getattr(snap, "order_book_imbalance", None)
            spread_bps = getattr(snap, "spread_bps", None)
            field_avail = dict(deriv_collection.field_availability)
            if any(v is None for v in (funding_rate, open_interest, oi_1h_change)):
                health = ScanHealth.DEGRADED
                health_reasons.append("DERIVATIVES_REQUIRED_FIELDS_UNKNOWN")
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
        oi_hist_source_ms: int | None = None
        try:
            oi_hist = self.client._optional_get(
                "/futures/data/openInterestHist",
                {"symbol": symbol, "period": "1h", "limit": 13},
            )
            oi_hist_receipt_ms = self.clock_ms()
            if oi_hist and len(oi_hist) >= 2:
                oi_hist_source_ms = _to_opt_int(oi_hist[-1].get("timestamp"))
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
        except Exception as exc:  # noqa: BLE001 - optional sources fail closed
            logger.debug("OI history parse failed for %s: %s", symbol, exc)

        # Optional top trader position/account ratio queries
        top_pos_receipt_ms: int | None = None
        try:
            top_pos_payload = self.client._optional_get(
                "/futures/data/topLongShortPositionRatio",
                {"symbol": symbol, "period": "1h", "limit": 1},
            )
            top_pos_receipt_ms = self.clock_ms()
            if top_pos_payload and isinstance(top_pos_payload, list) and "longShortRatio" in top_pos_payload[-1]:
                top_pos_ratio = float(top_pos_payload[-1]["longShortRatio"])
        except Exception as exc:  # noqa: BLE001 - optional sources fail closed
            logger.debug("Top pos ratio parse failed for %s: %s", symbol, exc)

        top_acc_receipt_ms: int | None = None
        try:
            top_acc_payload = self.client._optional_get(
                "/futures/data/topLongShortAccountRatio",
                {"symbol": symbol, "period": "1h", "limit": 1},
            )
            top_acc_receipt_ms = self.clock_ms()
            if top_acc_payload and isinstance(top_acc_payload, list) and "longShortRatio" in top_acc_payload[-1]:
                top_acc_ratio = float(top_acc_payload[-1]["longShortRatio"])
        except Exception as exc:  # noqa: BLE001 - optional sources fail closed
            logger.debug("Top acc ratio parse failed for %s: %s", symbol, exc)

        # Exchange time and staleness check
        exchange_time_ms = now_ms
        server_time_receipt_ms: int | None = None
        try:
            val = self.client.server_time_ms()
            server_time_receipt_ms = self.clock_ms()
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
            ticker_receipt_ms = self.clock_ms()
            if ticker and isinstance(ticker, dict):
                change_24h = float(ticker.get("priceChangePercent", 0.0)) / 100.0
                high_24h = float(ticker.get("highPrice", high_24h))
                low_24h = float(ticker.get("lowPrice", low_24h))
                quote_vol_24h = float(ticker.get("quoteVolume", 0.0))
        except Exception as exc:  # noqa: BLE001 - optional sources fail closed
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

        # 5. Compute true elapsed returns from confirmed closed 15m candles
        r1h_obs = compute_return_observation(raw_15m, horizon_ms=3_600_000, source_interval="15m")
        r4h_obs = compute_return_observation(raw_15m, horizon_ms=14_400_000, source_interval="15m")
        r12h_obs = compute_return_observation(raw_15m, horizon_ms=43_200_000, source_interval="15m")
        r1h, r1h_status = r1h_obs.value, ReturnAvailability(r1h_obs.availability)
        r4h, r4h_status = r4h_obs.value, ReturnAvailability(r4h_obs.availability)
        r12h, r12h_status = r12h_obs.value, ReturnAvailability(r12h_obs.availability)

        # 6. Assemble DerivativesMetrics
        basis_bps = (basis_rate * 10_000.0) if basis_rate is not None else None
        deriv_metrics = DerivativesMetrics(
            mark_price=mark_price,
            index_price=index_price,
            funding_rate=funding_rate,
            funding_time_ms=funding_time_ms,
            premium_index_time_ms=premium_index_time_ms,
            next_funding_time_ms=next_funding_time_ms,
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

        # Evaluate derivatives regime with true 1h elapsed return
        d_regime, d_reasons, d_risks = evaluate_derivatives_regime(
            price_change_1h_pct=r1h,
            derivatives=deriv_metrics,
            config=self.config,
        )
        deriv_metrics = DerivativesMetrics(
            mark_price=deriv_metrics.mark_price,
            index_price=deriv_metrics.index_price,
            funding_rate=deriv_metrics.funding_rate,
            funding_time_ms=deriv_metrics.funding_time_ms,
            premium_index_time_ms=deriv_metrics.premium_index_time_ms,
            next_funding_time_ms=deriv_metrics.next_funding_time_ms,
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
            risk_codes=tuple(d_risks),
            regime_reason_codes=tuple(d_reasons),
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

        collection_completed_ms = self.clock_ms()
        observed_at_ms = collection_completed_ms
        # Never move a decision into the future to make input clocks appear admissible.
        decision_time_ms = max(collection_completed_ms, now_ms)

        snap_hash = compute_snapshot_hash(
            symbol=symbol,
            decision_time_ms=decision_time_ms,
            price=price_metrics,
            tf_15m=tf_15m,
            tf_1h=tf_1h,
            tf_4h=tf_4h,
            derivatives=deriv_metrics,
        )

        closed_bar_watermarks = {
            "15m": raw_15m[-1].close_time_ms if raw_15m else 0,
            "1h": raw_1h[-1].close_time_ms if raw_1h else 0,
            "4h": raw_4h[-1].close_time_ms if raw_4h else 0,
        }
        source_receipt_timestamps: dict[str, int] = {
            "collection_started_at_ms": collection_started_at_ms,
            "collection_completed_at_ms": collection_completed_ms,
        }
        if deriv_observed_at_ms:
            source_receipt_timestamps["deriv_observed_at_ms"] = int(deriv_observed_at_ms)
        if oi_hist_receipt_ms:
            source_receipt_timestamps["oi_hist_receipt_ms"] = oi_hist_receipt_ms
        if top_pos_receipt_ms:
            source_receipt_timestamps["top_pos_receipt_ms"] = top_pos_receipt_ms
        if top_acc_receipt_ms:
            source_receipt_timestamps["top_acc_receipt_ms"] = top_acc_receipt_ms
        if ticker_receipt_ms:
            source_receipt_timestamps["ticker_receipt_ms"] = ticker_receipt_ms
        if server_time_receipt_ms:
            source_receipt_timestamps["server_time_receipt_ms"] = server_time_receipt_ms

        candle_clocks = {}
        candle_counts = {}
        for name, candles in (("15m", raw_15m), ("1h", raw_1h), ("4h", raw_4h)):
            receipts = [c.available_at_ms for c in candles]
            known_receipts = [t for t in receipts if timestamp(t)]
            known = max(known_receipts) if len(known_receipts) == len(receipts) else None
            candle_clocks[name] = InputClock(candles[-1].close_time_ms, known, known)
            candle_counts[name] = len(candles)
            if len(candles) < compute_required_closed_bars(self.config):
                health = ScanHealth.DEGRADED
                health_reasons.append(f"BARS_{name}_INSUFFICIENT")
        derivative_clocks = {
            "funding_rate": InputClock(premium_index_time_ms, deriv_observed_at_ms, deriv_observed_at_ms),
            "current_open_interest": InputClock(open_interest_time_ms, deriv_observed_at_ms, deriv_observed_at_ms),
            "oi_1h_change": InputClock(oi_hist_source_ms, oi_hist_receipt_ms, oi_hist_receipt_ms),
        }
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
            return_1h=r1h,
            return_4h=r4h,
            return_12h=r12h,
            return_1h_status=r1h_status.value,
            return_4h_status=r4h_status.value,
            return_12h_status=r12h_status.value,
            closed_bar_watermarks=closed_bar_watermarks,
            return_observations=(r1h_obs, r4h_obs, r12h_obs),
            source_receipt_timestamps=source_receipt_timestamps,
            clock=InputClock(max(closed_bar_watermarks.values()), collection_completed_ms, collection_completed_ms),
            candle_clocks=candle_clocks,
            candle_counts=candle_counts,
            derivative_clocks=derivative_clocks,
            symbol_filters=dict(self.symbol_filters.get(symbol, {})),
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
        if type(snapshot) is not MarketSnapshot:
            raise ValueError("SOURCE_METADATA_UNKNOWN")
        if not timestamp(snapshot.decision_time_ms):
            raise ValueError("SOURCE_DECISION_TIMING_UNKNOWN")
        if (type(snapshot.symbol) is not str or not snapshot.symbol.strip()
                or type(snapshot.snapshot_hash) is not str or not snapshot.snapshot_hash):
            raise ValueError("SOURCE_IDENTITY_UNKNOWN")
        symbol = snapshot.symbol
        timing_reasons = list(snapshot.reference_timing_reasons) if type(snapshot.reference_timing_reasons) in (tuple, list) and all(type(r) is str for r in snapshot.reference_timing_reasons) else ["SOURCE_METADATA_UNKNOWN"]
        normalized_maps: dict[str, Any] = {}
        for field in ("candle_clocks", "candle_counts", "derivative_clocks", "symbol_filters",
                      "reference_clocks", "closed_bar_watermarks", "source_receipt_timestamps"):
            value = getattr(snapshot, field)
            if type(value) is not dict:
                timing_reasons.append("SOURCE_METADATA_UNKNOWN")
                normalized_maps[field] = {}
        if normalized_maps:
            snapshot = replace(snapshot, **normalized_maps)
        reference_clocks = {}
        admitted = {}
        for name, ref in (("BTCUSDT", btc_snapshot), ("ETHUSDT", eth_snapshot)):
            if name == symbol:
                ref = snapshot
            failures = reference_reasons(snapshot, ref, name)
            timing_reasons.extend(failures)
            if not failures and ref is not None:
                admitted[name] = ref
                reference_clocks[name] = ref.clock
        snapshot = replace(snapshot, reference_clocks=reference_clocks,
                           reference_timing_reasons=tuple(sorted(set(timing_reasons))))
        btc_snapshot, eth_snapshot = admitted.get("BTCUSDT"), admitted.get("ETHUSDT")
        frozen_inputs_json = json.dumps({
            "snapshot": snapshot.as_dict(),
            "references": {name: ref.as_dict() for name, ref in admitted.items()},
            "relative_performance": source_json_value(asdict(relative_perf)) if type(relative_perf) is RelativePerformance else None,
        }, sort_keys=True, allow_nan=False)
        origin = self.store.get_decision_origin(snapshot, compute_market_watch_config_hash(self.config))
        if origin is not None:
            if origin["frozen_inputs_json"] != frozen_inputs_json:
                raise TacticalEvidenceConflictError("FROZEN_DECISION_INPUT_CONFLICT")
            prev_state = json.loads(origin["policy_state_before_json"])
        policy_state_before_json = json.dumps(prev_state, sort_keys=True, allow_nan=False)
        source_reasons = actionable_reasons(snapshot, self.config)
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

        # 4. Playbook candidate evaluation & selection
        candidates = evaluate_all_playbook_candidates(
            tf_4h=tf_4h,
            tf_1h=tf_1h,
            tf_15m=tf_15m,
            derivatives=derivatives,
            exhaustion=exhaustion,
            config=self.config,
            prev_state=prev_state,
        )
        selected_candidate, eligible_playbooks, actionable_playbooks = select_playbook_candidate(candidates)

        if selected_candidate is not None:
            raw_decision = selected_candidate.decision
            setup = selected_candidate.playbook
            entry_low = selected_candidate.entry_low or 0.0
            entry_high = selected_candidate.entry_high or 0.0
            stop_loss = selected_candidate.stop_loss or 0.0
            tp1 = selected_candidate.take_profit_1 or 0.0
            tp2 = selected_candidate.take_profit_2 or 0.0
            invalidation = selected_candidate.invalidation or 0.0
            confidence = selected_candidate.confidence
            bo_state = selected_candidate.breakout_state
            bo_level = selected_candidate.breakout_level
            bo_dir = selected_candidate.breakout_direction
            bo_bar_end_ms = selected_candidate.breakout_bar_end_ms
            reasons = list(selected_candidate.reason_codes) + tf_reasons + list(bench_reasons)
            risks = list(selected_candidate.risk_codes) + list(bench_risks)
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

        tick = metadata_map(snapshot.symbol_filters).get("tick_size")
        precision_reasons = []
        if positive(tick) and raw_decision != DirectionalDecision.WAIT:
            try:
                entry_low = increment(entry_low, tick, upward=True)
                entry_high = increment(entry_high, tick)
                # Tighten toward entry: never silently widen protective risk.
                stop_loss = increment(stop_loss, tick, upward=raw_decision == DirectionalDecision.LONG)
                if tp1 > 0:
                    tp1 = increment(tp1, tick, upward=raw_decision == DirectionalDecision.SHORT)
                if tp2 > 0:
                    tp2 = increment(tp2, tick, upward=raw_decision == DirectionalDecision.SHORT)
                if invalidation > 0:
                    invalidation = increment(invalidation, tick, upward=raw_decision == DirectionalDecision.LONG)
                if entry_low > entry_high or not (
                    stop_loss < entry_low if raw_decision == DirectionalDecision.LONG
                    else stop_loss > entry_high
                ):
                    raise ValueError("INVALID_ROUNDED_PLAN")
            except ValueError:
                precision_reasons.append("PRICE_INCREMENT_INVALID")
        source_reasons = tuple(sorted({*source_reasons, *precision_reasons}))
        initial_selected_decision = raw_decision.value

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
        input_eq = raw_decision
        new_eq_reasons: list[str] = []
        if raw_decision != DirectionalDecision.WAIT and quality_rank[entry_quality] < quality_rank[min_quality]:
            raw_decision = DirectionalDecision.WAIT
            new_eq_reasons.append("ENTRY_QUALITY_BELOW_MINIMUM_WAIT")
            reasons.append("ENTRY_QUALITY_BELOW_MINIMUM_WAIT")

        trace_entry_quality = PolicyGateStageTrace(
            stage_name="entry_quality_gate",
            input_decision=input_eq.value,
            output_decision=raw_decision.value,
            new_reason_codes=tuple(new_eq_reasons),
            new_risk_codes=(),
            veto_flag=False,
        )

        # 7. Benchmark Context Gate (e.g. BTC risk-off shock)
        input_bg = raw_decision
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
        trace_benchmark = PolicyGateStageTrace(
            stage_name="benchmark_gate",
            input_decision=input_bg.value,
            output_decision=gated_decision.value,
            new_reason_codes=tuple(bg_reasons),
            new_risk_codes=tuple(bg_risks),
            veto_flag=False,
        )

        # 7b. Derivatives Action Gate (R2)
        input_deriv = gated_decision
        gated_decision, deriv_reasons, deriv_risks = apply_derivatives_action_gate(
            decision=gated_decision,
            derivatives=derivatives,
            config=self.config,
        )
        reasons.extend(deriv_reasons)
        risks.extend(deriv_risks)
        trace_derivatives = PolicyGateStageTrace(
            stage_name="derivatives_gate",
            input_decision=input_deriv.value,
            output_decision=gated_decision.value,
            new_reason_codes=tuple(deriv_reasons),
            new_risk_codes=tuple(deriv_risks),
            veto_flag=False,
        )

        # 8. Fatal Vetoes (Enforced before ranking)
        input_fatal = gated_decision
        has_fatal_veto, fatal_reasons = check_fatal_vetoes(
            decision=gated_decision,
            exhaustion=exhaustion,
            net_rr=net_rr,
            tf_4h=tf_4h,
            derivatives=derivatives,
            benchmark_context=bench_context,
            config=self.config,
        )
        fatal_reasons = tuple(sorted({*fatal_reasons, *source_reasons}))
        has_fatal_veto = bool(fatal_reasons)
        if source_reasons:
            actionable_playbooks = ()
        if has_fatal_veto:
            gated_decision = DirectionalDecision.WAIT
            reasons.extend(fatal_reasons)

        trace_fatal_veto = PolicyGateStageTrace(
            stage_name="fatal_veto_gate",
            input_decision=input_fatal.value,
            output_decision=gated_decision.value,
            new_reason_codes=tuple(fatal_reasons),
            new_risk_codes=(),
            veto_flag=has_fatal_veto,
        )

        decision_trace = PolicyDecisionTrace(
            selected_candidate_decision=initial_selected_decision,
            after_entry_quality_gate=trace_entry_quality,
            after_benchmark_gate=trace_benchmark,
            after_derivatives_gate=trace_derivatives,
            after_fatal_veto=trace_fatal_veto,
            final_directional_decision=gated_decision.value,
        )

        # 9. Rule Score (formerly Opportunity Score)
        rule_score_breakdown = calculate_rule_score_breakdown(
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
        rule_score = rule_score_breakdown.final_rule_score

        directional_plan = DirectionalPlan(
            symbol=symbol,
            decision=gated_decision,
            setup=setup,
            regime=tf_1h.regime,
            entry_quality=entry_quality,
            entry_low=entry_low,
            entry_high=entry_high,
            stop_loss=stop_loss,
            take_profit_1=tp1,
            take_profit_2=tp2,
            invalidation_level=invalidation,
            gross_rr=gross_rr,
            net_rr=net_rr,
            confidence_band=confidence,
            rule_score=rule_score,
            opportunity_score=rule_score,
            rule_score_semantics=RULE_SCORE_SEMANTICS_VERSION,
            heuristic_quality_band_semantics=HEURISTIC_RULE_QUALITY_BAND_VERSION,
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

        if not source_reasons and grid_plan.decision != GridDecision.PAUSE:
            levels = (grid_plan.lower_bound, grid_plan.upper_bound,
                      grid_plan.stop_loss, grid_plan.take_profit)
            lower, upper = grid_plan.lower_bound, grid_plan.upper_bound
            if not (positive(tick) and positive(lower) and positive(upper) and lower < upper
                    and all(positive(level) and increment(level, tick) == level for level in levels)):
                grid_plan = GridPlan(symbol=symbol, decision=GridDecision.PAUSE,
                                     reason_codes=("GRID_PRECISION_INVALID",))
        if source_reasons:
            grid_plan = GridPlan(symbol=symbol, decision=GridDecision.PAUSE,
                                 reason_codes=tuple(sorted({*grid_plan.reason_codes, *source_reasons})))

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
            and curr_bo_level != prev_bo_level
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

        # Reference universe status and missing members
        if relative_perf is not None:
            ref_univ_status = relative_perf.universe_status
            missing_ref_members = relative_perf.missing_members
        else:
            ref_univ_status = "UNIVERSE_DEGRADED"
            missing_ref_members = tuple(self.config.relative_strength_universe)

        sem_id = TacticalSemanticIdentity(
            tactical_policy_version=TACTICAL_POLICY_VERSION,
            snapshot_schema_version=MARKET_SNAPSHOT_SCHEMA_VERSION,
            return_semantics_version=RETURN_FEATURE_SEMANTICS_VERSION,
            playbook_selection_version=PLAYBOOK_SELECTION_VERSION,
            reference_universe_version=REFERENCE_UNIVERSE_VERSION,
            rule_score_semantics_version=RULE_SCORE_SEMANTICS_VERSION,
            config_hash=cfg_hash,
        )

        # Temporary assessment to compute stable fingerprint
        temp_assessment = SymbolAssessment(
            symbol=symbol,
            snapshot=snapshot,
            directional=directional_plan,
            grid=grid_plan,
            rule_score=rule_score,
            opportunity_score=rule_score,
            rule_score_semantics=RULE_SCORE_SEMANTICS_VERSION,
            eligible_playbooks=eligible_playbooks,
            actionable_playbooks=actionable_playbooks,
            selected_playbook=str(selected_candidate.playbook.value if hasattr(selected_candidate.playbook, "value") else selected_candidate.playbook) if selected_candidate else "",
            selection_method="STATIC_PRECEDENCE",
            selection_version=PLAYBOOK_SELECTION_VERSION,
            reference_universe_status=ref_univ_status,
            missing_reference_members=missing_ref_members,
            semantic_identity=sem_id,
            relative_performance=relative_perf,
            exhaustion=exhaustion,
            rank=0,
            veto_reasons=fatal_reasons,
            alert_fingerprint="",
            lifecycle_state=lifecycle,
            policy_version=TACTICAL_POLICY_VERSION,
            config_hash=cfg_hash,
            signal_identity=sig_id,
            setup_key=setup_key,
            frozen_inputs_json=frozen_inputs_json,
            policy_state_before_json=policy_state_before_json,
        )
        evidence = build_tactical_feature_evidence(
            assessment=temp_assessment,
            playbook_candidates=candidates,
            decision_trace=decision_trace,
            rule_score_breakdown=rule_score_breakdown,
            config=self.config,
            policy_state_before=prev_state,
        )
        self._last_evidences[symbol] = evidence
        fp = compute_decision_fingerprint(temp_assessment, self.config)

        return replace(
            temp_assessment,
            feature_evidence_id=evidence.evidence_id,
            feature_evidence=evidence,
            alert_fingerprint=fp,
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
                    execution_path_model=ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value,
                    semantic_identity=a.semantic_identity,
                    feature_evidence_id=a.feature_evidence_id,
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

                pb_str = str(a.selected_playbook or a.directional.setup)
                prof = get_playbook_evaluation_profile(pb_str)

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
                    execution_path_model=ShadowExecutionPathModel.PARTIAL_FIRST_BAR_1M_THEN_15M.value,
                    semantic_identity=a.semantic_identity,
                    feature_evidence_id=a.feature_evidence_id,
                    evaluation_profile_version=DIRECTIONAL_OUTCOME_PROFILE_VERSION,
                    evaluation_horizon_bars=prof["horizon_bars"],
                    evaluation_horizon_ms=prof["horizon_ms"],
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
        target_symbols = [s.upper() for s in (symbols or self.config.symbols)]
        now_ms = self.clock_ms()

        # Frozen Section 21 collection semantics:
        # Collect target_symbols UNION reference_universe UNION benchmark_symbols
        ref_symbols = [s.upper() for s in self.config.relative_strength_universe]
        benchmarks = ["BTCUSDT", "ETHUSDT"]
        all_symbols_to_collect: list[str] = []
        for s in target_symbols + ref_symbols + benchmarks:
            if s not in all_symbols_to_collect:
                all_symbols_to_collect.append(s)

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

        # Relative inputs are admitted separately at each candidate decision cutoff.

        # 3. Retrieve benchmark snapshots


        # 4. Assess TARGET symbols only
        assessments: list[SymbolAssessment] = []
        for s in target_symbols:
            snap = snapshots.get(s)
            if snap is None:
                continue
            allowed = {name: ref for name, ref in snapshots.items()
                       if not reference_reasons(snap, ref, name)}
            excluded_reasons = tuple(reason for name, ref in snapshots.items()
                                     for reason in reference_reasons(snap, ref, name))
            if type(snap) is MarketSnapshot:
                snap = replace(snap, reference_timing_reasons=excluded_reasons)
            rel_perfs = compute_relative_performances(allowed, self.config)
            prev_st = self.store.get_symbol_state(s)
            item = self.assess_symbol(
                snapshot=snap,
                prev_state=prev_st,
                btc_snapshot=allowed.get("BTCUSDT"),
                eth_snapshot=allowed.get("ETHUSDT"),
                relative_perf=rel_perfs.get(s),
            )
            assessments.append(item)

        # 5. Rank assessments by rule_score descending (falling back to opportunity_score)
        def _get_sort_score(a: Any) -> float:
            rs = getattr(a, "rule_score", None)
            if isinstance(rs, (int, float)):
                return float(rs)
            os_score = getattr(a, "opportunity_score", None)
            if isinstance(os_score, (int, float)):
                return float(os_score)
            return 0.0

        assessments.sort(key=_get_sort_score, reverse=True)
        ranked_assessments: list[SymbolAssessment] = []
        for rank_num, a in enumerate(assessments, 1):
            if type(a) is SymbolAssessment:
                ranked_assessments.append(replace(a, rank=rank_num))
            else:
                try:
                    object.__setattr__(a, "rank", rank_num)
                except Exception:  # noqa: BLE001, S110
                    pass
                ranked_assessments.append(a)

        # 6. Evaluate alerts based on state changes & priority
        webhook_url = os.getenv("FEISHU_WEBHOOK_URL")
        secret = os.getenv("FEISHU_WEBHOOK_SECRET")

        candidate_alerts: list[tuple[SymbolAssessment, MarketWatchAlert, AlertSeverity]] = []
        for a in ranked_assessments:
            prev_st = self.store.get_symbol_state(a.symbol) or {}
            emit, severity, _reasons = evaluate_alert_emission(a, prev_st, self.config)
            if emit:
                source_veto = actionable_reasons(a.snapshot, self.config)
                if severity == AlertSeverity.ACTION and source_veto:
                    severity = AlertSeverity.WATCH
                alert = MarketWatchAlert(
                    symbol=a.symbol,
                    severity=severity,
                    title=f"{a.symbol} {a.directional.decision.value}",
                    directional=a.directional,
                    grid=a.grid,
                    fingerprint=a.alert_fingerprint,
                    evidence=a.directional.reason_codes,
                    risks=tuple(sorted({*a.directional.risk_codes, *source_veto})),
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
                candidate_alerts.append((a, alert, severity))

        # Severity priority: RISK > ACTION > WATCH > INFO
        # Within equal severity: opportunity_score descending, then symbol alphabetically
        severity_order = {
            AlertSeverity.RISK: 3,
            AlertSeverity.ACTION: 2,
            AlertSeverity.WATCH: 1,
            AlertSeverity.INFO: 0,
        }
        candidate_alerts.sort(
            key=lambda item: (
                -severity_order.get(item[2], 0),
                -item[0].opportunity_score,
                item[0].symbol,
            )
        )

        # Alert selection (Section 13):
        # RISK alerts bypass or reserve capacity against ordinary WATCH/ACTION cap.
        # Include all RISK alerts, then fill remaining slots up to max_alert_symbols with ACTION/WATCH.
        risk_candidates = [item for item in candidate_alerts if item[2] == AlertSeverity.RISK]
        non_risk_candidates = [item for item in candidate_alerts if item[2] != AlertSeverity.RISK]

        selected_candidates: list[tuple[SymbolAssessment, MarketWatchAlert, AlertSeverity]] = list(risk_candidates)
        remaining_slots = max(0, self.config.max_alert_symbols - len(selected_candidates))
        selected_candidates.extend(non_risk_candidates[:remaining_slots])

        alerts_to_send: list[MarketWatchAlert] = []

        # Evidence and assessment commit precedes event reservation and any sender call.
        for a in ranked_assessments:
            ev = getattr(a, "feature_evidence", None) or self._last_evidences.get(a.symbol)
            self.store.save_symbol_state(a.symbol, a, self.clock_ms(), alert_sent=False, evidence=ev)

        for a, alert, severity in selected_candidates:
            # Unknown source objects may expose a degraded observation, never a send.
            if (type(a) is not SymbolAssessment or type(a.snapshot) is not MarketSnapshot
                    or not timestamp(a.snapshot.decision_time_ms)
                    or type(a.feature_evidence) is not TacticalFeatureEvidenceV2):
                alerts_to_send.append(alert)
                continue
            event_id = self.store.prepare_notification(a, alert, self.clock_ms())
            alert = replace(alert, event_id=event_id)
            alerts_to_send.append(alert)
            if not (notify and self.config.feishu_enabled and webhook_url):
                continue
            # Recheck freshness at the actual send attempt, including queued/restarted work.
            if (severity == AlertSeverity.ACTION
                    and actionable_reasons(a.snapshot, self.config, cutoff_ms=self.clock_ms())):
                continue
            if not self.store.claim_notification(event_id, self.clock_ms()):
                continue
            try:
                send_market_watch_alert(
                    webhook_url, alert, secret,
                    payload=json.loads(self.store.get_notification(event_id)["payload_json"]),
                )
            except Exception as exc:  # noqa: BLE001 - remote acceptance may be unknown
                self.store.fail_notification(
                    event_id, self.clock_ms(), type(exc).__name__,
                    definitely_not_sent=isinstance(exc, NotificationNotSent),
                )
                logger.error("Feishu alert failed for %s: %s", a.symbol, type(exc).__name__)
            else:
                self.store.acknowledge_notification(event_id, self.clock_ms())

        for a in ranked_assessments:
            self._record_shadow_observations_if_needed(a, self.clock_ms())
        return ranked_assessments, alerts_to_send
