from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .config import AppConfig
from .data.derivatives import sanitize_derivatives
from .data.quality import validate_candles
from .domain import (
    Candle,
    DerivativesSnapshot,
    ScanResult,
    Signal,
    SignalStatus,
    TimeframeFeatures,
)
from .features import build_features
from .multifactor import assess_factors, macro_aligned
from .regime import classify_regime
from .risk import build_position_plan
from .strategies import find_candidate
from .structure import confirmed_levels

_FEATURE_CONFIG_FIELDS = (
    "ema_fast",
    "ema_mid",
    "ema_slow",
    "atr_period",
    "adx_period",
    "slope_lookback",
    "pivot_left",
    "pivot_right",
    "rsi_period",
    "roc_period",
    "bb_period",
    "cvd_window",
)


@dataclass
class HistoricalFeatureCache:
    """Opt-in cache for repeated research replays over one immutable dataset."""

    values: dict[tuple[object, ...], TimeframeFeatures] = field(default_factory=dict)

    def key(
        self, interval: str, candles: Sequence[Candle], config: AppConfig
    ) -> tuple[object, ...]:
        return (
            interval,
            len(candles),
            candles[0].open_time_ms,
            candles[-1].open_time_ms,
            *(getattr(config.strategy, name) for name in _FEATURE_CONFIG_FIELDS),
        )


