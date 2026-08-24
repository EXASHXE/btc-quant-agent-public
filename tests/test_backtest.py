import unittest
from dataclasses import replace

from helpers import signal

from btc_quant_agent.backtest import resolve_signal
from btc_quant_agent.domain import Candle


class BacktestTests(unittest.TestCase):
    def test_stop_first_when_stop_and_target_share_child_bar(self) -> None:
        bar = Candle(
            symbol="BTCUSDT",
            interval="1m",
            open_time_ms=60_000,
            close_time_ms=119_999,
            open=99.5,
            high=105.0,
            low=97.0,
            close=101.0,
            volume=10,
        )
        outcome = resolve_signal(signal(), [bar])
        self.assertEqual(outcome.outcome, "LOSS")
        self.assertAlmostEqual(outcome.r_multiple or 0, -1.0)

    def test_unfilled_entry_is_not_counted_as_trade(self) -> None:
        bar = Candle(
            symbol="BTCUSDT",
            interval="1m",
            open_time_ms=60_000,
            close_time_ms=119_999,
            open=110.0,
            high=111.0,
            low=109.0,
            close=110.0,
            volume=10,
        )
        self.assertEqual(resolve_signal(signal(), [bar]).outcome, "UNFILLED")

    def test_timeout_uses_last_child_bar_not_first_bar_after_deadline(self) -> None:
        first = Candle("BTCUSDT", "1m", 60_000, 119_999, 100, 101.5, 99.5, 101, 10)
        after_deadline = Candle("BTCUSDT", "1m", 120_000, 179_999, 101, 110, 100.5, 109, 10)
        outcome = resolve_signal(
            signal(), [first, after_deadline], max_holding_minutes=1, as_of_ms=180_000
        )
        self.assertEqual(outcome.outcome, "TIMEOUT")
        self.assertEqual(outcome.exit_price, first.close)
        self.assertEqual(outcome.exited_at_ms, first.close_time_ms)

    def test_setup_specific_default_holding_time(self) -> None:
        breakout = replace(signal(), setup=signal().setup.BREAKOUT_RETEST)
        entry = Candle("BTCUSDT", "1m", 60_000, 119_999, 100, 101, 99.5, 100.5, 10)
        last_valid = Candle(
            "BTCUSDT",
            "1m",
            60_000 + 479 * 60_000,
            60_000 + 480 * 60_000 - 1,
            100.5,
            101,
            100,
            100.75,
            10,
        )
        first_after = Candle(
            "BTCUSDT",
            "1m",
            60_000 + 480 * 60_000,
            60_000 + 481 * 60_000 - 1,
            100.75,
            110,
            100,
            109,
            10,
        )
        outcome = resolve_signal(
            breakout, [entry, last_valid, first_after], as_of_ms=first_after.close_time_ms
        )
        self.assertEqual(outcome.outcome, "TIMEOUT")
        self.assertEqual(outcome.exit_price, last_valid.close)


if __name__ == "__main__":
    unittest.main()
