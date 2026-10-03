"""Execution backends with exactly-once transport uncertainty handling, partial fills, and protective orders."""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from ..account_watch.models import AccountSnapshotV1
    from ..live_market.models import MarketObservationV1
    from .authorization import PreExecutionAuthorizationV1
    from .validator import PreExecutionValidator

from ..live_db import connection
from ..position_supervisor.kill_switch import KillSwitch
from .binance_signed import BinanceExecutionError, BinanceSignedClient
from .guard import ExecutionBlocked
from .intents import IntentStore, TradeIntentV1
from .policy import ExecutionCapabilityPolicyV1
from .protection import (
    ProtectionStore,
    parse_protective_bool,
    parse_protective_exchange_id,
    protective_field,
)

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
                 *, validator: PreExecutionValidator | None = None,
                 clock_ms: Callable[[], int] | None = None,
                 account_provider: Callable[[], AccountSnapshotV1] | None = None,
                 market_provider: Callable[[int], MarketObservationV1 | None] | None = None) -> None:
        self.path = Path(db_path)
        self.client = signed_client
        self.kill_switch = kill_switch
        self.validator = validator
        self.clock_ms = clock_ms or (lambda: int(time.time() * 1000))
        self.account_provider = account_provider
        self.market_provider = market_provider
        self.protections = ProtectionStore(self.path)
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

    def _active_receipt(self, auth: PreExecutionAuthorizationV1) -> int:
        now = self.clock_ms()
        if not auth.validated_at_ms <= now < auth.expires_at_ms or auth.expires_at_ms > auth.validated_at_ms + 5000:
            raise ExecutionBlocked("AUTHORIZATION_EXPIRED")
        if not self.kill_switch.allows_new_risk():
            raise ExecutionBlocked("KILL_SWITCH_ACTIVE")
        self._check_client_authority()
        return now

    def _fresh_placement_authority(self, auth: PreExecutionAuthorizationV1, intent: TradeIntentV1,
                                   *, claimed: bool) -> PreExecutionAuthorizationV1:
        """Forced REST read and full current-risk validation owned by the side-effect backend."""
        rest_started_at = self._active_receipt(auth)
        if self.validator is None or self.account_provider is None or self.market_provider is None:
            raise ExecutionBlocked("PLACEMENT_ACCOUNT_PROVIDER_REQUIRED")
        try:
            account = self.account_provider()
        except Exception:  # noqa: BLE001 - provider failure is never placement authority
            raise ExecutionBlocked("ACCOUNT_RECONCILIATION_FAILED") from None
        now = self._active_receipt(auth)
        try:
            market = self.market_provider(now)
        except Exception:  # noqa: BLE001 - provider failure is never placement authority
            raise ExecutionBlocked("MARKET_DATA_UNAVAILABLE") from None
        if account is None:
            raise ExecutionBlocked("ACCOUNT_RECONCILIATION_FAILED")
        if market is None:
            raise ExecutionBlocked("MARKET_DATA_UNAVAILABLE")
        if account.last_rest_at_ms < rest_started_at:
            raise ExecutionBlocked("PLACEMENT_REST_SNAPSHOT_NOT_CURRENT")
        client_auth = self.client.authority
        if (client_auth.environment != account.environment
                or client_auth.credential_namespace != account.credential_namespace
                or client_auth.rest_base_url != account.rest_base_url):
            raise ExecutionBlocked("AUTHORIZATION_CLIENT_ENVIRONMENT_MISMATCH")
        result = self.validator.validate(intent, market, account, now)
        if not result.is_valid:
            raise ExecutionBlocked(result.reason)
        from ..decision.models import content_hash
        from .intents import compile_executable_intent_fields
        case = self.validator.live_store.get_case(intent.case_id)
        proposal = self.validator.live_store.get_proposal(intent.proposal_hash)
        executable = compile_executable_intent_fields(case, proposal, account, self.validator.risk_policy)
        if content_hash(executable) != auth.execution_compilation_hash:
            raise ExecutionBlocked("AUTHORIZATION_COMPILATION_MISMATCH")
        self._active_receipt(auth)
        if claimed:
            return self.authorizations.refresh_claimed(auth, account, market, executable, now)
        return self.validator.authorize(intent.intent_id, market, account, now, expires_at_ms=auth.expires_at_ms)

    def submit_authorized(self, authorization_id: str, now_ms: int) -> ExecutionReport:
        # Caller time is diagnostic only. Existing side effects use observation authority.
        auth, intent, _account, _market = self.authorizations.load(authorization_id)
        if IntentStore(self.path).has_existing_side_effect(intent.intent_id):
            return self.reconcile_authorized(intent.intent_id, self.clock_ms())
        self._active_receipt(auth)
        auth = self._fresh_placement_authority(auth, intent, claimed=False)
        now_ms = self._active_receipt(auth)
        if not self.authorizations.claim(auth, now_ms):
            raise ExecutionBlocked("AUTHORIZATION_IN_FLIGHT_RECONCILIATION_REQUIRED")
        try:
            self.protections.reserve_owner(intent, now_ms)
            self._active_receipt(auth)
            try:
                self.client.change_margin_type(intent.symbol, "ISOLATED")
            except Exception as exc:
                if "-4046" not in str(exc):
                    raise
            self._active_receipt(auth)
            self.client.change_leverage(intent.symbol, intent.leverage)
            auth = self._fresh_placement_authority(auth, intent, claimed=True)
            now_ms = self._active_receipt(auth)
            stored, stored_intent, account, market = self.authorizations.load(auth.authorization_id)
            if stored != auth or stored_intent != intent:
                raise ExecutionBlocked("AUTHORIZATION_BINDING_MISMATCH")
            if self.validator is None:
                raise ExecutionBlocked("AUTHORIZATION_REQUIRED")
            final_result = self.validator.validate(intent, market, account, now_ms)
            if not final_result.is_valid:
                raise ExecutionBlocked(final_result.reason)
            if self.authorizations.for_claimed_intent(intent.intent_id) != auth.authorization_id:
                raise ExecutionBlocked("AUTHORIZATION_CLAIM_OWNERSHIP_LOST")

        except Exception:  # No entry request has begun in this phase.
            IntentStore(self.path).update_status(intent.intent_id, "ABORTED", reason="PRE_ENTRY_ABORTED", now_ms=self.clock_ms())
            raise

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
        now_ms = self._active_receipt(auth)
        try:
            raw_order = self.client.place_order(**params)
        except Exception:  # noqa: BLE001
            # Transport uncertainty rule:
            # Query order by client_order_id immediately before failing or retrying!
            try:
                raw_order = self.client.query_order_by_client_id(intent.symbol, intent.client_order_id)
            except Exception as query_exc:
                # If query proves order does not exist (-2013)
                if isinstance(query_exc, BinanceExecutionError) and query_exc.code == -2013:
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

        self._verify_exchange_entry(intent, raw_order, now_ms)
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
            mode = mode_data["dualSidePosition"]
            if mode not in (False, "false", "False"):
                raise BinanceExecutionError("unsupported hedge position mode")

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
                if not math.isfinite(amt):
                    raise BinanceExecutionError("invalid position quantity")
                if pos_side != "BOTH" or found:
                    raise BinanceExecutionError("ambiguous position side")
                open_qty = max(0.0, amt if side == "BUY" else -amt)
                found = True
            if not found:
                raise BinanceExecutionError("position row missing")
            return open_qty
        except Exception as exc:
            self._trip_kill_switch(now_ms, f"position query uncertainty: {exc}")
            raise ExecutionBlocked(f"position query uncertainty: {exc}") from exc

    def _reconcile_protective_stop(self, intent: TradeIntentV1, filled_qty: float, now_ms: int) -> str | None:
        self._require_claimed_intent(intent)
        owner = self.protections.get_owner(intent)
        if owner is None:
            self._trip_kill_switch(now_ms, "protective ownership missing")
            raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
        # A released terminal owner cannot claim any later position on this symbol.
        if owner.status == "RELEASED":
            return None
        open_qty = self._query_open_position(intent.symbol, intent.side, now_ms)
        target_qty = max(min(open_qty, filled_qty, intent.quantity), 0.0)
        try:
            if owner.status == "TERMINAL_CONFIRMED":
                if target_qty == 0:
                    self.protections.release_flat(intent, now_ms)
                    return None
                if owner.protective_client_id is None or owner.exchange_id is None:
                    raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
                self.protections.clear_stop(intent, owner.protective_client_id, owner.exchange_id, now_ms)
                owner = self.protections.get_owner(intent)
                if owner is None:
                    raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
            if owner.status not in {"RESERVED", "PENDING_CONFIRMATION", "ACTIVE", "CANCEL_PENDING"}:
                raise ExecutionBlocked("PROTECTION_OWNER_MISSING")

            # Pending/restarted ownership is confirmed only by its durable exact remote ID.
            # Aggregate listings never supply confirmation or authoritative absence.
            confirmed = None
            if owner.protective_client_id is not None:
                if owner.exchange_id is None:
                    raise ExecutionBlocked("PROTECTION_STOP_UNCERTAIN")
                confirmed, remote_status = self._query_exact_protection(
                    intent, owner.protective_client_id, owner.exchange_id, owner.quantity,
                    allow_absent=target_qty == 0,
                )
                if remote_status != "NEW":
                    self.protections.confirm_terminal(intent, owner.protective_client_id,
                                                      owner.exchange_id, remote_status, now_ms)
                    if target_qty == 0:
                        self.protections.release_flat(intent, now_ms)
                        return None
                    if owner.status != "CANCEL_PENDING":
                        raise ExecutionBlocked("PROTECTION_ORDER_MISSING")
                    self.protections.clear_stop(intent, owner.protective_client_id, owner.exchange_id, now_ms)
                    owner = self.protections.get_owner(intent)
                    if owner is None:
                        raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
                    confirmed = None
                elif owner.status == "CANCEL_PENDING":
                    # A previous cancel might still be in flight. Never repeat it blindly.
                    raise ExecutionBlocked("PROTECTION_CANCELLATION_UNCERTAIN")
            elif owner.status != "RESERVED":
                raise ExecutionBlocked("PROTECTION_STOP_UNCERTAIN")

            try:
                open_algos = self.client.open_protective_orders(intent.symbol)
            except Exception as exc:
                raise ExecutionBlocked("protective query uncertainty") from exc
            if not isinstance(open_algos, list):
                raise ExecutionBlocked("PROTECTION_ORDER_AMBIGUOUS")
            matched = False
            for algo in open_algos:
                if not isinstance(algo, dict):
                    raise ExecutionBlocked("PROTECTION_ORDER_AMBIGUOUS")
                if owner.protective_client_id is not None and algo.get("clientAlgoId") == owner.protective_client_id:
                    if matched:
                        raise ExecutionBlocked("PROTECTION_ORDER_AMBIGUOUS")
                    matched = True
                    if target_qty > 0:
                        self._validate_protective_contract(intent, algo, owner.protective_client_id,
                                                           owner.exchange_id, owner.quantity)
                elif target_qty > 0:
                    raise ExecutionBlocked("PROTECTION_ORDER_UNKNOWN")

            if target_qty == 0:
                if confirmed is not None:
                    assert owner.protective_client_id is not None and owner.exchange_id is not None
                    self._cancel_protective_stop(intent, owner.protective_client_id, owner.exchange_id, now_ms)
                self.protections.release_flat(intent, now_ms)
                return None
            if confirmed is not None:
                assert owner.protective_client_id is not None and owner.exchange_id is not None
                if owner.quantity == target_qty:
                    self.protections.record_stop(intent, owner.protective_client_id, owner.exchange_id,
                                                 target_qty, now_ms, confirmed_order=confirmed)
                    return owner.exchange_id
                self._cancel_protective_stop(intent, owner.protective_client_id, owner.exchange_id, now_ms)
                self.protections.clear_stop(intent, owner.protective_client_id, owner.exchange_id, now_ms)
            return self._place_protective_stop(intent, target_qty, now_ms)
        except Exception as exc:
            self._trip_kill_switch(now_ms, "protective reconciliation uncertainty")
            if isinstance(exc, ExecutionBlocked):
                raise
            raise ExecutionBlocked("PROTECTION_RECONCILIATION_UNCERTAIN") from exc

    def _query_exact_protection(self, intent: TradeIntentV1, client_id: str, exchange_id: str,
                                quantity: float, *, allow_absent: bool = False) -> tuple[Any, str]:
        try:
            raw = self.client.query_protective_order(exchange_id)
        except BinanceExecutionError as exc:
            # Only the signed provider's structured NO_SUCH_ORDER result proves absence.
            if allow_absent and exc.code == -2013:
                return None, "NOT_FOUND"
            raise
        self._validate_protective_contract(intent, raw, client_id, exchange_id, quantity,
                                           allowed_statuses=frozenset({"NEW", "CANCELED", "EXPIRED"}))
        return raw, protective_field(raw, "algoStatus", "status")

    def _cancel_protective_stop(self, intent: TradeIntentV1, client_id: str, exchange_id: str, now_ms: int) -> None:
        try:
            owner = self.protections.get_owner(intent)
            if owner is None:
                raise ExecutionBlocked("PROTECTION_OWNER_MISSING")
            self.protections.begin_cancellation(intent, client_id, exchange_id, now_ms)
            self.client.cancel_protective_order(intent.symbol, exchange_id)
            _, status = self._query_exact_protection(intent, client_id, exchange_id, owner.quantity,
                                                     allow_absent=True)
            if status == "NEW":
                raise ExecutionBlocked("PROTECTION_CANCELLATION_UNCERTAIN")
            self.protections.confirm_terminal(intent, client_id, exchange_id, status, now_ms)
        except Exception:  # noqa: BLE001 - cancellation uncertainty retains exact ownership.
            self._trip_kill_switch(now_ms, "protective cancellation uncertainty")
            raise ExecutionBlocked("PROTECTION_CANCELLATION_UNCERTAIN") from None

    @staticmethod
    def _validate_protective_contract(
        intent: TradeIntentV1, raw: Any, client_id: str | None, exchange_id: str | None,
        expected_quantity: float | None = None, *, allowed_statuses: frozenset[str] = frozenset({"NEW"}),
    ) -> tuple[str, float]:
        parsed_id = parse_protective_exchange_id(raw)
        try:
            quantity = protective_field(raw, "quantity", "origQty")
            stop = protective_field(raw, "triggerPrice", "stopPrice")
            if isinstance(quantity, bool) or isinstance(stop, bool):
                raise TypeError("invalid numeric protective contract")
            quantity = float(quantity)
            stop = float(stop)
            valid = (
                isinstance(client_id, str) and bool(client_id)
                and raw.get("clientAlgoId") == client_id
                and (exchange_id is None or parsed_id == exchange_id)
                and raw.get("symbol") == intent.symbol
                and raw.get("side") == ("SELL" if intent.side == "BUY" else "BUY")
                and raw.get("algoType") == "CONDITIONAL"
                and protective_field(raw, "orderType", "type") == "STOP_MARKET"
                and raw.get("workingType") == "MARK_PRICE"
                and parse_protective_bool(raw.get("priceProtect"))
                and not parse_protective_bool(raw.get("closePosition"))
                and raw.get("positionSide") == "BOTH"
                and parse_protective_bool(raw.get("reduceOnly"))
                and math.isfinite(stop) and stop == intent.stop_loss
                and math.isfinite(quantity) and 0 < quantity <= intent.quantity
                and (expected_quantity is None or quantity == expected_quantity)
                and protective_field(raw, "algoStatus", "status") in allowed_statuses
            )
        except (ValueError, TypeError, OverflowError):
            valid = False
        if not valid:
            raise ExecutionBlocked("PROTECTION_CONTRACT_MISMATCH")
        return parsed_id, quantity

    def _place_protective_stop(self, intent: TradeIntentV1, target_qty: float, now_ms: int) -> str:
        try:
            self._require_claimed_intent(intent)
            # Quantity MUST be <= actual filled position and current open position.
            target_qty = min(target_qty, intent.quantity, self._query_open_position(intent.symbol, intent.side, now_ms))
            if target_qty <= 0:
                raise ExecutionBlocked("PROTECTION_POSITION_FLAT")
            exit_side = "SELL" if intent.side == "BUY" else "BUY"
            stop_client_oid = self.protections.next_client_id(intent, now_ms, target_qty)
            raw_stop = self.client.place_protective_order(
                algoType="CONDITIONAL",
                positionSide="BOTH",
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
            stop_id = parse_protective_exchange_id(raw_stop)
            self.protections.pending_exchange_id(intent, stop_client_oid, stop_id, now_ms)
            # A successful POST is only a pending claim. The query establishes installation.
            confirmed = self.client.query_protective_order(stop_id)
            self._validate_protective_contract(intent, confirmed, stop_client_oid, stop_id, target_qty)
            if target_qty > self._query_open_position(intent.symbol, intent.side, now_ms):
                raise ExecutionBlocked("PROTECTION_POSITION_CHANGED")
            self.protections.record_stop(intent, stop_client_oid, stop_id, target_qty, now_ms,
                                         confirmed_order=confirmed)
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
        expected = compile_executable_intent_fields(case, proposal, account)
        if content_hash(expected) != _auth.execution_compilation_hash or any(getattr(intent, key) != value for key, value in expected.items()):
            raise ExecutionBlocked("EXECUTABLE_CONTRACT_MISMATCH")

    def _verify_exchange_entry(self, intent: TradeIntentV1, raw: Any, now_ms: int) -> None:
        try:
            if not isinstance(raw, dict) or not raw.get("orderId"):
                raise ValueError
            if (raw.get("clientOrderId") != intent.client_order_id
                    or raw.get("symbol") != intent.symbol
                    or raw.get("side") != intent.side
                    or raw.get("status") not in {"NEW", "PARTIALLY_FILLED", "FILLED", "CANCELED", "EXPIRED", "REJECTED"}):
                raise ValueError
            filled = float(raw.get("executedQty", 0))
            if not math.isfinite(filled) or not 0 <= filled <= intent.quantity + 1e-9:
                raise ValueError
            with connection(self.path) as db:
                rows = db.execute("SELECT intent_id,client_order_id,order_id FROM live_execution_orders WHERE client_order_id=? OR order_id=?",
                                  (intent.client_order_id, str(raw["orderId"]))).fetchall()
            if any(row["intent_id"] != intent.intent_id or row["client_order_id"] != intent.client_order_id
                   or row["order_id"] != str(raw["orderId"]) for row in rows):
                raise ValueError
        except (ValueError, TypeError):
            self._trip_kill_switch(now_ms, "ORDER_IDENTITY_CONFLICT")
            raise ExecutionBlocked("ORDER_IDENTITY_CONFLICT") from None

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
        except Exception as exc:  # noqa: BLE001 - uncertainty retains the durable claim
            if isinstance(exc, BinanceExecutionError) and exc.code == -2013:
                # Release only a durably proven pre-entry abort, never a live setup worker
                # or an uncertain submitted request whose order has not appeared yet.
                with connection(self.path) as db:
                    latest = db.execute("SELECT reason FROM live_intent_transitions WHERE intent_id=? ORDER BY rowid DESC LIMIT 1",
                                        (intent.intent_id,)).fetchone()
                    order = db.execute("SELECT 1 FROM live_execution_orders WHERE intent_id=? AND is_protective=0",
                                       (intent.intent_id,)).fetchone()
                if latest is not None and latest["reason"] == "PRE_ENTRY_ABORTED" and order is None:
                    owner = self.protections.get_owner(intent)
                    if owner is not None and owner.protective_client_id is None and self._query_open_position(intent.symbol, intent.side, now_ms) == 0:
                        self.protections.release_flat(intent, now_ms)
                        return ExecutionReport(intent.intent_id, "ABORTED", "", intent.client_order_id,
                                               intent.quantity, 0.0, 0.0, reason="PROVEN_PRE_ENTRY_ABORTED")
                return ExecutionReport(intent.intent_id, "UNKNOWN", "", intent.client_order_id,
                                       intent.quantity, 0.0, 0.0, reason="ENTRY_PROVEN_ABSENT_NO_NEW_PLACEMENT")
            self._trip_kill_switch(now_ms, "ORDER_RECONCILIATION_UNCERTAIN")
            raise ExecutionBlocked("ORDER_RECONCILIATION_UNCERTAIN") from None

        self._verify_exchange_entry(intent, raw, now_ms)
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
        if filled_qty > 0 or has_stop or status in {"CANCELED", "EXPIRED", "REJECTED"}:
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
