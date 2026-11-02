from __future__ import annotations

import copy
import json
import logging
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from ..data.binance import BinancePublicClient
from ..domain import Candle
from .domain import GridDecision, GridPlan
from .evidence import (
    GridPlanEvidence,
    TacticalFeatureEvidenceV2,
    validate_tactical_feature_evidence,
    verify_tactical_evidence_identity,
)
from .grid_policy import should_alert_grid_change
from .grid_shadow_evidence import (
    GRID_ACCOUNTING_VERSION,
    GRID_HORIZON_MS,
    GRID_OUTCOME_PROFILE_VERSION,
    GRID_PATH_MODEL_VERSION,
    TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION,
    GridEligibilityStatus,
    GridTerminalReason,
    TacticalGridShadowEvaluationV1,
    TacticalGridShadowEvaluationValidationError,
    compute_anchor_index,
    construct_grid_levels,
    resolve_reference_price,
    validate_tactical_grid_shadow_evaluation,
)
from .state import MarketWatchStateStore

logger = logging.getLogger(__name__)


# ==============================================================================
# Simulation Domain Models
# ==============================================================================

@dataclass
class OpenLot:
    """An active lot filling a specific grid slot."""

    slot_index: int
    side: str  # "LONG" or "SHORT"
    open_price: float
    open_time_ms: int
    quantity: float
    opening_fee: float


@dataclass
class GridSimulationState:
    """Mutable economic state tracking throughout a 1m candle path."""

    open_lots: dict[int, OpenLot] = field(default_factory=dict)
    paired_cycle_count: int = 0
    paired_gross_pnl: float = 0.0
    paired_maker_fees: float = 0.0
    terminal_unpaired_gross_pnl: float = 0.0
    terminal_taker_fee: float = 0.0
    terminal_slippage_cost: float = 0.0

    is_terminal: bool = False
    terminal_time_ms: int | None = None
    terminal_reason: str | None = None
    terminal_execution_price: float | None = None

    last_mark_price: float = 0.0
    last_mark_time_ms: int = 0

    accrued_funding_pnl: float = 0.0
    funding_status: str = "COMPLETE"
    funding_settlement_count: int = 0

    # Curve / metric tracking
    min_marked_equity: float = 0.0
    peak_marked_equity: float = 0.0
    max_drawdown_from_prior_peak: float = 0.0
    long_inventory_peak: float = 0.0
    short_inventory_peak: float = 0.0
    max_abs_inventory_notional: float = 0.0
    max_open_lot_count: int = 0

    # Time-weighted tracking: list of (duration_ms, abs_notional)
    time_weighted_inventory_segments: list[tuple[int, float]] = field(default_factory=list)
    equity_snapshots: list[tuple[int, float]] = field(default_factory=list)

    # Boundary metrics
    lower_boundary_breached: bool = False
    upper_boundary_breached: bool = False
    first_lower_boundary_breach_ms: int | None = None
    first_upper_boundary_breach_ms: int | None = None
    boundary_breach_count: int = 0

    ambiguity_events: list[dict[str, Any]] = field(default_factory=list)

    def clone(self) -> GridSimulationState:
        """Deep clone state for two-path intrabar branch simulation."""
        cloned = GridSimulationState(
            open_lots={k: copy.copy(v) for k, v in self.open_lots.items()},
            paired_cycle_count=self.paired_cycle_count,
            paired_gross_pnl=self.paired_gross_pnl,
            paired_maker_fees=self.paired_maker_fees,
            terminal_unpaired_gross_pnl=self.terminal_unpaired_gross_pnl,
            terminal_taker_fee=self.terminal_taker_fee,
            terminal_slippage_cost=self.terminal_slippage_cost,
            is_terminal=self.is_terminal,
            terminal_time_ms=self.terminal_time_ms,
            terminal_reason=self.terminal_reason,
            terminal_execution_price=self.terminal_execution_price,
            last_mark_price=self.last_mark_price,
            last_mark_time_ms=self.last_mark_time_ms,
            accrued_funding_pnl=self.accrued_funding_pnl,
            funding_status=self.funding_status,
            funding_settlement_count=self.funding_settlement_count,
            min_marked_equity=self.min_marked_equity,
            peak_marked_equity=self.peak_marked_equity,
            max_drawdown_from_prior_peak=self.max_drawdown_from_prior_peak,
            long_inventory_peak=self.long_inventory_peak,
            short_inventory_peak=self.short_inventory_peak,
            max_abs_inventory_notional=self.max_abs_inventory_notional,
            max_open_lot_count=self.max_open_lot_count,
            time_weighted_inventory_segments=list(self.time_weighted_inventory_segments),
            equity_snapshots=list(self.equity_snapshots),
            lower_boundary_breached=self.lower_boundary_breached,
            upper_boundary_breached=self.upper_boundary_breached,
            first_lower_boundary_breach_ms=self.first_lower_boundary_breach_ms,
            first_upper_boundary_breach_ms=self.first_upper_boundary_breach_ms,
            boundary_breach_count=self.boundary_breach_count,
            ambiguity_events=list(self.ambiguity_events),
        )
        return cloned

    def compute_signed_inventory_notional(self, mark_price: float) -> float:
        """Compute signed marked inventory notional (+1 long, -1 short)."""
        tot = 0.0
        for lot in self.open_lots.values():
            sign = 1.0 if lot.side == "LONG" else -1.0
            tot += lot.quantity * mark_price * sign
        return tot

    def compute_unrealized_pnl(self, mark_price: float) -> float:
        """Compute mark-to-market unrealized gross PnL of all open lots."""
        unrealized = 0.0
        for lot in self.open_lots.values():
            if lot.side == "LONG":
                unrealized += lot.quantity * (mark_price - lot.open_price)
            else:
                unrealized += lot.quantity * (lot.open_price - mark_price)
        return unrealized

    def compute_current_marked_equity(self, mark_price: float) -> float:
        """Compute total marked equity including realized PnL, fees, slippage, accrued funding, and unrealized PnL."""
        total_fees = self.paired_maker_fees + self.terminal_taker_fee
        total_slippage = self.terminal_slippage_cost
        realized_pnl = self.paired_gross_pnl + self.terminal_unpaired_gross_pnl
        unrealized = self.compute_unrealized_pnl(mark_price)
        funding = self.accrued_funding_pnl if self.funding_status == "COMPLETE" else 0.0
        return realized_pnl - total_fees - total_slippage + funding + unrealized

    def record_mark_snapshot(self, timestamp_ms: int, mark_price: float) -> None:
        """Update inventory peaks, drawdown, and time-weighted curve at timestamp."""
        if self.last_mark_time_ms > 0 and timestamp_ms > self.last_mark_time_ms:
            duration = timestamp_ms - self.last_mark_time_ms
            prev_notional = abs(self.compute_signed_inventory_notional(self.last_mark_price))
            self.time_weighted_inventory_segments.append((duration, prev_notional))

        self.last_mark_price = mark_price
        self.last_mark_time_ms = timestamp_ms

        signed_notional = self.compute_signed_inventory_notional(mark_price)
        abs_notional = abs(signed_notional)
        self.max_abs_inventory_notional = max(self.max_abs_inventory_notional, abs_notional)
        self.max_open_lot_count = max(self.max_open_lot_count, len(self.open_lots))

        long_notional = sum(lot.quantity * mark_price for lot in self.open_lots.values() if lot.side == "LONG")
        short_notional = sum(lot.quantity * mark_price for lot in self.open_lots.values() if lot.side == "SHORT")
        self.long_inventory_peak = max(self.long_inventory_peak, long_notional)
        self.short_inventory_peak = max(self.short_inventory_peak, short_notional)

        equity = self.compute_current_marked_equity(mark_price)
        self.equity_snapshots.append((timestamp_ms, equity))
        self.min_marked_equity = min(self.min_marked_equity, equity)
        self.peak_marked_equity = max(self.peak_marked_equity, equity)
        drawdown = equity - self.peak_marked_equity
        self.max_drawdown_from_prior_peak = min(self.max_drawdown_from_prior_peak, drawdown)


