import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from helpers import signal

from btc_quant_agent.config import AppConfig, ExecutionConfig
from btc_quant_agent.domain import Candle
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.service import ExecutionService
from btc_quant_agent.storage import Repository


class FakePublicClient:
    def server_time_ms(self) -> int:
        return 1_100_000

    def klines(self, _symbol: str, interval: str, _limit: int):
        duration = {"15m": 900_000, "1h": 3_600_000, "4h": 14_400_000}[interval]
        return [
            Candle(
                "BTCUSDT",
                interval,
                900_000 - duration,
                899_999,
                100,
                101,
                99,
                100,
                10,
            )
        ]

    def symbol_filters(self, symbol: str) -> dict[str, float]:
        return {
            "step_size": 0.001,
            "min_quantity": 0.001,
            "tick_size": 0.1,
            "min_notional": 5.0,
        }


class FakeSignedClient:
    def __init__(self) -> None:
        self.protective: list[dict[str, object]] = []

    def position_mode(self):
        return {"dualSidePosition": False}

    def positions(self, symbol=None):
        return []

    def realized_pnl(self, start_time_ms):
        return 0.0

    def change_margin_type(self, symbol, margin_type):
        return {"code": 200}

    def change_leverage(self, symbol, leverage):
        return {"leverage": leverage}

    def place_order(self, **params):
        return {"orderId": "entry-1", "status": "NEW", **params}

    def query_order(self, symbol, order_id):
        return {"orderId": order_id, "status": "FILLED"}

    def place_protective_order(self, **params):
        self.protective.append(params)
        return {"algoId": f"algo-{len(self.protective)}", "algoStatus": "NEW"}

    def cancel_order(self, symbol, order_id):
        return {"orderId": order_id, "status": "CANCELED"}

    def cancel_protective_order(self, symbol, algo_id):
        return {"algoId": algo_id, "status": "CANCELED"}


class ExecutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.repository = Repository(str(Path(self.tempdir.name) / "execution.db"))
        current_signal = replace(
            signal(),
            data_timestamp_ms=899_999,
            created_at_ms=1_000_000,
            expires_at_ms=2_000_000,
        )
        self.repository.save_signal(current_signal, 0)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def test_default_mode_cannot_submit_even_with_valid_plan_hash(self) -> None:
        service = ExecutionService(AppConfig(), self.repository, FakePublicClient())
        plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
        with self.assertRaisesRegex(ExecutionBlocked, "disabled"):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_001)

    def test_paper_mode_records_order_without_credentials(self) -> None:
        config = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(config, self.repository, FakePublicClient())
        plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
        receipt = service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_001)
        self.assertEqual(receipt.role, "ENTRY")
        self.assertTrue(receipt.raw["paper"])
        reconciled = service.reconcile(plan.plan_id)
        self.assertEqual(reconciled["status"], "PROTECTED")
        self.assertEqual(len(reconciled["orders"]), 2)

    def test_testnet_entry_reconciles_both_protective_orders(self) -> None:
        config = AppConfig(execution=ExecutionConfig(mode="testnet"))
        signed = FakeSignedClient()
        service = ExecutionService(
            config, self.repository, FakePublicClient(), signed_client=signed
        )
        with patch.dict(
            "os.environ",
            {
                "BINANCE_TESTNET_API_KEY": "test-key",
                "BINANCE_TESTNET_API_SECRET": "test-secret",
            },
        ):
            plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_001)
            with self.assertRaisesRegex(ExecutionBlocked, "already"):
                service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_002)
            reconciled = service.reconcile(plan.plan_id)
        self.assertEqual(reconciled["status"], "PROTECTED")
        self.assertEqual(len(signed.protective), 2)

    def test_degraded_signal_cannot_prepare(self) -> None:
        degraded = replace(
            signal(),
            signal_id="degraded",
            fingerprint="degraded-fingerprint",
            data_timestamp_ms=899_999,
            expires_at_ms=2_000_000,
            data_health="DEGRADED",
        )
        self.repository.save_signal(degraded, 0)
        service = ExecutionService(
            AppConfig(execution=ExecutionConfig(mode="paper")),
            self.repository,
            FakePublicClient(),
        )
        with self.assertRaisesRegex(ExecutionBlocked, "data_health"):
            service.build_entry_plan("degraded", now_ms=1_100_000)

    def test_direction_aware_rounding_preserves_geometry_and_risk(self) -> None:
        item = replace(
            signal(),
            signal_id="short",
            fingerprint="short-fingerprint",
            direction=signal().direction.SHORT,
            data_timestamp_ms=899_999,
            expires_at_ms=2_000_000,
            entry_low=99.91,
            entry_high=100.09,
            stop_loss=102.01,
            take_profit=95.09,
        )
        self.repository.save_signal(item, 0)
        plan = ExecutionService(AppConfig(), self.repository, FakePublicClient()).build_entry_plan(
            "short", now_ms=1_100_000
        )
        self.assertGreater(plan.stop_price, plan.entry_price)
        self.assertLess(plan.take_profit_price, plan.entry_price)
        self.assertLessEqual(plan.estimated_max_loss_usdt, item.max_loss_usdt)


if __name__ == "__main__":
    unittest.main()
