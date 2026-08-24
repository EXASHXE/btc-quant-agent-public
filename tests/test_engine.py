import unittest

from helpers import candles

from btc_quant_agent.config import AppConfig
from btc_quant_agent.engine import QuantEngine


class EngineTests(unittest.TestCase):
    def test_flat_market_returns_wait_without_inventing_probability(self) -> None:
        four_hour = candles(500, "4h", 14_400_000)
        end_ms = four_hour[-1].close_time_ms
        one_hour = candles(500, "1h", 3_600_000, start=end_ms + 1 - 500 * 3_600_000)
        fifteen = candles(500, "15m", 900_000, start=end_ms + 1 - 500 * 900_000)
        now = end_ms + 1
        result = QuantEngine(AppConfig()).scan(four_hour, one_hour, fifteen, None, now)
        self.assertEqual(result.action, "WAIT")
        self.assertIsNone(result.signal)


if __name__ == "__main__":
    unittest.main()
