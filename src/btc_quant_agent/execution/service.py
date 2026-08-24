from __future__ import annotations

import hashlib
import math
import os
import time
from dataclasses import replace
from typing import Any

from ..config import AppConfig
from ..data.binance import BinancePublicClient
from ..domain import Direction, Signal, SignalStatus
from ..storage import Repository
from .binance_signed import BinanceSignedClient
from .guard import ExecutionBlocked, ExecutionGuard
from .models import ClosePlan, ExecutionMode, ExecutionPlan, OrderReceipt


def _floor_to(value: float, increment: float) -> float:
    if increment <= 0:
        raise ExecutionBlocked("exchange filter increment is unavailable")
    return math.floor((value + 1e-12) / increment) * increment


class ExecutionService:
    def __init__(
        self,
        config: AppConfig,
        repository: Repository,
        public_client: BinancePublicClient,
        signed_client: BinanceSignedClient | None = None,
    ):
        self.config = config
        self.repository = repository
        self.public_client = public_client
        self.guard = ExecutionGuard(config.execution)
        self._injected_signed_client = signed_client

    def status(self) -> dict[str, Any]:
        mode = ExecutionMode(self.config.execution.mode)
        credentials_present = (
            self.guard.credentials_present() if mode != ExecutionMode.DISABLED else False
        )
        live_armed = mode != ExecutionMode.LIVE or (
            self.config.execution.allow_live
            and os.getenv("BTC_QUANT_LIVE_CONFIRM") == "I_UNDERSTAND_REAL_ORDERS"
        )
        ready = mode == ExecutionMode.PAPER or (
            mode in {ExecutionMode.TESTNET, ExecutionMode.LIVE}
            and credentials_present
            and live_armed
        )
        return {
            "mode": mode.value,
            "order_submission_enabled": ready,
            "auto_execute": self.config.execution.auto_execute,
            "allow_live": self.config.execution.allow_live,
            "credentials_present": credentials_present,
            "max_notional_usdt": self.config.execution.max_notional_usdt,
            "max_leverage": self.config.execution.max_leverage,
            "max_daily_loss_usdt": self.config.execution.max_daily_loss_usdt,
            "protective_orders_required": self.config.execution.require_protective_orders,
        }

    def _signed_client(self) -> BinanceSignedClient:
        if self._injected_signed_client:
            return self._injected_signed_client
        key_name, secret_name = self.guard.credential_names()
        api_key = os.getenv(key_name, "")
        api_secret = os.getenv(secret_name, "")
        mode = ExecutionMode(self.config.execution.mode)
        base_url = (
            self.config.execution.testnet_base_url
            if mode == ExecutionMode.TESTNET
            else self.config.data.rest_base_url
        )
        return BinanceSignedClient(
            base_url,
            api_key,
            api_secret,
            self.config.execution.recv_window_ms,
            self.config.data.request_timeout_seconds,
        )

    def build_entry_plan(self, signal_id: str, now_ms: int | None = None) -> ExecutionPlan:
        signal = self.repository.get_signal(signal_id)
        if signal is None:
            raise KeyError(f"unknown signal: {signal_id}")
        current = now_ms or int(time.time() * 1000)
        if signal.status != SignalStatus.ACTIVE or current > signal.expires_at_ms:
            raise ExecutionBlocked("only a fresh ACTIVE signal can become an execution plan")
        filters = self.public_client.symbol_filters(signal.symbol)
        entry = (signal.entry_low + signal.entry_high) / 2.0
        entry = _floor_to(entry, filters["tick_size"])
        quantity = _floor_to(signal.recommended_notional / entry, filters["step_size"])
        notional = quantity * entry
        if quantity < filters["min_quantity"] or notional < filters["min_notional"]:
            raise ExecutionBlocked("risk-sized order is below exchange minimum filters")
        created = current
        plan_id = hashlib.sha256(f"entry:{signal.signal_id}:{created}".encode()).hexdigest()[:20]
        unsigned = ExecutionPlan(
            plan_id=plan_id,
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            direction=signal.direction,
            mode=ExecutionMode(self.config.execution.mode),
            order_type=self.config.execution.entry_order_type.upper(),
            quantity=quantity,
            entry_price=entry,
            stop_price=_floor_to(signal.stop_loss, filters["tick_size"]),
            take_profit_price=_floor_to(signal.take_profit, filters["tick_size"]),
            notional_usdt=notional,
            leverage=min(int(signal.display_leverage), self.config.execution.max_leverage),
            validation_status=signal.validation_status,
            created_at_ms=created,
            expires_at_ms=min(
                signal.expires_at_ms,
                created + self.config.execution.plan_ttl_seconds * 1000,
            ),
            signal_expires_at_ms=signal.expires_at_ms,
            plan_hash="",
        )
        plan = replace(unsigned, plan_hash=unsigned.calculated_hash())
        self.repository.save_execution_plan("ENTRY", plan.as_dict())
        return plan

    def submit_entry(
        self,
        plan_id: str,
        confirmation_hash: str,
        automatic: bool = False,
        now_ms: int | None = None,
    ) -> OrderReceipt:
        raw_plan = self.repository.get_execution_plan(plan_id)
        if raw_plan is None or raw_plan["kind"] != "ENTRY":
            raise KeyError(f"unknown entry plan: {plan_id}")
        if raw_plan["status"] != "PREPARED":
            raise ExecutionBlocked(f"entry plan is already {raw_plan['status']}")
        plan = ExecutionPlan.from_dict(raw_plan["payload"])
        current = now_ms or int(time.time() * 1000)
        mode = ExecutionMode(self.config.execution.mode)
        open_positions = 0
        daily_loss = self.repository.daily_realized_loss_usdt(current)
        if mode in {ExecutionMode.TESTNET, ExecutionMode.LIVE}:
            client = self._signed_client()
            dual_side = client.position_mode().get("dualSidePosition")
            if dual_side is True or str(dual_side).lower() == "true":
                raise ExecutionBlocked("hedge mode is enabled; phase two requires ONE_WAY mode")
            open_positions = sum(
                1 for item in client.positions() if abs(float(item.get("positionAmt", 0.0))) > 0
            )
            day_start = current - current % 86_400_000
            exchange_pnl = client.realized_pnl(day_start)
            daily_loss = max(daily_loss, abs(min(exchange_pnl, 0.0)))
        self.guard.validate_entry(
            plan,
            confirmation_hash,
            current,
            open_positions,
            daily_loss,
            automatic,
        )
        if plan.order_type == "MARKET":
            signal = self.repository.get_signal(plan.signal_id)
            if signal is None:
                raise ExecutionBlocked("source signal no longer exists")
            current_mark = self.public_client.mark_price(plan.symbol)
            if not signal.entry_low <= current_mark <= signal.entry_high:
                raise ExecutionBlocked("MARKET entry is outside the immutable signal entry range")
        if mode == ExecutionMode.PAPER:
            raw = {
                "orderId": f"paper-{plan.plan_id}",
                "status": "FILLED",
                "executedPrice": plan.entry_price,
                "paper": True,
            }
        else:
            client = self._signed_client()
            try:
                client.change_margin_type(plan.symbol, self.config.execution.margin_type)
            except Exception as exc:
                if "-4046" not in str(exc):
                    raise
            client.change_leverage(plan.symbol, plan.leverage)
            params: dict[str, Any] = {
                "symbol": plan.symbol,
                "side": "BUY" if plan.direction == Direction.LONG else "SELL",
                "type": plan.order_type,
                "quantity": plan.quantity,
                "newClientOrderId": f"bqa-{plan.plan_id}",
            }
            if plan.order_type == "LIMIT":
                params.update({"price": plan.entry_price, "timeInForce": "GTC"})
            raw = client.place_order(**params)
        receipt = OrderReceipt(
            plan.plan_id,
            "ENTRY",
            str(raw.get("orderId", raw.get("clientOrderId", "unknown"))),
            str(raw.get("status", "NEW")),
            raw,
        )
        self.repository.save_execution_order(receipt.as_dict())
        self.repository.update_execution_plan_status(plan.plan_id, "SUBMITTED")
        return receipt

    def reconcile(self, plan_id: str) -> dict[str, Any]:
        raw_plan = self.repository.get_execution_plan(plan_id)
        if raw_plan is None or raw_plan["kind"] != "ENTRY":
            raise KeyError(f"unknown entry plan: {plan_id}")
        plan = ExecutionPlan.from_dict(raw_plan["payload"])
        entry = self.repository.latest_execution_order(plan_id, "ENTRY")
        if entry is None:
            raise ExecutionBlocked("entry has not been submitted")
        mode = ExecutionMode(self.config.execution.mode)
        if mode == ExecutionMode.DISABLED:
            raise ExecutionBlocked("execution.mode=disabled")
        if mode == ExecutionMode.PAPER:
            paper_receipts: list[dict[str, Any]] = []
            for role, trigger in (
                ("STOP", plan.stop_price),
                ("TAKE_PROFIT", plan.take_profit_price),
            ):
                paper_receipt = OrderReceipt(
                    plan.plan_id,
                    role,
                    f"paper-{role.lower()}-{plan.plan_id}",
                    "NEW",
                    {"paper": True, "triggerPrice": trigger},
                )
                self.repository.save_execution_order(paper_receipt.as_dict())
                paper_receipts.append(paper_receipt.as_dict())
            self.repository.update_execution_plan_status(plan.plan_id, "PROTECTED")
            return {"status": "PROTECTED", "plan_id": plan_id, "orders": paper_receipts}
        client = self._signed_client()
        current = client.query_order(plan.symbol, entry["order_id"])
        order_status = str(current.get("status", "UNKNOWN"))
        if (
            order_status in {"NEW", "PENDING_NEW"}
            and int(time.time() * 1000) > plan.signal_expires_at_ms
        ):
            cancelled = client.cancel_order(plan.symbol, entry["order_id"])
            self.repository.update_execution_plan_status(plan.plan_id, "CANCELLED_EXPIRED")
            return {"status": "CANCELLED_EXPIRED", "plan_id": plan_id, "order": cancelled}
        if order_status not in {"FILLED", "PARTIALLY_FILLED"}:
            return {"status": current.get("status", "UNKNOWN"), "plan_id": plan_id}
        if order_status == "PARTIALLY_FILLED":
            client.cancel_order(plan.symbol, entry["order_id"])
        existing_stop = self.repository.latest_execution_order(plan_id, "STOP")
        existing_take_profit = self.repository.latest_execution_order(plan_id, "TAKE_PROFIT")
        if existing_stop and existing_take_profit:
            return {"status": "PROTECTED", "plan_id": plan_id}
        exit_side = "SELL" if plan.direction == Direction.LONG else "BUY"
        common = {
            "algoType": "CONDITIONAL",
            "symbol": plan.symbol,
            "side": exit_side,
            "closePosition": "true",
            "workingType": "MARK_PRICE",
            "priceProtect": "TRUE",
        }
        receipts: list[dict[str, Any]] = []
        try:
            for role, order_type, trigger in (
                ("STOP", "STOP_MARKET", plan.stop_price),
                ("TAKE_PROFIT", "TAKE_PROFIT_MARKET", plan.take_profit_price),
            ):
                if self.repository.latest_execution_order(plan_id, role):
                    continue
                raw = client.place_protective_order(**common, type=order_type, triggerPrice=trigger)
                protective_receipt = OrderReceipt(
                    plan.plan_id,
                    role,
                    str(raw.get("algoId", raw.get("orderId", "unknown"))),
                    str(raw.get("algoStatus", raw.get("status", "NEW"))),
                    raw,
                )
                self.repository.save_execution_order(protective_receipt.as_dict())
                receipts.append(protective_receipt.as_dict())
        except Exception:
            if self.config.execution.require_protective_orders:
                for receipt in receipts:
                    try:
                        client.cancel_protective_order(plan.symbol, receipt["order_id"])
                    except Exception as cancel_error:  # noqa: BLE001
                        self.repository.record_event(
                            "protective_cancel_failed",
                            {
                                "plan_id": plan.plan_id,
                                "order_id": receipt["order_id"],
                                "error": str(cancel_error),
                            },
                        )
                client.place_order(
                    symbol=plan.symbol,
                    side=exit_side,
                    type="MARKET",
                    quantity=plan.quantity,
                    reduceOnly="true",
                    newClientOrderId=f"bqa-failsafe-{plan.plan_id}",
                )
                self.repository.update_execution_plan_status(plan.plan_id, "FAILSAFE_CLOSED")
            raise
        self.repository.update_execution_plan_status(plan.plan_id, "PROTECTED")
        return {"status": "PROTECTED", "plan_id": plan_id, "orders": receipts}

    def prepare_close(self, symbol: str, now_ms: int | None = None) -> ClosePlan:
        mode = ExecutionMode(self.config.execution.mode)
        self.guard.risk_reducing_gate(mode)
        if mode == ExecutionMode.PAPER:
            raise ExecutionBlocked("paper close requires a simulated fill and is not inferred")
        positions = self._signed_client().positions(symbol.upper())
        position = next(
            (item for item in positions if abs(float(item.get("positionAmt", 0.0))) > 0),
            None,
        )
        if position is None:
            raise ExecutionBlocked("no open position")
        amount = float(position["positionAmt"])
        created = now_ms or int(time.time() * 1000)
        plan_id = hashlib.sha256(f"close:{symbol}:{created}".encode()).hexdigest()[:20]
        unsigned = ClosePlan(
            plan_id,
            symbol.upper(),
            mode,
            "SELL" if amount > 0 else "BUY",
            abs(amount),
            created,
            created + self.config.execution.plan_ttl_seconds * 1000,
            "",
        )
        plan = replace(unsigned, plan_hash=unsigned.calculated_hash())
        self.repository.save_execution_plan("CLOSE", plan.as_dict())
        return plan

    def submit_close(
        self, plan_id: str, confirmation_hash: str, now_ms: int | None = None
    ) -> OrderReceipt:
        raw_plan = self.repository.get_execution_plan(plan_id)
        if raw_plan is None or raw_plan["kind"] != "CLOSE":
            raise KeyError(f"unknown close plan: {plan_id}")
        if raw_plan["status"] != "PREPARED":
            raise ExecutionBlocked(f"close plan is already {raw_plan['status']}")
        plan = ClosePlan.from_dict(raw_plan["payload"])
        self.guard.validate_close(plan, confirmation_hash, now_ms or int(time.time() * 1000))
        raw = self._signed_client().place_order(
            symbol=plan.symbol,
            side=plan.side,
            type="MARKET",
            quantity=plan.quantity,
            reduceOnly="true",
            newClientOrderId=f"bqa-close-{plan.plan_id}",
        )
        receipt = OrderReceipt(
            plan.plan_id,
            "CLOSE",
            str(raw.get("orderId", "unknown")),
            str(raw.get("status", "NEW")),
            raw,
        )
        self.repository.save_execution_order(receipt.as_dict())
        self.repository.update_execution_plan_status(plan.plan_id, "SUBMITTED")
        return receipt

    def cancel_entry(self, plan_id: str, confirmation_hash: str) -> dict[str, Any]:
        raw_plan = self.repository.get_execution_plan(plan_id)
        if raw_plan is None or raw_plan["kind"] != "ENTRY":
            raise KeyError(f"unknown entry plan: {plan_id}")
        plan = ExecutionPlan.from_dict(raw_plan["payload"])
        self.guard.validate_cancel(plan, confirmation_hash)
        entry = self.repository.latest_execution_order(plan_id, "ENTRY")
        if entry is None:
            raise ExecutionBlocked("entry has not been submitted")
        if plan.mode == ExecutionMode.PAPER:
            self.repository.update_execution_plan_status(plan.plan_id, "CANCELLED")
            return {"orderId": entry["order_id"], "status": "CANCELED", "paper": True}
        return self._signed_client().cancel_order(plan.symbol, entry["order_id"])

    def auto_submit(self, signal: Signal) -> OrderReceipt:
        plan = self.build_entry_plan(signal.signal_id)
        return self.submit_entry(plan.plan_id, plan.plan_hash, automatic=True)

    def reconcile_open_plans(self) -> list[dict[str, Any]]:
        if ExecutionMode(self.config.execution.mode) == ExecutionMode.DISABLED:
            return []
        output: list[dict[str, Any]] = []
        for plan_id in self.repository.open_entry_plan_ids():
            try:
                output.append(self.reconcile(plan_id))
            except Exception as exc:  # noqa: BLE001 - reconcile all plans independently
                output.append({"plan_id": plan_id, "status": "ERROR", "error": str(exc)})
        return output