# ==============================================================================
# Crossing & Path Simulation Engine
# ==============================================================================

def _process_monotonic_segment(
    state: GridSimulationState,
    p0: float,
    p1: float,
    timestamp_ms: int,
    *,
    grid_decision: str,
    levels: tuple[float, ...],
    anchor_index: int,
    unit_notional: float,
    maker_fee_rate: float,
    taker_fee_rate: float,
    slippage_bps_per_side: float,
    stop_loss: float | None,
    take_profit: float | None,
) -> bool:
    """Process a single monotonic price segment (p0 -> p1). Returns True if terminal event reached."""
    if state.is_terminal:
        return True

    # Identify terminal triggers along segment
    is_ascending = p0 < p1
    is_descending = p0 > p1

    terminal_hit: str | None = None
    terminal_target_price: float | None = None

    if stop_loss is not None and ((is_descending and p0 >= stop_loss >= p1) or (is_ascending and p0 <= stop_loss <= p1)):
        terminal_hit = GridTerminalReason.STOP_LOSS.value
        terminal_target_price = stop_loss

    if take_profit is not None and ((is_ascending and p0 <= take_profit <= p1) or (is_descending and p0 >= take_profit >= p1)):
        # If both stop and tp are in range, earlier one along segment triggers
        if terminal_hit is not None and terminal_target_price is not None:
            dist_stop = abs(terminal_target_price - p0)
            dist_tp = abs(take_profit - p0)
            if dist_tp < dist_stop:
                terminal_hit = GridTerminalReason.TAKE_PROFIT.value
                terminal_target_price = take_profit
        else:
            terminal_hit = GridTerminalReason.TAKE_PROFIT.value
            terminal_target_price = take_profit

    # Restrict level crossings to before the terminal trigger if one occurs
    effective_p1 = p1 if terminal_target_price is None else terminal_target_price

    n_levels = len(levels)
    n_slots = n_levels - 1

    if is_ascending:
        # Crossings in ascending order (lowest crossed -> highest crossed)
        crossed_indices = [
            i for i in range(n_levels)
            if p0 <= levels[i] <= effective_p1
        ]
        crossed_indices.sort()

        for idx in crossed_indices:
            lvl = levels[idx]
            if grid_decision == GridDecision.LONG_BIAS.value:
                # Upward crossing of level[idx] closes long slot idx - 1
                closing_slot = idx - 1
                if closing_slot in state.open_lots:
                    lot = state.open_lots.pop(closing_slot)
                    gross = lot.quantity * (lvl - lot.open_price)
                    close_fee = abs(lot.quantity * lvl) * maker_fee_rate
                    state.paired_cycle_count += 1
                    state.paired_gross_pnl += gross
                    state.paired_maker_fees += close_fee
                    state.record_mark_snapshot(timestamp_ms, lvl)

            elif grid_decision == GridDecision.SHORT_BIAS.value:
                # Upward crossing of level[idx] opens short slot idx
                if 1 <= idx <= n_slots and idx not in state.open_lots:
                    qty = unit_notional / lvl
                    open_fee = unit_notional * maker_fee_rate
                    lot = OpenLot(
                        slot_index=idx,
                        side="SHORT",
                        open_price=lvl,
                        open_time_ms=timestamp_ms,
                        quantity=qty,
                        opening_fee=open_fee,
                    )
                    state.open_lots[idx] = lot
                    state.paired_maker_fees += open_fee
                    state.record_mark_snapshot(timestamp_ms, lvl)

            elif grid_decision == GridDecision.NEUTRAL.value:
                # Below or at anchor: upward crossing closes long slot idx - 1
                if idx <= anchor_index:
                    closing_slot = idx - 1
                    if closing_slot in state.open_lots:
                        lot = state.open_lots.pop(closing_slot)
                        gross = lot.quantity * (lvl - lot.open_price)
                        close_fee = abs(lot.quantity * lvl) * maker_fee_rate
                        state.paired_cycle_count += 1
                        state.paired_gross_pnl += gross
                        state.paired_maker_fees += close_fee
                        state.record_mark_snapshot(timestamp_ms, lvl)
                # Above anchor: upward crossing opens short slot idx
                elif idx > anchor_index:
                    if idx not in state.open_lots:
                        qty = unit_notional / lvl
                        open_fee = unit_notional * maker_fee_rate
                        lot = OpenLot(
                            slot_index=idx,
                            side="SHORT",
                            open_price=lvl,
                            open_time_ms=timestamp_ms,
                            quantity=qty,
                            opening_fee=open_fee,
                        )
                        state.open_lots[idx] = lot
                        state.paired_maker_fees += open_fee
                        state.record_mark_snapshot(timestamp_ms, lvl)

    elif is_descending:
        # Crossings in descending order (highest crossed -> lowest crossed)
        crossed_indices = [
            i for i in range(n_levels)
            if effective_p1 <= levels[i] <= p0
        ]
        crossed_indices.sort(reverse=True)

        for idx in crossed_indices:
            lvl = levels[idx]
            if grid_decision == GridDecision.LONG_BIAS.value:
                # Downward crossing of level[idx] opens long slot idx
                if 0 <= idx < n_slots and idx not in state.open_lots:
                    qty = unit_notional / lvl
                    open_fee = unit_notional * maker_fee_rate
                    lot = OpenLot(
                        slot_index=idx,
                        side="LONG",
                        open_price=lvl,
                        open_time_ms=timestamp_ms,
                        quantity=qty,
                        opening_fee=open_fee,
                    )
                    state.open_lots[idx] = lot
                    state.paired_maker_fees += open_fee
                    state.record_mark_snapshot(timestamp_ms, lvl)

            elif grid_decision == GridDecision.SHORT_BIAS.value:
                # Downward crossing of level[idx] closes short slot idx + 1
                closing_slot = idx + 1
                if closing_slot in state.open_lots:
                    lot = state.open_lots.pop(closing_slot)
                    gross = lot.quantity * (lot.open_price - lvl)
                    close_fee = abs(lot.quantity * lvl) * maker_fee_rate
                    state.paired_cycle_count += 1
                    state.paired_gross_pnl += gross
                    state.paired_maker_fees += close_fee
                    state.record_mark_snapshot(timestamp_ms, lvl)

            elif grid_decision == GridDecision.NEUTRAL.value:
                # Above or at anchor: downward crossing closes short slot idx + 1
                if idx >= anchor_index:
                    closing_slot = idx + 1
                    if closing_slot in state.open_lots:
                        lot = state.open_lots.pop(closing_slot)
                        gross = lot.quantity * (lot.open_price - lvl)
                        close_fee = abs(lot.quantity * lvl) * maker_fee_rate
                        state.paired_cycle_count += 1
                        state.paired_gross_pnl += gross
                        state.paired_maker_fees += close_fee
                        state.record_mark_snapshot(timestamp_ms, lvl)
                # Below anchor: downward crossing opens long slot idx
                elif idx < anchor_index:
                    if idx not in state.open_lots:
                        qty = unit_notional / lvl
                        open_fee = unit_notional * maker_fee_rate
                        lot = OpenLot(
                            slot_index=idx,
                            side="LONG",
                            open_price=lvl,
                            open_time_ms=timestamp_ms,
                            quantity=qty,
                            opening_fee=open_fee,
                        )
                        state.open_lots[idx] = lot
                        state.paired_maker_fees += open_fee
                        state.record_mark_snapshot(timestamp_ms, lvl)

    if terminal_hit is not None and terminal_target_price is not None:
        _force_close_at_terminal(
            state,
            terminal_price=terminal_target_price,
            terminal_time_ms=timestamp_ms,
            reason=terminal_hit,
            taker_fee_rate=taker_fee_rate,
            slippage_bps_per_side=slippage_bps_per_side,
        )
        return True

    state.record_mark_snapshot(timestamp_ms, p1)
    return False


