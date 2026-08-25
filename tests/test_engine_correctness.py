import json
import unittest
from dataclasses import replace
from unittest.mock import patch

from btc_quant_agent.config import AppConfig, RuntimeConfig
from btc_quant_agent.data.quality import QualityReport
from btc_quant_agent.domain import (
    Candidate,
    Candle,
    DerivativesSnapshot,
    Direction,
    PositionPlan,
    Regime,
    Setup,
    TimeframeFeatures,
)
from btc_quant_agent.engine import QuantEngine
from btc_quant_agent.multifactor import FactorAssessment


def candle(interval: str, interval_ms: int) -> Candle:
    return Candle("BTCUSDT", interval, 0, interval_ms - 1, 100, 101, 99, 100.5, 10)


def features(close: float = 110.0) -> TimeframeFeatures:
    return TimeframeFeatures(
        close=close,
        ema_fast=108.0,
        ema_mid=105.0,
        ema_slow=100.0,
        ema_mid_slope=1.0,
        ema_slow_slope=0.5,
        atr=2.0,
        atr_percentile=0.5,
        adx=28.0,
        volume_z=1.0,
        rsi=55.0,
        roc=0.01,
        bb_width_percentile=0.5,
        cvd_slope=1.0,
        cvd_available=True,
        last_swing_high=115.0,
        previous_swing_high=112.0,
        last_swing_low=100.0,
        previous_swing_low=98.0,
        structure="HH_HL",
        bar_open_time_ms=0,
        bar_close_time_ms=899_999,
    )


class EngineCorrectnessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candles = (
            [candle("4h", 14_400_000)],
            [candle("1h", 3_600_000)],
            [candle("15m", 900_000)],
        )
        self.candidate = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            109.0,
            110.0,
            100.0,
            125.0,
            80,
            "structure",
            ("setup",),
        )
        self.plan = PositionPlan(109.5, 99.5, 125.0, 1.55, 1.8, 0.5, 5.0, 0.25, 0.005, 0.002, 0.0)
        self.assessment = FactorAssessment(80.0, 4, {"trend_structure": 100.0}, ("confirmed",), ())

    def _scan(self, config: AppConfig, now_ms: int, derivatives=None):
        with (
            patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
            patch("btc_quant_agent.engine.build_features", return_value=features()),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
            patch("btc_quant_agent.engine.find_candidate", return_value=self.candidate),
            patch("btc_quant_agent.engine.assess_factors", return_value=self.assessment),
            patch("btc_quant_agent.engine.build_position_plan", return_value=self.plan),
            patch("btc_quant_agent.engine.confirmed_levels", return_value=([100.0], [125.0])),
        ):
            return QuantEngine(config).scan(*self.candles, derivatives, now_ms)

    def test_signal_ttl_is_anchored_to_decision_data_timestamp(self) -> None:
        result = self._scan(AppConfig(), 900_000)
        assert result.signal
        self.assertEqual(result.signal.expires_at_ms, 899_999 + 45 * 60_000)
        self.assertNotEqual(result.signal.expires_at_ms, 900_000 + 45 * 60_000)

    def test_stale_setup_is_not_returned_active(self) -> None:
        config = AppConfig(runtime=RuntimeConfig(ttl_minutes=1, max_data_age_seconds=10_000))
        result = self._scan(config, 899_999 + 60_001)
        self.assertIsNone(result.signal)
        self.assertEqual(result.reason_code, "STALE_SETUP")

    def test_max_data_age_seconds_is_enforced(self) -> None:
        result = self._scan(AppConfig(), 899_999 + 121_000)
        self.assertEqual(result.action, "NO_SIGNAL")
        self.assertEqual(result.reason_code, "STALE_DECISION_DATA")

    def test_stale_derivatives_are_removed_before_scoring(self) -> None:
        now_ms = 900_001
        derivatives = DerivativesSnapshot(
            observed_at_ms=now_ms,
            open_interest=1000.0,
            open_interest_change_pct=0.1,
            open_interest_time_ms=0,
            funding_rate=0.0001,
            funding_time_ms=now_ms,
        )
        with (
            patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
            patch("btc_quant_agent.engine.build_features", return_value=features()),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
            patch("btc_quant_agent.engine.find_candidate", return_value=self.candidate),
            patch("btc_quant_agent.engine.assess_factors", return_value=self.assessment) as assess,
            patch("btc_quant_agent.engine.build_position_plan", return_value=self.plan),
            patch("btc_quant_agent.engine.confirmed_levels", return_value=([], [])),
        ):
            QuantEngine(AppConfig()).scan(*self.candles, derivatives, now_ms)
        sanitized = assess.call_args.args[4]
        self.assertIsNone(sanitized.open_interest)
        self.assertIsNone(sanitized.open_interest_change_pct)
        self.assertEqual(sanitized.funding_rate, 0.0001)

    def test_derivatives_disabled_missing_snapshot_health_ok(self) -> None:
        config = AppConfig(
            strategy=replace(
                AppConfig().strategy,
                enable_derivatives_group=False,
                enable_order_book_factor=False,
            )
        )
        self.assertEqual(self._scan(config, 900_000, None).health, "OK")

    def test_derivatives_enabled_missing_snapshot_degraded(self) -> None:
        self.assertEqual(self._scan(AppConfig(), 900_000, None).health, "DEGRADED")

    def test_orderbook_disabled_missing_depth_health_ok(self) -> None:
        now_ms = 900_000
        config = AppConfig(
            strategy=replace(
                AppConfig().strategy,
                enable_derivatives_group=False,
                enable_order_book_factor=False,
            )
        )
        snapshot = DerivativesSnapshot(observed_at_ms=now_ms)
        self.assertEqual(self._scan(config, now_ms, snapshot).health, "OK")

    def test_required_stale_derivative_field_degrades_health(self) -> None:
        now_ms = 900_001
        snapshot = DerivativesSnapshot(
            observed_at_ms=now_ms,
            open_interest=1000.0,
            open_interest_time_ms=0,
            funding_time_ms=now_ms,
            taker_time_ms=now_ms,
            basis_time_ms=now_ms,
            long_short_time_ms=now_ms,
        )
        result = self._scan(AppConfig(), now_ms, snapshot)
        self.assertEqual(result.health, "DEGRADED")
        self.assertIn("open_interest", result.diagnostics["required_stale_derivative_fields"])

    def test_same_snapshot_100_times_has_identical_signal_json(self) -> None:
        values = [
            json.dumps(self._scan(AppConfig(), 900_000).signal.as_dict(), sort_keys=True)
            for _ in range(100)
        ]
        self.assertEqual(len(set(values)), 1)

    def test_active_signal_invalidates_on_level_breach(self) -> None:
        result = self._scan(AppConfig(), 900_000)
        assert result.signal
        next_15m = replace(self.candles[2][0], close_time_ms=1_799_999, close=99.0)
        with patch(
            "btc_quant_agent.engine.build_features",
            side_effect=[features(), features(), features(close=99.0)],
        ):
            reason = QuantEngine(AppConfig()).invalidation_reason(
                result.signal,
                self.candles[0],
                self.candles[1],
                [next_15m],
                1_800_000,
            )
        self.assertEqual(reason, "INVALIDATION_LEVEL_BREACHED")

    def test_scan_rejection_paths_have_machine_codes(self) -> None:
        with (
            patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
            patch("btc_quant_agent.engine.build_features", side_effect=ValueError("bad feature")),
        ):
            feature_error = QuantEngine(AppConfig()).scan(*self.candles, None, 900_000)
        self.assertEqual(feature_error.reason_code, "FEATURE_ERROR")

        with (
            patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
            patch("btc_quant_agent.engine.build_features", return_value=features()),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
            patch("btc_quant_agent.engine.find_candidate", return_value=None),
        ):
            no_setup = QuantEngine(AppConfig()).scan(*self.candles, None, 900_000)
        self.assertEqual(no_setup.reason_code, "NO_SETUP")

        blocked = replace(self.assessment, blocked_reason="blocked")
        result = self._scan_with_overrides(assessment=blocked)
        self.assertEqual(result.reason_code, "FACTOR_REJECTED")
        result = self._scan_with_overrides(plan=None)
        self.assertEqual(result.reason_code, "RISK_PLAN_REJECTED")

    def _scan_with_overrides(self, *, assessment=None, plan="default"):
        selected_assessment = assessment or self.assessment
        selected_plan = self.plan if plan == "default" else plan
        with (
            patch("btc_quant_agent.engine.validate_candles", return_value=QualityReport(True, ())),
            patch("btc_quant_agent.engine.build_features", return_value=features()),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
            patch("btc_quant_agent.engine.find_candidate", return_value=self.candidate),
            patch("btc_quant_agent.engine.assess_factors", return_value=selected_assessment),
            patch("btc_quant_agent.engine.build_position_plan", return_value=selected_plan),
        ):
            return QuantEngine(AppConfig()).scan(*self.candles, None, 900_000)

    def test_invalidation_rechecks_ttl_data_regime_macro_and_rr(self) -> None:
        result = self._scan(AppConfig(), 900_000)
        assert result.signal
        engine = QuantEngine(AppConfig())
        self.assertEqual(
            engine.invalidation_reason(
                result.signal, *self.candles, result.signal.expires_at_ms + 1
            ),
            "TTL_EXPIRED",
        )
        self.assertIsNone(engine.invalidation_reason(result.signal, *self.candles, 900_000))

        next_bar = replace(self.candles[2][0], close_time_ms=1_799_999)
        with patch("btc_quant_agent.engine.build_features", side_effect=ValueError("bad")):
            self.assertEqual(
                engine.invalidation_reason(
                    result.signal,
                    self.candles[0],
                    self.candles[1],
                    [next_bar],
                    1_800_000,
                ),
                "DATA_INVALID",
            )
        with (
            patch("btc_quant_agent.engine.build_features", return_value=features(close=105)),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.RANGE),
        ):
            self.assertEqual(
                engine.invalidation_reason(
                    result.signal, self.candles[0], self.candles[1], [next_bar], 1_800_000
                ),
                "REGIME_REVERSED",
            )
        bearish_macro = replace(
            features(close=90),
            ema_mid=95,
            ema_slow=100,
            ema_mid_slope=-1,
            ema_slow_slope=-0.5,
        )
        with (
            patch(
                "btc_quant_agent.engine.build_features",
                side_effect=[bearish_macro, features(105), features(105)],
            ),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
        ):
            self.assertEqual(
                engine.invalidation_reason(
                    result.signal, self.candles[0], self.candles[1], [next_bar], 1_800_000
                ),
                "MACRO_4H_CONFLICT",
            )
        with (
            patch("btc_quant_agent.engine.build_features", return_value=features(close=123)),
            patch("btc_quant_agent.engine.classify_regime", return_value=Regime.TREND_UP),
        ):
            self.assertEqual(
                engine.invalidation_reason(
                    result.signal, self.candles[0], self.candles[1], [next_bar], 1_800_000
                ),
                "RR_BELOW_MINIMUM",
            )


if __name__ == "__main__":
    unittest.main()
