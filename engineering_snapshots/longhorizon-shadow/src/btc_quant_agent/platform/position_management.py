"""User-authoritative ledger and deterministic supervision on existing SQLite primitives."""

from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal

from btc_quant_agent.market_watch.alerting import NotificationNotSent
from btc_quant_agent.market_watch.state import MarketWatchStateStore

from .config import ExitConfig

from .core import (
    InstrumentSpec,
    ManagementAction,
    MarketEvent,
    PositionState,
    UserReportedFill,
    dec,
    fingerprint,
    primitive,
    quantize,
)


class AdvisoryStore(MarketWatchStateStore):
    """Adds generic decision/position records; inherits the existing durable notification outbox."""

    def __init__(self, path, clock_ms=None):
        super().__init__(path, clock_ms=clock_ms)
        with self._connect() as db:
            db.executescript("""
              CREATE TABLE IF NOT EXISTS platform_decisions (
                id TEXT PRIMARY KEY, decision_ts INTEGER NOT NULL, commit_ts INTEGER NOT NULL,
                evidence TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS platform_position_versions (
                id TEXT NOT NULL, version INTEGER NOT NULL, evidence TEXT NOT NULL,
                PRIMARY KEY(id, version));
              CREATE TABLE IF NOT EXISTS platform_user_reports (
                report_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, position_id TEXT NOT NULL,
                result_version INTEGER NOT NULL);
              CREATE TABLE IF NOT EXISTS platform_decision_origins (
                origin TEXT PRIMARY KEY, decision_id TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS platform_position_funding (
                event_id TEXT PRIMARY KEY, evidence TEXT NOT NULL, position_id TEXT NOT NULL,
                result_version INTEGER NOT NULL);
            """)

    def commit_decision(
        self, evidence, decision_ts: int, commit_ts: int, *, origin: str | None = None
    ) -> str:
        if commit_ts < decision_ts:
            raise ValueError("COMMIT_BEFORE_DECISION")
        value = primitive(evidence)
        identity = fingerprint(value)
        if origin is None and hasattr(evidence, "candidate"):
            origin = fingerprint(["ENTRY", evidence.candidate.id, decision_ts, evidence.config_hash])
        if origin is None and isinstance(evidence, ManagementAction):
            origin = fingerprint(["MANAGEMENT", evidence.position_id, decision_ts])
        origin = origin or identity
        encoded = json.dumps(value, sort_keys=True, allow_nan=False)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            bound = db.execute(
                "SELECT decision_id FROM platform_decision_origins WHERE origin=?", (origin,)
            ).fetchone()
            if bound and bound[0] != identity:
                raise ValueError("IMMUTABLE_ORIGIN_CONFLICT")
            old = db.execute("SELECT evidence FROM platform_decisions WHERE id=?", (identity,)).fetchone()
            if old and old[0] != encoded:
                raise ValueError("IMMUTABLE_DECISION_CONFLICT")
            db.execute(
                "INSERT OR IGNORE INTO platform_decisions VALUES (?,?,?,?)",
                (identity, decision_ts, commit_ts, encoded),
            )
            db.execute("INSERT OR IGNORE INTO platform_decision_origins VALUES (?,?)", (origin, identity))
        return identity

    def prepare(self, identity: str, symbol: str, commit_ts: int) -> str:
        """Freeze generic wire evidence in the already-tested Foundation outbox schema."""
        with self._connect() as db:
            row = db.execute(
                "SELECT decision_ts,commit_ts,evidence FROM platform_decisions WHERE id=?", (identity,)
            ).fetchone()
            if not row or row[1] > commit_ts:
                raise ValueError("DECISION_NOT_COMMITTED")
            event_id = fingerprint(["PLATFORM_NOTIFICATION_V1", identity])
            payload = json.dumps({"event_id": event_id, "evidence": json.loads(row[2])}, sort_keys=True)
            db.execute(
                """INSERT OR IGNORE INTO market_watch_notifications
                (event_id,symbol,fingerprint,decision_time_ms,prepared_at_ms,status,assessment_json,
                 payload_json,persisted_commit_at_ms) VALUES (?,?,?,?,?,'PENDING',?,?,?)""",
                (event_id, symbol, identity, row[0], commit_ts, row[2], payload, commit_ts),
            )
        return event_id

    def dispatch(self, event_id: str, sender, now_ms: int, *, notify: bool = True) -> str:
        if not notify:
            return self.get_notification(event_id)["status"]
        if not self.claim_notification(event_id, now_ms):
            return self.get_notification(event_id)["status"]
        notification = self.get_notification(event_id)
        try:
            sender(json.loads(notification["payload_json"]))
        except NotificationNotSent as exc:
            self.fail_notification(event_id, now_ms, str(exc), definitely_not_sent=True)
        except Exception as exc:
            self.fail_notification(event_id, now_ms, str(exc), definitely_not_sent=False)
        else:
            self.acknowledge_notification(event_id, now_ms)
        return self.get_notification(event_id)["status"]

    @staticmethod
    def _decode(encoded: str) -> PositionState:
        raw = json.loads(encoded)
        for key in ("entry", "quantity", "stop", "initial_stop"):
            raw[key] = dec(raw[key])
        return PositionState(**raw)

    def position(self, id: str) -> PositionState:
        with self._connect() as db:
            row = db.execute(
                "SELECT evidence FROM platform_position_versions WHERE id=? ORDER BY version DESC LIMIT 1",
                (id,),
            ).fetchone()
        if row is None:
            raise KeyError(id)
        return self._decode(row[0])

    def report(
        self, fill: UserReportedFill, spec: InstrumentSpec, *, stop: Decimal | None = None,
        accept_breached_stop: bool = False,
    ) -> PositionState:
        if fill.source != "USER_REPORTED":
            raise ValueError("ACTUAL_FILL_REQUIRES_USER_REPORT")
        if fill.symbol != spec.symbol or fill.direction not in ("LONG", "SHORT"):
            raise ValueError("REPORT_IDENTITY_INVALID")
        if fill.price <= 0 or fill.quantity <= 0:
            raise ValueError("INVALID_FILL_SIZE_OR_PRICE")
        if fill.price % spec.tick_size or fill.quantity % spec.quantity_step:
            raise ValueError("FILL_PRECISION_INVALID")
        if not 0 < fill.user_action_ts <= fill.received_ts:
            raise ValueError("USER_CLOCK_INVALID")
        if not 1 <= fill.leverage <= spec.max_leverage or fill.margin_mode not in ("ISOLATED", "CROSS"):
            raise ValueError("INVALID_REPORTED_MARGIN")
        encoded = json.dumps(primitive(fill), sort_keys=True)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT evidence,position_id,result_version FROM platform_user_reports WHERE report_id=?",
                (fill.report_id,),
            ).fetchone()
            if prior:
                if prior[0] != encoded:
                    raise ValueError("CONFLICTING_REPORT_ID")
                row = db.execute(
                    "SELECT evidence FROM platform_position_versions WHERE id=? AND version=?",
                    (prior[1], prior[2]),
                ).fetchone()
                return self._decode(row[0])
            old = db.execute(
                "SELECT evidence FROM platform_position_versions WHERE id=? ORDER BY version DESC LIMIT 1",
                (fill.position_id,),
            ).fetchone()
            if old is None:
                if fill.operation != "OPEN" or stop is None:
                    raise ValueError("INITIAL_FILL_REQUIRES_STOP")
                if stop <= 0 or stop % spec.tick_size:
                    raise ValueError("INVALID_STOP_PRECISION")
                breached = (fill.direction == "LONG" and stop >= fill.price) or (
                    fill.direction == "SHORT" and stop <= fill.price
                )
                if breached and not accept_breached_stop:
                    raise ValueError("INVALID_INITIAL_STOP")
                position = PositionState(
                    fill.position_id,
                    fill.symbol,
                    fill.direction,
                    fill.price,
                    fill.quantity,
                    stop,
                    stop,
                    fill.leverage,
                    fill.margin_mode,
                    1,
                    "STOP_BREACHED" if breached else "OPEN",
                    "USER_REPORTED",
                    fill.received_ts,
                )
            else:
                p = self._decode(old[0])
                if p.status == "CLOSED":
                    raise ValueError("CLOSED_POSITION_REQUIRES_NEW_ID")
                if p.symbol != fill.symbol or p.direction != fill.direction:
                    raise ValueError("POSITION_IDENTITY_CONFLICT")
                if p.leverage != fill.leverage or p.margin_mode != fill.margin_mode:
                    raise ValueError("MARGIN_CHANGE_REQUIRES_EXPLICIT_AMENDMENT")
                if fill.received_ts < p.updated_ts:
                    raise ValueError("REPORT_TIME_REGRESSION")
                if fill.operation == "CLOSE":
                    if fill.quantity > p.quantity:
                        raise ValueError("CLOSE_EXCEEDS_REPORTED_POSITION")
                    qty = p.quantity - fill.quantity
                    position = replace(
                        p,
                        quantity=qty,
                        status="CLOSED" if qty == 0 else "OPEN",
                        version=p.version + 1,
                        updated_ts=fill.received_ts,
                        partial_closes=p.partial_closes + (1 if qty > 0 else 0),
                    )
                elif fill.operation == "OPEN":
                    qty = p.quantity + fill.quantity
                    entry = (p.entry * p.quantity + fill.price * fill.quantity) / qty
                    position = replace(
                        p, entry=entry, quantity=qty, version=p.version + 1, updated_ts=fill.received_ts
                    )
                else:
                    raise ValueError("UNSUPPORTED_USER_REPORT_OPERATION")
            db.execute(
                "INSERT INTO platform_position_versions VALUES (?,?,?)",
                (position.id, position.version, json.dumps(primitive(position), sort_keys=True)),
            )
            db.execute(
                "INSERT INTO platform_user_reports VALUES (?,?,?,?)",
                (fill.report_id, encoded, position.id, position.version),
            )
        return position

    def amend_stop(
        self, id: str, stop: Decimal, spec: InstrumentSpec, user_action_ts: int, *, expected_version: int
    ) -> PositionState:
        if stop <= 0 or stop % spec.tick_size:
            raise ValueError("INVALID_STOP_PRECISION")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT evidence FROM platform_position_versions WHERE id=? ORDER BY version DESC LIMIT 1",
                (id,),
            ).fetchone()
            if row is None:
                raise KeyError(id)
            p = self._decode(row[0])
            if p.symbol != spec.symbol or p.version != expected_version:
                raise ValueError("POSITION_VERSION_CONFLICT")
            if p.status == "CLOSED" or user_action_ts < p.updated_ts:
                raise ValueError("INVALID_AMENDMENT_STATE_OR_TIME")
            if (p.direction == "LONG" and stop < p.stop) or (p.direction == "SHORT" and stop > p.stop):
                raise ValueError("STOP_CANNOT_LOOSEN")
            updated = replace(p, stop=stop, version=p.version + 1, updated_ts=user_action_ts)
            db.execute(
                "INSERT INTO platform_position_versions VALUES (?,?,?)",
                (id, updated.version, json.dumps(primitive(updated), sort_keys=True)),
            )
        return updated

    def settle_funding(self, id: str, event: MarketEvent) -> PositionState:
        from btc_quant_agent.economic.funding import FundingModel

        d = event.derivatives
        if (
            d is None
            or not d.funding_settlement
            or d.funding_rate is None
            or d.mark_price is None
            or d.provenance.reason(event.decision_ts, 90000)
        ):
            raise ValueError("FUNDING_SETTLEMENT_NOT_ADMISSIBLE")
        encoded = json.dumps(primitive(d), sort_keys=True, allow_nan=False)
        event_id = fingerprint([id, d.provenance.provider, d.provenance.source_id])
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute(
                "SELECT evidence,result_version FROM platform_position_funding WHERE event_id=?", (event_id,)
            ).fetchone()
            if old:
                if old[0] != encoded:
                    raise ValueError("FUNDING_EVENT_CONFLICT")
                row = db.execute(
                    "SELECT evidence FROM platform_position_versions WHERE id=? AND version=?", (id, old[1])
                ).fetchone()
                return self._decode(row[0])
            row = db.execute(
                "SELECT evidence FROM platform_position_versions WHERE id=? ORDER BY version DESC LIMIT 1",
                (id,),
            ).fetchone()
            if row is None:
                raise KeyError(id)
            p = self._decode(row[0])
            if p.symbol != event.spec.symbol or event.spec.market != "PERPETUAL":
                raise ValueError("FUNDING_CONTRACT_MISMATCH")
            if p.status == "CLOSED" or d.provenance.exchange_event_ts < p.updated_ts:
                raise ValueError("FUNDING_REQUIRES_CHRONOLOGICAL_POSITION_RECONCILIATION")
            sign = 1 if p.direction == "LONG" else -1
            cash = FundingModel().calculate_cashflow(
                sign * float(p.quantity * event.spec.multiplier), d.mark_price, d.funding_rate
            )
            updated = replace(
                p, funding=p.funding + cash, version=p.version + 1, updated_ts=event.decision_ts
            )
            db.execute(
                "INSERT INTO platform_position_versions VALUES (?,?,?)",
                (id, updated.version, json.dumps(primitive(updated), sort_keys=True)),
            )
            db.execute(
                "INSERT INTO platform_position_funding VALUES (?,?,?,?)",
                (event_id, encoded, id, updated.version),
            )
        return updated