def _force_close_at_terminal(
    state: GridSimulationState,
    terminal_price: float,
    terminal_time_ms: int,
    reason: str,
    taker_fee_rate: float,
    slippage_bps_per_side: float,
) -> None:
    """Force close all remaining open lots at terminal liquidation price."""
    state.is_terminal = True
    state.terminal_reason = reason
    state.terminal_time_ms = terminal_time_ms
    state.terminal_execution_price = terminal_price

    unpaired_gross = 0.0
    taker_fees = 0.0
    slippage_costs = 0.0

    slippage_mult = slippage_bps_per_side / 10000.0

    for lot in list(state.open_lots.values()):
        if lot.side == "LONG":
            exec_price = terminal_price * (1.0 - slippage_mult)
            gross = lot.quantity * (exec_price - lot.open_price)
            slip = lot.quantity * terminal_price * slippage_mult
            fee = abs(lot.quantity * exec_price) * taker_fee_rate
        else:
            exec_price = terminal_price * (1.0 + slippage_mult)
            gross = lot.quantity * (lot.open_price - exec_price)
            slip = lot.quantity * terminal_price * slippage_mult
            fee = abs(lot.quantity * exec_price) * taker_fee_rate

        unpaired_gross += gross
        taker_fees += fee
        slippage_costs += slip

    state.open_lots.clear()
    state.terminal_unpaired_gross_pnl = unpaired_gross
    state.terminal_taker_fee = taker_fees
    state.terminal_slippage_cost = slippage_costs

    state.record_mark_snapshot(terminal_time_ms, terminal_price)


