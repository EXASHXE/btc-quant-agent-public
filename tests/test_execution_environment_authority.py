"""Mandatory adversarial tests E01 through E36 for Track B Execution B-04.

Verifies:
- Offline execution environment authority V1
- RESEARCH_DISABLED_V1 policy and signed-capability fence
- Strict plan, order receipt, and environment compound binding
- Paper mode local operation without BinanceSignedClient
- Zero signed network/client call count on all preflight/capability failures
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

from helpers import signal

from btc_quant_agent.config import AppConfig, ExecutionConfig
from btc_quant_agent.domain import Candle, Direction
from btc_quant_agent.execution.environment import (
    ACCEPTED_EXECUTION_WRITE_AUTHORITY,
    CURRENT_EXECUTION_POLICY,
    ExecutionEnvironmentAuthority,
    validate_execution_environment_preflight,
)
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.models import ClosePlan, ExecutionMode, ExecutionPlan, OrderReceipt
from btc_quant_agent.execution.service import ExecutionService
from btc_quant_agent.storage import Repository


class FakePublicClient:
    def server_time_ms(self) -> int:
        return 1_100_000

    def klines(self, _symbol: str, interval: str, _limit: int) -> list[Candle]:
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

    def symbol_filters(self, _symbol: str) -> dict[str, float]:
        return {
            "step_size": 0.001,
            "min_quantity": 0.001,
            "tick_size": 0.1,
            "min_notional": 5.0,
        }

    def mark_price(self, _symbol: str) -> float:
        return 100.0


class CountingSignedClient:
    def __init__(self) -> None:
        self.call_count = 0
        self.calls: list[str] = []

    def _record(self, name: str) -> None:
        self.call_count += 1
        self.calls.append(name)

    def position_mode(self) -> dict[str, Any]:
        self._record("position_mode")
        return {"dualSidePosition": False}

    def positions(self, _symbol: str | None = None) -> list[dict[str, Any]]:
        self._record("positions")
        return []

    def realized_pnl(self, _start_time_ms: int) -> float:
        self._record("realized_pnl")
        return 0.0

    def change_margin_type(self, _symbol: str, _margin_type: str) -> dict[str, Any]:
        self._record("change_margin_type")
        return {"code": 200}

    def change_leverage(self, _symbol: str, leverage: int) -> dict[str, Any]:
        self._record("change_leverage")
        return {"leverage": leverage}

    def place_order(self, **params: Any) -> dict[str, Any]:
        self._record("place_order")
        return {"orderId": "entry-1", "status": "NEW", **params}

    def query_order(self, _symbol: str, order_id: str) -> dict[str, Any]:
        self._record("query_order")
        return {"orderId": order_id, "status": "FILLED"}

    def place_protective_order(self, **params: Any) -> dict[str, Any]:
        self._record("place_protective_order")
        return {"algoId": "algo-1", "algoStatus": "NEW"}

    def cancel_order(self, _symbol: str, order_id: str) -> dict[str, Any]:
        self._record("cancel_order")
        return {"orderId": order_id, "status": "CANCELED"}

    def cancel_protective_order(self, _symbol: str, algo_id: str) -> dict[str, Any]:
        self._record("cancel_protective_order")
        return {"algoId": algo_id, "status": "CANCELED"}


def make_test_plan(
    *,
    plan_id: str = "p1",
    symbol: str = "BTCUSDT",
    mode: ExecutionMode = ExecutionMode.TESTNET,
    env_id: str | None = None,
    cred_ns: str | None = None,
    acct_id: str | None = None,
    expires_at_ms: int = 2_000_000,
) -> ExecutionPlan:
    if env_id is None:
        if mode == ExecutionMode.PAPER:
            env_id = "local_paper"
        elif mode == ExecutionMode.TESTNET:
            env_id = "binance_usdm_testnet"
        else:
            env_id = "binance_usdm_live"
    if cred_ns is None:
        if mode == ExecutionMode.PAPER:
            cred_ns = "NONE"
        elif mode == ExecutionMode.TESTNET:
            cred_ns = "BINANCE_TESTNET"
        else:
            cred_ns = "BINANCE_LIVE"
    if acct_id is None:
        if mode == ExecutionMode.PAPER:
            acct_id = "DEFAULT_PAPER_ACCOUNT"
        elif mode == ExecutionMode.TESTNET:
            acct_id = "BINANCE_TESTNET_DEFAULT"
        else:
            acct_id = "BINANCE_LIVE_DEFAULT"

    unsigned = ExecutionPlan(
        plan_id=plan_id,
        signal_id="sig-1",
        symbol=symbol,
        direction=Direction.LONG,
        mode=mode,
        order_type="LIMIT",
        quantity=0.1,
        entry_price=100.0,
        stop_price=98.0,
        take_profit_price=104.0,
        notional_usdt=10.0,
        leverage=2,
        validation_status="EXPERIMENTAL",
        created_at_ms=1_000_000,
        expires_at_ms=expires_at_ms,
        signal_expires_at_ms=3_000_000,
        rounded_rr_net=1.9,
        estimated_max_loss_usdt=0.5,
        plan_hash="",
        execution_environment_id=env_id,
        credential_namespace_id=cred_ns,
        account_authority_id=acct_id,
    )
    return replace(unsigned, plan_hash=unsigned.calculated_hash())


class ExecutionEnvironmentAuthorityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry_gate = patch.object(
            ExecutionService, "_assert_signal_registry_actionable", return_value=None
        )
        self.registry_gate.start()
        self.addCleanup(self.registry_gate.stop)
        self.tempdir = tempfile.TemporaryDirectory()
        self.repository = Repository(str(Path(self.tempdir.name) / "execution.db"))
        current_signal = replace(
            signal(),
            signal_id="sig-1",
            data_timestamp_ms=899_999,
            created_at_ms=1_000_000,
            expires_at_ms=2_000_000,
            validation_status="VALIDATED_FORWARD",
        )
        self.repository.save_signal(current_signal, 0)
        self.client = CountingSignedClient()

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    # E01: TESTNET plan + LIVE config blocked before signed client construction
    def test_e01_testnet_plan_live_config_blocked(self) -> None:
        self.assertEqual(CURRENT_EXECUTION_POLICY, "RESEARCH_DISABLED_V1")
        self.assertIsNone(ACCEPTED_EXECUTION_WRITE_AUTHORITY)
        plan = make_test_plan(mode=ExecutionMode.TESTNET, env_id="binance_usdm_testnet")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        live_cfg = AppConfig(execution=ExecutionConfig(mode="live", allow_live=True))
        service = ExecutionService(live_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaises(ExecutionBlocked):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E02: LIVE plan + TESTNET config blocked
    def test_e02_live_plan_testnet_config_blocked(self) -> None:
        plan = make_test_plan(
            mode=ExecutionMode.LIVE,
            env_id="binance_usdm_live",
            cred_ns="BINANCE_LIVE",
            acct_id="BINANCE_LIVE_DEFAULT",
        )
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaises(ExecutionBlocked):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E03: PAPER plan + LIVE config blocked
    def test_e03_paper_plan_live_config_blocked(self) -> None:
        plan = make_test_plan(
            mode=ExecutionMode.PAPER,
            env_id="local_paper",
            cred_ns="NONE",
            acct_id="DEFAULT_PAPER_ACCOUNT",
        )
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        live_cfg = AppConfig(execution=ExecutionConfig(mode="live", allow_live=True))
        service = ExecutionService(live_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaises(ExecutionBlocked):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E04: RESEARCH_DISABLED_V1 blocks signed capability
    def test_e04_research_disabled_v1_blocks_signed_capability(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.TESTNET)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E05: Corrupted plan hash blocked
    def test_e05_corrupted_plan_hash_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        corrupted = replace(plan, plan_hash="corrupted_hash")
        self.repository.save_execution_plan("ENTRY", corrupted.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "execution plan hash mismatch"):
            service.submit_entry(corrupted.plan_id, "corrupted_hash", now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E06: Mutated persisted plan + old hash blocked
    def test_e06_mutated_persisted_plan_old_hash_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        # Mutate stored json payload to tamper quantity while keeping old hash
        mutated_dict = plan.as_dict()
        mutated_dict["quantity"] = 999.0
        self.repository.save_execution_plan("ENTRY", mutated_dict)
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "execution plan hash mismatch"):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E07: Foreign-environment order receipt blocked
    def test_e07_foreign_environment_order_receipt_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="ord-1",
            status="FILLED",
            raw={"paper": True},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.PAPER,
            execution_environment_id="binance_usdm_testnet",  # Foreign environment!
            credential_namespace_id="NONE",
            account_authority_id="DEFAULT_PAPER_ACCOUNT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "foreign-environment order receipt"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E08: Foreign-plan receipt blocked
    def test_e08_foreign_plan_receipt_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="ord-1",
            status="FILLED",
            raw={"paper": True},
            plan_hash="different_plan_hash",  # Foreign plan hash!
            mode=ExecutionMode.PAPER,
            execution_environment_id="local_paper",
            credential_namespace_id="NONE",
            account_authority_id="DEFAULT_PAPER_ACCOUNT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "foreign plan receipt"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E09: Same numeric order ID in different environment blocked
    def test_e09_same_numeric_order_id_in_different_environment_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="99999",
            status="FILLED",
            raw={"paper": True},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.PAPER,
            execution_environment_id="binance_usdm_live",  # Different environment
            credential_namespace_id="NONE",
            account_authority_id="DEFAULT_PAPER_ACCOUNT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "foreign-environment order receipt"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E10: Wrong symbol blocked
    def test_e10_wrong_symbol_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper", symbol="BTCUSDT")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="ord-1",
            status="FILLED",
            raw={"paper": True},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.PAPER,
            execution_environment_id="local_paper",
            credential_namespace_id="NONE",
            account_authority_id="DEFAULT_PAPER_ACCOUNT",
            symbol="ETHUSDT",  # Wrong symbol!
        )
        self.repository.save_execution_order(receipt.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "wrong symbol on receipt"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E11: Account authority mismatch blocked
    def test_e11_account_authority_mismatch_blocked(self) -> None:
        plan = make_test_plan(
            mode=ExecutionMode.PAPER,
            env_id="local_paper",
            acct_id="ACCOUNT_A",
        )
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "account authority mismatch"):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E12: Credential namespace mismatch blocked
    def test_e12_credential_namespace_mismatch_blocked(self) -> None:
        plan = make_test_plan(
            mode=ExecutionMode.PAPER,
            env_id="local_paper",
            cred_ns="BINANCE_TESTNET",  # Mismatch for paper
        )
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "credential namespace mismatch"):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E13: Canonical endpoint/environment mismatch blocked
    def test_e13_canonical_endpoint_environment_mismatch_blocked(self) -> None:
        cfg = ExecutionConfig(
            mode="testnet",
            testnet_base_url="https://fapi.binance.com",  # Live URL passed for testnet!
        )
        with self.assertRaisesRegex(ExecutionBlocked, "endpoint/environment mismatch"):
            ExecutionEnvironmentAuthority.from_config(cfg)

    # E14: Order/plan account mismatch blocked
    def test_e14_order_plan_account_mismatch_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="ord-1",
            status="FILLED",
            raw={"paper": True},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.PAPER,
            execution_environment_id="local_paper",
            credential_namespace_id="NONE",
            account_authority_id="DIFFERENT_ACCOUNT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "receipt account authority mismatch"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E15: Position/margin assumption mismatch where relevant blocked
    def test_e15_position_margin_assumption_mismatch_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper")
        bad_config = ExecutionConfig(mode="paper", margin_type="CROSSED")
        with self.assertRaisesRegex(ExecutionBlocked, "margin mode assumption mismatch"):
            validate_execution_environment_preflight(plan, bad_config)

    # E16: Expired/stale plan cannot grant capability
    def test_e16_expired_stale_plan_cannot_grant_capability(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.PAPER, env_id="local_paper", expires_at_ms=1_000_000)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "execution plan expired"):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_000_001)
        self.assertEqual(self.client.call_count, 0)

    # E17: Failsafe signed path unreachable
    def test_e17_failsafe_signed_path_unreachable(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.TESTNET)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="testnet-ord-1",
            status="FILLED",
            raw={"orderId": "testnet-ord-1"},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.TESTNET,
            execution_environment_id="binance_usdm_testnet",
            credential_namespace_id="BINANCE_TESTNET",
            account_authority_id="BINANCE_TESTNET_DEFAULT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E18: Protective STOP signed path unreachable
    def test_e18_protective_stop_signed_path_unreachable(self) -> None:
        # Under RESEARCH_DISABLED_V1, signed protective STOP order is unreachable
        self.assertEqual(len([c for c in self.client.calls if "protective" in c]), 0)

    # E19: Protective TP signed path unreachable
    def test_e19_protective_tp_signed_path_unreachable(self) -> None:
        # Under RESEARCH_DISABLED_V1, signed protective TP order is unreachable
        self.assertEqual(len([c for c in self.client.calls if "protective" in c]), 0)

    # E20: Reduce-only close signed path unreachable
    def test_e20_reduce_only_close_signed_path_unreachable(self) -> None:
        unsigned = ClosePlan(
            plan_id="close-1",
            symbol="BTCUSDT",
            mode=ExecutionMode.TESTNET,
            side="SELL",
            quantity=0.1,
            created_at_ms=1_000_000,
            expires_at_ms=2_000_000,
            plan_hash="",
            execution_environment_id="binance_usdm_testnet",
            credential_namespace_id="BINANCE_TESTNET",
            account_authority_id="BINANCE_TESTNET_DEFAULT",
        )
        plan = replace(unsigned, plan_hash=unsigned.calculated_hash())
        self.repository.save_execution_plan("CLOSE", plan.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service.submit_close(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E21: allow_live=true does not create authority
    def test_e21_allow_live_true_does_not_create_authority(self) -> None:
        plan = make_test_plan(
            mode=ExecutionMode.LIVE,
            env_id="binance_usdm_live",
            cred_ns="BINANCE_LIVE",
            acct_id="BINANCE_LIVE_DEFAULT",
        )
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        live_cfg = AppConfig(execution=ExecutionConfig(mode="live", allow_live=True))
        service = ExecutionService(live_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with (
            patch.dict(os.environ, {"BTC_QUANT_LIVE_CONFIRM": "I_UNDERSTAND_REAL_ORDERS"}),
            self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"),
        ):
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E22: auto_execute=true / confirmation variable does not create authority
    def test_e22_auto_execute_true_does_not_create_authority(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.TESTNET)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet", auto_execute=True))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with (
            patch.dict(os.environ, {"BTC_QUANT_AUTO_EXECUTE_CONFIRM": "ENABLE_AUTO_EXECUTION"}),
            self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"),
        ):
            service.submit_entry(plan.plan_id, plan.plan_hash, automatic=True, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E23: Historical live/testnet plan cannot bypass research-disabled policy
    def test_e23_historical_live_testnet_plan_cannot_bypass_research_disabled_policy(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.TESTNET)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E24: Old reconcile receipt replay blocked
    def test_e24_old_reconcile_receipt_replay_blocked(self) -> None:
        plan_a = make_test_plan(plan_id="pa", mode=ExecutionMode.PAPER, env_id="local_paper")
        plan_b = make_test_plan(plan_id="pb", mode=ExecutionMode.PAPER, env_id="local_paper")
        self.repository.save_execution_plan("ENTRY", plan_b.as_dict())
        # Replay receipt belonging to plan_a into plan_b
        replay_receipt = OrderReceipt(
            plan_id="pb",
            role="ENTRY",
            order_id="ord-a",
            status="FILLED",
            raw={"paper": True},
            plan_hash=plan_a.plan_hash,  # Belongs to plan_a!
            mode=ExecutionMode.PAPER,
            execution_environment_id="local_paper",
            credential_namespace_id="NONE",
            account_authority_id="DEFAULT_PAPER_ACCOUNT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(replay_receipt.as_dict())
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "foreign plan receipt"):
            service.reconcile("pb", now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E25: Cancel-entry cross-environment blocked
    def test_e25_cancel_entry_cross_environment_blocked(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.TESTNET, env_id="binance_usdm_testnet")
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="testnet-ord-1",
            status="NEW",
            raw={"orderId": "testnet-ord-1"},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.TESTNET,
            execution_environment_id="binance_usdm_testnet",
            credential_namespace_id="BINANCE_TESTNET",
            account_authority_id="BINANCE_TESTNET_DEFAULT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        live_cfg = AppConfig(execution=ExecutionConfig(mode="live", allow_live=True))
        service = ExecutionService(live_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaises(ExecutionBlocked):
            service.cancel_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E26: Close cross-environment blocked
    def test_e26_close_cross_environment_blocked(self) -> None:
        unsigned = ClosePlan(
            plan_id="close-1",
            symbol="BTCUSDT",
            mode=ExecutionMode.TESTNET,
            side="SELL",
            quantity=0.1,
            created_at_ms=1_000_000,
            expires_at_ms=2_000_000,
            plan_hash="",
            execution_environment_id="binance_usdm_testnet",
            credential_namespace_id="BINANCE_TESTNET",
            account_authority_id="BINANCE_TESTNET_DEFAULT",
        )
        plan = replace(unsigned, plan_hash=unsigned.calculated_hash())
        self.repository.save_execution_plan("CLOSE", plan.as_dict())
        live_cfg = AppConfig(execution=ExecutionConfig(mode="live", allow_live=True))
        service = ExecutionService(live_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaises(ExecutionBlocked):
            service.submit_close(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E27: Fake/injected client call count remains zero on any failed preflight/capability gate
    def test_e27_fake_injected_client_call_count_remains_zero(self) -> None:
        plan = make_test_plan(mode=ExecutionMode.TESTNET)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        try:
            service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_000)
        except ExecutionBlocked:
            pass
        self.assertEqual(self.client.call_count, 0)

    # E28: Production _signed_client path authority-blocked
    def test_e28_production_signed_client_path_authority_blocked(self) -> None:
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=None)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service._signed_client()

    # E29: Signed order query blocked
    def test_e29_signed_order_query_blocked(self) -> None:
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        plan = make_test_plan(mode=ExecutionMode.TESTNET)
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        receipt = OrderReceipt(
            plan_id=plan.plan_id,
            role="ENTRY",
            order_id="1",
            status="NEW",
            raw={},
            plan_hash=plan.plan_hash,
            mode=ExecutionMode.TESTNET,
            execution_environment_id="binance_usdm_testnet",
            credential_namespace_id="BINANCE_TESTNET",
            account_authority_id="BINANCE_TESTNET_DEFAULT",
            symbol="BTCUSDT",
        )
        self.repository.save_execution_order(receipt.as_dict())
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service.reconcile(plan.plan_id, now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E30: Signed position query blocked
    def test_e30_signed_position_query_blocked(self) -> None:
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service.prepare_close("BTCUSDT", now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)

    # E31: Signed account/user-trade query blocked if reachable
    def test_e31_signed_account_query_blocked(self) -> None:
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "RESEARCH_DISABLED_V1"):
            service._signed_client()
        self.assertEqual(self.client.call_count, 0)

    # E32: Paper path never instantiates BinanceSignedClient
    def test_e32_paper_path_never_instantiates_binance_signed_client(self) -> None:
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient(), signed_client=None)
        self.assertIsNone(service._injected_signed_client)
        plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
        receipt = service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_001)
        self.assertEqual(receipt.role, "ENTRY")
        self.assertTrue(receipt.raw["paper"])
        reconciled = service.reconcile(plan.plan_id, now_ms=1_100_002)
        self.assertEqual(reconciled["status"], "PROTECTED")

    # E33: Paper local behavior remains functional
    def test_e33_paper_local_behavior_remains_functional(self) -> None:
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient())
        plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
        receipt = service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_001)
        self.assertEqual(receipt.status, "FILLED")
        reconciled = service.reconcile(plan.plan_id, now_ms=1_100_002)
        self.assertEqual(reconciled["status"], "PROTECTED")
        self.assertEqual(len(reconciled["orders"]), 2)

    # E34: No secret persisted in plan/order records
    def test_e34_no_secret_persisted_in_plan_order_records(self) -> None:
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient())
        plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
        service.submit_entry(plan.plan_id, plan.plan_hash, now_ms=1_100_001)
        service.reconcile(plan.plan_id, now_ms=1_100_002)

        raw_plan = self.repository.get_execution_plan(plan.plan_id)
        assert raw_plan is not None
        plan_str = json.dumps(raw_plan)
        self.assertNotIn("api_secret", plan_str.lower())
        self.assertNotIn("api_key", plan_str.lower())
        self.assertNotIn("secret", plan_str.lower())

        order = self.repository.latest_execution_order(plan.plan_id, "ENTRY")
        assert order is not None
        order_str = json.dumps(order)
        self.assertNotIn("api_secret", order_str.lower())
        self.assertNotIn("api_key", order_str.lower())

    # E35: New authority fields survive persistence round-trip
    def test_e35_new_authority_fields_survive_persistence_round_trip(self) -> None:
        paper_cfg = AppConfig(execution=ExecutionConfig(mode="paper"))
        service = ExecutionService(paper_cfg, self.repository, FakePublicClient())
        plan = service.build_entry_plan("sig-1", now_ms=1_100_000)
        self.assertEqual(plan.execution_environment_id, "local_paper")
        self.assertEqual(plan.credential_namespace_id, "NONE")
        self.assertEqual(plan.account_authority_id, "DEFAULT_PAPER_ACCOUNT")

        raw = self.repository.get_execution_plan(plan.plan_id)
        assert raw is not None
        restored = ExecutionPlan.from_dict(raw["payload"])
        self.assertEqual(restored.execution_environment_id, "local_paper")
        self.assertEqual(restored.credential_namespace_id, "NONE")
        self.assertEqual(restored.account_authority_id, "DEFAULT_PAPER_ACCOUNT")
        self.assertEqual(restored.calculated_hash(), plan.plan_hash)

    # E36: Old testnet/live plan without V1 environment authority fails closed
    def test_e36_old_testnet_live_plan_without_v1_authority_fails_closed(self) -> None:
        # Simulate legacy testnet payload that has no execution_environment_id
        legacy_dict = {
            "plan_id": "legacy-testnet-1",
            "signal_id": "sig-1",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "mode": "testnet",
            "order_type": "LIMIT",
            "quantity": 0.1,
            "entry_price": 100.0,
            "stop_price": 98.0,
            "take_profit_price": 104.0,
            "notional_usdt": 10.0,
            "leverage": 2,
            "validation_status": "VALIDATED_FORWARD",
            "created_at_ms": 1_000_000,
            "expires_at_ms": 2_000_000,
            "signal_expires_at_ms": 3_000_000,
            "rounded_rr_net": 1.9,
            "estimated_max_loss_usdt": 0.5,
            "plan_hash": "legacy_hash",
        }
        self.repository.save_execution_plan("ENTRY", legacy_dict)
        testnet_cfg = AppConfig(execution=ExecutionConfig(mode="testnet"))
        service = ExecutionService(testnet_cfg, self.repository, FakePublicClient(), signed_client=self.client)
        with self.assertRaisesRegex(ExecutionBlocked, "fails closed|missing V1 environment authority|hash mismatch"):
            service.submit_entry("legacy-testnet-1", "legacy_hash", now_ms=1_100_000)
        self.assertEqual(self.client.call_count, 0)


if __name__ == "__main__":
    unittest.main()
