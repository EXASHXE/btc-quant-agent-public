import unittest
from dataclasses import replace

from test_strategies import feature

from btc_quant_agent.config import StrategyConfig
from btc_quant_agent.domain import Regime
from btc_quant_agent.regime import classify_regime


class RegimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = StrategyConfig()

    def test_high_volatility_has_priority(self) -> None:
        item = replace(feature(ema_fast=108), atr_percentile=0.95)
        self.assertEqual(classify_regime(item, self.config), Regime.HIGH_VOLATILITY)

    def test_trend_up(self) -> None:
        item = replace(feature(ema_fast=108), close=110, structure="HH_HL")
        self.assertEqual(classify_regime(item, self.config), Regime.TREND_UP)

    def test_trend_down(self) -> None:
        item = replace(
            feature(ema_fast=92),
            close=90,
            ema_mid=95,
            ema_slow=100,
            ema_mid_slope=-1,
            ema_slow_slope=-0.5,
            structure="LH_LL",
        )
        self.assertEqual(classify_regime(item, self.config), Regime.TREND_DOWN)

    def test_range(self) -> None:
        item = replace(feature(ema_fast=100), close=100, adx=10, structure="MIXED")
        self.assertEqual(classify_regime(item, self.config), Regime.RANGE)

    def test_transition(self) -> None:
        item = replace(feature(ema_fast=100), close=100, adx=18, structure="MIXED")
        self.assertEqual(classify_regime(item, self.config), Regime.TRANSITION)


if __name__ == "__main__":
    unittest.main()
