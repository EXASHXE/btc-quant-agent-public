from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class TokenKind(StrEnum):
    FEATURE = "FEATURE"
    CONSTANT = "CONSTANT"
    OPERATOR = "OPERATOR"


class Operator(StrEnum):
    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    NEG = "NEG"
    ABS = "ABS"
    SIGN = "SIGN"
    MIN = "MIN"
    MAX = "MAX"
    GATE = "GATE"
    DELAY_1 = "DELAY_1"
    DELAY_N = "DELAY_N"
    ROLL_SUM_N = "ROLL_SUM_N"
    ROLL_MEAN_N = "ROLL_MEAN_N"
    ROLL_STD_N = "ROLL_STD_N"
    ROLL_Z_N = "ROLL_Z_N"
    EMA_N = "EMA_N"
    DECAY_N = "DECAY_N"
    CLIP = "CLIP"


ARITY: dict[Operator, int] = {
    Operator.ADD: 2,
    Operator.SUB: 2,
    Operator.MUL: 2,
    Operator.DIV: 2,
    Operator.NEG: 1,
    Operator.ABS: 1,
    Operator.SIGN: 1,
    Operator.MIN: 2,
    Operator.MAX: 2,
    Operator.GATE: 3,
    Operator.DELAY_1: 1,
    Operator.DELAY_N: 1,
    Operator.ROLL_SUM_N: 1,
    Operator.ROLL_MEAN_N: 1,
    Operator.ROLL_STD_N: 1,
    Operator.ROLL_Z_N: 1,
    Operator.EMA_N: 1,
    Operator.DECAY_N: 1,
    Operator.CLIP: 3,
}

PARAMETERIZED = {
    Operator.DELAY_N,
    Operator.ROLL_SUM_N,
    Operator.ROLL_MEAN_N,
    Operator.ROLL_STD_N,
    Operator.ROLL_Z_N,
    Operator.EMA_N,
    Operator.DECAY_N,
}


@dataclass(frozen=True)
class FormulaToken:
    kind: TokenKind
    value: str | float
    parameter: int | None = None

    def __post_init__(self) -> None:
        if self.kind == TokenKind.OPERATOR:
            operator = Operator(str(self.value))
            if operator in PARAMETERIZED and (self.parameter is None or self.parameter < 2):
                raise ValueError(f"{operator.value} requires parameter >= 2")
            if operator not in PARAMETERIZED and self.parameter is not None:
                raise ValueError(f"{operator.value} does not accept a parameter")
        elif self.parameter is not None:
            raise ValueError("only operator tokens accept parameters")

    def as_dict(self) -> dict[str, Any]:
        output: dict[str, Any] = {"kind": self.kind.value, "value": self.value}
        if self.parameter is not None:
            output["parameter"] = self.parameter
        return output


@dataclass(frozen=True)
class Formula:
    tokens: tuple[FormulaToken, ...]

    def __post_init__(self) -> None:
        depth = 0
        for token in self.tokens:
            if token.kind in {TokenKind.FEATURE, TokenKind.CONSTANT}:
                depth += 1
            else:
                arity = ARITY[Operator(str(token.value))]
                if depth < arity:
                    raise ValueError("invalid postfix formula stack underflow")
                depth = depth - arity + 1
        if depth != 1:
            raise ValueError("postfix formula must leave exactly one stack value")

    def canonical_json(self) -> str:
        return json.dumps(
            [token.as_dict() for token in self.tokens],
            sort_keys=True,
            separators=(",", ":"),
        )

    @property
    def formula_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode()).hexdigest()

    @property
    def complexity(self) -> int:
        return sum(token.kind == TokenKind.OPERATOR for token in self.tokens)

    @property
    def input_features(self) -> tuple[str, ...]:
        return tuple(
            sorted({str(token.value) for token in self.tokens if token.kind == TokenKind.FEATURE})
        )

    def max_lookback(self, feature_lookbacks: dict[str, int]) -> int:
        stack: list[int] = []
        for token in self.tokens:
            if token.kind == TokenKind.FEATURE:
                if str(token.value) not in feature_lookbacks:
                    raise KeyError(f"unregistered feature: {token.value}")
                stack.append(feature_lookbacks[str(token.value)])
            elif token.kind == TokenKind.CONSTANT:
                stack.append(0)
            else:
                operator = Operator(str(token.value))
                arity = ARITY[operator]
                children = stack[-arity:]
                del stack[-arity:]
                added = 0
                if operator == Operator.DELAY_1:
                    added = 1
                elif operator in PARAMETERIZED:
                    assert token.parameter is not None
                    added = token.parameter if operator == Operator.DELAY_N else token.parameter - 1
                stack.append(max(children) + added)
        return stack[0]

