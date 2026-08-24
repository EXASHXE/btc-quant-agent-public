import unittest

from helpers import candles

from btc_quant_agent.backtest import TradeOutcome
from btc_quant_agent.config import AppConfig
from btc_quant_agent.engine import QuantEngine
from btc_quant_agent.research import (
    ablation_configs,
    replay_decisions,
    research_summary,
    walk_forward_report,
)


class ResearchTests(unittest.TestCase):
    def test_summary_splits_direction_setup_regime_and_year(self) -> None:
        outcome = TradeOutcome(
            "s1",
            "WIN",
            100,
            102,
            1.0,
            1_609_459_200_000,
            1_609_462_800_000,
            direction="LONG",
            setup="TREND_PULLBACK",
            regime="TREND_UP",
        )
        summary = research_summary([outcome])
        self.assertEqual(summary["overall"]["trades"], 1)
        self.assertIn("2021", summary["by_year"])
        self.assertIn("LONG", summary["by_direction"])
        self.assertIn("TREND_PULLBACK", summary["by_setup"])

    def test_ablation_skips_unavailable_point_in_time_groups(self) -> None:
        variants = ablation_configs(AppConfig(), has_derivatives=False)
        self.assertIsNone(variants["D_plus_derivatives"])
        self.assertIsNone(variants["E_plus_order_book"])
        assert variants["C_plus_participation"]
        self.assertFalse(
            variants["C_plus_participation"].strategy.enable_derivatives_group
        )

    def test_walk_forward_is_strictly_chronological(self) -> None:
        folds = walk_forward_report([], 0, 24 * 30 * 86_400_000)
        self.assertGreater(len(folds), 0)
        for fold in folds:
            self.assertLessEqual(fold["train"][1], fold["validation"][0])
            self.assertLessEqual(fold["validation"][1], fold["test"][0])

    def test_replay_emits_each_closed_15m_decision_without_future_data(self) -> None:
        rows = replay_decisions(candles(60, "1m", 60_000), QuantEngine(AppConfig()))
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["timestamp_ms"], 900_000)
        self.assertIn(rows[0]["decision"], {"WAIT", "NO_SIGNAL"})


if __name__ == "__main__":
    unittest.main()
