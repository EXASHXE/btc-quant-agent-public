"""Execution backends with exactly-once transport uncertainty handling, partial fills, and protective orders."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from .validator import PreExecutionValidator

from ..live_db import connection
from ..position_supervisor.kill_switch import KillSwitch
from .binance_signed import BinanceExecutionError, BinanceSignedClient
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
    def submit_authorized(self, authorization_id: str, now_ms: int) -> ExecutionReport: ...
    def reconcile_authorized(self, intent_id: str, now_ms: int) -> ExecutionReport: ...


class DryRunExecutionBackend:
    """Deterministic simulated execution backend."""

    def __init__(
        self,
        db_path: str | Path,
        open_position_provider: Callable[[str, str], float | None] | None = None,
    ) -> None:
        self.path = Path(db_path)
        self.open_position_provider = open_position_provider
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

    def reconcile_intent(
        self, intent: TradeIntentV1, now_ms: int, open_position: float | None = None
    ) -> ExecutionReport:
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

        filled_qty = float(row["filled_qty"])
        open_qty = open_position
        if open_qty is None and self.open_position_provider is not None:
            open_qty = self.open_position_provider(intent.symbol, intent.side)
        if open_qty is None:
            open_qty = filled_qty

        target_qty = min(open_qty, filled_qty, intent.quantity)
        stop_order_id: str | None = None

        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            stop_row = db.execute(
                "SELECT * FROM live_execution_orders WHERE intent_id=? AND is_protective=1",
                (intent.intent_id,),
            ).fetchone()

            if target_qty <= 0.0:
                # If flat, cancel stale protection
                if stop_row is not None:
                    db.execute(
                        "UPDATE live_execution_orders SET status='CANCELED' WHERE order_id=?",
                        (stop_row["order_id"],),
                    )
            else:
                stop_order_id = f"sim-stop-{intent.intent_id}"
                stop_client_oid = f"bqa-stop-{intent.client_order_id[:12]}-{int(target_qty * 1000):04d}"

                if stop_row is None:
                    db.execute(
                        "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (
                            stop_order_id,
                            intent.intent_id,
                            stop_client_oid,
                            intent.symbol,
                            "SELL" if intent.side == "BUY" else "BUY",
                            "NEW",
                            target_qty,
                            0.0,
                            0.0,
                            intent.stop_loss,
                            1,
                            1,
                            now_ms,
                            now_ms,
                            json.dumps({"dry_run": True, "type": "STOP_MARKET", "stopPrice": intent.stop_loss, "quantity": target_qty}),
                        ),
                    )
                elif float(stop_row["requested_qty"]) != target_qty or stop_row["status"] == "CANCELED":
                    db.execute(
                        "UPDATE live_execution_orders SET requested_qty=?, status='NEW', client_order_id=?, receipt_time_ms=?, payload=? WHERE order_id=?",
                        (
                            target_qty,
                            stop_client_oid,
                            now_ms,
                            json.dumps({"dry_run": True, "type": "STOP_MARKET", "stopPrice": intent.stop_loss, "quantity": target_qty}),
                            stop_row["order_id"],
                        ),
                    )
                    stop_order_id = stop_row["order_id"]
                else:
                    stop_order_id = stop_row["order_id"]

        return ExecutionReport(
            intent_id=intent.intent_id,
            status=row["status"],
            order_id=row["order_id"],
            client_order_id=row["client_order_id"],
            requested_qty=row["requested_qty"],
            filled_qty=filled_qty,
            avg_price=row["avg_price"],
            protective_stop_id=stop_order_id,
            reason="RECONCILED",
        )


class TestnetExecutionBackend:
    """Binance USD(S)-M Futures Testnet execution backend with exact-once uncertainty handling."""

    __test__ = False

    def __init__(self, db_path: str | Path, signed_client: BinanceSignedClient, kill_switch: KillSwitch,
                 *, validator: PreExecutionValidator | None = None) -> None:
        self.path = Path(db_path)
        self.client = signed_client
        self.kill_switch = kill_switch
        self.validator = validator
        from .authorization import AuthorizationStore
        self.authorizations = AuthorizationStore(self.path)
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
        self._check_client_authority()
        raise ExecutionBlocked("AUTHORIZATION_REQUIRED: submit a persisted authorization ID")

    def _check_client_authority(self) -> None:
        authority = getattr(self.client, "authority", None)
        if authority is None:
            raise ExecutionBlocked("missing credential authority on signed client")
        ExecutionCapabilityPolicyV1.check_capability(
            authority.environment, "SUBMIT_INTENT", env_id=authority.environment,
            cred_ns=authority.credential_namespace, rest_url=authority.rest_base_url,
        )
        if authority.environment != "TESTNET":
            raise ExecutionBlocked("TESTNET_CREDENTIAL_AUTHORITY_REQUIRED")

    def submit_authorized(self, authorization_id: str, now_ms: int) -> ExecutionReport:
        auth, intent, account, market = self.authorizations.load(authorization_id)
        if not auth.validated_at_ms <= now_ms < auth.expires_at_ms or auth.expires_at_ms > auth.validated_at_ms + 5000:
            raise ExecutionBlocked("AUTHORIZATION_EXPIRED")
        if self.validator is None:
            raise ExecutionBlocked("AUTHORIZATION_REQUIRED")
        from ..account_watch.store import AccountStore
        from ..decision.models import content_hash
        from .intents import compile_executable_intent_fields
        latest = AccountStore(self.path).latest(account.account_id)
        if latest is None or latest.snapshot_hash != auth.account_snapshot_hash:
            raise ExecutionBlocked("AUTHORIZATION_CURRENT_ACCOUNT_CHANGED")
        result = self.validator.validate(intent, market, account, now_ms)
        if not result.is_valid:
            raise ExecutionBlocked(result.reason)
        case = self.validator.live_store.get_case(intent.case_id)
        proposal = self.validator.live_store.get_proposal(intent.proposal_hash)
        compiled = compile_executable_intent_fields(case, proposal, account, self.validator.risk_policy)
        if content_hash(compiled) != auth.execution_compilation_hash:
            raise ExecutionBlocked("AUTHORIZATION_COMPILATION_MISMATCH")
        # 1. Capability check using client's actual authority metadata
        client_auth = getattr(self.client, "authority", None)
        if client_auth is None:
            raise ExecutionBlocked("missing credential authority on signed client")
        ExecutionCapabilityPolicyV1.check_capability(
            client_auth.environment,
            "SUBMIT_INTENT",
            env_id=client_auth.environment,
            cred_ns=client_auth.credential_namespace,
            rest_url=client_auth.rest_base_url,
        )
        if (client_auth.environment != auth.environment
                or client_auth.credential_namespace != account.credential_namespace
                or client_auth.rest_base_url != account.rest_base_url):
            raise ExecutionBlocked("AUTHORIZATION_CLIENT_ENVIRONMENT_MISMATCH")

        receipt, _, _, _ = self.authorizations.load(authorization_id)
        claimed = self.authorizations.claim(receipt, now_ms)

        # 2. Check local database for existing order with this client_order_id (idempotency)
        with connection(self.path) as db:
            row = db.execute(
                "SELECT * FROM live_execution_orders WHERE client_order_id=?",
                (intent.client_order_id,),
            ).fetchone()
            if row is not None:
                if row["intent_id"] != intent.intent_id:
                    raise ExecutionBlocked("ORDER_INTENT_BINDING_MISMATCH")
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

        if not claimed:
            raise ExecutionBlocked("AUTHORIZATION_IN_FLIGHT_RECONCILIATION_REQUIRED")

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
            stop_order_id = self._reconcile_protective_stop(intent, filled_qty, now_ms)

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

    def _trip_kill_switch(self, now_ms: int, reason: str) -> None:
        from ..position_supervisor.models import KillObservationV1
        auth = getattr(self.client, "authority", None)
        env = auth.environment if auth else "TESTNET"
        ns = auth.credential_namespace if auth else "TESTNET"
        url = auth.rest_base_url if auth else getattr(self.client, "base_url", "https://testnet.binancefuture.com")
        obs = KillObservationV1(
            account_snapshot_hash="0" * 64,
            environment=env,
            credential_namespace=ns,
            rest_url=url,
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

    def _query_open_position(self, symbol: str, side: str, now_ms: int) -> float:
        """Query authoritative open position from exchange for symbol and side.

        Returns the intent-side open quantity (>= 0.0).
        Fails closed and trips kill switch on uncertainty or unsupported mode.
        """
        try:
            mode_data = self.client.position_mode()
            if not isinstance(mode_data, dict) or "dualSidePosition" not in mode_data:
                raise BinanceExecutionError(f"unparseable position mode response: {mode_data}")
            is_hedge = bool(mode_data["dualSidePosition"])

            risk_rows = self.client.positions(symbol)
            if not isinstance(risk_rows, list):
                raise BinanceExecutionError(f"unparseable position risk response: {risk_rows}")

            open_qty = 0.0
            found = False
            for row in risk_rows:
                if not isinstance(row, dict):
                    continue
                if row.get("symbol") != symbol:
                    continue
                pos_side = str(row.get("positionSide", "BOTH"))
                amt = float(row.get("positionAmt", 0.0))
                if is_hedge:
                    if side == "BUY" and pos_side == "LONG":
                        open_qty = max(0.0, amt)
                        found = True
                        break
                    elif side == "SELL" and pos_side == "SHORT":
                        open_qty = max(0.0, abs(amt))
                        found = True
                        break
                else:
                    if pos_side == "BOTH":
                        if side == "BUY":
                            open_qty = max(0.0, amt)
                        else:
                            open_qty = max(0.0, -amt)
                        found = True
                        break
            if not found:
                open_qty = 0.0
            return open_qty
        except Exception as exc:
            self._trip_kill_switch(now_ms, f"position query uncertainty: {exc}")
            raise ExecutionBlocked(f"position query uncertainty: {exc}") from exc

    def _reconcile_protective_stop(self, intent: TradeIntentV1, filled_qty: float, now_ms: int) -> str | None:
        self._require_claimed_intent(intent)
        open_qty = self._query_open_position(intent.symbol, intent.side, now_ms)
        target_qty = max(min(open_qty, filled_qty, intent.quantity), 0.0)

        # 1. Query open protective orders from exchange
        try:
            open_algos_raw = self.client.open_protective_orders(intent.symbol)
            open_algos = open_algos_raw if isinstance(open_algos_raw, list) else []
        except Exception as exc:
            self._trip_kill_switch(now_ms, f"protective query failed: {exc}")
            raise ExecutionBlocked(f"protective query uncertainty: {exc}") from exc

        # 2. Check for active protective order on exchange for this intent
        target_prefix = f"bqa-stop-{intent.client_order_id[:12]}"
        matched_algo: dict[str, Any] | None = None
        for algo in open_algos:
            if not isinstance(algo, dict):
                continue
            client_id = str(algo.get("clientAlgoId", ""))
            if client_id.startswith(target_prefix):
                matched_algo = algo
                break

        if target_qty <= 0.0:
            if matched_algo is not None:
                algo_id = str(matched_algo.get("algoId", matched_algo.get("orderId", "")))
                try:
                    self.client.cancel_protective_order(intent.symbol, algo_id)
                except Exception as exc:
                    self._trip_kill_switch(now_ms, f"failed to cancel stale protective stop {algo_id}: {exc}")
                    raise ExecutionBlocked(f"failed to cancel stale protective stop: {exc}") from exc

                with connection(self.path) as db:
                    db.execute(
                        "UPDATE live_execution_orders SET status='CANCELED' WHERE order_id=?",
                        (algo_id,),
                    )
            return None

        if matched_algo is not None:
            algo_id = str(matched_algo.get("algoId", matched_algo.get("orderId", "")))
            current_protected_qty = float(matched_algo.get("quantity", matched_algo.get("origQty", 0.0)))
            if current_protected_qty == target_qty:
                # Already adequately protected (idempotent replay)
                return algo_id

            # Existing protection size differs: cancel mismatched order before replacing
            try:
                self.client.cancel_protective_order(intent.symbol, algo_id)
            except Exception as exc:
                self._trip_kill_switch(now_ms, f"failed to cancel mismatched protective stop {algo_id}: {exc}")
                raise ExecutionBlocked(f"failed to cancel mismatched protective stop: {exc}") from exc

            # Mark cancelled in local DB
            with connection(self.path) as db:
                db.execute(
                    "UPDATE live_execution_orders SET status='CANCELED' WHERE order_id=?",
                    (algo_id,),
                )

        # 3. Place resized or new protective stop for target_qty
        return self._place_protective_stop(intent, target_qty, now_ms)

    def _place_protective_stop(self, intent: TradeIntentV1, target_qty: float, now_ms: int) -> str:
        self._require_claimed_intent(intent)
        # Quantity MUST be <= actual filled position and current open position
        target_qty = min(target_qty, intent.quantity)
        exit_side = "SELL" if intent.side == "BUY" else "BUY"
        stop_client_oid = f"bqa-stop-{intent.client_order_id[:12]}-{int(target_qty * 1000):04d}"

        try:
            raw_stop = self.client.place_protective_order(
                algoType="CONDITIONAL",
                symbol=intent.symbol,
                side=exit_side,
                type="STOP_MARKET",
                triggerPrice=intent.stop_loss,
                closePosition="false",
                quantity=target_qty,
                reduceOnly="true",
                workingType="MARK_PRICE",
                priceProtect="TRUE",
                clientAlgoId=stop_client_oid,
            )
            stop_id = str(raw_stop.get("algoId", raw_stop.get("orderId", "")))

            with connection(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                    "ON CONFLICT(order_id) DO UPDATE SET requested_qty=excluded.requested_qty, status=excluded.status",
                    (
                        stop_id,
                        intent.intent_id,
                        stop_client_oid,
                        intent.symbol,
                        exit_side,
                        "NEW",
                        target_qty,
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
            self._trip_kill_switch(now_ms, f"failed to place required protective stop: {exc}")
            raise ExecutionBlocked(f"failed to place required protective stop: {exc}") from exc

    def reconcile_intent(self, intent: TradeIntentV1, now_ms: int) -> ExecutionReport:
        raise ExecutionBlocked("AUTHORIZATION_REQUIRED: reconcile a persisted intent ID")

    def _require_claimed_intent(self, intent: TradeIntentV1) -> None:
        auth_id = self.authorizations.for_claimed_intent(intent.intent_id)
        _auth, persisted, account, _market = self.authorizations.load(auth_id)
        if persisted.intent_hash != intent.intent_hash or self.validator is None:
            raise ExecutionBlocked("AUTHORIZATION_INTENT_MISMATCH")
        from ..decision.models import content_hash
        from .intents import compile_executable_intent_fields
        with self.validator.live_store._connection() as db:
            approval = db.execute(
                "SELECT event_id, action, actor, proposal_hash, case_hash, at_ms FROM approval_records WHERE event_id=?",
                (intent.approval_event_id,),
            ).fetchone()
        if (approval is None or approval["action"] != "APPROVE"
                or approval["actor"] != intent.approval_actor
                or approval["proposal_hash"] != intent.proposal_hash
                or approval["case_hash"] != intent.case_hash
                or content_hash(dict(approval)) != intent.approval_hash):
            raise ExecutionBlocked("APPROVAL_AUTHORITY_MISMATCH")
        self._check_client_authority()
        client_auth = self.client.authority
        if (client_auth.environment != account.environment
                or client_auth.credential_namespace != account.credential_namespace
                or client_auth.rest_base_url != account.rest_base_url):
            raise ExecutionBlocked("AUTHORIZATION_CLIENT_ENVIRONMENT_MISMATCH")
        case = self.validator.live_store.get_case(intent.case_id)
        proposal = self.validator.live_store.get_proposal(intent.proposal_hash)
        expected = compile_executable_intent_fields(case, proposal, account, self.validator.risk_policy)
        if content_hash(expected) != _auth.execution_compilation_hash or any(getattr(intent, key) != value for key, value in expected.items()):
            raise ExecutionBlocked("EXECUTABLE_CONTRACT_MISMATCH")

    def reconcile_authorized(self, intent_id: str, now_ms: int) -> ExecutionReport:
        auth_id = self.authorizations.for_claimed_intent(intent_id)
        _receipt, intent, _account, _market = self.authorizations.load(auth_id)
        self._require_claimed_intent(intent)
        auth = getattr(self.client, "authority", None)
        if auth is None:
            raise ExecutionBlocked("missing credential authority on signed client")
        ExecutionCapabilityPolicyV1.check_capability(
            auth.environment,
            "RECONCILE_INTENT",
            env_id=auth.environment,
            cred_ns=auth.credential_namespace,
            rest_url=auth.rest_base_url,
        )

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
                "INSERT INTO live_execution_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(client_order_id) DO UPDATE SET status=excluded.status, "
                "filled_qty=excluded.filled_qty, avg_price=excluded.avg_price, "
                "exchange_time_ms=excluded.exchange_time_ms, receipt_time_ms=excluded.receipt_time_ms, payload=excluded.payload",
                (order_id, intent.intent_id, intent.client_order_id, intent.symbol, intent.side,
                 status, intent.quantity, filled_qty, avg_price, None, 0, 0,
                 int(raw.get("updateTime", now_ms)), now_ms, json.dumps(raw)),
            )

        has_stop = False
        with connection(self.path) as db:
            row_stop = db.execute(
                "SELECT 1 FROM live_execution_orders WHERE intent_id=? AND is_protective=1 AND status != 'CANCELED'",
                (intent.intent_id,),
            ).fetchone()
            if row_stop is not None:
                has_stop = True

        stop_order_id: str | None = None
        if filled_qty > 0 or has_stop:
            stop_order_id = self._reconcile_protective_stop(intent, filled_qty, now_ms)

        return ExecutionReport(
            intent_id=intent.intent_id,
            status=status,
            order_id=order_id,
            client_order_id=intent.client_order_id,
            requested_qty=intent.quantity,
            filled_qty=filled_qty,
            avg_price=avg_price,
            protective_stop_id=stop_order_id,
            raw=raw,
        )
