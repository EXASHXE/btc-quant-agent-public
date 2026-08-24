import os
import unittest
from dataclasses import replace
from unittest.mock import patch

from btc_quant_agent.config import ExecutionConfig
from btc_quant_agent.domain import Direction
from btc_quant_agent.execution.guard import ExecutionBlocked, ExecutionGuard
from btc_quant_agent.execution.models import ClosePlan, ExecutionMode, ExecutionPlan


def entry_plan(mode: ExecutionMode = ExecutionMode.PAPER) -> ExecutionPlan:
    unsigned = ExecutionPlan(
        "p1",
        "s1",
        "BTCUSDT",
        Direction.LONG,
        mode,
        "LIMIT",
        0.1,
        100.0,
        98.0,
        104.0,
        10.0,
        2,
        "EXPERIMENTAL",
        1_000,
        2_000,
        3_000,
        1.9,
        0.5,
        "",
    )
    return replace(unsigned, plan_hash=unsigned.calculated_hash())


def rehash(plan: ExecutionPlan) -> ExecutionPlan:
    unsigned = replace(plan, plan_hash="")
    return replace(unsigned, plan_hash=unsigned.calculated_hash())


class ExecutionGuardTests(unittest.TestCase):
    def test_paper_entry_enforces_hash_expiry_limits_and_loss_gates(self) -> None:
        guard = ExecutionGuard(
            ExecutionConfig(
                mode="paper",
                max_notional_usdt=20,
                max_leverage=3,
                max_open_positions=1,
                max_daily_loss_usdt=2,
            )
        )
        plan = entry_plan()
        guard.validate_entry(plan, plan.plan_hash, 1_500)
        cases = [
            (replace(plan, plan_hash="bad"), plan.plan_hash, 1_500, 0, 0.0, "hash"),
            (plan, plan.plan_hash, 2_001, 0, 0.0, "expired"),
            (rehash(replace(plan, notional_usdt=21)), None, 1_500, 0, 0.0, "notional"),
            (rehash(replace(plan, leverage=4)), None, 1_500, 0, 0.0, "leverage"),
            (plan, plan.plan_hash, 1_500, 1, 0.0, "open_positions"),
            (plan, plan.plan_hash, 1_500, 0, 2.0, "daily_loss"),
        ]
        for candidate, confirmation, now_ms, positions, loss, message in cases:
            with self.subTest(message=message), self.assertRaises(ExecutionBlocked):
                guard.validate_entry(
                    candidate,
                    confirmation or candidate.plan_hash,
                    now_ms,
                    positions,
                    loss,
                )

    def test_automatic_and_live_entries_require_all_explicit_arms(self) -> None:
        automatic = ExecutionGuard(ExecutionConfig(mode="paper", auto_execute=False))
        plan = entry_plan()
        with self.assertRaisesRegex(ExecutionBlocked, "auto_execute"):
            automatic.validate_entry(plan, plan.plan_hash, 1_500, automatic=True)
        auto_guard = ExecutionGuard(ExecutionConfig(mode="paper", auto_execute=True))
        with self.assertRaisesRegex(ExecutionBlocked, "VALIDATED_FORWARD"):
            auto_guard.validate_entry(plan, plan.plan_hash, 1_500, automatic=True)
        validated_auto = rehash(replace(plan, validation_status="VALIDATED_FORWARD"))
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ExecutionBlocked, "AUTO_EXECUTE_CONFIRM"),
        ):
            auto_guard.validate_entry(
                validated_auto, validated_auto.plan_hash, 1_500, automatic=True
            )

        live_config = ExecutionConfig(mode="live", allow_live=True)
        live_guard = ExecutionGuard(live_config)
        live_plan = entry_plan(ExecutionMode.LIVE)
        environment = {
            "BINANCE_API_KEY": "key",
            "BINANCE_API_SECRET": "secret",
            "BTC_QUANT_LIVE_CONFIRM": "I_UNDERSTAND_REAL_ORDERS",
        }
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ExecutionBlocked, "VALIDATED_FORWARD"):
                live_guard.validate_entry(live_plan, live_plan.plan_hash, 1_500)
            validated = replace(live_plan, validation_status="VALIDATED_FORWARD", plan_hash="")
            validated = replace(validated, plan_hash=validated.calculated_hash())
            live_guard.validate_entry(validated, validated.plan_hash, 1_500)
        with (
            patch.dict(os.environ, environment, clear=True),
            self.assertRaisesRegex(ExecutionBlocked, "allow_live"),
        ):
            ExecutionGuard(ExecutionConfig(mode="live")).validate_entry(
                live_plan, live_plan.plan_hash, 1_500
            )
        incomplete = {
            key: value for key, value in environment.items() if key != "BTC_QUANT_LIVE_CONFIRM"
        }
        with (
            patch.dict(os.environ, incomplete, clear=True),
            self.assertRaisesRegex(ExecutionBlocked, "LIVE_CONFIRM"),
        ):
            live_guard.validate_entry(live_plan, live_plan.plan_hash, 1_500)

    def test_disabled_missing_credentials_and_risk_reducing_hashes_are_blocked(self) -> None:
        with self.assertRaisesRegex(ExecutionBlocked, "disabled"):
            ExecutionGuard(ExecutionConfig()).validate_entry(
                entry_plan(ExecutionMode.DISABLED), "x", 1_500
            )
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaisesRegex(ExecutionBlocked, "credentials"),
        ):
            ExecutionGuard(ExecutionConfig(mode="testnet")).validate_entry(
                entry_plan(ExecutionMode.TESTNET), "x", 1_500
            )
        guard = ExecutionGuard(ExecutionConfig(mode="paper"))
        close = ClosePlan("c1", "BTCUSDT", ExecutionMode.PAPER, "SELL", 1.0, 1_000, 2_000, "")
        close = replace(close, plan_hash=close.calculated_hash())
        guard.validate_close(close, close.plan_hash, 1_500)
        guard.validate_cancel(entry_plan(), entry_plan().plan_hash)
        with self.assertRaisesRegex(ExecutionBlocked, "expired"):
            guard.validate_close(close, close.plan_hash, 2_001)
        with self.assertRaisesRegex(ExecutionBlocked, "hash"):
            guard.validate_cancel(entry_plan(), "wrong")


if __name__ == "__main__":
    unittest.main()
