"""Isolated structural governance checks. No real execution authority."""

MODE = "EXPLORATORY_RETROSPECTIVE_NO_HOLDOUT_CLAIM"
SCHEMA = "quant.v065.exploratory-retrospective-no-holdout-claim.v1"


class GateError(ValueError):
    """A fail-closed governance or filesystem boundary."""


def require(condition: bool, code: str) -> None:
    if not condition:
        raise GateError(code)
