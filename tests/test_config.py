import unittest

from btc_quant_agent.config import BacktestConfig, RiskConfig, RuntimeConfig


class ConfigTests(unittest.TestCase):
    def test_unsafe_or_unsupported_values_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RiskConfig(min_notional_usdt=101, max_notional_usdt=100)
        with self.assertRaises(ValueError):
            RuntimeConfig(decision_interval="5m")
        with self.assertRaises(ValueError):
            BacktestConfig(trend_pullback_holding_minutes=0)


if __name__ == "__main__":
    unittest.main()
