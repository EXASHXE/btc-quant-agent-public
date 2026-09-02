from __future__ import annotations

from dataclasses import asdict, dataclass

from .dsl import Formula
from .evaluate import EvaluationMetrics, evaluate_formula
from .proposal import FormulaProposalEngine, ProposalConstraints
from .vm import Series


@dataclass(frozen=True)
class ScoredFormula:
    formula: Formula
    score: float
    metrics: EvaluationMetrics


@dataclass(frozen=True)
class SearchResult:
    ranked: tuple[ScoredFormula, ...]
    accounting: dict[str, int]

    def audit_dict(self) -> dict[str, object]:
        return {
            "accounting": self.accounting,
            "ranked": [
                {
                    "formula_hash": item.formula.formula_hash,
                    "canonical_formula": item.formula.canonical_json(),
                    "complexity": item.formula.complexity,
                    "score": item.score,
                    "metrics": asdict(item.metrics),
                }
                for item in self.ranked
            ],
        }


def run_discovery_search(
    engine: FormulaProposalEngine,
    budget: int,
    feature_lookbacks: dict[str, int],
    seed: int,
    constraints: ProposalConstraints,
    features: dict[str, Series],
    returns: Series,
    indices: range,
    complexity_penalty: float,
) -> SearchResult:
    formulas, accounting = engine.propose(budget, feature_lookbacks, seed, constraints)
    ranked: list[ScoredFormula] = []
    vm_failures = 0
    for formula in formulas:
        try:
            metrics = evaluate_formula(
                formula,
                features,
                returns,
                indices,
                cost_rate=0.0,
                bootstrap_seed=seed,
            )
        except ValueError:
            vm_failures += 1
            continue
        t_stat = metrics.t_stat if metrics.t_stat is not None else -1e9
        score = t_stat - complexity_penalty * formula.complexity
        ranked.append(ScoredFormula(formula, score, metrics))
    ranked.sort(key=lambda item: (-item.score, item.formula.formula_hash))
    accounting = {
        **accounting,
        "formula_evaluations": len(formulas),
        "vm_failures": vm_failures,
    }
    return SearchResult(tuple(ranked), accounting)

