"""Explicit owner of Live V1 operational services and their async lifecycle."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from .config import ExecutionConfig, LiveV1Config
from .execution.guard import ExecutionBlocked

if TYPE_CHECKING:
    from .account_watch.service import AccountWatch
    from .decision.models import CasePackageV1
    from .decision.service import TacticalLiveService
    from .execution.executor import LiveExecutionService
    from .execution.intents import IntentStore
    from .live_market.service import MarketStreamService
    from .position_supervisor.kill_switch import KillSwitch
    from .position_supervisor.supervisor import PositionSupervisor


class LiveV1Runtime:
    def __init__(
        self, *, config: LiveV1Config, tactical_service: TacticalLiveService,
        market_stream: MarketStreamService, account_watch: AccountWatch,
        intent_store: IntentStore, execution_service: LiveExecutionService,
        supervisor: PositionSupervisor, kill_switch: KillSwitch,
        case_loader: Callable[[str], CasePackageV1] | None = None,
    ) -> None:
        if not config.runtime_enabled:
            raise ValueError("Live V1 operational runtime is disabled")
        if config.execution_mode == "TESTNET" and account_watch.environment != "TESTNET":
            raise ExecutionBlocked("TESTNET account authority required")
        if config.execution_mode == "DRY_RUN" and account_watch.environment != "DRY_RUN":
            raise ExecutionBlocked("DRY_RUN account authority required")
        self.config = config
        self.tactical_service = tactical_service
        self.market_stream = market_stream
        self.account_watch = account_watch
        self.intent_store = intent_store
        self.execution_service = execution_service
        self.supervisor = supervisor
        self.kill_switch = kill_switch
        self._case_loader = case_loader
        self._case_cache: dict[str, CasePackageV1] = {}
        self._position_quantities: dict[str, float] = {}
        self.accepting_risk = False
        self.blocked_reason = "RUNTIME_NOT_STARTED"
        self.tasks: tuple[asyncio.Task[None], ...] = ()
        self._started = False
        self._stop_event = asyncio.Event()
        self._reconcile_lock = asyncio.Lock()

    @classmethod
    def create(cls, config: LiveV1Config, tactical_service: TacticalLiveService) -> LiveV1Runtime:
        """Construct B4 only after a separate runtime switch is enabled."""
        if not config.runtime_enabled:
            raise ValueError("Live V1 operational runtime is disabled")
        from .account_watch.service import AccountWatch
        from .account_watch.store import AccountStore
        from .decision.case import case_from_assessment
        from .execution.backend import DryRunExecutionBackend, TestnetExecutionBackend
        from .execution.binance_signed import create_testnet_signed_client
        from .execution.executor import LiveExecutionService
        from .execution.intents import IntentStore
        from .execution.validator import PreExecutionValidator
        from .live_market.service import MarketStreamService
        from .position_supervisor.kill_switch import KillSwitch
        from .position_supervisor.supervisor import PositionSupervisor

        path = config.sqlite_path
        mode = config.execution_mode
        signed_client = create_testnet_signed_client() if mode == "TESTNET" else None
        account = AccountWatch(ExecutionConfig(mode="testnet" if mode == "TESTNET" else "paper"),
                               AccountStore(path), signed_client=signed_client,
                               account_id=config.account_id)
        market = MarketStreamService(symbol=config.symbol)
        intents = IntentStore(path)
        kill = KillSwitch(path)
        market_watch = tactical_service.market_watch

        case_cache: dict[str, CasePackageV1] = {}

        def scan_case(symbol: str) -> CasePackageV1:
            if market_watch is None:
                raise ValueError("MARKET_WATCH_UNAVAILABLE")
            assessments = market_watch.scan([symbol], False)
            matching = [a for a in assessments if a.symbol == symbol]
            if len(matching) != 1:
                raise ValueError("FRESH_MARKET_CASE_UNAVAILABLE")
            return case_from_assessment(matching[0], ttl_ms=config.case_ttl_ms)

        def fresh_case(symbol: str) -> CasePackageV1:
            case = case_cache.get(symbol)
            now = int(time.time() * 1000)
            if (case is None or case.direction not in {"LONG", "SHORT"}
                    or case.data_quality != "OK" or case.entry_quality not in {"GOOD", "EXCELLENT"}
                    or case.veto_reasons or case.source_errors or case.missing_fields
                    or not case.observed_at_ms <= now < case.expires_at_ms
                    or now - case.observed_at_ms > tactical_service.compiler.policy.max_staleness_ms):
                raise ValueError("FRESH_MARKET_CASE_UNAVAILABLE")
            return case

        def tactical_valid(symbol: str, now_ms: int) -> bool:
            case = fresh_case(symbol)
            return case.observed_at_ms <= now_ms < case.expires_at_ms

        supervisor = PositionSupervisor(path, analysis_service=tactical_service,
                                        fresh_market_case=fresh_case)
        validator = PreExecutionValidator(
            tactical_service.store, intents, kill,
            risk_policy=tactical_service.compiler.policy,
            tactical_validity_provider=tactical_valid,
            tactical_case_provider=lambda symbol, _now: fresh_case(symbol),
        )
        dry = DryRunExecutionBackend(path)
        testnet = (TestnetExecutionBackend(path, signed_client, kill, validator=validator)
                   if signed_client is not None else None)
        execution = LiveExecutionService(intents, tactical_service.store, account, market,
                                         validator, kill, dry, testnet_backend=testnet,
                                         supervisor=supervisor)
        runtime = cls(config=config, tactical_service=tactical_service, market_stream=market,
                   account_watch=account, intent_store=intents, execution_service=execution,
                   supervisor=supervisor, kill_switch=kill, case_loader=scan_case)
        runtime._case_cache = case_cache
        return runtime

    async def _refresh_case(self, symbol: str) -> None:
        if self._case_loader is None:
            return
        operation = asyncio.create_task(asyncio.to_thread(self._case_loader, symbol))
        try:
            case = await asyncio.shield(operation)
        except asyncio.CancelledError:
            await operation
            raise
        case.verify()
        self._case_cache[symbol] = case

    async def reconcile_unfinished_intents(self) -> None:
        async with self._reconcile_lock:
            for intent_id in self.intent_store.unfinished_intent_ids():
                await self.execution_service.reconcile_intent(intent_id)

    async def poll_positions(self, now_ms: int) -> None:
        """Reconcile known orders and observe actual current account quantities."""
        from .position_supervisor.models import PositionObservationV1

        await self.reconcile_unfinished_intents()
        snapshot = self.account_watch.latest_snapshot()
        market = self.market_stream.latest_observation(now_ms)
        if snapshot is not None and any(
            position.symbol != self.config.symbol and position.quantity != 0
            for position in snapshot.positions
        ):
            self.accepting_risk = False
            self.blocked_reason = "UNCONFIGURED_POSITION_SYMBOL"
        if (snapshot is None or market is None or not snapshot.reconciled
                or snapshot.quality != "OK"
                or (self.config.execution_mode == "TESTNET" and not self.account_watch.is_stream_connected)):
            return
        if market.symbol != self.config.symbol:
            self.accepting_risk = False
            self.blocked_reason = "MARKET_SYMBOL_MISMATCH"
            return
        intents = [self.intent_store.get_intent(intent_id)
                   for intent_id in self.intent_store.unfinished_intent_ids()]
        by_symbol = {intent.symbol: intent for intent in intents if intent is not None}
        positions = {position.symbol: position for position in snapshot.positions}
        for symbol in positions.keys() | self._position_quantities.keys():
            if symbol != self.config.symbol:
                continue
            position = positions.get(symbol)
            quantity = position.quantity if position is not None else 0.0
            previous = self._position_quantities.get(symbol, 0.0)
            if quantity == 0 and previous == 0:
                continue
            intent = by_symbol.get(symbol)
            if position is None and intent is None:
                continue
            order = next((item for item in snapshot.orders
                          if intent is not None and item.client_order_id == intent.client_order_id), None)
            entry = (position.entry_price if position is not None
                     else intent.price if intent is not None else 0.0)
            obs = PositionObservationV1.build(
                account_snapshot_hash=snapshot.snapshot_hash,
                market_source_hash=market.observation_hash,
                symbol=symbol, observed_at_ms=now_ms,
                quantity=quantity, previous_quantity=previous,
                entry_price=entry, mark_price=market.mark_price,
                unrealized_pnl_usdt=position.unrealized_pnl_usdt if position is not None else 0.0,
                realized_pnl_usdt=0.0,
                margin_usdt=(abs(quantity) * entry / position.leverage) if position is not None else 0.0,
                stop_price=intent.stop_loss if intent is not None else 0.0,
                take_profit_price=intent.take_profit_1 if intent is not None else 0.0,
                spread_bps=market.spread_bps,
                order_status=order.status if order is not None else "UNKNOWN",
                order_filled_quantity=order.filled_quantity if order is not None else abs(quantity),
                order_observed_at_ms=order.observed_at_ms if order is not None else now_ms,
            )
            await self.supervisor.process(obs, now_ms)
            self._position_quantities[symbol] = quantity

    async def _position_loop(self) -> None:
        while not self._stop_event.is_set():
            await self.poll_positions(int(time.time() * 1000))
            try:
                async with asyncio.timeout(5):
                    await self._stop_event.wait()
            except TimeoutError:
                pass

    async def _rest_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                async with asyncio.timeout(self.config.rest_reconcile_seconds):
                    await self._stop_event.wait()
            except TimeoutError:
                try:
                    snapshot = await self.account_watch.reconcile_rest_async()
                except Exception:  # noqa: BLE001 - any REST failure blocks new risk
                    self.accepting_risk = False
                    self.blocked_reason = "ACCOUNT_REST_RECONCILIATION_FAILED"
                    self.account_watch.mark_stream_disconnected()
                    continue
                try:
                    await self._refresh_case(self.config.symbol)
                    await self.reconcile_unfinished_intents()
                except Exception:  # noqa: BLE001 - recovery failure keeps new risk blocked
                    self.accepting_risk = False
                    self.blocked_reason = "RUNTIME_RECOVERY_FAILED"
                    continue
                self.accepting_risk = bool(
                    snapshot.reconciled and snapshot.quality == "OK"
                    and self.kill_switch.allows_new_risk()
                    and not any(position.symbol != self.config.symbol and position.quantity != 0
                                for position in snapshot.positions)
                    and (self.config.execution_mode != "TESTNET"
                         or self.account_watch.is_stream_connected)
                )
                self.blocked_reason = "" if self.accepting_risk else "ACCOUNT_OR_KILL_NOT_READY"

    async def run_position_outbox(self) -> None:
        while not self._stop_event.is_set():
            await self.supervisor.drain_pending_dispatches(int(time.time() * 1000))
            try:
                async with asyncio.timeout(5):
                    await self._stop_event.wait()
            except TimeoutError:
                pass

    async def start(self) -> None:
        if self._started:
            return
        self.accepting_risk = False
        self.blocked_reason = "RUNTIME_STARTING"
        self._stop_event.clear()
        try:
            restored = self.account_watch.latest_snapshot()
            if restored is not None:
                self._position_quantities = {position.symbol: position.quantity
                                             for position in restored.positions}
            self.account_watch.mark_stream_disconnected()
            await self.account_watch.reconcile_rest_async()
            snapshot = self.account_watch.latest_snapshot()
            if snapshot is None or not snapshot.reconciled or snapshot.quality != "OK":
                raise ExecutionBlocked("ACCOUNT_RECONCILIATION_REQUIRED")
            await self.reconcile_unfinished_intents()
            await self._refresh_case(self.config.symbol)
            await self.supervisor.drain_pending_dispatches(int(time.time() * 1000))
            tasks = [asyncio.create_task(self.market_stream.run_stream(), name="live-v1-market")]
            if self.config.execution_mode == "TESTNET":
                tasks.append(asyncio.create_task(self.account_watch.run_user_stream(),
                                                 name="live-v1-account"))
            tasks.append(asyncio.create_task(self._rest_loop(), name="live-v1-rest"))
            tasks.append(asyncio.create_task(self.run_position_outbox(), name="live-v1-outbox"))
            tasks.append(asyncio.create_task(self._position_loop(), name="live-v1-position"))
            self.tasks = tuple(tasks)
            self._started = True
            self.accepting_risk = self.kill_switch.allows_new_risk()
            self.blocked_reason = "" if self.accepting_risk else "KILL_SWITCH_ACTIVE"
        except Exception:
            await self.stop()
            raise

    async def stop(self) -> None:
        self.accepting_risk = False
        self.blocked_reason = "RUNTIME_STOPPED"
        self._stop_event.set()
        self.market_stream.stop()
        self.account_watch.stop()
        for task in self.tasks:
            # Position reconciliation may be inside a signed REST thread. Let it finish
            # after the stop event, so shutdown never leaves a detached exchange read.
            if task.get_name() != "live-v1-position":
                task.cancel()
        if self.tasks:
            await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.account_watch.close_user_stream()
        self.account_watch.mark_stream_disconnected()
        self._started = False

    async def execute_intent(self, intent_id: str) -> Any:
        reason = self._readiness_reason()
        if reason:
            raise ExecutionBlocked(reason)
        intent = self.intent_store.get_intent(intent_id)
        if intent is None:
            raise KeyError(f"unknown intent: {intent_id}")
        if intent.symbol != self.config.symbol:
            raise ExecutionBlocked("INTENT_SYMBOL_UNCONFIGURED")
        await self._refresh_case(intent.symbol)
        return await self.execution_service.execute_approved_intent(intent_id)

    def _readiness_reason(self) -> str:
        if not self._started or not self.accepting_risk:
            return self.blocked_reason or "LIVE_RUNTIME_NOT_READY"
        if not self.kill_switch.allows_new_risk():
            return "KILL_SWITCH_ACTIVE"
        if any(task.done() for task in self.tasks):
            return "RUNTIME_TASK_FAILED"
        if not self.market_stream.is_connected:
            return "MARKET_STREAM_DISCONNECTED"
        snapshot = self.account_watch.latest_snapshot()
        if snapshot is None or not snapshot.reconciled or snapshot.quality != "OK":
            return "ACCOUNT_RECONCILIATION_REQUIRED"
        if any(position.symbol != self.config.symbol and position.quantity != 0
               for position in snapshot.positions):
            return "UNCONFIGURED_POSITION_SYMBOL"
        if self.config.execution_mode == "TESTNET" and not self.account_watch.is_stream_connected:
            return "ACCOUNT_STREAM_DISCONNECTED"
        return ""

    def status(self) -> dict[str, object]:
        reason = self._readiness_reason()
        return {"enabled": self._started, "execution_mode": self.config.execution_mode,
                "accepting_risk": not reason,
                "account_stream_connected": self.account_watch.is_stream_connected,
                "blocked_reason": reason,
                "tasks_running": sum(not task.done() for task in self.tasks)}
