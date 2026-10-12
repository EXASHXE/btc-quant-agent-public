"""Immutable hypothesis preregistration registry for Goal B.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
CONTROLLER_DISPATCH_SHA: e35724f1d1ee7458709e003dfc5673c826c68ffd
START_SHA: 55ac4c631c69f6edbd275462ad23e4486b9782ed
AUTHORITY: reviews/v0.6/b_line/V06_FORWARD_SHADOW_G1G3_THREE_GEMINI_GOALS_R1_CONTROLLER_AUTHORITY.md
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Any


class SignalFamily(str, Enum):
    P1_BASIS_REVERSION_V2_SHADOW = "P1_BASIS_REVERSION_V2_SHADOW"
    P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW = "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW"


class Horizon(int, Enum):
    H6 = 6
    H12 = 12
    H18 = 18

    @property
    def minutes(self) -> int:
        return self.value * 60

    @property
    def ms(self) -> int:
        return self.value * 3600 * 1000


# Exactly six selectable observation cells
SELECTABLE_OBSERVATION_CELLS: tuple[str, ...] = (
    "P1_BASIS_REVERSION_V2_SHADOW_6H",
    "P1_BASIS_REVERSION_V2_SHADOW_12H",
    "P1_BASIS_REVERSION_V2_SHADOW_18H",
    "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_6H",
    "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_12H",
    "P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_18H",
)


@dataclass(frozen=True)
class PreRegisteredHypothesis:
    family: SignalFamily
    horizon_hours: Horizon
    cell_id: str
    decision_interval_minutes: int
    confirmation_intervals_minutes: tuple[int, ...]
    min_dislocation_bps: float
    spread_multiplier: float
    past_premium_shrink_window_minutes: int
    stale_mark_max_ms: int
    stale_depth_max_ms: int
    abnormal_vol_cap_bps: float
    agg_trade_imbalance_threshold: float
    book_imbalance_threshold: float
    book_top_levels: int
    directional_filter_window_minutes: int
    atr_period: int
    atr_min_warmup_hours: int
    stop_r_multiple: float
    target_r_multiple: float
    account_capital_usdt: float
    reserve_fraction: float
    leverage_max: float
    lot_step_btc: float
    cooldown_hours: int
    taker_fee_bps: float
    adverse_slippage_bps: float


def get_default_hypotheses() -> dict[str, PreRegisteredHypothesis]:
    """Return dictionary of the 6 prespecified frozen observation cells."""
    hypotheses = {}
    for horizon in (Horizon.H6, Horizon.H12, Horizon.H18):
        # P1 Basis Reversion V2 Shadow
        p1_cell = f"P1_BASIS_REVERSION_V2_SHADOW_{horizon.value}H"
        hypotheses[p1_cell] = PreRegisteredHypothesis(
            family=SignalFamily.P1_BASIS_REVERSION_V2_SHADOW,
            horizon_hours=horizon,
            cell_id=p1_cell,
            decision_interval_minutes=15,
            confirmation_intervals_minutes=(5, 15, 30),
            min_dislocation_bps=5.0,  # 5bp = 0.0005
            spread_multiplier=2.0,   # 2x spread
            past_premium_shrink_window_minutes=5,
            stale_mark_max_ms=2000,
            stale_depth_max_ms=1000,
            abnormal_vol_cap_bps=300.0,  # 300 bps 30m vol cap
            agg_trade_imbalance_threshold=0.0,
            book_imbalance_threshold=0.0,
            book_top_levels=10,
            directional_filter_window_minutes=30,
            atr_period=14,
            atr_min_warmup_hours=200,
            stop_r_multiple=1.0,     # 1R stop
            target_r_multiple=2.0,   # 2R target
            account_capital_usdt=1000.0,
            reserve_fraction=0.05,   # 5% cash reserve
            leverage_max=1.0,        # 1x paper account
            lot_step_btc=0.001,      # BTC 0.001 step
            cooldown_hours=6,        # 6h cooldown
            taker_fee_bps=5.0,       # 5 bps marketable taker fee
            adverse_slippage_bps=0.5, # 0.5 bps adverse impact
        )

        # P2 Orderflow Book Resilience Shadow
        p2_cell = f"P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW_{horizon.value}H"
        hypotheses[p2_cell] = PreRegisteredHypothesis(
            family=SignalFamily.P2_ORDERFLOW_BOOK_RESILIENCE_SHADOW,
            horizon_hours=horizon,
            cell_id=p2_cell,
            decision_interval_minutes=15,
            confirmation_intervals_minutes=(5, 15, 30),
            min_dislocation_bps=0.0,
            spread_multiplier=0.0,
            past_premium_shrink_window_minutes=0,
            stale_mark_max_ms=2000,
            stale_depth_max_ms=1000,
            abnormal_vol_cap_bps=300.0,
            agg_trade_imbalance_threshold=0.20,  # > +0.20 or < -0.20
            book_imbalance_threshold=0.10,       # > +0.10 or < -0.10
            book_top_levels=10,
            directional_filter_window_minutes=30, # 30m prior close directional agreement
            atr_period=14,
            atr_min_warmup_hours=200,
            stop_r_multiple=1.0,     # 1R stop
            target_r_multiple=2.0,   # 2R target
            account_capital_usdt=1000.0,
            reserve_fraction=0.05,
            leverage_max=1.0,
            lot_step_btc=0.001,
            cooldown_hours=6,
            taker_fee_bps=5.0,
            adverse_slippage_bps=0.5,
        )

    return hypotheses


@dataclass(frozen=True)
class SampleReadinessGate:
    """Predeclared minimum sample readiness criteria.

    Before meeting all criteria, status must remain EVIDENCE_IMMATURE.
    No inferential PASS / edge claims are permitted.
    """
    min_distinct_events_per_family: int = 30
    min_nonoverlapping_utc_weeks: int = 15
    min_independent_volatility_regimes: int = 2
    min_source_coverage_pct: float = 95.0
    volatility_lookback_days: int = 30

    def evaluate_readiness(
        self,
        event_count_p1: int,
        event_count_p2: int,
        distinct_utc_weeks: int,
        distinct_volatility_regimes: int,
        source_coverage_pct: float,
        has_30d_forward_warmup: bool,
    ) -> dict[str, Any]:
        """Evaluate if sample meets pre-registered independent readiness gate."""
        passed_p1_events = event_count_p1 >= self.min_distinct_events_per_family
        passed_p2_events = event_count_p2 >= self.min_distinct_events_per_family
        passed_weeks = distinct_utc_weeks >= self.min_nonoverlapping_utc_weeks
        passed_coverage = source_coverage_pct >= self.min_source_coverage_pct
        passed_regimes = (
            has_30d_forward_warmup
            and distinct_volatility_regimes >= self.min_independent_volatility_regimes
        )

        all_passed = (
            passed_p1_events
            and passed_p2_events
            and passed_weeks
            and passed_coverage
            and passed_regimes
        )

        return {
            "ready_for_controller_evaluation": all_passed,
            "status": "SAMPLE_READINESS_MET" if all_passed else "EVIDENCE_IMMATURE",
            "criteria": {
                "p1_events": {
                    "required": self.min_distinct_events_per_family,
                    "actual": event_count_p1,
                    "passed": passed_p1_events,
                },
                "p2_events": {
                    "required": self.min_distinct_events_per_family,
                    "actual": event_count_p2,
                    "passed": passed_p2_events,
                },
                "distinct_utc_weeks": {
                    "required": self.min_nonoverlapping_utc_weeks,
                    "actual": distinct_utc_weeks,
                    "passed": passed_weeks,
                },
                "volatility_regimes": {
                    "required": self.min_independent_volatility_regimes,
                    "actual": distinct_volatility_regimes,
                    "has_30d_forward_warmup": has_30d_forward_warmup,
                    "passed": passed_regimes,
                },
                "source_coverage_pct": {
                    "required": self.min_source_coverage_pct,
                    "actual": source_coverage_pct,
                    "passed": passed_coverage,
                },
            },
            "prohibition_notice": (
                "ZERO_HISTORICAL_OUTCOME_SEARCH: "
                "Evaluation restricted strictly to post-dispatch prospective arrivals. "
                "No 2021-23 search multiples, no 2024-26 historical backfills."
            ),
        }


def compute_policy_fingerprint() -> str:
    """Compute deterministic SHA-256 fingerprint of the frozen preregistration policy."""
    hypotheses = get_default_hypotheses()
    raw = {
        "selectable_cells": list(SELECTABLE_OBSERVATION_CELLS),
        "cells": {
            k: {
                "family": v.family.value,
                "horizon_hours": v.horizon_hours.value,
                "cell_id": v.cell_id,
                "decision_interval_minutes": v.decision_interval_minutes,
                "confirmation_intervals_minutes": list(v.confirmation_intervals_minutes),
                "min_dislocation_bps": v.min_dislocation_bps,
                "spread_multiplier": v.spread_multiplier,
                "past_premium_shrink_window_minutes": v.past_premium_shrink_window_minutes,
                "stale_mark_max_ms": v.stale_mark_max_ms,
                "stale_depth_max_ms": v.stale_depth_max_ms,
                "abnormal_vol_cap_bps": v.abnormal_vol_cap_bps,
                "agg_trade_imbalance_threshold": v.agg_trade_imbalance_threshold,
                "book_imbalance_threshold": v.book_imbalance_threshold,
                "book_top_levels": v.book_top_levels,
                "directional_filter_window_minutes": v.directional_filter_window_minutes,
                "atr_period": v.atr_period,
                "atr_min_warmup_hours": v.atr_min_warmup_hours,
                "stop_r_multiple": v.stop_r_multiple,
                "target_r_multiple": v.target_r_multiple,
                "account_capital_usdt": v.account_capital_usdt,
                "reserve_fraction": v.reserve_fraction,
                "leverage_max": v.leverage_max,
                "lot_step_btc": v.lot_step_btc,
                "cooldown_hours": v.cooldown_hours,
                "taker_fee_bps": v.taker_fee_bps,
                "adverse_slippage_bps": v.adverse_slippage_bps,
            }
            for k, v in sorted(hypotheses.items())
        },
        "sample_readiness_gate": {
            "min_distinct_events_per_family": 30,
            "min_nonoverlapping_utc_weeks": 15,
            "min_independent_volatility_regimes": 2,
            "min_source_coverage_pct": 95.0,
            "volatility_lookback_days": 30,
        },
    }
    encoded = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
