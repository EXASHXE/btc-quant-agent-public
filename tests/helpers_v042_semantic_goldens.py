"""Independent, test-only oracles for the v0.4.2 A04 semantic goldens."""

from __future__ import annotations

import json
import random
from collections.abc import Sequence
from decimal import Decimal
from pathlib import Path
from typing import Any

GOLDEN_PATH = Path(__file__).parent / "goldens" / "v042_semantic_goldens.json"


def load_goldens() -> dict[str, Any]:
    value = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("semantic golden document must be an object")
    return value


def case_by_id(document: dict[str, Any], case_id: str) -> dict[str, Any]:
    matches = [case for case in document["cases"] if case["case_id"] == case_id]
    if len(matches) != 1:
        raise AssertionError(f"expected exactly one semantic golden {case_id}")
    return matches[0]


def decimal(value: str | int | float) -> Decimal:
    """Convert through text so the oracle never inherits binary-float arithmetic."""
    return Decimal(str(value))


def linear_realized_pnl(
    *, side: str, quantity: str, open_price: str, close_price: str
) -> Decimal:
    direction = Decimal(1) if side == "LONG" else Decimal(-1)
    return direction * decimal(quantity) * (decimal(close_price) - decimal(open_price))


def funding_cashflow(
    *, signed_quantity: str, mark_price: str, funding_rate: str
) -> Decimal:
    """Positive rates transfer cash from longs to shorts."""
    return -decimal(signed_quantity) * decimal(mark_price) * decimal(funding_rate)


def preregistered_random_draws(
    *,
    master_seed: int,
    ordered_opportunities: Sequence[dict[str, Any]],
    sample_count: int,
    direction_template: Sequence[int],
    trial_count: int,
) -> list[dict[str, Any]]:
    """Independent transcription of the documented P6 stdlib draw primitive."""
    master = random.Random(master_seed)
    result: list[dict[str, Any]] = []
    opportunities = sorted(
        ordered_opportunities,
        key=lambda item: (int(item["timestamp_ms"]), str(item["opportunity_id"])),
    )
    for trial_id in range(trial_count):
        trial_seed = master.randrange(0, 2**63)
        trial = random.Random(trial_seed)
        selected = trial.sample(opportunities, sample_count)
        selected.sort(key=lambda item: int(item["timestamp_ms"]))
        directions = list(direction_template)
        trial.shuffle(directions)
        result.append(
            {
                "trial_id": trial_id,
                "trial_seed": trial_seed,
                "selected_opportunity_ids": [item["opportunity_id"] for item in selected],
                "directions": directions,
            }
        )
    return result
