"""Deterministic Position Supervisor for Live V1."""

from __future__ import annotations

import json
import secrets
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ..decision.models import CasePackageV1
from ..live_db import connection
from .models import PositionEventV1, PositionObservationV1, SupervisorPolicyV1


def position_case_from_event(
    base: CasePackageV1, event: PositionEventV1, now_ms: int
) -> CasePackageV1:
    ttl = max(60_000, base.expires_at_ms - base.created_at_ms)
    return CasePackageV1.build(
        case_id=f"pos-{event.event_id}",
        created_at_ms=now_ms,
        observed_at_ms=now_ms,
        expires_at_ms=now_ms + ttl,
        symbol=base.symbol,
        trigger=event.trigger,
        strategy=base.strategy,
        strategy_version=base.strategy_version,
        direction=base.direction,
        evidence_id=base.evidence_id,
        snapshot_hash=base.snapshot_hash,
        signal_identity=base.signal_identity,
        source="POSITION_SUPERVISOR",
        base_case_hash=base.case_hash,
        position_event_hash=event.event_hash,
        price=base.price,
        entry_low=base.entry_low,
        entry_high=base.entry_high,
        stop_loss=base.stop_loss,
        take_profit_1=base.take_profit_1,
        take_profit_2=base.take_profit_2,
        atr=base.atr,
        data_quality=base.data_quality,
        spread_bps=base.spread_bps,
        liquidity_usdt=base.liquidity_usdt,
    )