def supervise(
    position: PositionState,
    event: MarketEvent,
    *,
    atr: float | None = None,
    thesis_invalid: bool = False,
    partial_at_r: float = 1.5,
    already_partial: bool = False,
    policy: ExitConfig | None = None,
    episode_policy=None,
) -> ManagementAction:
    if episode_policy is not None:
        from .selection.management import manage

        return manage(position, event, episode_policy)
    now = event.decision_ts

    def action(kind, reason, stop=None, fraction=None, status="UNCONFIRMED"):
        return ManagementAction(position.id, kind, reason, now, stop, fraction, status)

    if event.spec.symbol != position.symbol:
        return action("RECONCILE", "SYMBOL_MISMATCH")
    if position.status == "CLOSED":
        return action("RECONCILE", "POSITION_ALREADY_USER_CONFIRMED_CLOSED")
    if event.reason(90000):
        return action("RECONCILE", "DATA_STALE_OR_RECONNECT")
    side = 1 if position.direction == "LONG" else -1
    quote = event.quote
    derivative = event.derivatives
    mark = (
        derivative.mark_price
        if derivative and not derivative.field_reason("mark_price", now, 90000)
        else None
    )
    breach = (
        event.candle.low <= float(position.stop) if side == 1 else event.candle.high >= float(position.stop)
    )
    if breach:
        return action(
            "EXIT", "STOP_BREACHED; execution must be confirmed by the user", status="EXECUTION_UNKNOWN"
        )
    if mark is not None and event.spec.market == "PERPETUAL":
        distance = 1 / position.leverage - event.spec.maintenance_margin_rate
        liquidation = float(position.entry) * (1 - side * distance)
        if side * (mark - liquidation) / float(position.entry) < 0.03:
            return action("REDUCE", "LIQUIDATION_DISTANCE_WARNING", fraction=0.5)
    if thesis_invalid:
        return action("EXIT", "STRATEGY_THESIS_INVALIDATED")
    if quote is None or quote.reason(event.spec, now):
        return action("RECONCILE", "EXECUTABLE_PRICE_UNKNOWN; mark is not an executable quote")
    price = float(quote.bid if side == 1 else quote.ask)
    risk = abs(float(position.entry - position.initial_stop))
    r = side * (price - float(position.entry)) / risk if risk else 0
    threshold = policy.partial_at_r if policy else partial_at_r
    fraction = policy.partial_fraction if policy else 0.5
    trailing = policy.trailing_atr if policy else 2
    if r >= threshold and not already_partial and position.partial_closes == 0:
        return action("PARTIAL_EXIT", "PROFIT_POLICY_TRIGGERED", fraction=fraction)
    if atr and r > 0.5:
        suggested = quantize(
            dec(price) - dec(side) * dec(trailing) * dec(atr), event.spec.tick_size, up=side == -1
        )
        if side * float(suggested - position.stop) > 0:
            return action("TIGHTEN_STOP", "VOLATILITY_TRAIL_PROJECTION", suggested)
    return action("HOLD", "THESIS_AND_STOP_INTACT")