def _simulate_path(
    initial_state: GridSimulationState,
    path_points: Sequence[float],
    timestamp_ms: int,
    **kwargs: Any,
) -> GridSimulationState:
    """Run simulation sequentially across segments defined by path points."""
    st = initial_state.clone()
    for i in range(len(path_points) - 1):
        p0 = path_points[i]
        p1 = path_points[i + 1]
        terminated = _process_monotonic_segment(st, p0, p1, timestamp_ms, **kwargs)
        if terminated:
            break
    return st


# ==============================================================================
# Conservative Two-Path Intrabar Arbiter
# ==============================================================================

def _select_conservative_state(
    state_a: GridSimulationState,
    state_b: GridSimulationState,
    close_price: float,
) -> tuple[GridSimulationState, str, bool]:
    """Select between PATH_A and PATH_B states according to deterministic conservative hierarchy.

    Precedence:
    1. Lower total marked equity
    2. Larger absolute inventory notional
    3. Larger cumulative fees/costs
    4. Lexicographically smaller path identity ("PATH_A" < "PATH_B")
    """
    eq_a = state_a.compute_current_marked_equity(close_price)
    eq_b = state_b.compute_current_marked_equity(close_price)

    inv_a = abs(state_a.compute_signed_inventory_notional(close_price))
    inv_b = abs(state_b.compute_signed_inventory_notional(close_price))

    costs_a = (state_a.paired_maker_fees + state_a.terminal_taker_fee + state_a.terminal_slippage_cost)
    costs_b = (state_b.paired_maker_fees + state_b.terminal_taker_fee + state_b.terminal_slippage_cost)

    is_divergent = not (
        math.isclose(eq_a, eq_b, rel_tol=1e-8, abs_tol=1e-8)
        and math.isclose(inv_a, inv_b, rel_tol=1e-8, abs_tol=1e-8)
        and state_a.paired_cycle_count == state_b.paired_cycle_count
        and state_a.is_terminal == state_b.is_terminal
    )

    if not math.isclose(eq_a, eq_b, rel_tol=1e-8, abs_tol=1e-8):
        if eq_a < eq_b:
            return state_a, "PATH_A", is_divergent
        return state_b, "PATH_B", is_divergent

    if not math.isclose(inv_a, inv_b, rel_tol=1e-8, abs_tol=1e-8):
        if inv_a > inv_b:
            return state_a, "PATH_A", is_divergent
        return state_b, "PATH_B", is_divergent

    if not math.isclose(costs_a, costs_b, rel_tol=1e-8, abs_tol=1e-8):
        if costs_a > costs_b:
            return state_a, "PATH_A", is_divergent
        return state_b, "PATH_B", is_divergent

    return state_a, "PATH_A", is_divergent


# ==============================================================================
# Full Episode Evaluator
# ==============================================================================

