from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from statistics import fmean, pstdev

from .dsl import ARITY, PARAMETERIZED, Formula, Operator, TokenKind

Series = list[float | None]


@dataclass(frozen=True)
class VMFailure:
    code: str
    token_index: int
    detail: str


@dataclass(frozen=True)
class VMResult:
    values: Series | None
    output_hash: str | None
    failure: VMFailure | None


def _unary(values: Series, function: object) -> Series:
    callable_function = function
    return [None if value is None else callable_function(value) for value in values]  # type: ignore[operator]


def _binary(left: Series, right: Series, operator: Operator) -> Series:
    output: Series = []
    for a, b in zip(left, right, strict=True):
        if a is None or b is None:
            output.append(None)
        elif operator == Operator.ADD:
            output.append(a + b)
        elif operator == Operator.SUB:
            output.append(a - b)
        elif operator == Operator.MUL:
            output.append(a * b)
        elif operator == Operator.DIV:
            output.append(None if abs(b) <= 1e-15 else a / b)
        elif operator == Operator.MIN:
            output.append(min(a, b))
        elif operator == Operator.MAX:
            output.append(max(a, b))
        else:
            raise ValueError(f"unsupported binary operator {operator.value}")
    return output


def _rolling(values: Series, window: int, operator: Operator) -> Series:
    output: Series = [None] * len(values)
    for index in range(window - 1, len(values)):
        block = values[index - window + 1 : index + 1]
        if any(value is None for value in block):
            continue
        clean = [float(value) for value in block if value is not None]
        if operator == Operator.ROLL_SUM_N:
            output[index] = sum(clean)
        elif operator == Operator.ROLL_MEAN_N:
            output[index] = fmean(clean)
        elif operator == Operator.ROLL_STD_N:
            output[index] = pstdev(clean)
        elif operator == Operator.ROLL_Z_N:
            deviation = pstdev(clean)
            output[index] = None if deviation <= 1e-15 else (clean[-1] - fmean(clean)) / deviation
        elif operator == Operator.DECAY_N:
            weights = range(1, window + 1)
            output[index] = sum(value * weight for value, weight in zip(clean, weights, strict=True)) / sum(weights)
    return output


def _ema(values: Series, window: int) -> Series:
    output: Series = [None] * len(values)
    alpha = 2.0 / (window + 1)
    previous: float | None = None
    consecutive = 0
    for index, value in enumerate(values):
        if value is None:
            previous = None
            consecutive = 0
            continue
        previous = value if previous is None else alpha * value + (1 - alpha) * previous
        consecutive += 1
        if consecutive >= window:
            output[index] = previous
    return output


class FormulaVM:
    def execute(self, formula: Formula, features: dict[str, Series]) -> VMResult:
        lengths = {len(values) for values in features.values()}
        if len(lengths) != 1:
            return VMResult(None, None, VMFailure("LENGTH_MISMATCH", -1, "feature lengths differ"))
        length = next(iter(lengths), 0)
        stack: list[Series] = []
        try:
            for index, token in enumerate(formula.tokens):
                if token.kind == TokenKind.FEATURE:
                    if str(token.value) not in features:
                        return VMResult(
                            None,
                            None,
                            VMFailure("FEATURE_UNAVAILABLE", index, str(token.value)),
                        )
                    stack.append(list(features[str(token.value)]))
                    continue
                if token.kind == TokenKind.CONSTANT:
                    stack.append([float(token.value)] * length)
                    continue
                operator = Operator(str(token.value))
                arity = ARITY[operator]
                arguments = stack[-arity:]
                del stack[-arity:]
                if operator in {Operator.ADD, Operator.SUB, Operator.MUL, Operator.DIV, Operator.MIN, Operator.MAX}:
                    result = _binary(arguments[0], arguments[1], operator)
                elif operator == Operator.NEG:
                    result = _unary(arguments[0], lambda value: -value)
                elif operator == Operator.ABS:
                    result = _unary(arguments[0], abs)
                elif operator == Operator.SIGN:
                    result = _unary(arguments[0], lambda value: float((value > 0) - (value < 0)))
                elif operator == Operator.GATE:
                    result = [
                        None if gate is None or yes is None or no is None else (yes if gate > 0 else no)
                        for gate, yes, no in zip(*arguments, strict=True)
                    ]
                elif operator == Operator.CLIP:
                    result = [
                        None
                        if value is None or low is None or high is None or low > high
                        else min(max(value, low), high)
                        for value, low, high in zip(*arguments, strict=True)
                    ]
                elif operator == Operator.DELAY_1:
                    result = [None, *arguments[0][:-1]] if length else []
                elif operator == Operator.DELAY_N:
                    assert token.parameter is not None
                    prefix: Series = [None] * min(token.parameter, length)
                    result = prefix + arguments[0][:-token.parameter]
                elif operator == Operator.EMA_N:
                    assert token.parameter is not None
                    result = _ema(arguments[0], token.parameter)
                elif operator in PARAMETERIZED:
                    assert token.parameter is not None
                    result = _rolling(arguments[0], token.parameter, operator)
                else:
                    return VMResult(None, None, VMFailure("UNSUPPORTED_OPERATOR", index, operator.value))
                if any(value is not None and not math.isfinite(value) for value in result):
                    return VMResult(None, None, VMFailure("NON_FINITE_OUTPUT", index, operator.value))
                stack.append(result)
        except (ArithmeticError, TypeError, ValueError) as exc:
            return VMResult(None, None, VMFailure("OPERATOR_ERROR", index, str(exc)))
        output = stack[0]
        canonical = json.dumps(output, separators=(",", ":"), allow_nan=False)
        return VMResult(output, hashlib.sha256(canonical.encode()).hexdigest(), None)
