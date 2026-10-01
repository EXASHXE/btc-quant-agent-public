"""Execution backends with exactly-once transport uncertainty handling, partial fills, and protective orders."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ..live_db import connection
from ..position_supervisor.kill_switch import KillSwitch
from .binance_signed import BinanceSignedClient
from .guard import ExecutionBlocked
from .intents import TradeIntentV1
from .policy import ExecutionCapabilityPolicyV1

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ExecutionReport:
    intent_id: str
    status: str  # SUBMITTED, FILLED, PARTIALLY_FILLED, ABORTED, FAILED_CLOSED
    order_id: str
    client_order_id: str
    requested_qty: float
    filled_qty: float
    avg_price: float
    protective_stop_id: str | None = None
    reason: str = ""
    raw: dict[str, Any] | None = None


class ExecutionBackend(Protocol):
    def submit_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport: ...
    def reconcile_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport: ...


class DryRunExecutionBackend:
    """Deterministic simulated execution backend."""

    def __init__(self, db_path: str | Path) -> None:
        self.path = Path(db_path)
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_execution_orders (
                    order_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    client_order_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_qty REAL NOT NULL,
                    filled_qty REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    stop_price REAL,
                    is_protective INTEGER NOT NULL,
                    reduce_only INTEGER NOT NULL,
                    exchange_time_ms INTEGER NOT NULL,
                    receipt_time_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
            """)

    def submit_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport:
        ExecutionCapabilityPolicyV1.check_capability("DRY_RUN", "SUBMIT_INTENT", cred_ns="NONE")
        order_id = f"sim-{intent.intent_id}"

        # In DRY_RUN, simulate full fill at intent price
        filled_qty = intent.quantity
        avg_price = intent.price
        status = "FILLED"

        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            # Idempotency check: if order already exists, return existing
            row = db.execute(
                "SELECT * FROM live_execution_orders WHERE client_order_id=?",
                (intent.client_order_id,),
            ).fetchone()
            if row is not None:
                return ExecutionReport(
                    intent_id=intent.intent_id,
                    status=row["status"],
                    order_id=row["order_id"],
                    client_order_id=row["client_order_id"],
                    requested_qty=row["requested_qty"],
                    filled_qty=row["filled_qty"],
                    avg_price=row["avg_price"],
                    protective_stop_id=f"sim-stop-{intent.intent_id}",
                    reason="IDEMPOTENT_REPLAY",
                )

            # Record entry order
            db.execute(
                "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    intent.intent_id,
                    intent.client_order_id,
                    intent.symbol,
                    intent.side,
                    status,
                    intent.quantity,
                    filled_qty,
                    avg_price,
                    None,
                    0,
                    0,
                    now_ms,
                    now_ms,
                    json.dumps({"dry_run": True, "filled": True}),
                ),
            )

            # Record protective STOP order sized strictly to actual filled quantity
            stop_order_id = f"sim-stop-{intent.intent_id}"
            stop_client_oid = f"bqa-stop-{intent.client_order_id[:16]}"
            db.execute(
                "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    stop_order_id,
                    intent.intent_id,
                    stop_client_oid,
                    intent.symbol,
                    "SELL" if intent.side == "BUY" else "BUY",
                    "NEW",
                    filled_qty,
                    0.0,
                    0.0,
                    intent.stop_loss,
                    1,
                    1,
                    now_ms,
                    now_ms,
                    json.dumps({"dry_run": True, "type": "STOP_MARKET", "stopPrice": intent.stop_loss}),
                ),
            )

        return ExecutionReport(
            intent_id=intent.intent_id,
            status=status,
            order_id=order_id,
            client_order_id=intent.client_order_id,
            requested_qty=intent.quantity,
            filled_qty=filled_qty,
            avg_price=avg_price,
            protective_stop_id=stop_order_id,
            reason="FILLED",
        )

    def reconcile_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_execution_orders WHERE client_order_id=?",
                (intent.client_order_id,),
            ).fetchone()
        if row is None:
            return ExecutionReport(
                intent_id=intent.intent_id,
                status="NOT_FOUND",
                order_id="",
                client_order_id=intent.client_order_id,
                requested_qty=intent.quantity,
                filled_qty=0.0,
                avg_price=0.0,
                reason="ORDER_NOT_FOUND",
            )
        return ExecutionReport(
            intent_id=intent.intent_id,
            status=row["status"],
            order_id=row["order_id"],
            client_order_id=row["client_order_id"],
            requested_qty=row["requested_qty"],
            filled_qty=row["filled_qty"],
            avg_price=row["avg_price"],
            protective_stop_id=f"sim-stop-{intent.intent_id}",
            reason="RECONCILED",
        )


