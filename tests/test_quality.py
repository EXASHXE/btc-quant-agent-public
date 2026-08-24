import unittest

from helpers import candles

from btc_quant_agent.data.quality import validate_candles


class QualityTests(unittest.TestCase):
    def test_valid_closed_sequence(self) -> None:
        bars = candles(10, "15m", 900_000)
        report = validate_candles(bars, "15m", bars[-1].close_time_ms + 1)
        self.assertTrue(report.valid)

    def test_gap_is_rejected(self) -> None:
        bars = candles(10, "15m", 900_000)
        report = validate_candles(bars[:4] + bars[5:], "15m")
        self.assertFalse(report.valid)
        self.assertTrue(any("missing candle" in issue for issue in report.issues))


if __name__ == "__main__":
    unittest.main()
