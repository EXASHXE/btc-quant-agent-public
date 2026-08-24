import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from helpers import signal

from btc_quant_agent.config import AppConfig, ExecutionConfig
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.service import ExecutionService
from btc_quant_agent.storage import Repository


class FakePublicClient:
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
        current_signal = replace(signal(), created_at_ms=1_000_000, expires_at_ms=2_000_000)
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


if __name__ == "__main__":
    unittest.main()
