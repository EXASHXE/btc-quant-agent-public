"""Live V1 Execution Coordinator with execute_approved_intent entrypoint."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..account_watch.models import AccountSnapshotV1
    from ..account_watch.service import AccountWatch
    from ..live_market.models import MarketObservationV1
    from ..live_market.service import MarketStreamService
    from ..position_supervisor.supervisor import PositionSupervisor
from ..approval.store import LiveStore
from ..position_supervisor.kill_switch import KillSwitch
from ..position_supervisor.models import PositionObservationV1
from .backend import DryRunExecutionBackend, ExecutionReport, TestnetExecutionBackend
from .guard import ExecutionBlocked
from .intents import IntentStore, TradeIntentV1
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
        *,
        tactical_regime_provider: Callable[[str], str | None] | None = None,
        funding_rate_provider: Callable[[str], float | None] | None = None,
        oi_change_provider: Callable[[str], float | None] | None = None,
        volatility_provider: Callable[[str], float | None] | None = None,
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
        self.tactical_regime_provider = tactical_regime_provider
        self.funding_rate_provider = funding_rate_provider
        self.oi_change_provider = oi_change_provider
        self.volatility_provider = volatility_provider

    def _build_position_observation(
        self,
        intent: TradeIntentV1,
        report: ExecutionReport,
        account_snap: AccountSnapshotV1,
        market_obs: MarketObservationV1,
        now_ms: int,
    ) -> PositionObservationV1:
        # Extract verified source-bound evidence and signal identity from actual case in live_store
        evidence_id: str | None = None
        signal_identity: str | None = None
        try:
            case = self.live_store.get_case(intent.case_id)
            evidence_id = case.evidence_id
            signal_identity = case.signal_identity
        except KeyError:
            pass

        # Source-bound market and tactical inputs (None if unavailable, no fabricated neutral values)
        funding_rate = self.funding_rate_provider(intent.symbol) if self.funding_rate_provider else None
        oi_change_pct = self.oi_change_provider(intent.symbol) if self.oi_change_provider else None
        volatility = self.volatility_provider(intent.symbol) if self.volatility_provider else None
        tactical_regime = self.tactical_regime_provider(intent.symbol) if self.tactical_regime_provider else None

        return PositionObservationV1.build(
            account_snapshot_hash=account_snap.snapshot_hash,
            market_source_hash=market_obs.observation_hash,
            symbol=intent.symbol,
            observed_at_ms=now_ms,
            quantity=report.filled_qty if intent.side == "BUY" else -report.filled_qty,
            previous_quantity=0.0,
            entry_price=report.avg_price,
            mark_price=market_obs.mark_price,
            unrealized_pnl_usdt=0.0,
            realized_pnl_usdt=0.0,
            margin_usdt=(report.filled_qty * report.avg_price) / intent.leverage,
            stop_price=intent.stop_loss,
            take_profit_price=intent.take_profit_1,
            funding_rate=funding_rate,
            oi_change_pct=oi_change_pct,
            volatility_percentile=volatility,
            spread_bps=market_obs.spread_bps,
            tactical_regime=tactical_regime,
            grid_boundary_breached=False,
            order_status=report.status,
            order_filled_quantity=report.filled_qty,
            order_observed_at_ms=now_ms,
            evidence_id=evidence_id,
            signal_identity=signal_identity,
            add_opportunity=False,
        )

    async def execute_approved_intent(
        self, intent_id: str, now_ms: int | None = None
    ) -> ExecutionReport:
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

        # If fill occurred and supervisor is present, orchestrate end-to-end position supervision
        if report.filled_qty > 0 and self.supervisor is not None:
            obs = self._build_position_observation(intent, report, account_snap, market_obs, now)
            await self.supervisor.process(obs, now)

        return report

    def execute_approved_intent_sync(
        self, intent_id: str, now_ms: int | None = None
    ) -> ExecutionReport:
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.execute_approved_intent(intent_id, now_ms)).result()
        return asyncio.run(self.execute_approved_intent(intent_id, now_ms))

    async def reconcile_intent(
        self, intent_id: str, now_ms: int | None = None
    ) -> ExecutionReport:
        now = self.clock_ms() if now_ms is None else now_ms
        intent = self.intent_store.get_intent(intent_id)
        if intent is None:
            raise KeyError(f"unknown intent: {intent_id}")

        backend: DryRunExecutionBackend | TestnetExecutionBackend
        if intent.environment == "TESTNET":
            if self.testnet_backend is None:
                raise ExecutionBlocked("TESTNET backend is not configured")
            backend = self.testnet_backend
        else:
            backend = self.dry_run_backend

        report = backend.reconcile_intent(intent, now)
        self.intent_store.update_status(intent_id, report.status, reason=report.reason, now_ms=now)

        if report.filled_qty > 0 and self.supervisor is not None:
            market_obs = self.market_stream.latest_observation(now)
            account_snap = self.account_watch.latest_snapshot()
            if market_obs is not None and account_snap is not None:
                obs = self._build_position_observation(intent, report, account_snap, market_obs, now)
                await self.supervisor.process(obs, now)

        return report

    def reconcile_intent_sync(
        self, intent_id: str, now_ms: int | None = None
    ) -> ExecutionReport:
        try:
            asyncio.get_running_loop()
            in_loop = True
        except RuntimeError:
            in_loop = False

        if in_loop:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                return pool.submit(asyncio.run, self.reconcile_intent(intent_id, now_ms)).result()
        return asyncio.run(self.reconcile_intent(intent_id, now_ms))