class TestnetExecutionBackend:
    """Binance USD(S)-M Futures Testnet execution backend with exact-once uncertainty handling."""

    __test__ = False

    def __init__(self, db_path: str | Path, signed_client: BinanceSignedClient, kill_switch: KillSwitch) -> None:
        self.path = Path(db_path)
        self.client = signed_client
        self.kill_switch = kill_switch
        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_execution_orders (
                    order_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    client_order_id TEXT NOT NULL UNIQUE,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    requested_qty REAL NOT NULL,
                    filled_qty REAL NOT NULL,
                    avg_price REAL NOT NULL,
                    stop_price REAL,
                    is_protective INTEGER NOT NULL,
                    reduce_only INTEGER NOT NULL,
                    exchange_time_ms INTEGER NOT NULL,
                    receipt_time_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
            """)

    def submit_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport:
        # 1. Capability check
        ExecutionCapabilityPolicyV1.check_capability(
            "TESTNET",
            "SUBMIT_INTENT",
            env_id="binance_usdm_testnet",
            cred_ns="BINANCE_TESTNET",
            rest_url=self.client.base_url,
        )

        # 2. Check local database for existing order with this client_order_id (idempotency)
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_execution_orders WHERE client_order_id=?",
                (intent.client_order_id,),
            ).fetchone()
            if row is not None:
                return ExecutionReport(
                    intent_id=intent.intent_id,
                    status=row["status"],
                    order_id=row["order_id"],
                    client_order_id=row["client_order_id"],
                    requested_qty=row["requested_qty"],
                    filled_qty=row["filled_qty"],
                    avg_price=row["avg_price"],
                    reason="LOCAL_IDEMPOTENT_REPLAY",
                )

        # 3. Setup margin type and leverage
        try:
            self.client.change_margin_type(intent.symbol, "ISOLATED")
        except Exception as exc:
            if "-4046" not in str(exc):  # -4046 = No need to change margin type
                raise
        self.client.change_leverage(intent.symbol, intent.leverage)

        # 4. Submit order with transport uncertainty handling
        params: dict[str, Any] = {
            "symbol": intent.symbol,
            "side": intent.side,
            "type": intent.order_type,
            "quantity": intent.quantity,
            "newClientOrderId": intent.client_order_id,
        }
        if intent.order_type == "LIMIT":
            params["price"] = intent.price
            params["timeInForce"] = "GTC"

        raw_order: dict[str, Any]
        try:
            raw_order = self.client.place_order(**params)
        except Exception:  # noqa: BLE001
            # Transport uncertainty rule:
            # Query order by client_order_id immediately before failing or retrying!
            try:
                raw_order = self.client.query_order_by_client_id(intent.symbol, intent.client_order_id)
            except Exception as query_exc:
                # If query proves order does not exist (-2013)
                if "-2013" in str(query_exc):
                    return ExecutionReport(
                        intent_id=intent.intent_id,
                        status="ABORTED",
                        order_id="",
                        client_order_id=intent.client_order_id,
                        requested_qty=intent.quantity,
                        filled_qty=0.0,
                        avg_price=0.0,
                        reason="TRANSPORT_FAILURE_PROVEN_ABSENT",
                    )
                # Uncertain response and query failed -> FAIL CLOSED!
                raise ExecutionBlocked(
                    f"Transport uncertainty: order submission timed out and query failed: {query_exc}"
                ) from query_exc

        order_id = str(raw_order.get("orderId", ""))
        status = str(raw_order.get("status", "NEW"))
        filled_qty = float(raw_order.get("executedQty", 0.0))
        avg_price = float(raw_order.get("avgPrice", 0.0))
        exchange_time = int(raw_order.get("updateTime", now_ms))

        # Save order to DB
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    intent.intent_id,
                    intent.client_order_id,
                    intent.symbol,
                    intent.side,
                    status,
                    intent.quantity,
                    filled_qty,
                    avg_price,
                    None,
                    0,
                    0,
                    exchange_time,
                    now_ms,
                    json.dumps(raw_order),
                ),
            )

        # 5. Protective orders for actual filled quantity
        stop_order_id: str | None = None
        if filled_qty > 0:
            stop_order_id = self._place_protective_stop(intent, filled_qty, now_ms)

        return ExecutionReport(
            intent_id=intent.intent_id,
            status=status,
            order_id=order_id,
            client_order_id=intent.client_order_id,
            requested_qty=intent.quantity,
            filled_qty=filled_qty,
            avg_price=avg_price,
            protective_stop_id=stop_order_id,
            raw=raw_order,
        )

    def _place_protective_stop(self, intent: TradeIntentV1, filled_qty: float, now_ms: int) -> str:
        # Quantity MUST be <= actual filled position
        exit_side = "SELL" if intent.side == "BUY" else "BUY"
        stop_client_oid = f"bqa-stop-{intent.client_order_id[:16]}"

        try:
            raw_stop = self.client.place_protective_order(
                algoType="CONDITIONAL",
                symbol=intent.symbol,
                side=exit_side,
                type="STOP_MARKET",
                triggerPrice=intent.stop_loss,
                closePosition="false",
                quantity=filled_qty,
                reduceOnly="true",
                workingType="MARK_PRICE",
                priceProtect="TRUE",
                clientAlgoId=stop_client_oid,
            )
            stop_id = str(raw_stop.get("algoId", raw_stop.get("orderId", "")))

            with connection(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        stop_id,
                        intent.intent_id,
                        stop_client_oid,
                        intent.symbol,
                        exit_side,
                        "NEW",
                        filled_qty,
                        0.0,
                        0.0,
                        intent.stop_loss,
                        1,
                        1,
                        now_ms,
                        now_ms,
                        json.dumps(raw_stop),
                    ),
                )
            return stop_id
        except Exception as exc:
            # If placing protective stop fails, activate Kill Switch!
            from ..position_supervisor.models import KillObservationV1
            obs = KillObservationV1(
                account_snapshot_hash="0" * 64,
                environment="TESTNET",
                credential_namespace="TESTNET",
                rest_url=self.client.base_url,
                observed_at_ms=now_ms,
                last_reconciled_at_ms=now_ms,
                reconciled=True,
                equity_usdt=1000.0,
                daily_loss_usdt=0.0,
                drawdown_pct=0.0,
                order_conflicts=0,
                protective_missing_since_ms=now_ms - 20_000,
            )
            self.kill_switch.evaluate(obs, now_ms)
            raise ExecutionBlocked(f"failed to place required protective stop: {exc}") from exc

    def reconcile_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport:
        try:
            raw = self.client.query_order_by_client_id(intent.symbol, intent.client_order_id)
        except Exception as exc:
            raise ExecutionBlocked(f"reconcile query failed: {exc}") from exc

        order_id = str(raw.get("orderId", ""))
        status = str(raw.get("status", "UNKNOWN"))
        filled_qty = float(raw.get("executedQty", 0.0))
        avg_price = float(raw.get("avgPrice", 0.0))

        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute(
                "UPDATE live_execution_orders SET status=?, filled_qty=?, avg_price=?, exchange_time_ms=? "
                "WHERE client_order_id=?",
                (status, filled_qty, avg_price, int(raw.get("updateTime", now_ms)), intent.client_order_id),
            )

        return ExecutionReport(
            intent_id=intent.intent_id,
            status=status,
            order_id=order_id,
            client_order_id=intent.client_order_id,
            requested_qty=intent.quantity,
            filled_qty=filled_qty,
            avg_price=avg_price,
            raw=raw,
        )