def evaluate_grid_shadow_episode(
    evidence: TacticalFeatureEvidenceV2,
    candles_1m: Sequence[Candle],
    *,
    funding_records: Sequence[Mapping[str, Any]] = (),
    future_assessments: Sequence[Mapping[str, Any]] = (),
    assessment_diagnostic_coverage: str = "COMPLETE",
) -> TacticalGridShadowEvaluationV1:
    """Evaluate realized forward outcome of a frozen TacticalFeatureEvidenceV2 grid plan."""
    validate_tactical_feature_evidence(evidence)
    verify_tactical_evidence_identity(evidence)

    grid_plan_ev = evidence.grid_advisory_plan
    if grid_plan_ev is None:
        raise TacticalGridShadowEvaluationValidationError("feature evidence has null grid_advisory_plan")

    symbol = evidence.symbol
    decision_time_ms = evidence.decision_time_ms
    horizon_end_ms = decision_time_ms + GRID_HORIZON_MS

    # Decode cost parameters from decision-time config
    cfg_dict = evidence.decision_config.to_dict()
    maker_fee_rate = float(cfg_dict.get("maker_fee_rate", 0.0002))
    taker_fee_rate = float(cfg_dict.get("taker_fee_rate", 0.0005))
    slippage_bps = float(cfg_dict.get("slippage_bps_per_side", 2.0))

    grid_decision = grid_plan_ev.decision

    # 1. NOT_ACTIVE_PAUSE handling
    if grid_decision == GridDecision.PAUSE.value:
        return _build_pause_evaluation(
            evidence=evidence,
            grid_plan_ev=grid_plan_ev,
            future_assessments=future_assessments,
            assessment_diagnostic_coverage=assessment_diagnostic_coverage,
        )

    # 2. Active grid geometry
    if grid_plan_ev.lower_bound is None or grid_plan_ev.upper_bound is None or grid_plan_ev.grid_count < 3:
        raise TacticalGridShadowEvaluationValidationError(
            f"Active grid plan has invalid bounds/count: lower={grid_plan_ev.lower_bound}, upper={grid_plan_ev.upper_bound}, N={grid_plan_ev.grid_count}"
        )

    ref_price = resolve_reference_price(grid_plan_ev, evidence)
    levels = construct_grid_levels(grid_plan_ev.lower_bound, grid_plan_ev.upper_bound, grid_plan_ev.grid_count)
    anchor_idx = compute_anchor_index(levels, ref_price)
    unit_notional = 1.0 / grid_plan_ev.grid_count

    # Filter candles strictly after decision time
    valid_candles = [c for c in candles_1m if c.close_time_ms > decision_time_ms and c.open_time_ms < horizon_end_ms]
    valid_candles.sort(key=lambda c: c.open_time_ms)

    # Check 1m coverage
    market_path_coverage = "COMPLETE"
    if not valid_candles:
        market_path_coverage = "INCOMPLETE"
    else:
        # Check start coverage: first candle should open at or before decision_time_ms + 60_000
        if valid_candles[0].open_time_ms > decision_time_ms + 60_000:
            market_path_coverage = "INCOMPLETE"
        # Check continuity
        for i in range(len(valid_candles) - 1):
            if valid_candles[i + 1].open_time_ms != valid_candles[i].close_time_ms:
                market_path_coverage = "INCOMPLETE"
                break

    state = GridSimulationState()
    state.record_mark_snapshot(decision_time_ms, ref_price)

    # Index funding records
    funding_events_sorted = sorted(funding_records, key=lambda f: int(f.get("funding_time_ms", 0)))

    sim_params = {
        "grid_decision": grid_decision,
        "levels": levels,
        "anchor_index": anchor_idx,
        "unit_notional": unit_notional,
        "maker_fee_rate": maker_fee_rate,
        "taker_fee_rate": taker_fee_rate,
        "slippage_bps_per_side": slippage_bps,
        "stop_loss": grid_plan_ev.stop_loss,
        "take_profit": grid_plan_ev.take_profit,
    }

    # Simulate minute-by-minute
    for candle in valid_candles:
        if state.is_terminal:
            break

        # Check boundary breaches
        if candle.low < grid_plan_ev.lower_bound:
            state.lower_boundary_breached = True
            if state.first_lower_boundary_breach_ms is None:
                state.first_lower_boundary_breach_ms = candle.open_time_ms
            state.boundary_breach_count += 1
        if candle.high > grid_plan_ev.upper_bound:
            state.upper_boundary_breached = True
            if state.first_upper_boundary_breach_ms is None:
                state.first_upper_boundary_breach_ms = candle.open_time_ms
            state.boundary_breach_count += 1

        prev_lots_count = len(state.open_lots)
        prev_cycles = state.paired_cycle_count

        # Run Two-Path Intrabar Model
        path_a_points = [candle.open, candle.high, candle.low, candle.close]
        path_b_points = [candle.open, candle.low, candle.high, candle.close]

        state_a = _simulate_path(state, path_a_points, candle.close_time_ms, **sim_params)
        state_b = _simulate_path(state, path_b_points, candle.close_time_ms, **sim_params)

        chosen_state, chosen_path, is_divergent = _select_conservative_state(state_a, state_b, candle.close)
        if is_divergent:
            state.ambiguity_events.append({
                "type": "TWO_PATH_DIVERGENCE",
                "candle_open_ms": candle.open_time_ms,
                "selected_path": chosen_path,
            })

        state = chosen_state

        # Check funding settlements falling in this candle
        lots_changed = (len(state.open_lots) != prev_lots_count) or (state.paired_cycle_count != prev_cycles)
        for f in funding_events_sorted:
            f_time = int(f.get("funding_time_ms", 0))
            if candle.open_time_ms <= f_time <= candle.close_time_ms:
                if lots_changed:
                    state.funding_status = "AMBIGUOUS_FUNDING_BOUNDARY"
                    state.ambiguity_events.append({
                        "type": "AMBIGUOUS_FUNDING_BOUNDARY",
                        "funding_time_ms": f_time,
                        "candle_open_ms": candle.open_time_ms,
                    })
                else:
                    f_rate = float(f.get("funding_rate", 0.0))
                    f_mark = f.get("mark_price")
                    if f_mark is None:
                        state.funding_status = "INCOMPLETE"
                    elif state.funding_status == "COMPLETE":
                        signed_notional = state.compute_signed_inventory_notional(float(f_mark))
                        cash = -signed_notional * f_rate
                        state.accrued_funding_pnl += cash
                        state.funding_settlement_count += 1

    # End of horizon check
    if not state.is_terminal and valid_candles and valid_candles[-1].close_time_ms >= horizon_end_ms:
        final_c = valid_candles[-1]
        _force_close_at_terminal(
            state,
            terminal_price=final_c.close,
            terminal_time_ms=horizon_end_ms,
            reason=GridTerminalReason.HORIZON.value,
            taker_fee_rate=taker_fee_rate,
            slippage_bps_per_side=slippage_bps,
        )

    # Compute aggregate time-weighted inventory
    total_time_ms = sum(dur for dur, _ in state.time_weighted_inventory_segments)
    if total_time_ms > 0:
        mean_abs_inv = sum(dur * notional for dur, notional in state.time_weighted_inventory_segments) / total_time_ms
    else:
        mean_abs_inv = 0.0

    mean_utilization = mean_abs_inv / 1.0
    peak_utilization = state.max_abs_inventory_notional / 1.0

    gross_before_costs = state.paired_gross_pnl + state.terminal_unpaired_gross_pnl
    total_fees = state.paired_maker_fees + state.terminal_taker_fee
    total_slippage = state.terminal_slippage_cost
    net_pnl_fees_slip = gross_before_costs - total_fees - total_slippage

    funding_pnl = state.accrued_funding_pnl if state.funding_status == "COMPLETE" else None
    net_pnl_funding = (net_pnl_fees_slip + funding_pnl) if funding_pnl is not None else None

    # Eligibility & terminal status
    if market_path_coverage == "INCOMPLETE":
        eligibility = GridEligibilityStatus.PENDING_DATA_GAP.value
    elif not state.is_terminal:
        eligibility = GridEligibilityStatus.PENDING_HORIZON.value
    else:
        eligibility = GridEligibilityStatus.RESOLVED.value

    # Compute future policy diagnostics
    diag_metrics = _compute_future_policy_diagnostics(
        future_assessments=future_assessments,
        initial_grid_plan=grid_plan_ev,
        evaluation_start_ms=decision_time_ms,
        terminal_time_ms=state.terminal_time_ms or horizon_end_ms,
        equity_snapshots=state.equity_snapshots,
        terminal_net_pnl=net_pnl_fees_slip,
        diagnostic_coverage=assessment_diagnostic_coverage,
    )

    ev_dict = TacticalGridShadowEvaluationV1(
        evaluation_schema_version=TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION,
        evaluation_id="",  # populated below
        evaluation_profile_version=GRID_OUTCOME_PROFILE_VERSION,
        grid_path_model_version=GRID_PATH_MODEL_VERSION,
        grid_accounting_version=GRID_ACCOUNTING_VERSION,
        feature_evidence_id=evidence.evidence_id,
        symbol=symbol,
        decision_time_ms=decision_time_ms,
        snapshot_hash=evidence.snapshot_hash,
        policy_version=evidence.policy_version,
        config_hash=evidence.config_hash,
        semantic_identity=evidence.semantic_identity.to_dict(),
        grid_decision=grid_decision,
        frozen_grid_plan=grid_plan_ev.to_dict(),
        reference_price=ref_price,
        anchor_index=anchor_idx,
        grid_levels=levels,
        evaluation_start_ms=decision_time_ms,
        evaluation_end_ms=horizon_end_ms,
        terminal_time_ms=state.terminal_time_ms,
        terminal_reason=state.terminal_reason,
        eligibility_status=eligibility,
        market_path_coverage=market_path_coverage,
        funding_coverage=state.funding_status,
        future_assessment_diagnostic_status=assessment_diagnostic_coverage,
        ambiguity_events=tuple(state.ambiguity_events),
        paired_cycle_count=state.paired_cycle_count,
        paired_gross_pnl=state.paired_gross_pnl,
        paired_maker_fees=state.paired_maker_fees,
        paired_net_pnl=state.paired_gross_pnl - state.paired_maker_fees,
        terminal_unpaired_gross_pnl=state.terminal_unpaired_gross_pnl,
        terminal_taker_fee=state.terminal_taker_fee,
        terminal_slippage_cost=state.terminal_slippage_cost,
        gross_pnl_before_costs=gross_before_costs,
        total_trading_fees=total_fees,
        total_slippage_cost=total_slippage,
        funding_pnl=funding_pnl,
        net_pnl_after_fees_slippage=net_pnl_fees_slip,
        net_pnl_after_funding=net_pnl_funding,
        max_abs_inventory_notional=state.max_abs_inventory_notional,
        mean_abs_inventory_notional_time_weighted=mean_abs_inv,
        max_open_lot_count=state.max_open_lot_count,
        long_inventory_peak=state.long_inventory_peak,
        short_inventory_peak=state.short_inventory_peak,
        peak_capital_utilization=peak_utilization,
        mean_capital_utilization=mean_utilization,
        min_marked_equity=state.min_marked_equity,
        maximum_underwater=min(0.0, state.min_marked_equity),
        max_drawdown_from_prior_peak=state.max_drawdown_from_prior_peak,
        lower_boundary_breached=state.lower_boundary_breached,
        upper_boundary_breached=state.upper_boundary_breached,
        first_lower_boundary_breach_ms=state.first_lower_boundary_breach_ms,
        first_upper_boundary_breach_ms=state.first_upper_boundary_breach_ms,
        boundary_breach_count=state.boundary_breach_count,
        grid_shift_count=diag_metrics["grid_shift_count"],
        grid_shift_frequency_per_day=diag_metrics["grid_shift_frequency_per_day"],
        first_grid_shift_ms=diag_metrics["first_grid_shift_ms"],
        first_policy_pause_ms=diag_metrics["first_policy_pause_ms"],
        first_technical_trend_transition_ms=diag_metrics["first_technical_trend_transition_ms"],
        net_equity_at_first_trend_transition=diag_metrics["net_equity_at_first_trend_transition"],
        post_transition_net_pnl_delta=diag_metrics["post_transition_net_pnl_delta"],
        trend_transition_loss=diag_metrics["trend_transition_loss"],
        persisted_at_ms=None,
    )

    ev_id = ev_dict.recompute_evaluation_id()
    final_eval = TacticalGridShadowEvaluationV1(
        **{**ev_dict.__dict__, "evaluation_id": ev_id}
    )
    validate_tactical_grid_shadow_evaluation(final_eval)
    return final_eval


