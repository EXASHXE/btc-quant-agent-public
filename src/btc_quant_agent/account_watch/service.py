"""Authoritative Account Watch service with signed REST reconciliation and User Data Stream."""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections.abc import Callable
from typing import Any, cast

from ..config import AppConfig, ExecutionConfig
from ..execution.binance_signed import BinanceSignedClient
from ..execution.guard import ExecutionBlocked
from .models import AccountSnapshotV1, OrderSide, OrderStatus, OrderV1, PositionV1
from .store import AccountStore


class AccountWatch:
    def __init__(
        self,
        config: ExecutionConfig | AppConfig,
        store: AccountStore,
        signed_client: BinanceSignedClient | None = None,
        account_id: str = "DEFAULT_ACCOUNT",
        clock_ms: Callable[[], int] | None = None,
        websocket_connect: Callable[..., Any] | None = None,
    ) -> None:
        exec_cfg = config.execution if isinstance(config, AppConfig) else config
        self.config = exec_cfg
        self.store = store
        self.signed_client = signed_client
        self.account_id = account_id
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self._websocket_connect = websocket_connect

        mode = getattr(exec_cfg, "mode", "paper").lower()
        if mode == "testnet":
            if self.signed_client is None:
                raise ExecutionBlocked("TESTNET mode requires a signed_client")
            auth = getattr(self.signed_client, "authority", None)
            if (
                auth is None
                or auth.environment != "TESTNET"
                or auth.credential_namespace != "BINANCE_TESTNET"
                or auth.rest_base_url.rstrip("/").lower() != "https://testnet.binancefuture.com"
            ):
                raise ExecutionBlocked("AccountWatch signed client authority mismatch for TESTNET")
            self.environment = auth.environment
            self.credential_namespace = auth.credential_namespace
            self.rest_base_url = auth.rest_base_url
            self.ws_base_url = "wss://stream.binancefuture.com"
        else:
            self.environment = "DRY_RUN"
            self.credential_namespace = "NONE"
            self.rest_base_url = "local://paper"
            self.ws_base_url = "local://ws"

        self._stream_connected: bool = False
        self._reconciled: bool = False
        self._conflict_count: int = 0
        self._last_rest_at_ms: int = 0
        self._peak_equity_usdt: float = 1000.0
        self._stream_task: asyncio.Task[None] | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._listen_key: str | None = None
        self._stop_event = asyncio.Event()

        # Simulated state for DRY_RUN mode
        self._simulated_equity: float = 1000.0
        self._simulated_available: float = 1000.0
        self._simulated_wallet: float = 1000.0
        self._simulated_margin: float = 0.0
        self._simulated_daily_loss: float = 0.0
        self._simulated_drawdown: float = 0.0
        self._simulated_positions: tuple[PositionV1, ...] = ()
        self._simulated_orders: tuple[OrderV1, ...] = ()

        self._latest_snapshot: AccountSnapshotV1 | None = None
        self._last_user_event_ms = 0
        self._user_event_sources: dict[str, tuple[int, str]] = {}
        self._state_generation = 0
        self._rest_lock = threading.Lock()
        self._state_lock = threading.RLock()
        restored = self.store.latest(self.account_id)
        if restored is not None:
            self._latest_snapshot = restored
            self._peak_equity_usdt = restored.peak_equity_usdt
            self._conflict_count = restored.conflict_count
            self._last_rest_at_ms = restored.last_rest_at_ms
            # A process restart invalidates all in-memory stream continuity.
            if restored.environment == "TESTNET" and (restored.reconciled or restored.stream_connected):
                self.mark_stream_disconnected(self.clock_ms())

    @property
    def is_reconciled(self) -> bool:
        return self._reconciled

    @property
    def is_stream_connected(self) -> bool:
        return self._stream_connected

    def set_simulated_state(
        self,
        equity: float = 1000.0,
        available: float = 1000.0,
        wallet: float = 1000.0,
        margin: float = 0.0,
        daily_loss: float = 0.0,
        drawdown: float = 0.0,
        positions: tuple[PositionV1, ...] = (),
        orders: tuple[OrderV1, ...] = (),
    ) -> None:
        self._simulated_equity = equity
        self._simulated_available = available
        self._simulated_wallet = wallet
        self._simulated_margin = margin
        self._simulated_daily_loss = daily_loss
        self._simulated_drawdown = drawdown
        self._simulated_positions = positions
        self._simulated_orders = orders

    def reconcile_rest(self, now_ms: int | None = None) -> AccountSnapshotV1:
        with self._rest_lock:
            return self._reconcile_rest_locked(now_ms)

    def _reconcile_rest_locked(self, now_ms: int | None = None) -> AccountSnapshotV1:
        generation = self._state_generation
        now = self.clock_ms() if now_ms is None else now_ms

        if self.environment == "TESTNET":
            if self.signed_client is None:
                raise RuntimeError("signed client required for TESTNET account reconciliation")
            acct_info = self.signed_client.account_information()
            self.signed_client.balances()
            raw_positions = self.signed_client.positions()
            raw_orders = self.signed_client.open_orders()

            day_start = now - (now % 86_400_000)
            realized_pnl = self.signed_client.realized_pnl(day_start)
            daily_loss = abs(min(0.0, realized_pnl))

            wallet_balance = float(acct_info.get("totalWalletBalance", 0.0))
            margin_balance = float(acct_info.get("totalMarginBalance", wallet_balance))
            available_balance = float(acct_info.get("availableBalance", 0.0))
            margin_used = float(acct_info.get("totalInitialMargin", 0.0))
            equity = margin_balance

            self._peak_equity_usdt = max(self._peak_equity_usdt, equity)
            drawdown = max(0.0, (self._peak_equity_usdt - equity) / self._peak_equity_usdt) if self._peak_equity_usdt > 0 else 0.0

            parsed_positions: list[PositionV1] = []
            for p in raw_positions:
                if str(p.get("positionSide", "BOTH")) != "BOTH":
                    raise ValueError("UNSUPPORTED_HEDGE_POSITION_AUTHORITY")
                qty = float(p.get("positionAmt", 0.0))
                if abs(qty) > 0:
                    entry = float(p.get("entryPrice", 0.0))
                    mark = float(p.get("markPrice", entry))
                    liq = float(p.get("liquidationPrice", 0.0))
                    parsed_positions.append(
                        PositionV1(
                            symbol=str(p["symbol"]),
                            quantity=qty,
                            entry_price=entry,
                            mark_price=mark,
                            unrealized_pnl_usdt=float(p.get("unRealizedProfit", 0.0)),
                            leverage=max(1, int(p.get("leverage", 1))),
                            liquidation_price=liq if liq > 0 else None,
                            margin_type=str(p.get("marginType", "ISOLATED")),
                            observed_at_ms=now,
                        )
                    )

            parsed_orders: list[OrderV1] = []
            for o in raw_orders:
                qty = float(o.get("origQty", 0.0))
                filled = float(o.get("executedQty", 0.0))
                price = float(o.get("price", 0.0))
                avg_price = float(o.get("avgPrice", 0.0))
                stop_px = float(o.get("stopPrice", 0.0))
                status_raw = str(o.get("status", "NEW"))
                valid_statuses: set[str] = {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "REJECTED"}
                status: OrderStatus = status_raw if status_raw in valid_statuses else "NEW"  # type: ignore[assignment]
                side_raw = str(o.get("side", "BUY")).upper()
                side: OrderSide = "SELL" if side_raw == "SELL" else "BUY"
                parsed_orders.append(
                    OrderV1(
                        symbol=str(o["symbol"]),
                        order_id=str(o["orderId"]),
                        client_order_id=str(o.get("clientOrderId", "")),
                        side=side,
                        status=status,
                        order_type=str(o.get("type", "LIMIT")),
                        quantity=qty,
                        filled_quantity=filled,
                        price=price,
                        average_price=avg_price,
                        reduce_only=bool(o.get("reduceOnly", False)),
                        stop_price=stop_px if stop_px > 0 else None,
                        observed_at_ms=now,
                    )
                )

            self._last_rest_at_ms = now
            self._reconciled = True
            quality = "OK"

            snapshot = AccountSnapshotV1.build(
                account_id=self.account_id,
                environment="TESTNET",
                credential_namespace="BINANCE_TESTNET",
                rest_base_url="https://testnet.binancefuture.com",
                observed_at_ms=now,
                last_rest_at_ms=now,
                stream_connected=self._stream_connected,
                reconciled=self._reconciled,
                conflict_count=self._conflict_count,
                equity_usdt=equity,
                available_balance_usdt=available_balance,
                wallet_balance_usdt=wallet_balance,
                margin_used_usdt=margin_used,
                daily_loss_usdt=daily_loss,
                drawdown_pct=min(1.0, drawdown),
                peak_equity_usdt=self._peak_equity_usdt,
                positions=tuple(parsed_positions),
                orders=tuple(parsed_orders),
                quality=quality,
            )
        else:
            self._last_rest_at_ms = now
            self._reconciled = True
            self._peak_equity_usdt = max(self._peak_equity_usdt, self._simulated_equity)
            drawdown = max(0.0, (self._peak_equity_usdt - self._simulated_equity) / self._peak_equity_usdt) if self._peak_equity_usdt > 0 else 0.0

            snapshot = AccountSnapshotV1.build(
                account_id=self.account_id,
                environment="DRY_RUN",
                credential_namespace="NONE",
                rest_base_url="local://paper",
                observed_at_ms=now,
                last_rest_at_ms=now,
                stream_connected=self._stream_connected,
                reconciled=self._reconciled,
                conflict_count=self._conflict_count,
                equity_usdt=self._simulated_equity,
                available_balance_usdt=self._simulated_available,
                wallet_balance_usdt=self._simulated_wallet,
                margin_used_usdt=self._simulated_margin,
                daily_loss_usdt=self._simulated_daily_loss,
                drawdown_pct=min(1.0, drawdown),
                peak_equity_usdt=self._peak_equity_usdt,
                positions=self._simulated_positions,
                orders=self._simulated_orders,
                quality="OK" if self._reconciled else "STALE",
            )

        with self._state_lock:
            if self._state_generation != generation:
                latest = self._latest_snapshot
                if latest is not None:
                    self._conflict_count += 1
                    self._reconciled = False
                    snapshot = AccountSnapshotV1.build(
                        **{**latest.model_dump(exclude={"snapshot_hash"}),
                           "reconciled": False,
                           "quality": "STALE" if latest.quality == "STALE" else "CONFLICT",
                           "conflict_count": self._conflict_count,
                           "observed_at_ms": max(latest.observed_at_ms, now),
                           "last_rest_at_ms": max(latest.last_rest_at_ms, now)}
                    )
            self.store.save(snapshot, event_type="REST_RECONCILED")
            self._latest_snapshot = snapshot
        return snapshot

    def mark_stream_disconnected(self, now_ms: int | None = None) -> None:
        """Mark account state unreconciled on user-stream disconnect."""
        with self._state_lock:
            self._mark_stream_disconnected_locked(now_ms)

    def _mark_stream_disconnected_locked(self, now_ms: int | None = None) -> None:
        now = self.clock_ms() if now_ms is None else now_ms
        self._state_generation += 1
        self._stream_connected = False
        self._reconciled = False
        if self._latest_snapshot is not None:
            unreconciled_snap = AccountSnapshotV1.build(
                account_id=self._latest_snapshot.account_id,
                environment=self._latest_snapshot.environment,
                credential_namespace=self._latest_snapshot.credential_namespace,
                rest_base_url=self._latest_snapshot.rest_base_url,
                observed_at_ms=now,
                last_rest_at_ms=self._latest_snapshot.last_rest_at_ms,
                stream_connected=False,
                reconciled=False,
                conflict_count=self._conflict_count,
                equity_usdt=self._latest_snapshot.equity_usdt,
                available_balance_usdt=self._latest_snapshot.available_balance_usdt,
                wallet_balance_usdt=self._latest_snapshot.wallet_balance_usdt,
                margin_used_usdt=self._latest_snapshot.margin_used_usdt,
                daily_loss_usdt=self._latest_snapshot.daily_loss_usdt,
                drawdown_pct=self._latest_snapshot.drawdown_pct,
                peak_equity_usdt=self._latest_snapshot.peak_equity_usdt,
                positions=self._latest_snapshot.positions,
                orders=self._latest_snapshot.orders,
                quality="STALE",
            )
            self.store.save(unreconciled_snap, event_type="WS_DISCONNECTED")
            self._latest_snapshot = unreconciled_snap

    def latest_snapshot(self) -> AccountSnapshotV1 | None:
        if self._latest_snapshot is not None:
            return self._latest_snapshot
        return self.store.latest(self.account_id)

    def handle_user_event(self, payload: dict[str, object], now_ms: int) -> bool:
        """Apply allowlisted TESTNET account events over a fresh REST baseline."""
        with self._state_lock:
            return self._handle_user_event_locked(payload, now_ms)

    def _handle_user_event_locked(self, payload: dict[str, object], now_ms: int) -> bool:
        if self.environment != "TESTNET" or not isinstance(payload, dict):
            self.mark_stream_disconnected(now_ms)
            return False
        event_type = payload.get("e")
        if event_type == "listenKeyExpired":
            self.mark_stream_disconnected(now_ms)
            return False
        if event_type in {"MARGIN_CALL", "ALGO_UPDATE"}:
            self._conflict_count += 1
            self.mark_stream_disconnected(now_ms)
            return False
        if event_type not in {"ACCOUNT_UPDATE", "ORDER_TRADE_UPDATE"}:
            self.mark_stream_disconnected(now_ms)
            return False
        try:
            event_ms = int(str(payload["E"]))
            tx_ms = int(str(payload.get("T", event_ms)))
        except (KeyError, TypeError, ValueError):
            self.mark_stream_disconnected(now_ms)
            return False
        snap = self.latest_snapshot()
        order_payload = payload.get("o")
        order_key = str(order_payload.get("i")) if isinstance(order_payload, dict) else "ACCOUNT"
        source = str(event_type) + ":" + order_key
        event_digest = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        prior = self._user_event_sources.get(source)
        if prior is not None and event_ms == prior[0] and event_digest == prior[1]:
            return False
        if (not self._reconciled or snap is None or not snap.reconciled
                or event_ms < self._last_user_event_ms or event_ms <= snap.last_rest_at_ms
                or (prior is not None and event_ms <= prior[0])
                or tx_ms < 0):
            self._conflict_count += 1
            self.mark_stream_disconnected(now_ms)
            return False
        try:
            values = snap.model_dump(exclude={"snapshot_hash"})
            values["observed_at_ms"] = max(snap.observed_at_ms, event_ms)
            values["stream_connected"] = True
            if event_type == "ACCOUNT_UPDATE":
                account = payload["a"]
                if not isinstance(account, dict):
                    raise ValueError("invalid account update")
                balances = account.get("B", [])
                positions = account.get("P", [])
                if not isinstance(balances, list) or not isinstance(positions, list):
                    raise ValueError("invalid account update rows")
                wallet = snap.wallet_balance_usdt
                available = snap.available_balance_usdt
                for balance in balances:
                    if not isinstance(balance, dict):
                        raise TypeError("invalid balance row")
                    if balance.get("a") == "USDT":
                        wallet = float(balance["wb"])
                current = {p.symbol: p for p in snap.positions}
                for item in positions:
                    if not isinstance(item, dict):
                        raise TypeError("invalid position row")
                    symbol = str(item["s"])
                    qty = float(item["pa"])
                    if qty == 0:
                        current.pop(symbol, None)
                        continue
                    old_position = current.get(symbol)
                    entry = float(item.get("ep", old_position.entry_price if old_position else 0))
                    unrealized = float(item.get("up", old_position.unrealized_pnl_usdt if old_position else 0))
                    current[symbol] = PositionV1(
                        symbol=symbol, quantity=qty, entry_price=entry,
                        mark_price=old_position.mark_price if old_position else entry,
                        unrealized_pnl_usdt=unrealized,
                        leverage=old_position.leverage if old_position else 1,
                        liquidation_price=old_position.liquidation_price if old_position else None,
                        margin_type=str(item.get("mt", old_position.margin_type if old_position else "ISOLATED")).upper(),
                        observed_at_ms=event_ms,
                    )
                new_positions = tuple(sorted(current.values(), key=lambda p: p.symbol))
                equity = max(0.0, wallet + sum(p.unrealized_pnl_usdt for p in new_positions))
                values.update(wallet_balance_usdt=wallet, available_balance_usdt=available,
                              equity_usdt=equity,
                              positions=new_positions)
            else:
                order = payload["o"]
                if not isinstance(order, dict):
                    raise ValueError("invalid order update")
                status = str(order["X"])
                if status == "EXPIRED_IN_MATCH":
                    status = "EXPIRED"
                if status not in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "REJECTED"}:
                    raise ValueError("unsupported order status")
                order_id = str(order["i"])
                old_orders = {o.order_id: o for o in snap.orders}
                quantity = float(order["q"])
                filled = float(order["z"])
                old_order = old_orders.get(order_id)
                old_orders[order_id] = OrderV1(
                    symbol=str(order["s"]), order_id=order_id,
                    client_order_id=str(order.get("c", "")),
                    side="SELL" if str(order["S"]).upper() == "SELL" else "BUY",
                    status=cast(OrderStatus, status), order_type=str(order.get("o", "UNKNOWN")),
                    quantity=quantity, filled_quantity=filled,
                    price=float(order.get("p", old_order.price if old_order else 0)),
                    average_price=float(order.get("ap", old_order.average_price if old_order else 0)),
                    reduce_only=bool(order.get("R", False)),
                    stop_price=(float(order["sp"]) if float(order.get("sp", 0)) > 0 else None),
                    observed_at_ms=event_ms,
                )
                values["orders"] = tuple(sorted(old_orders.values(), key=lambda o: o.order_id))
            updated = AccountSnapshotV1.build(**values)
        except (KeyError, TypeError, ValueError, OverflowError):
            self.mark_stream_disconnected(now_ms)
            return False
        self.store.save(updated, event_type="WS_UPDATE")
        self._latest_snapshot = updated
        self._last_user_event_ms = max(self._last_user_event_ms, event_ms)
        self._user_event_sources[source] = (event_ms, event_digest)
        self._state_generation += 1
        return True

    async def _keepalive_user_stream(self, listen_key: str) -> None:
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=30 * 60)
            except TimeoutError:
                if self.signed_client is None:
                    return
                await asyncio.to_thread(self.signed_client.keepalive_user_stream, listen_key)

    async def reconcile_rest_async(self, now_ms: int | None = None) -> AccountSnapshotV1:
        """Keep an in-flight REST read owned through task cancellation."""
        operation = asyncio.create_task(asyncio.to_thread(self.reconcile_rest, now_ms))
        cancelled: asyncio.CancelledError | None = None
        while True:
            try:
                result = await asyncio.shield(operation)
                break
            except asyncio.CancelledError as exc:
                if operation.cancelled():
                    raise
                cancelled = exc
        if cancelled is not None:
            raise cancelled
        return result

    async def close_user_stream(self) -> None:
        task = self._keepalive_task
        self._keepalive_task = None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        listen_key, self._listen_key = self._listen_key, None
        if listen_key and self.signed_client is not None:
            try:
                await asyncio.to_thread(self.signed_client.close_user_stream, listen_key)
            except Exception:  # noqa: BLE001,S110 - cleanup is best effort; key is never exposed
                pass

    async def run_user_stream(self) -> None:
        """Own the TESTNET websocket/listen-key lifecycle until stopped."""
        if self.environment != "TESTNET" or self.signed_client is None:
            raise ExecutionBlocked("account user stream requires TESTNET authority")
        auth = getattr(self.signed_client, "authority", None)
        if (auth is None or auth.environment != "TESTNET"
                or auth.credential_namespace != "BINANCE_TESTNET"
                or auth.rest_base_url.rstrip("/").lower() != "https://testnet.binancefuture.com"):
            raise ExecutionBlocked("account user stream authority mismatch for TESTNET")
        if self._websocket_connect is None:
            import websockets
            connect: Callable[..., Any] = cast(Callable[..., Any], websockets.connect)
        else:
            connect = self._websocket_connect
        self._stop_event.clear()
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                listen_key = await asyncio.to_thread(self.signed_client.start_user_stream)
                self._listen_key = listen_key
                self._keepalive_task = asyncio.create_task(self._keepalive_user_stream(listen_key))
                # The Futures TESTNET stream is restricted to this host. Never derive it from
                # a configurable or production REST endpoint.
                url = f"{self.ws_base_url.rstrip('/')}/ws/{listen_key}"
                async with connect(url, open_timeout=15) as socket:
                    self.mark_stream_disconnected(self.clock_ms())
                    try:
                        await self.reconcile_rest_async()
                    except Exception:  # noqa: BLE001 - remain fail-closed until REST repair works
                        raise RuntimeError("account REST repair failed") from None
                    self._stream_connected = True
                    snap = self._latest_snapshot
                    if snap is not None:
                        self._latest_snapshot = AccountSnapshotV1.build(
                            **{**snap.model_dump(exclude={"snapshot_hash"}),
                               "stream_connected": True})
                        self.store.save(self._latest_snapshot, event_type="REST_RECONCILED")
                    backoff = 1.0
                    async for message in socket:
                        if self._stop_event.is_set():
                            break
                        try:
                            payload = json.loads(message)
                            if isinstance(payload, dict):
                                accepted = self.handle_user_event(payload, self.clock_ms())
                                if payload.get("e") == "listenKeyExpired":
                                    break
                                if not accepted and not self._reconciled:
                                    await self.reconcile_rest_async()
                                    self._stream_connected = True
                                    snap = self._latest_snapshot
                                    if snap is not None:
                                        self._latest_snapshot = AccountSnapshotV1.build(
                                            **{**snap.model_dump(exclude={"snapshot_hash"}),
                                               "stream_connected": True})
                                        self.store.save(self._latest_snapshot, event_type="REST_RECONCILED")
                        except (ValueError, TypeError, json.JSONDecodeError):
                            self.mark_stream_disconnected(self.clock_ms())
                            break
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001,S110 - retry without exposing transport/key details
                pass
            finally:
                self.mark_stream_disconnected(self.clock_ms())
                await self.close_user_stream()
            if not self._stop_event.is_set():
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=backoff)
                except TimeoutError:
                    backoff = min(30.0, backoff * 2)

    async def run_reconciliation_loop(self, interval_seconds: float = 30.0) -> None:
        while not self._stop_event.is_set():
            try:
                await self.reconcile_rest_async()
            except Exception:  # noqa: BLE001,S110 - keep reconciliation loop resilient
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        self.mark_stream_disconnected(self.clock_ms())
        # The runtime owns and awaits run_user_stream; this method only requests shutdown.
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
