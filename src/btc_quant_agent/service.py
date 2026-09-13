from __future__ import annotations

import os
import time
from dataclasses import dataclass

from .config import AppConfig
from .data.binance import BinancePublicClient
from .domain import ScanResult, UserDecision
from .engine import EngineMode, QuantEngine
from .execution.service import ExecutionService
from .formal_research import FormalResearchJobSpec
from .notify.feishu import send_invalidation, send_signal
from .shadow import update_formal_shadow
from .storage import Repository
from .time_boundary import validate_clock_skew


@dataclass
class QuantService:
    config: AppConfig
    repository: Repository
    client: BinancePublicClient
    execution: ExecutionService

    @classmethod
    def create(cls, config: AppConfig) -> QuantService:
        repository = Repository(config.storage.sqlite_path)
        client = BinancePublicClient(config.data)
        return cls(config, repository, client, ExecutionService(config, repository, client))

    def scan(self, symbol: str | None = None, notify: bool = True) -> ScanResult:
        symbol = (symbol or self.config.runtime.symbol).upper()
        if symbol != "BTCUSDT":
            raise ValueError("phase one supports BTCUSDT only")
        now_ms = self.client.server_time_ms()
        candles_15m = self.client.klines(symbol, "15m", self.config.data.history_limit_15m)
        candles_1h = self.client.klines(symbol, "1h", self.config.data.history_limit_1h)
        candles_4h = self.client.klines(symbol, "4h", self.config.data.history_limit_4h)
        derivatives = self.client.derivatives(
            symbol, include_order_book=self.config.strategy.enable_order_book_factor
        )
        validate_clock_skew(
            exchange_time_ms=now_ms,
            receipt_time_ms=derivatives.observed_at_ms,
            max_abs_skew_ms=self.config.data.max_clock_skew_ms,
        )
        # Runtime decisions use the explicit receipt/availability clock. Source
        # event timestamps remain exchange timestamps and are sanitized as-of it.
        now_ms = derivatives.observed_at_ms
        engine = QuantEngine(self.config, mode=EngineMode.RUNTIME_GATED)
        self.repository.expire_signals(now_ms)
        webhook = os.getenv("FEISHU_WEBHOOK_URL")
        secret = os.getenv("FEISHU_WEBHOOK_SECRET")
        for active in self.repository.active_signals():
            reason = engine.invalidation_reason(active, candles_4h, candles_1h, candles_15m, now_ms)
            if reason is None or reason == "TTL_EXPIRED":
                continue
            self.repository.invalidate_signal(active.signal_id, reason)
            self.repository.record_event(
                "signal_invalidated", {"signal_id": active.signal_id, "reason": reason}
            )
            if self.config.notify.feishu_enabled and webhook and active.notified_at_ms:
                send_invalidation(webhook, active, reason, secret)
        result = engine.scan(
            candles_4h,
            candles_1h,
            candles_15m,
            derivatives,
            now_ms,
            include_order_book=self.config.strategy.enable_order_book_factor,
        )
        self.repository.record_event("scan", result.as_dict())
        if result.opportunity is not None:
            self.repository.save_opportunity(result.opportunity)
        if result.signal is None:
            return result
        inserted = self.repository.save_signal(result.signal, self.config.runtime.cooldown_minutes)
        if not inserted:
            return ScanResult(
                "WAIT",
                result.health,
                "duplicate signal in cooldown",
                diagnostics=result.diagnostics,
            )
        if notify and self.config.notify.feishu_enabled and webhook:
            send_signal(webhook, result.signal, secret)
            self.repository.mark_signal_notified(result.signal.signal_id, now_ms)
        if self.config.execution.auto_execute:
            try:
                receipt = self.execution.auto_submit(result.signal)
                self.repository.record_event("auto_execution_submitted", receipt.as_dict())
            except Exception as exc:  # noqa: BLE001 - execution boundary records all failures
                self.repository.record_event(
                    "auto_execution_blocked",
                    {"signal_id": result.signal.signal_id, "error": str(exc)},
                )
        return result

    def update_shadow(
        self, spec: FormalResearchJobSpec | None = None, *, output_directory: str | None = None,
    ) -> list[dict[str, object]]:
        if spec is None:
            return [{
                "classification": "NOT_TESTABLE_FOR_NEW_PROMOTION", "execution": "DISABLED",
                "reason": "formal shadow requires an explicit protocol/PIT-evidence job; "
                          "legacy runtime signals are not converted to formal evidence",
            }]
        return update_formal_shadow(spec, output_directory=output_directory)

    def mark_decision(
        self, signal_id: str, decision: str, actual_entry: float | None = None
    ) -> None:
        self.repository.mark_decision(
            signal_id, UserDecision(decision.upper()), actual_entry, int(time.time() * 1000)
        )

    def health(self) -> dict[str, object]:
        from .data.forward_store import ForwardDerivativeStore, scheduler_status
        from .research_registry import RegistryError, load_registry

        registry_status: dict[str, object]
        try:
            registry = load_registry()
            registry_status = {
                "research_registry_gate": "VALID",
                "qualified_direction_engine": "NONE",
                "runtime_actionability": registry.runtime_maximum_stage,
            }
        except RegistryError as exc:
            registry_status = {
                "research_registry_gate": "FAIL_CLOSED",
                "qualified_direction_engine": "NONE",
                "runtime_actionability": "NO_OPPORTUNITY",
                "error": str(exc),
            }
        forward = ForwardDerivativeStore("data/forward/BTCUSDT/derivatives.sqlite3").status(
            scheduler=scheduler_status()
        )
        report: dict[str, object] = {
            "status": "OK",
            "database": self.config.storage.sqlite_path,
            "strategy_version": self.config.runtime.strategy_version,
            "validation_status": self.config.runtime.validation_status,
            "execution": self.execution.status(),
            **registry_status,
            "forward_derivatives": forward,
        }
        try:
            report["binance_public_data"] = self.client.connectivity()
        except Exception as exc:  # noqa: BLE001 - health endpoint must always return a report
            report["status"] = "DEGRADED"
            report["binance_public_data"] = False
            report["error"] = str(exc)
        return report