class QuantEngine:
    def __init__(
        self,
        config: AppConfig,
        historical_feature_cache: HistoricalFeatureCache | None = None,
    ):
        self.config = config
        self._feature_cache: dict[str, tuple[tuple[Candle, ...], TimeframeFeatures]] = {}
        self._historical_feature_cache = historical_feature_cache

    def _features(
        self, interval: str, candles: Sequence[Candle]
    ) -> TimeframeFeatures:
        frozen = tuple(candles)
        cached = self._feature_cache.get(interval)
        if cached is not None and cached[0] == frozen:
            return cached[1]
        historical_cache = self._historical_feature_cache
        historical_key = (
            historical_cache.key(interval, frozen, self.config)
            if historical_cache is not None
            else None
        )
        if historical_key is not None:
            assert historical_cache is not None
            historical = historical_cache.values.get(historical_key)
            if historical is not None:
                self._feature_cache[interval] = (frozen, historical)
                return historical
        features = build_features(frozen, self.config.strategy)
        self._feature_cache[interval] = (frozen, features)
        if historical_key is not None:
            assert historical_cache is not None
            historical_cache.values[historical_key] = features
        return features

    def diagnostic_features(
        self, interval: str, candles: Sequence[Candle]
    ) -> TimeframeFeatures:
        """Return the same cached features used by ``scan`` for read-only diagnostics."""
        return self._features(interval, candles)

    def scan(
        self,
        candles_4h: Sequence[Candle],
        candles_1h: Sequence[Candle],
        candles_15m: Sequence[Candle],
        derivatives: DerivativesSnapshot | None,
        now_ms: int,
        *,
        include_order_book: bool | None = None,
    ) -> ScanResult:
        if include_order_book is None:
            include_order_book = self.config.strategy.enable_order_book_factor
        quality_4h = validate_candles(candles_4h, "4h", now_ms)
        quality_1h = validate_candles(candles_1h, "1h", now_ms)
        quality_15m = validate_candles(candles_15m, "15m", now_ms)
        issues = [*quality_4h.issues, *quality_1h.issues, *quality_15m.issues]
        if issues:
            return ScanResult(
                "NO_SIGNAL",
                "DATA_INVALID",
                "; ".join(issues),
                reason_code="INVALID_CANDLES",
            )
        decision_age_ms = now_ms - candles_15m[-1].close_time_ms
        if decision_age_ms > self.config.runtime.max_data_age_seconds * 1000:
            return ScanResult(
                "NO_SIGNAL",
                "DATA_INVALID",
                "latest decision candle exceeds max_data_age_seconds",
                reason_code="STALE_DECISION_DATA",
            )

        try:
            features_4h = self._features("4h", candles_4h)
            features_1h = self._features("1h", candles_1h)
            features_15m = self._features("15m", candles_15m)
        except ValueError as exc:
            return ScanResult("NO_SIGNAL", "DATA_INVALID", str(exc), reason_code="FEATURE_ERROR")

        regime = classify_regime(features_1h, self.config.strategy)
        diagnostics: dict[str, Any] = {
            "regime": str(regime),
            "close": features_15m.close,
            "atr": features_15m.atr,
            "adx_1h": features_1h.adx,
            "structure_1h": features_1h.structure,
            "structure_15m": features_15m.structure,
            "macro_4h": {
                "close": features_4h.close,
                "ema_mid": features_4h.ema_mid,
                "ema_slow": features_4h.ema_slow,
            },
            "rsi_15m": features_15m.rsi,
            "ema_15m": {
                "fast": features_15m.ema_fast,
                "mid": features_15m.ema_mid,
                "slow": features_15m.ema_slow,
            },
            "roc_15m": features_15m.roc,
            "bb_width_percentile_15m": features_15m.bb_width_percentile,
            "cvd_slope_15m": features_15m.cvd_slope,
        }
        if regime.value in ("RANGE", "HIGH_VOLATILITY", "TRANSITION"):
            return ScanResult(
                "WAIT",
                "OK",
                f"regime={regime}",
                diagnostics=diagnostics,
                reason_code=f"REGIME_{regime.value}",
            )

        candidate = find_candidate(candles_15m, features_15m, regime, self.config.strategy)
        if candidate is None:
            return ScanResult(
                "WAIT",
                "OK",
                "no deterministic setup",
                diagnostics=diagnostics,
                reason_code="NO_SETUP",
            )

        derivative_risks: list[str] = list(candidate.risks)
        health = "OK"
        derivatives, stale_fields = sanitize_derivatives(
            derivatives,
            now_ms,
            self.config.data,
            include_order_book=include_order_book,
        )
        diagnostics["stale_derivative_fields"] = list(stale_fields)
        required_stale_fields: set[str] = set()
        if self.config.strategy.enable_derivatives_group:
            required_stale_fields.update(
                {"snapshot", "open_interest", "funding", "taker", "basis", "long_short"}
            )
        if self.config.strategy.enable_order_book_factor:
            required_stale_fields.update({"snapshot", "order_book"})
        missing_required_snapshot = derivatives is None and bool(required_stale_fields)
        required_stale = [name for name in stale_fields if name in required_stale_fields]
        diagnostics["required_stale_derivative_fields"] = required_stale
        if missing_required_snapshot:
            health = "DEGRADED"
            derivative_risks.append("策略要求的衍生品快照缺失")
        elif required_stale:
            health = "DEGRADED"
            derivative_risks.extend(
                f"策略要求的衍生品字段过期或尚不可见：{name}"
                for name in required_stale
            )

        assessment = assess_factors(
            candidate,
            features_4h,
            features_1h,
            features_15m,
            derivatives,
            self.config.strategy,
        )
        diagnostics["factor_score"] = assessment.score
        diagnostics["factor_scores"] = assessment.group_scores
        diagnostics["positive_factor_groups"] = assessment.positive_groups
        if assessment.blocked_reason:
            return ScanResult(
                "WAIT",
                health,
                assessment.blocked_reason,
                diagnostics=diagnostics,
                reason_code="FACTOR_REJECTED",
            )
        derivative_risks.extend(assessment.risks)

        plan = build_position_plan(
            candidate,
            features_15m.atr,
            self.config.strategy,
            self.config.risk,
            derivatives.funding_rate if derivatives else None,
        )
        if plan is None:
            return ScanResult(
                "WAIT",
                health,
                "net RR below threshold or position below exchange minimum",
                diagnostics=diagnostics,
                reason_code="RISK_PLAN_REJECTED",
            )

        decision_interval_ms = _interval_ms(self.config.runtime.decision_interval)
        expires_at_ms = candles_15m[-1].close_time_ms + min(
            self.config.runtime.ttl_minutes * 60_000,
            self.config.strategy.max_signal_age_bars * decision_interval_ms,
        )
        if now_ms > expires_at_ms:
            return ScanResult(
                "WAIT",
                health,
                "setup was already stale at scan time",
                diagnostics=diagnostics,
                reason_code="STALE_SETUP",
            )

        fingerprint_raw = (
            f"{self.config.runtime.symbol}:{candidate.direction}:{candidate.setup}:"
            f"{candidate.structure_id}"
        )
        fingerprint = hashlib.sha256(fingerprint_raw.encode()).hexdigest()[:20]
        timestamp = datetime.fromtimestamp(candles_15m[-1].close_time_ms / 1000, tz=UTC).strftime(
            "%Y%m%d-%H%M"
        )
        signal_id = f"{self.config.runtime.symbol}-{timestamp}-{candidate.direction.value}-{fingerprint[:6]}"
        support, resistance = confirmed_levels(
            candles_15m[-self.config.strategy.level_lookback_bars :],
            self.config.strategy.pivot_left,
            self.config.strategy.pivot_right,
        )
        signal = Signal(
            signal_id=signal_id,
            fingerprint=fingerprint,
            strategy_version=self.config.runtime.strategy_version,
            feature_version=self.config.runtime.feature_version,
            model_version=None,
            config_hash=self.config.config_hash,
            validation_status=self.config.runtime.validation_status,
            symbol=self.config.runtime.symbol,
            direction=candidate.direction,
            setup=candidate.setup,
            regime=regime,
            status=SignalStatus.ACTIVE,
            data_timestamp_ms=candles_15m[-1].close_time_ms,
            created_at_ms=now_ms,
            expires_at_ms=expires_at_ms,
            entry_low=candidate.entry_low,
            entry_high=candidate.entry_high,
            stop_loss=plan.stop_loss,
            invalidation_level=candidate.invalidation_level,
            take_profit=plan.take_profit,
            rr_gross=plan.rr_gross,
            rr_net=plan.rr_net,
            pattern_score=candidate.pattern_score,
            factor_score=assessment.score,
            p_win=None,
            expected_r=None,
            recommended_notional=plan.recommended_notional,
            margin_at_leverage=plan.required_margin,
            display_leverage=self.config.risk.display_leverage,
            max_loss_usdt=plan.risk_usdt,
            estimated_fee_usdt=plan.estimated_fee_usdt,
            estimated_slippage_usdt=plan.estimated_slippage_usdt,
            estimated_funding_usdt=plan.estimated_funding_usdt,
            support=sorted([level for level in support if level < features_15m.close])[-3:],
            resistance=sorted([level for level in resistance if level > features_15m.close])[:3],
            reasons=[*candidate.reasons, *assessment.evidence],
            risks=derivative_risks,
            factor_scores=assessment.group_scores,
            factor_evidence=list(assessment.evidence),
            positive_factor_groups=assessment.positive_groups,
            macro_4h=diagnostics["macro_4h"],
            structure_15m=features_15m.structure,
            data_health=health,
        )
        diagnostics["fingerprint"] = fingerprint
        return ScanResult(
            signal.direction.value,
            health,
            "confirmed",
            signal,
            diagnostics,
            "CONFIRMED",
        )

    def invalidation_reason(
        self,
        signal: Signal,
        candles_4h: Sequence[Candle],
        candles_1h: Sequence[Candle],
        candles_15m: Sequence[Candle],
        now_ms: int,
    ) -> str | None:
        """Revalidate an ACTIVE signal after a newly closed decision candle."""
        if now_ms > signal.expires_at_ms:
            return "TTL_EXPIRED"
        if not candles_15m or candles_15m[-1].close_time_ms <= signal.data_timestamp_ms:
            return None
        try:
            features_4h = build_features(candles_4h, self.config.strategy)
            features_1h = build_features(candles_1h, self.config.strategy)
            features_15m = build_features(candles_15m, self.config.strategy)
        except ValueError:
            return "DATA_INVALID"
        if signal.direction.value == "LONG":
            if features_15m.close <= signal.invalidation_level:
                return "INVALIDATION_LEVEL_BREACHED"
        elif features_15m.close >= signal.invalidation_level:
            return "INVALIDATION_LEVEL_BREACHED"
        if classify_regime(features_1h, self.config.strategy) != signal.regime:
            return "REGIME_REVERSED"
        if not macro_aligned(features_4h, signal.direction):
            return "MACRO_4H_CONFLICT"
        current = features_15m.close
        if signal.direction.value == "LONG":
            reward = signal.take_profit - current
            risk = current - signal.stop_loss
        else:
            reward = current - signal.take_profit
            risk = signal.stop_loss - current
        cost_rate = (
            signal.estimated_fee_usdt
            + signal.estimated_slippage_usdt
            + signal.estimated_funding_usdt
        ) / signal.recommended_notional
        net_rr = (
            (reward / current - cost_rate) / (risk / current + cost_rate)
            if risk > 0 and current > 0
            else -1.0
        )
        if reward <= 0 or net_rr < self.config.strategy.rr_min:
            return "RR_BELOW_MINIMUM"
        return None


def _interval_ms(interval: str) -> int:
    units = {"m": 60_000, "h": 3_600_000}
    if len(interval) < 2 or interval[-1] not in units:
        raise ValueError(f"unsupported decision interval: {interval}")
    return int(interval[:-1]) * units[interval[-1]]