def _build_pause_evaluation(
    evidence: TacticalFeatureEvidenceV2,
    grid_plan_ev: GridPlanEvidence,
    future_assessments: Sequence[Mapping[str, Any]],
    assessment_diagnostic_coverage: str,
) -> TacticalGridShadowEvaluationV1:
    """Construct an auditable NOT_ACTIVE_PAUSE evaluation."""
    symbol = evidence.symbol
    decision_time_ms = evidence.decision_time_ms
    horizon_end_ms = decision_time_ms + GRID_HORIZON_MS

    diag_metrics = _compute_future_policy_diagnostics(
        future_assessments=future_assessments,
        initial_grid_plan=grid_plan_ev,
        evaluation_start_ms=decision_time_ms,
        terminal_time_ms=horizon_end_ms,
        equity_snapshots=[(decision_time_ms, 0.0)],
        terminal_net_pnl=0.0,
        diagnostic_coverage=assessment_diagnostic_coverage,
    )

    eval_proto = TacticalGridShadowEvaluationV1(
        evaluation_schema_version=TACTICAL_GRID_SHADOW_EVALUATION_SCHEMA_VERSION,
        evaluation_id="",
        evaluation_profile_version=GRID_OUTCOME_PROFILE_VERSION,
        grid_path_model_version=GRID_PATH_MODEL_VERSION,
        grid_accounting_version=GRID_ACCOUNTING_VERSION,
        feature_evidence_id=evidence.evidence_id,
        symbol=symbol,
        decision_time_ms=decision_time_ms,
        snapshot_hash=evidence.snapshot_hash,
        policy_version=evidence.policy_version,
        config_hash=evidence.config_hash,
        semantic_identity=evidence.semantic_identity.to_dict(),
        grid_decision=GridDecision.PAUSE.value,
        frozen_grid_plan=grid_plan_ev.to_dict(),
        reference_price=None,
        anchor_index=None,
        grid_levels=(),
        evaluation_start_ms=decision_time_ms,
        evaluation_end_ms=horizon_end_ms,
        terminal_time_ms=None,
        terminal_reason=None,
        eligibility_status=GridEligibilityStatus.NOT_ACTIVE_PAUSE.value,
        market_path_coverage="NOT_APPLICABLE",
        funding_coverage="NOT_APPLICABLE",
        future_assessment_diagnostic_status=assessment_diagnostic_coverage,
        ambiguity_events=(),
        paired_cycle_count=0,
        paired_gross_pnl=0.0,
        paired_maker_fees=0.0,
        paired_net_pnl=0.0,
        terminal_unpaired_gross_pnl=0.0,
        terminal_taker_fee=0.0,
        terminal_slippage_cost=0.0,
        gross_pnl_before_costs=0.0,
        total_trading_fees=0.0,
        total_slippage_cost=0.0,
        funding_pnl=None,
        net_pnl_after_fees_slippage=0.0,
        net_pnl_after_funding=None,
        max_abs_inventory_notional=0.0,
        mean_abs_inventory_notional_time_weighted=0.0,
        max_open_lot_count=0,
        long_inventory_peak=0.0,
        short_inventory_peak=0.0,
        peak_capital_utilization=0.0,
        mean_capital_utilization=0.0,
        min_marked_equity=0.0,
        maximum_underwater=0.0,
        max_drawdown_from_prior_peak=0.0,
        lower_boundary_breached=False,
        upper_boundary_breached=False,
        first_lower_boundary_breach_ms=None,
        first_upper_boundary_breach_ms=None,
        boundary_breach_count=0,
        grid_shift_count=diag_metrics["grid_shift_count"],
        grid_shift_frequency_per_day=diag_metrics["grid_shift_frequency_per_day"],
        first_grid_shift_ms=diag_metrics["first_grid_shift_ms"],
        first_policy_pause_ms=diag_metrics["first_policy_pause_ms"],
        first_technical_trend_transition_ms=diag_metrics["first_technical_trend_transition_ms"],
        net_equity_at_first_trend_transition=diag_metrics["net_equity_at_first_trend_transition"],
        post_transition_net_pnl_delta=diag_metrics["post_transition_net_pnl_delta"],
        trend_transition_loss=diag_metrics["trend_transition_loss"],
        persisted_at_ms=None,
    )

    ev_id = eval_proto.recompute_evaluation_id()
    final_eval = TacticalGridShadowEvaluationV1(**{**eval_proto.__dict__, "evaluation_id": ev_id})
    validate_tactical_grid_shadow_evaluation(final_eval)
    return final_eval