class PositionSupervisor:
    def __init__(
        self,
        path: str | Path,
        analysis_service: Any = None,
        fresh_market_case: Callable[[str], CasePackageV1] | None = None,
        policy: SupervisorPolicyV1 | None = None,
    ) -> None:
        self.path = Path(path)
        self.analysis_service = analysis_service
        self.fresh_market_case = fresh_market_case
        self.policy = policy or SupervisorPolicyV1()

        with connection(self.path) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS live_position_events (
                    event_id TEXT PRIMARY KEY,
                    event_hash TEXT NOT NULL UNIQUE,
                    trigger TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    source_hash TEXT NOT NULL,
                    observed_at_ms INTEGER NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_live_position_events_lookup
                    ON live_position_events(symbol, trigger, observed_at_ms DESC);
                CREATE INDEX IF NOT EXISTS idx_live_position_events_source
                    ON live_position_events(source_hash);
                CREATE TABLE IF NOT EXISTS live_position_active (
                    symbol TEXT PRIMARY KEY,
                    is_open INTEGER NOT NULL DEFAULT 0,
                    last_opened_at_ms INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS live_position_case_dispatches (
                    event_hash TEXT PRIMARY KEY,
                    case_hash TEXT NOT NULL,
                    dispatched_at_ms INTEGER NOT NULL
                );
            """)

    def evaluate(
        self, obs: PositionObservationV1, now_ms: int
    ) -> tuple[PositionEventV1, ...]:
        with connection(self.path) as db:
            db.execute("BEGIN IMMEDIATE")

            # 1. Exact source deduplication
            existing = db.execute(
                "SELECT 1 FROM live_position_events WHERE source_hash=? LIMIT 1",
                (obs.observation_hash,),
            ).fetchone()
            if existing is not None:
                return ()

            active_row = db.execute(
                "SELECT is_open FROM live_position_active WHERE symbol=?",
                (obs.symbol,),
            ).fetchone()
            is_currently_open = bool(active_row and active_row["is_open"])

            # Handle position closing update
            if obs.quantity == 0.0 and is_currently_open:
                db.execute(
                    "UPDATE live_position_active SET is_open=0 WHERE symbol=?",
                    (obs.symbol,),
                )
                is_currently_open = False

            events: list[PositionEventV1] = []

            # 2. Check each trigger predicate
            triggers_to_check: list[str] = []

            if obs.previous_quantity == 0.0 and obs.quantity != 0.0 and not is_currently_open:
                triggers_to_check.append("POSITION_OPENED")

            if (
                obs.order_status == "PARTIALLY_FILLED"
                and (now_ms - obs.order_observed_at_ms) >= self.policy.stale_partial_fill_ms
            ):
                triggers_to_check.append("PARTIAL_FILL_STALE")

            if obs.stop_price > 0 and obs.entry_price > 0:
                dist_stop = abs(obs.mark_price - obs.stop_price) / obs.entry_price
                if dist_stop <= self.policy.stop_near_pct:
                    triggers_to_check.append("STOP_NEAR")

            if obs.take_profit_price > 0 and obs.entry_price > 0:
                dist_tp = abs(obs.take_profit_price - obs.mark_price) / obs.entry_price
                if dist_tp <= self.policy.tp_near_pct:
                    triggers_to_check.append("TP_NEAR")

            if obs.tactical_regime is not None and (
                (obs.quantity > 0 and obs.tactical_regime == "BEARISH")
                or (obs.quantity < 0 and obs.tactical_regime == "BULLISH")
            ):
                triggers_to_check.append("REGIME_REVERSAL")

            if obs.oi_change_pct is not None and abs(obs.oi_change_pct) >= self.policy.oi_shock_pct:
                triggers_to_check.append("OI_SHOCK")

            if obs.funding_rate is not None and abs(obs.funding_rate) >= self.policy.funding_shock_rate:
                triggers_to_check.append("FUNDING_SHOCK")

            if obs.volatility_percentile is not None and obs.volatility_percentile >= self.policy.volatility_spike_percentile:
                triggers_to_check.append("VOLATILITY_SPIKE")

            if obs.spread_bps is not None and obs.spread_bps >= self.policy.liquidity_deterioration_bps:
                triggers_to_check.append("LIQUIDITY_DETERIORATION")

            if obs.grid_boundary_breached:
                triggers_to_check.append("GRID_BOUNDARY_BREACH")

            if (
                obs.add_opportunity
                and obs.evidence_id is not None
                and obs.signal_identity is not None
                and obs.evidence_id not in obs.prior_evidence_ids
                and obs.signal_identity not in obs.prior_signal_identities
            ):
                triggers_to_check.append("ADD_OPPORTUNITY")

            for trigger in triggers_to_check:
                # Cooldown check
                recent = db.execute(
                    "SELECT observed_at_ms FROM live_position_events "
                    "WHERE symbol=? AND trigger=? AND (? - observed_at_ms) < ? "
                    "ORDER BY observed_at_ms DESC LIMIT 1",
                    (obs.symbol, trigger, now_ms, self.policy.cooldown_ms),
                ).fetchone()
                if recent is not None:
                    continue

                event = PositionEventV1.build(
                    event_id=f"pe-{secrets.token_hex(12)}",
                    trigger=trigger,
                    symbol=obs.symbol,
                    source_hash=obs.observation_hash,
                    observed_at_ms=now_ms,
                    details={"mark_price": obs.mark_price, "quantity": obs.quantity},
                )
                db.execute(
                    "INSERT INTO live_position_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.event_hash,
                        event.trigger,
                        event.symbol,
                        event.source_hash,
                        event.observed_at_ms,
                        event.canonical_json(),
                    ),
                )
                events.append(event)

                if trigger == "POSITION_OPENED":
                    db.execute(
                        "INSERT INTO live_position_active (symbol, is_open, last_opened_at_ms) "
                        "VALUES (?, 1, ?) "
                        "ON CONFLICT(symbol) DO UPDATE SET is_open=1, last_opened_at_ms=?",
                        (obs.symbol, now_ms, now_ms),
                    )

            return tuple(events)

    def get_event(self, event_id: str) -> PositionEventV1 | None:
        with connection(self.path) as db:
            row = db.execute(
                "SELECT payload FROM live_position_events WHERE event_id=?",
                (event_id,),
            ).fetchone()
            if row is None:
                return None
            return PositionEventV1.model_validate(json.loads(row["payload"]))

    async def process(
        self, obs: PositionObservationV1, now_ms: int
    ) -> tuple[PositionEventV1, ...]:
        events = self.evaluate(obs, now_ms)
        if events and self.analysis_service is not None and self.fresh_market_case is not None:
            for event in events:
                with connection(self.path) as db:
                    dispatched = db.execute(
                        "SELECT 1 FROM live_position_case_dispatches WHERE event_hash=?",
                        (event.event_hash,),
                    ).fetchone()
                if dispatched is not None:
                    continue

                base_case = self.fresh_market_case(obs.symbol)
                pos_case = position_case_from_event(base_case, event, now_ms=now_ms)
                await self.analysis_service.analyze_case(pos_case)

                with connection(self.path) as db:
                    db.execute(
                        "INSERT OR IGNORE INTO live_position_case_dispatches VALUES (?, ?, ?)",
                        (event.event_hash, pos_case.case_hash, now_ms),
                    )
        return events
