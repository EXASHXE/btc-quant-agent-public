"""Live V1 Execution Coordinator with execute_approved_intent entrypoint."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..account_watch.service import AccountWatch
    from ..live_market.service import MarketStreamService
    from ..position_supervisor.supervisor import PositionSupervisor
from ..approval.store import LiveStore
from ..position_supervisor.kill_switch import KillSwitch
from ..position_supervisor.models import PositionObservationV1
from .backend import DryRunExecutionBackend, ExecutionReport, TestnetExecutionBackend
from .guard import ExecutionBlocked
from .intents import IntentStore
from .validator import PreExecutionValidator


class LiveExecutionService:
    def __init__(
        self,
        intent_store: IntentStore,
        live_store: LiveStore,
        account_watch: AccountWatch,
        market_stream: MarketStreamService,
        validator: PreExecutionValidator,
        kill_switch: KillSwitch,
        dry_run_backend: DryRunExecutionBackend,
        testnet_backend: TestnetExecutionBackend | None = None,
        supervisor: PositionSupervisor | None = None,
        clock_ms: Any = None,
    ) -> None:
        self.intent_store = intent_store
        self.live_store = live_store
        self.account_watch = account_watch
        self.market_stream = market_stream
        self.validator = validator
        self.kill_switch = kill_switch
        self.dry_run_backend = dry_run_backend
        self.testnet_backend = testnet_backend
        self.supervisor = supervisor
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    def execute_approved_intent(self, intent_id: str, now_ms: int | None = None) -> ExecutionReport:
        now = self.clock_ms() if now_ms is None else now_ms
        intent = self.intent_store.get_intent(intent_id)
        if intent is None:
            raise KeyError(f"unknown intent: {intent_id}")

        market_obs = self.market_stream.latest_observation(now)
        if market_obs is None:
            self.intent_store.update_status(intent_id, "ABORTED", reason="MARKET_DATA_UNAVAILABLE", now_ms=now)
            return ExecutionReport(
                intent_id=intent_id,
                status="ABORTED",
                order_id="",
                client_order_id=intent.client_order_id,
                requested_qty=intent.quantity,
                filled_qty=0.0,
                avg_price=0.0,
                reason="MARKET_DATA_UNAVAILABLE",
            )

        account_snap = self.account_watch.latest_snapshot()
        if account_snap is None:
            self.intent_store.update_status(intent_id, "ABORTED", reason="ACCOUNT_SNAPSHOT_UNAVAILABLE", now_ms=now)
            return ExecutionReport(
                intent_id=intent_id,
                status="ABORTED",
                order_id="",
                client_order_id=intent.client_order_id,
                requested_qty=intent.quantity,
                filled_qty=0.0,
                avg_price=0.0,
                reason="ACCOUNT_SNAPSHOT_UNAVAILABLE",
            )

        # Pre-execution validation gate
        val_result = self.validator.validate(intent, market_obs, account_snap, now)
        if not val_result.is_valid:
            self.intent_store.update_status(intent_id, "ABORTED", reason=val_result.reason, now_ms=now)
            return ExecutionReport(
                intent_id=intent_id,
                status="ABORTED",
                order_id="",
                client_order_id=intent.client_order_id,
                requested_qty=intent.quantity,
                filled_qty=0.0,
                avg_price=0.0,
                reason=val_result.reason,
            )

        # Backend selection
        backend: DryRunExecutionBackend | TestnetExecutionBackend
        if intent.environment == "TESTNET":
            if self.testnet_backend is None:
                raise ExecutionBlocked("TESTNET backend is not configured")
            backend = self.testnet_backend
        else:
            backend = self.dry_run_backend

        self.intent_store.update_status(intent_id, "SUBMITTING", reason="SUBMITTING_ORDER", now_ms=now)

        report = backend.submit_intent(intent, now)
        self.intent_store.update_status(intent_id, report.status, reason=report.reason, now_ms=now)

        # If fill occurred and supervisor is present, generate observation
        if report.filled_qty > 0 and self.supervisor is not None:
            obs = PositionObservationV1.build(
                account_snapshot_hash=account_snap.snapshot_hash,
                market_source_hash=market_obs.observation_hash,
                symbol=intent.symbol,
                observed_at_ms=now,
                quantity=report.filled_qty if intent.side == "BUY" else -report.filled_qty,
                previous_quantity=0.0,
                entry_price=report.avg_price,
                mark_price=market_obs.mark_price,
                unrealized_pnl_usdt=0.0,
                realized_pnl_usdt=0.0,
                margin_usdt=(report.filled_qty * report.avg_price) / intent.leverage,
                stop_price=intent.stop_loss,
                take_profit_price=intent.take_profit_1,
                funding_rate=0.0,
                oi_change_pct=0.0,
                volatility_percentile=0.2,
                spread_bps=market_obs.spread_bps,
                tactical_regime="BULLISH" if intent.side == "BUY" else "BEARISH",
                grid_boundary_breached=False,
                order_status=report.status,
                order_filled_quantity=report.filled_qty,
                order_observed_at_ms=now,
                evidence_id="0" * 64,
                signal_identity="live-signal",
                add_opportunity=False,
            )
            self.supervisor.evaluate(obs, now)

        return report
