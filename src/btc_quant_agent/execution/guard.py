from __future__ import annotations

import os

from ..config import ExecutionConfig
from .models import ClosePlan, ExecutionMode, ExecutionPlan


class ExecutionBlocked(RuntimeError):
    pass


class ExecutionGuard:
    def __init__(self, config: ExecutionConfig):
        self.config = config

    def credential_names(self) -> tuple[str, str]:
        if self.config.mode == ExecutionMode.TESTNET.value:
            return "BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET"
        return "BINANCE_API_KEY", "BINANCE_API_SECRET"

    def credentials_present(self) -> bool:
        key_name, secret_name = self.credential_names()
        return bool(os.getenv(key_name) and os.getenv(secret_name))

    def _mode_gate(self, mode: ExecutionMode) -> None:
        configured = ExecutionMode(self.config.mode)
        if configured == ExecutionMode.DISABLED:
            raise ExecutionBlocked("execution.mode=disabled")
        if mode != configured:
            raise ExecutionBlocked("plan mode does not match current execution mode")
        if (
            configured in {ExecutionMode.TESTNET, ExecutionMode.LIVE}
            and not self.credentials_present()
        ):
            raise ExecutionBlocked("mode-specific Binance API credentials are missing")
        if configured == ExecutionMode.LIVE:
            if not self.config.allow_live:
                raise ExecutionBlocked("execution.allow_live=false")
            if os.getenv("BTC_QUANT_LIVE_CONFIRM") != "I_UNDERSTAND_REAL_ORDERS":
                raise ExecutionBlocked("BTC_QUANT_LIVE_CONFIRM is not set to the required phrase")

    def risk_reducing_gate(self, mode: ExecutionMode) -> None:
        configured = ExecutionMode(self.config.mode)
        if configured == ExecutionMode.DISABLED:
            raise ExecutionBlocked("execution.mode=disabled")
        if mode != configured:
            raise ExecutionBlocked("plan mode does not match current execution mode")
        if (
            configured in {ExecutionMode.TESTNET, ExecutionMode.LIVE}
            and not self.credentials_present()
        ):
            raise ExecutionBlocked("mode-specific Binance API credentials are missing")

    def validate_entry(
        self,
        plan: ExecutionPlan,
        confirmation_hash: str,
        now_ms: int,
        open_positions: int = 0,
        daily_realized_loss_usdt: float = 0.0,
        automatic: bool = False,
    ) -> None:
        self._mode_gate(plan.mode)
        if plan.calculated_hash() != plan.plan_hash or confirmation_hash != plan.plan_hash:
            raise ExecutionBlocked("execution plan hash mismatch")
        if now_ms > plan.expires_at_ms:
            raise ExecutionBlocked("execution plan expired")
        if plan.notional_usdt > self.config.max_notional_usdt:
            raise ExecutionBlocked("plan exceeds max_notional_usdt")
        if plan.leverage > self.config.max_leverage:
            raise ExecutionBlocked("plan exceeds max_leverage")
        if plan.mode == ExecutionMode.LIVE and plan.validation_status != "VALIDATED_FORWARD":
            raise ExecutionBlocked("live execution requires VALIDATED_FORWARD")
        if open_positions >= self.config.max_open_positions:
            raise ExecutionBlocked("max_open_positions reached")
        if daily_realized_loss_usdt >= self.config.max_daily_loss_usdt:
            raise ExecutionBlocked("max_daily_loss_usdt reached")
        if automatic:
            if not self.config.auto_execute:
                raise ExecutionBlocked("execution.auto_execute=false")
            if plan.validation_status != "VALIDATED_FORWARD":
                raise ExecutionBlocked("automatic execution requires VALIDATED_FORWARD")
            if os.getenv("BTC_QUANT_AUTO_EXECUTE_CONFIRM") != "ENABLE_AUTO_EXECUTION":
                raise ExecutionBlocked("BTC_QUANT_AUTO_EXECUTE_CONFIRM is missing")

    def validate_close(self, plan: ClosePlan, confirmation_hash: str, now_ms: int) -> None:
        self.risk_reducing_gate(plan.mode)
        if plan.calculated_hash() != plan.plan_hash or confirmation_hash != plan.plan_hash:
            raise ExecutionBlocked("close plan hash mismatch")
        if now_ms > plan.expires_at_ms:
            raise ExecutionBlocked("close plan expired")

    def validate_cancel(self, plan: ExecutionPlan, confirmation_hash: str) -> None:
        self.risk_reducing_gate(plan.mode)
        if plan.calculated_hash() != plan.plan_hash or confirmation_hash != plan.plan_hash:
            raise ExecutionBlocked("execution plan hash mismatch")