def _compute_future_policy_diagnostics(
    *,
    future_assessments: Sequence[Mapping[str, Any]],
    initial_grid_plan: GridPlanEvidence,
    evaluation_start_ms: int,
    terminal_time_ms: int,
    equity_snapshots: Sequence[tuple[int, float]],
    terminal_net_pnl: float,
    diagnostic_coverage: str,
) -> dict[str, Any]:
    """Derive read-only policy shift, pause, and trend transition metrics."""
    if diagnostic_coverage != "COMPLETE":
        return {
            "grid_shift_count": None,
            "grid_shift_frequency_per_day": None,
            "first_grid_shift_ms": None,
            "first_policy_pause_ms": None,
            "first_technical_trend_transition_ms": None,
            "net_equity_at_first_trend_transition": None,
            "post_transition_net_pnl_delta": None,
            "trend_transition_loss": None,
        }

    # Filter subsequent assessments strictly within episode
    subsequent: list[dict[str, Any]] = []
    for asmt in future_assessments:
        t = int(asmt.get("decision_time_ms", 0))
        if evaluation_start_ms < t <= terminal_time_ms:
            subsequent.append(dict(asmt))

    subsequent.sort(key=lambda a: int(a.get("decision_time_ms", 0)))

    prev_plan = GridPlan(
        symbol=initial_grid_plan.decision,
        decision=GridDecision(initial_grid_plan.decision),
        lower_bound=initial_grid_plan.lower_bound,
        upper_bound=initial_grid_plan.upper_bound,
        grid_count=initial_grid_plan.grid_count,
        estimated_grid_pct=initial_grid_plan.estimated_grid_pct,
        trigger_price=initial_grid_plan.trigger_price,
        stop_loss=initial_grid_plan.stop_loss,
        take_profit=initial_grid_plan.take_profit,
        reason_codes=initial_grid_plan.reason_codes,
    )

    shift_count = 0
    first_shift_ms: int | None = None
    first_pause_ms: int | None = None
    first_trend_ms: int | None = None

    for a in subsequent:
        t_ms = int(a.get("decision_time_ms", 0))
        # Parse decision JSON
        dec_payload = a.get("decision_json", "{}")
        if isinstance(dec_payload, str):
            try:
                dec_dict = json.loads(dec_payload)
            except (ValueError, TypeError, json.JSONDecodeError):
                dec_dict = {}
        else:
            dec_dict = dict(dec_payload)

        grid_dict = dec_dict.get("grid", {})
        dec_str = grid_dict.get("decision", GridDecision.PAUSE.value)

        # Parse reason codes
        rc_payload = a.get("reason_codes_json", "[]")
        if isinstance(rc_payload, str):
            try:
                rc_list = json.loads(rc_payload)
            except (ValueError, TypeError, json.JSONDecodeError):
                rc_list = []
        else:
            rc_list = list(rc_payload)

        curr_plan = GridPlan(
            symbol=str(a.get("symbol", "")),
            decision=GridDecision(dec_str) if dec_str in GridDecision._value2member_map_ else GridDecision.PAUSE,
            lower_bound=float(grid_dict["lower_bound"]) if grid_dict.get("lower_bound") is not None else None,
            upper_bound=float(grid_dict["upper_bound"]) if grid_dict.get("upper_bound") is not None else None,
            grid_count=int(grid_dict.get("grid_count", 0)),
            estimated_grid_pct=float(grid_dict["estimated_grid_pct"]) if grid_dict.get("estimated_grid_pct") is not None else None,
            trigger_price=float(grid_dict["trigger_price"]) if grid_dict.get("trigger_price") is not None else None,
            stop_loss=float(grid_dict["stop_loss"]) if grid_dict.get("stop_loss") is not None else None,
            take_profit=float(grid_dict["take_profit"]) if grid_dict.get("take_profit") is not None else None,
            reason_codes=tuple(str(r) for r in rc_list),
        )

        if should_alert_grid_change(curr_plan, prev_plan, threshold_pct=2.0):
            shift_count += 1
            if first_shift_ms is None:
                first_shift_ms = t_ms
            prev_plan = curr_plan

        if curr_plan.decision == GridDecision.PAUSE and first_pause_ms is None:
            first_pause_ms = t_ms

        if (
            first_trend_ms is None
            and any(r in rc_list for r in ("HIGH_ADX_OR_TREND_DOMINANT", "GRID_UNSUITABLE_IN_TREND"))
        ):
            first_trend_ms = t_ms

    shift_freq = float(shift_count)  # per 24 hours (1.0 day)

    net_eq_transition: float | None = None
    delta_pnl: float | None = None
    trend_loss: float | None = None

    if first_trend_ms is not None:
        # Interpolate marked equity at transition time
        matching = [eq for t, eq in equity_snapshots if t <= first_trend_ms]
        net_eq_transition = matching[-1] if matching else 0.0
        delta_pnl = terminal_net_pnl - net_eq_transition
        trend_loss = min(0.0, delta_pnl)

    return {
        "grid_shift_count": shift_count,
        "grid_shift_frequency_per_day": shift_freq,
        "first_grid_shift_ms": first_shift_ms,
        "first_policy_pause_ms": first_pause_ms,
        "first_technical_trend_transition_ms": first_trend_ms,
        "net_equity_at_first_trend_transition": net_eq_transition,
        "post_transition_net_pnl_delta": delta_pnl,
        "trend_transition_loss": trend_loss,
    }


