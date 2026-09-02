from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Protocol

from .dsl import ARITY, PARAMETERIZED, Formula, FormulaToken, Operator, TokenKind


@dataclass(frozen=True)
class ProposalConstraints:
    maximum_tokens: int
    maximum_lookback: int
    windows: tuple[int, ...]
    operators: tuple[Operator, ...]


class FormulaProposalEngine(Protocol):
    def propose(
        self,
        n: int,
        feature_lookbacks: dict[str, int],
        seed: int,
        constraints: ProposalConstraints,
    ) -> tuple[list[Formula], dict[str, int]]: ...


class RandomGrammarProposalEngine:
    name = "RANDOM_GRAMMAR_SEARCH"

    def _expression(
        self,
        rng: random.Random,
        features: tuple[str, ...],
        constraints: ProposalConstraints,
        depth: int,
    ) -> list[FormulaToken]:
        if depth <= 0 or rng.random() < 0.35:
            if rng.random() < 0.88:
                return [FormulaToken(TokenKind.FEATURE, rng.choice(features))]
            return [FormulaToken(TokenKind.CONSTANT, rng.choice((-1.0, -0.5, 0.0, 0.5, 1.0)))]
        operator = rng.choice(constraints.operators)
        tokens: list[FormulaToken] = []
        for _ in range(ARITY[operator]):
            tokens.extend(self._expression(rng, features, constraints, depth - 1))
        parameter = rng.choice(constraints.windows) if operator in PARAMETERIZED else None
        tokens.append(FormulaToken(TokenKind.OPERATOR, operator.value, parameter))
        return tokens

    def propose(
        self,
        n: int,
        feature_lookbacks: dict[str, int],
        seed: int,
        constraints: ProposalConstraints,
    ) -> tuple[list[Formula], dict[str, int]]:
        rng = random.Random(seed)
        features = tuple(sorted(feature_lookbacks))
        unique: dict[str, Formula] = {}
        attempts = invalid = duplicate = over_lookback = over_tokens = 0
        maximum_attempts = max(n * 100, 1_000)
        while len(unique) < n and attempts < maximum_attempts:
            attempts += 1
            try:
                formula = Formula(tuple(self._expression(rng, features, constraints, 3)))
                if len(formula.tokens) > constraints.maximum_tokens:
                    over_tokens += 1
                    continue
                if formula.max_lookback(feature_lookbacks) > constraints.maximum_lookback:
                    over_lookback += 1
                    continue
                if formula.formula_hash in unique:
                    duplicate += 1
                    continue
                unique[formula.formula_hash] = formula
            except (KeyError, ValueError):
                invalid += 1
        if len(unique) != n:
            raise RuntimeError(f"proposal budget not satisfied: {len(unique)}/{n}")
        return list(unique.values()), {
            "attempts": attempts,
            "valid_unique_formulas": len(unique),
            "invalid_formulas": invalid,
            "duplicates_rejected": duplicate,
            "over_lookback_rejected": over_lookback,
            "over_token_limit_rejected": over_tokens,
        }


class LocalTransformerProposalEngine:
    """Architecture contract only; formal v0.3.18 results use the random baseline."""

    name = "LOCAL_FORMULA_POLICY_MODEL"
    external_api = False
    natural_language_vocabulary = False
    discovery_reward_only = True

    def propose(
        self,
        n: int,
        feature_lookbacks: dict[str, int],
        seed: int,
        constraints: ProposalConstraints,
    ) -> tuple[list[Formula], dict[str, int]]:
        raise RuntimeError("tiny Transformer training was not preregistered for the formal run")

