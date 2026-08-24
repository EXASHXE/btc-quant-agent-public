import unittest
from dataclasses import replace

from helpers import signal

from btc_quant_agent.backtest import (
    FundingEvent,
    TradeOutcome,
    bootstrap,
    metrics,
    monte_carlo,
    resolve_signal,
)
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

    def test_funding_is_charged_only_when_position_crosses_settlement(self) -> None:
        entry = Candle("BTCUSDT", "1m", 60_000, 119_999, 100, 101, 99.5, 100.5, 10)
        exit_bar = Candle("BTCUSDT", "1m", 120_000, 179_999, 100.5, 104, 100, 103, 10)
        event = FundingEvent(120_000, 0.001, 100.0)
        charged = resolve_signal(signal(), [entry, exit_bar], funding_events=[event])
        not_crossed = resolve_signal(
            signal(), [entry, exit_bar], funding_events=[FundingEvent(60_000, 0.001)]
        )
        self.assertLess(charged.funding_pnl_usdt, 0)
        self.assertEqual(not_crossed.funding_pnl_usdt, 0)
        self.assertLess(charged.net_pnl_usdt or 0, not_crossed.net_pnl_usdt or 0)

    def test_metrics_and_resampling_statistics_cover_research_outputs(self) -> None:
        outcomes = [
            TradeOutcome(
                "w",
                "WIN",
                100,
                102,
                2.0,
                0,
                60_000,
                gross_pnl_usdt=2.0,
                net_pnl_usdt=1.8,
                holding_minutes=1,
            ),
            TradeOutcome(
                "l1",
                "LOSS",
                100,
                99,
                -1.0,
                60_000,
                120_000,
                gross_pnl_usdt=-1.0,
                net_pnl_usdt=-1.2,
                holding_minutes=1,
            ),
            TradeOutcome("l2", "LOSS", 100, 99, -0.5, 120_000, 180_000, holding_minutes=1),
        ]
        summary = metrics(outcomes)
        self.assertEqual(summary["trades"], 3)
        self.assertEqual(summary["max_losing_streak"], 2)
        self.assertAlmostEqual(summary["profit_factor"] or 0, 4 / 3)
        self.assertIsNotNone(monte_carlo(outcomes, simulations=20, seed=1)["p95_max_drawdown_r"])
        bootstrapped = bootstrap(outcomes, simulations=20, seed=1, block_size=2)
        self.assertIsNotNone(bootstrapped["p05_expectancy_r"])

    def test_empty_simulations_are_explicitly_null(self) -> None:
        self.assertIsNone(monte_carlo([])["p95_max_drawdown_r"])
        self.assertIsNone(bootstrap([])["p99_max_drawdown_r"])


if __name__ == "__main__":
    unittest.main()