# ==============================================================================
# Service Resolver & Manager
# ==============================================================================

class GridShadowEvaluationManager:
    """Dedicated orchestrator for evaluating pending B2B grid shadow evaluations."""

    def __init__(self, store: MarketWatchStateStore) -> None:
        self.store = store

    def resolve_grid_evaluations(
        self,
        client: BinancePublicClient,
        current_time_ms: int,
        symbols: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        """Discover eligible TacticalFeatureEvidenceV2 and resolve B2B evaluations forward."""
        # Find feature evidence records
        all_evidence = self.store.list_tactical_feature_evidence()
        if symbols:
            target_symbols = {s.upper() for s in symbols}
            all_evidence = [e for e in all_evidence if e.symbol.upper() in target_symbols]

        resolved_count = 0
        pending_count = 0
        skipped_count = 0
        results: list[dict[str, Any]] = []

        for ev in all_evidence:
            try:
                # Check if already evaluated under B2B profile
                existing = self.store.get_grid_shadow_evaluation_by_feature_id(
                    ev.evidence_id, GRID_OUTCOME_PROFILE_VERSION
                )
                if existing is not None and existing.eligibility_status in (
                    GridEligibilityStatus.RESOLVED.value,
                    GridEligibilityStatus.NOT_ACTIVE_PAUSE.value,
                ):
                    skipped_count += 1
                    continue

                if ev.grid_advisory_plan is None:
                    skipped_count += 1
                    continue

                # Inactive / PAUSE plan resolves immediately without forward candle queries
                if ev.grid_advisory_plan.decision == GridDecision.PAUSE.value:
                    future_asmts = self.store.get_tactical_assessments(ev.symbol)
                    eval_res = _build_pause_evaluation(
                        evidence=ev,
                        grid_plan_ev=ev.grid_advisory_plan,
                        future_assessments=future_asmts,
                        assessment_diagnostic_coverage="COMPLETE" if future_asmts else "UNAVAILABLE",
                    )
                    saved_id = self.store.save_grid_shadow_evaluation(eval_res)
                    resolved_count += 1
                    results.append({"evidence_id": ev.evidence_id, "status": "NOT_ACTIVE_PAUSE", "evaluation_id": saved_id})
                    continue

                # Active plan: fetch 1m candles across forward window
                start_ms = ev.decision_time_ms
                end_ms = min(current_time_ms, start_ms + GRID_HORIZON_MS)

                candles_1m = client.historical_klines(ev.symbol, "1m", start_ms, end_ms)

                # Fetch funding history
                funding_history = client.funding_rate_history(ev.symbol, start_ms, end_ms)
                future_asmts = self.store.get_tactical_assessments(ev.symbol)

                eval_res = evaluate_grid_shadow_episode(
                    evidence=ev,
                    candles_1m=candles_1m,
                    funding_records=funding_history,
                    future_assessments=future_asmts,
                    assessment_diagnostic_coverage="COMPLETE" if future_asmts else "UNAVAILABLE",
                )

                saved_id = self.store.save_grid_shadow_evaluation(eval_res)
                if eval_res.eligibility_status == GridEligibilityStatus.RESOLVED.value:
                    resolved_count += 1
                    results.append({"evidence_id": ev.evidence_id, "status": "RESOLVED", "evaluation_id": saved_id})
                else:
                    pending_count += 1
                    results.append({"evidence_id": ev.evidence_id, "status": eval_res.eligibility_status, "evaluation_id": saved_id})

            except Exception as exc:  # noqa: BLE001
                logger.error(f"Error evaluating grid shadow for evidence {ev.evidence_id}: {exc}")
                results.append({"evidence_id": ev.evidence_id, "status": "ERROR", "error": str(exc)})

        return {
            "resolved_count": resolved_count,
            "pending_count": pending_count,
            "skipped_count": skipped_count,
            "results": results,
        }

    resolve_pending_evaluations = resolve_grid_evaluations
