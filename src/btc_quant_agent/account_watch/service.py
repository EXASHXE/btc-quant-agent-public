"""Authoritative Account Watch service with signed REST reconciliation and User Data Stream."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

from ..config import AppConfig, ExecutionConfig
from ..execution.binance_signed import BinanceSignedClient
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
    ) -> None:
        exec_cfg = config.execution if isinstance(config, AppConfig) else config
        self.config = exec_cfg
        self.store = store
        self.signed_client = signed_client
        self.account_id = account_id
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))

        mode = getattr(exec_cfg, "mode", "paper")
        if mode == "testnet":
            self.environment = "TESTNET"
            self.credential_namespace = "BINANCE_TESTNET"
            self.rest_base_url = "https://testnet.binancefuture.com"
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
                        filled_quantity=min(filled, qty),
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

        self.store.save(snapshot, event_type="REST_RECONCILED")
        self._latest_snapshot = snapshot
        return snapshot

    def mark_stream_disconnected(self, now_ms: int | None = None) -> None:
        """Mark account state unreconciled on user-stream disconnect."""
        now = self.clock_ms() if now_ms is None else now_ms
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

    async def run_reconciliation_loop(self, interval_seconds: float = 30.0) -> None:
        while not self._stop_event.is_set():
            try:
                self.reconcile_rest()
            except Exception:  # noqa: BLE001,S110 - keep reconciliation loop resilient
                pass
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval_seconds)
            except TimeoutError:
                pass

    def stop(self) -> None:
        self._stop_event.set()
        if self._stream_task and not self._stream_task.done():
            self._stream_task.cancel()
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
