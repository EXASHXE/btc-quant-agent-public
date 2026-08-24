import unittest

from btc_quant_agent.config import RiskConfig, StrategyConfig
from btc_quant_agent.domain import Candidate, Direction, Setup
from btc_quant_agent.risk import build_position_plan


class RiskTests(unittest.TestCase):
    def setUp(self) -> None:
        self.candidate = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            99.5,
            100.5,
            98.0,
            110.0,
            80,
            "structure",
            (),
        )
        self.strategy = StrategyConfig(stop_atr_buffer=0.0, rr_min=1.0)

    def test_position_size_includes_fees(self) -> None:
        without = build_position_plan(
            self.candidate,
            2.0,
            self.strategy,
            RiskConfig(taker_fee_rate=0.0, slippage_bps_per_side=0.0),
        )
        with_fees = build_position_plan(
            self.candidate,
            2.0,
            self.strategy,
            RiskConfig(taker_fee_rate=0.001, slippage_bps_per_side=0.0),
        )
        assert without and with_fees
        self.assertLess(with_fees.recommended_notional, without.recommended_notional)
        self.assertGreater(with_fees.estimated_fee_usdt, 0)

    def test_position_size_includes_slippage(self) -> None:
        without = build_position_plan(
            self.candidate,
            2.0,
            self.strategy,
            RiskConfig(taker_fee_rate=0.0, slippage_bps_per_side=0.0),
        )
        with_slippage = build_position_plan(
            self.candidate,
            2.0,
            self.strategy,
            RiskConfig(taker_fee_rate=0.0, slippage_bps_per_side=10.0),
        )
        assert without and with_slippage
        self.assertLess(with_slippage.recommended_notional, without.recommended_notional)

    def test_position_size_includes_funding(self) -> None:
        without = build_position_plan(
            self.candidate, 2.0, self.strategy, RiskConfig(funding_rate_estimate=0.0)
        )
        with_funding = build_position_plan(
            self.candidate, 2.0, self.strategy, RiskConfig(funding_rate_estimate=0.002)
        )
        assert without and with_funding
        self.assertLess(with_funding.recommended_notional, without.recommended_notional)
        self.assertGreater(with_funding.estimated_funding_usdt, 0)

    def test_estimated_loss_never_exceeds_risk_budget(self) -> None:
        config = RiskConfig(
            account_equity_usdt=500.0,
            risk_per_trade=0.007,
            max_notional_usdt=10_000.0,
            taker_fee_rate=0.0007,
            slippage_bps_per_side=8.0,
            funding_rate_estimate=0.001,
        )
        plan = build_position_plan(self.candidate, 2.0, self.strategy, config)
        assert plan
        self.assertLessEqual(
            plan.risk_usdt, config.account_equity_usdt * config.risk_per_trade + 1e-12
        )

    def test_notional_cap_still_applies(self) -> None:
        config = RiskConfig(
            account_equity_usdt=100_000.0,
            risk_per_trade=0.01,
            max_notional_usdt=75.0,
        )
        plan = build_position_plan(self.candidate, 2.0, self.strategy, config)
        assert plan
        self.assertEqual(plan.recommended_notional, 75.0)

    def test_min_notional_handling(self) -> None:
        config = RiskConfig(
            account_equity_usdt=10.0,
            risk_per_trade=0.001,
            min_notional_usdt=5.0,
        )
        self.assertIsNone(build_position_plan(self.candidate, 2.0, self.strategy, config))

    def test_short_plan_is_symmetric_and_includes_adverse_funding(self) -> None:
        candidate = Candidate(
            Direction.SHORT,
            Setup.TREND_PULLBACK,
            99.5,
            100.5,
            102.0,
            90.0,
            80,
            "structure",
            (),
        )
        plan = build_position_plan(candidate, 2.0, self.strategy, RiskConfig(), funding_rate=-0.001)
        assert plan
        self.assertGreater(plan.stop_loss, plan.entry_reference)
        self.assertGreater(plan.estimated_funding_usdt, 0)

    def test_invalid_price_geometry_is_rejected(self) -> None:
        invalid = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            99.5,
            100.5,
            101.0,
            110.0,
            80,
            "structure",
            (),
        )
        self.assertIsNone(build_position_plan(invalid, 0.0, self.strategy, RiskConfig()))

    def test_risk_sizing_is_independent_of_display_leverage(self) -> None:
        candidate = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            99.5,
            100.5,
            98.0,
            106.0,
            80,
            "structure",
            (),
        )
        strategy = StrategyConfig(stop_atr_buffer=0.25, rr_min=1.8)
        low_leverage = build_position_plan(candidate, 2.0, strategy, RiskConfig(display_leverage=5))
        high_leverage = build_position_plan(
            candidate, 2.0, strategy, RiskConfig(display_leverage=20)
        )
        self.assertIsNotNone(low_leverage)
        self.assertIsNotNone(high_leverage)
        assert low_leverage and high_leverage
        self.assertAlmostEqual(
            low_leverage.recommended_notional, high_leverage.recommended_notional
        )
        self.assertAlmostEqual(low_leverage.required_margin / 4, high_leverage.required_margin)

    def test_low_rr_is_rejected_after_costs(self) -> None:
        candidate = Candidate(
            Direction.LONG,
            Setup.TREND_PULLBACK,
            99.5,
            100.5,
            98.0,
            103.0,
            80,
            "structure",
            (),
        )
        self.assertIsNone(
            build_position_plan(candidate, 2.0, StrategyConfig(rr_min=1.8), RiskConfig())
        )


if __name__ == "__main__":
    unittest.main()
