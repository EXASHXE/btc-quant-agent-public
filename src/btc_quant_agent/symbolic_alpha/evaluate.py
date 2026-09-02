from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import pairwise
from statistics import fmean, stdev

from .dsl import Formula
from .vm import FormulaVM, Series


@dataclass(frozen=True)
class EvaluationMetrics:
    event_count: int
    long_count: int
    short_count: int
    wait_count: int
    long_fraction: float | None
    gross_mean_return: float | None
    net_mean_return: float | None
    standard_error: float | None
    t_stat: float | None
    turnover: float | None
    bootstrap_ci_low: float | None
    bootstrap_ci_high: float | None
    chronological_fold_means: tuple[float | None, ...]
    bootstrap_block_hours: int | None
    bootstrap_block_events: int | None


def block_hours_to_events(block_hours: int, sample_step_hours: int) -> int:
    if block_hours <= 0 or sample_step_hours <= 0:
        raise ValueError("block_hours and sample_step_hours must be positive")
    return math.ceil(block_hours / sample_step_hours)


class EvaluationFirewall:
    def __init__(self) -> None:
        self._top_k_hashes: tuple[str, ...] | None = None
        self.pseudo_forward_touches = 0

    def freeze_top_k(self, formulas: list[Formula]) -> tuple[str, ...]:
        if self._top_k_hashes is not None:
            raise RuntimeError("top-K already frozen")
        self._top_k_hashes = tuple(formula.formula_hash for formula in formulas)
        return self._top_k_hashes

    def authorize_pseudo_forward(self, formula: Formula) -> None:
        if self._top_k_hashes is None:
            raise PermissionError("pseudo-forward cannot be touched before top-K freeze")
        if formula.formula_hash not in self._top_k_hashes:
            raise PermissionError("formula is outside frozen pseudo-forward top-K")
        self.pseudo_forward_touches += 1


def forward_returns(close: Series, horizon: int) -> Series:
    output: Series = [None] * len(close)
    for index in range(len(close) - horizon):
        current = close[index]
        future = close[index + horizon]
        if current is not None and future is not None and current > 0 and future > 0:
            output[index] = math.log(future / current)
    return output


def _block_bootstrap_ci(
    values: list[float], seed: int, resamples: int, block: int
) -> tuple[float, float]:
    if not values:
        return math.nan, math.nan
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sample: list[float] = []
        while len(sample) < len(values):
            start = rng.randrange(len(values))
            sample.extend(values[(start + offset) % len(values)] for offset in range(block))
        estimates.append(fmean(sample[: len(values)]))
    estimates.sort()
    return estimates[int(0.025 * (len(estimates) - 1))], estimates[
        int(0.975 * (len(estimates) - 1))
    ]


def evaluate_formula(
    formula: Formula,
    features: dict[str, Series],
    returns: Series,
    indices: range,
    *,
    cost_rate: float,
    bootstrap_seed: int,
    bootstrap_resamples: int = 0,
    bootstrap_block_hours: int = 168,
    sample_step_hours: int = 1,
    folds: int = 4,
) -> EvaluationMetrics:
    result = FormulaVM().execute(formula, features)
    if result.failure or result.values is None:
        raise ValueError(f"formula VM failure: {result.failure}")
    pnl: list[float] = []
    sides: list[int] = []
    waits = 0
    for index in indices:
        value = result.values[index]
        outcome = returns[index]
        if value is None or outcome is None or value == 0:
            waits += 1
            continue
        side = 1 if value > 0 else -1
        pnl.append(side * outcome - cost_rate)
        sides.append(side)
    count = len(pnl)
    mean = fmean(pnl) if pnl else None
    error = stdev(pnl) / math.sqrt(count) if count > 1 else None
    turnover = (
        sum(left != right for left, right in pairwise(sides)) / (len(sides) - 1)
        if len(sides) > 1
        else None
    )
    ci_low: float | None = None
    ci_high: float | None = None
    block_events = block_hours_to_events(bootstrap_block_hours, sample_step_hours)
    if bootstrap_resamples and pnl:
        ci_low, ci_high = _block_bootstrap_ci(
            pnl, bootstrap_seed, bootstrap_resamples, block_events
        )
    fold_means: list[float | None] = []
    for fold in range(folds):
        start = count * fold // folds
        end = count * (fold + 1) // folds
        fold_means.append(fmean(pnl[start:end]) if end > start else None)
    return EvaluationMetrics(
        event_count=count,
        long_count=sum(side > 0 for side in sides),
        short_count=sum(side < 0 for side in sides),
        wait_count=waits,
        long_fraction=sum(side > 0 for side in sides) / count if count else None,
        gross_mean_return=(mean + cost_rate if mean is not None else None),
        net_mean_return=mean,
        standard_error=error,
        t_stat=mean / error if mean is not None and error and error > 0 else None,
        turnover=turnover,
        bootstrap_ci_low=ci_low,
        bootstrap_ci_high=ci_high,
        chronological_fold_means=tuple(fold_means),
        bootstrap_block_hours=bootstrap_block_hours if bootstrap_resamples else None,
        bootstrap_block_events=block_events if bootstrap_resamples else None,
    )
