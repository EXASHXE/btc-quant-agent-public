import unittest

from btc_quant_agent.config import StrategyConfig
from btc_quant_agent.domain import (
    Candidate,
    DerivativesSnapshot,
    Direction,
    Setup,
    TimeframeFeatures,
)
from btc_quant_agent.multifactor import assess_factors


def features(close: float = 110.0, ema_mid: float = 105.0, ema_slow: float = 100.0):
    return TimeframeFeatures(
        close=close,
        ema_fast=108.0,
        ema_mid=ema_mid,
        ema_slow=ema_slow,
        ema_mid_slope=1.0,
        ema_slow_slope=0.5,
        atr=2.0,
        atr_percentile=0.5,
        adx=28.0,
        volume_z=1.0,
        rsi=58.0,
        roc=0.02,
        bb_width_percentile=0.6,
        cvd_slope=10.0,
        cvd_available=True,
        last_swing_high=112.0,
        previous_swing_high=108.0,
        last_swing_low=102.0,
        previous_swing_low=99.0,
        structure="HH_HL",
        bar_open_time_ms=0,
        bar_close_time_ms=1,
    )


class MultiFactorTests(unittest.TestCase):
    def test_aligned_independent_groups_pass(self) -> None:
        candidate = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            109.0,
            110.0,
            102.0,
            125.0,
            80,
            "structure",
            (),
        )
        derivatives = DerivativesSnapshot(
            observed_at_ms=1,
            funding_rate=0.0001,
            open_interest_change_pct=0.02,
            taker_buy_sell_ratio=1.2,
            basis_rate=0.0002,
            long_short_account_ratio=1.1,
            spread_bps=0.5,
            order_book_imbalance=0.2,
        )
        result = assess_factors(
            candidate, features(), features(), features(), derivatives, StrategyConfig()
        )
        self.assertIsNone(result.blocked_reason)
        self.assertGreaterEqual(result.positive_groups, 4)

    def test_macro_misalignment_is_hard_wait(self) -> None:
        candidate = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            109.0,
            110.0,
            102.0,
            125.0,
            80,
            "structure",
            (),
        )
        bearish = features(close=90.0, ema_mid=95.0, ema_slow=100.0)
        result = assess_factors(candidate, bearish, features(), features(), None, StrategyConfig())
        self.assertIn("4H", result.blocked_reason or "")


if __name__ == "__main__":
    unittest.main()
