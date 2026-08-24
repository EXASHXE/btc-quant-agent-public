import unittest
from unittest.mock import patch

from btc_quant_agent.config import StrategyConfig
from btc_quant_agent.domain import Candle, Direction, Pivot, Regime, Setup, TimeframeFeatures
from btc_quant_agent.strategies import breakout_retest, trend_pullback


def feature(
    *,
    ema_fast: float,
    ema_mid: float = 100.0,
    swing_low: float = 90.0,
    swing_high: float = 110.0,
) -> TimeframeFeatures:
    return TimeframeFeatures(
        close=103.0,
        ema_fast=ema_fast,
        ema_mid=ema_mid,
        ema_slow=95.0,
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
        last_swing_high=swing_high,
        previous_swing_high=105.0,
        last_swing_low=swing_low,
        previous_swing_low=85.0,
        structure="HH_HL",
        bar_open_time_ms=0,
        bar_close_time_ms=1,
    )


def bar(index: int, open_: float, high: float, low: float, close: float) -> Candle:
    return Candle(
        "BTCUSDT",
        "15m",
        index * 900_000,
        (index + 1) * 900_000 - 1,
        open_,
        high,
        low,
        close,
        10.0,
    )


class StrategyBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = StrategyConfig()

    def test_insufficient_history_is_rejected(self) -> None:
        self.assertIsNone(trend_pullback([], feature(ema_fast=100), Regime.TREND_UP, self.config))
        self.assertIsNone(breakout_retest([], feature(ema_fast=100), Regime.TREND_UP, self.config))

    @patch(
        "btc_quant_agent.strategies.confirmed_pivots",
        return_value=[Pivot("LOW", 1, 3, 90.0, 0), Pivot("HIGH", 2, 4, 110.0, 0)],
    )
    def test_level_extraction_uses_confirmed_pivots(self, _mock: object) -> None:
        from btc_quant_agent.strategies import _levels

        self.assertEqual(_levels(self._long_pullback(99.9), self.config), ([90.0], [110.0]))

    def _long_pullback(self, pullback_low: float) -> list[Candle]:
        return [
            bar(0, 101, 102, 100.5, 101.5),
            bar(1, 101, 102, 100.4, 101.4),
            bar(2, 101, 102, pullback_low, 101.3),
            bar(3, 101, 102, 100.2, 101.5),
            bar(4, 101.5, 102.5, 100.4, 102.0),
            bar(5, 102.0, 103.5, 101.0, 103.0),
        ]

    @patch("btc_quant_agent.strategies._levels", return_value=([90.0], [110.0]))
    def test_trend_pullback_long_near_ema_zone(self, _mock: object) -> None:
        candidate = trend_pullback(
            self._long_pullback(99.9), feature(ema_fast=102.0), Regime.TREND_UP, self.config
        )
        assert candidate
        self.assertEqual(candidate.direction, Direction.LONG)
        self.assertEqual(candidate.setup, Setup.TREND_PULLBACK)

    @patch("btc_quant_agent.strategies._levels", return_value=([90.0], [110.0]))
    def test_trend_pullback_long_far_below_ema_rejected(self, _mock: object) -> None:
        self.assertIsNone(
            trend_pullback(
                self._long_pullback(95.0),
                feature(ema_fast=102.0),
                Regime.TREND_UP,
                self.config,
            )
        )

    @patch("btc_quant_agent.strategies._levels", return_value=([90.0], [110.0]))
    def test_trend_pullback_long_far_above_ema_rejected(self, _mock: object) -> None:
        candles = self._long_pullback(101.0)
        candles[1] = bar(1, 102, 103, 101.0, 102)
        candles[3] = bar(3, 102, 103, 101.0, 102)
        candles[4] = bar(4, 102, 102.5, 101.0, 102)
        self.assertIsNone(
            trend_pullback(candles, feature(ema_fast=102.0), Regime.TREND_UP, self.config)
        )

    @patch("btc_quant_agent.strategies._levels", return_value=([90.0], [110.0]))
    def test_trend_pullback_short_near_ema_zone(self, _mock: object) -> None:
        candles = [
            bar(0, 99, 99.5, 98, 98.5),
            bar(1, 99, 99.8, 98, 98.5),
            bar(2, 99, 100.2, 98, 98.7),
            bar(3, 99, 99.9, 98, 98.5),
            bar(4, 98.5, 99.5, 97.5, 98.0),
            bar(5, 98.0, 99.0, 96.5, 97.0),
        ]
        candidate = trend_pullback(candles, feature(ema_fast=98.0), Regime.TREND_DOWN, self.config)
        assert candidate
        self.assertEqual(candidate.direction, Direction.SHORT)

    @patch("btc_quant_agent.strategies.confirmed_pivots")
    def test_breakout_retest_long(self, pivots: object) -> None:
        pivots.return_value = [Pivot("HIGH", 2, 4, 100.0, 0)]  # type: ignore[attr-defined]
        candles = [bar(i, 99, 99.8, 98.5, 99.2) for i in range(6)]
        candles.extend([bar(6, 99.8, 101.2, 99.7, 101.0), bar(7, 100.1, 101, 99.9, 100.8)])
        candidate = breakout_retest(candles, feature(ema_fast=99.0), Regime.TREND_UP, self.config)
        assert candidate
        self.assertEqual(candidate.direction, Direction.LONG)

    @patch("btc_quant_agent.strategies.confirmed_pivots")
    def test_breakout_retest_short(self, pivots: object) -> None:
        pivots.return_value = [Pivot("LOW", 2, 4, 100.0, 0)]  # type: ignore[attr-defined]
        candles = [bar(i, 101, 101.5, 100.2, 100.8) for i in range(6)]
        candles.extend([bar(6, 100.2, 100.3, 98.6, 98.8), bar(7, 99.8, 100.1, 99, 99.2)])
        candidate = breakout_retest(
            candles, feature(ema_fast=101.0), Regime.TREND_DOWN, self.config
        )
        assert candidate
        self.assertEqual(candidate.direction, Direction.SHORT)

    @patch("btc_quant_agent.strategies.confirmed_pivots")
    def test_fake_breakout_wick_is_rejected(self, pivots: object) -> None:
        pivots.return_value = [Pivot("HIGH", 2, 4, 100.0, 0)]  # type: ignore[attr-defined]
        candles = [bar(i, 99, 99.8, 98.5, 99.2) for i in range(6)]
        candles.extend([bar(6, 99.8, 101.5, 99.7, 100.1), bar(7, 100, 101, 99.9, 100.8)])
        self.assertIsNone(
            breakout_retest(candles, feature(ema_fast=99), Regime.TREND_UP, self.config)
        )

    @patch("btc_quant_agent.strategies.confirmed_pivots")
    def test_breakout_without_retest_is_rejected(self, pivots: object) -> None:
        pivots.return_value = [Pivot("HIGH", 2, 4, 100.0, 0)]  # type: ignore[attr-defined]
        candles = [bar(i, 99, 99.8, 98.5, 99.2) for i in range(6)]
        candles.extend([bar(6, 99.8, 101.2, 99.7, 101), bar(7, 101.1, 102, 101, 101.8)])
        self.assertIsNone(
            breakout_retest(candles, feature(ema_fast=99), Regime.TREND_UP, self.config)
        )


if __name__ == "__main__":
    unittest.main()
