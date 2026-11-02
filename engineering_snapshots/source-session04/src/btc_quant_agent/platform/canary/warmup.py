"""Readiness from actual L23 dependency counts; elapsed hours are never sufficient."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..selection.selector import metrics, portfolio_beta
from ..selection.sources import STRUCTURE, SourceHistory


def contract(*, full_beta_reference_required=False):
    source = Path(__file__).resolve().parents[1] / "selection/selector.py"
    return {
        "version": "L4-WARMUP-FROM-L23-1",
        "l23_selector_source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "dependencies_completed_5m_bars": {
            "EMA20": 20,
            "EMA40_with_three_bar_slope": 43,
            "ATR14": 14,
            "ADX14_min_periods": 28,
            "ER20": 21,
            "prior_60_one_bar_return_sigma": 62,
            "prior_60_true_range_median": 61,
            "L23_explicit_structural_guard": 65,
            "two_regime_confirmations_from_cold_start": 66,
            "prior_observed_channel_20_plus_current": 21,
            "observed_trailing_stop": 12,
            "beta_minimum_200_aligned_returns": 201,
            "beta_complete_288_return_reference_if_required": 289,
        },
        "structural_minimum": 66,
        "action_minimum_aligned_bars": 289 if full_beta_reference_required else 201,
        "beta_implementation": "L23 uses at most 289 bars and requires at least 200 aligned returns; a full 288-return reference is optional stricter acquisition policy",
        "confirmed_pivots": "Not used by the three enabled V1 playbooks; do not pretend Astra pivot hypotheses are active",
        "daily_volatility_percentile": "NOT_IMPLEMENTED; no 10-20-day readiness claim",
        "percentile_members": 10,
        "entry_confirmations": 2,
        "entry_confirmation_rule": "Distinct continuous completed 1m observations AFTER known setup; mechanism must also confirm",
        "delayed_response_rule": "New admissible actually received quote after modeled acknowledgement; no setup-quote reuse",
        "source_qualification_is_strategy_readiness": False,
    }


def assess(history: SourceHistory, *, full_beta_reference_required=False) -> dict:
    requirement = contract(full_beta_reference_required=full_beta_reference_required)
    members, ready = {}, True
    for symbol, df in history.frames.items():
        count = len(df)
        gaps = count > 1 and bool((np.diff(df.ts) != STRUCTURE).any())
        reasons = []
        if count < requirement["structural_minimum"]:
            reasons.append("WARMUP_INSUFFICIENT:STRUCTURAL_66")
        if count < requirement["action_minimum_aligned_bars"]:
            reasons.append("WARMUP_INSUFFICIENT:BETA_ALIGNED_RETURNS")
        if gaps:
            reasons.append("WARMUP_INSUFFICIENT:CONTIGUOUS_HISTORY_REQUIRED")
        if not history.synchronized():
            reasons.append("FROZEN_UNIVERSE_OR_BENCHMARK_MISALIGNED")
        if len(history.universe.members) < 10:
            reasons.append("RANK_MEMBERSHIP_BELOW_TEN_WATCH_ONLY")
        m = metrics(history, symbol)
        beta = portfolio_beta(history, symbol)
        if not m.get("usable"):
            reasons.append("STRUCTURAL_FACTORS_NOT_USABLE:" + m.get("reason", "UNKNOWN"))
        if beta is None:
            reasons.append("BETA_UNDEFINED_OR_UNAVAILABLE")
        members[symbol] = {
            "completed_5m_bars": count,
            "aligned_returns_upper_bound": max(0, count - 1),
            "history_gap": bool(gaps),
            "beta": beta,
            "reasons": reasons,
            "feature_warmup_ready": not reasons,
        }
        ready &= not reasons
    return {
        "contract": requirement,
        "members": members,
        "synchronized_universe": history.synchronized(),
        "frozen_universe_hash": history.universe.hash,
        "feature_warmup_ready": bool(ready),
        "strategy_ready": False,
        "remaining_action_gates": [
            "admitted sources and grant",
            "persisted regime",
            "actual mechanism confirmation",
            "new post-ack quote",
            "funding cadence/clock",
            "current portfolio risk",
        ],
        "source_qualified": False,
        "source_exposure": "SYNTHETIC",
        "qualification": "Counts plus actual L23 feature admissibility; not a trade trigger or market evidence",
    }
