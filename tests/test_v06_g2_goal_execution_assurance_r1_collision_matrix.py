"""Deterministic pytest suite for the 48-fixture adversarial collision matrix (Target 3)."""
from __future__ import annotations

import pytest

from scripts.strategy_research.g2_goal_execution_assurance_r1.collision_matrix import (
    COLLISION_FIXTURE_REGISTRY,
    execute_collision_fixture,
    run_all_collision_fixtures,
)


def test_fixture_registry_has_at_least_40_unique_cases() -> None:
    """Verify the fixture registry has >=40 distinct deterministic fixtures."""
    assert len(COLLISION_FIXTURE_REGISTRY) >= 40
    ids = [spec["id"] for spec in COLLISION_FIXTURE_REGISTRY]
    assert len(ids) == len(set(ids))


@pytest.mark.parametrize(
    "fixture_id",
    [spec["id"] for spec in COLLISION_FIXTURE_REGISTRY],
)
def test_adversarial_collision_fixture(fixture_id: str) -> None:
    """Execute each deterministic adversarial collision fixture and assert PASS."""
    res = execute_collision_fixture(fixture_id)
    assert res["status"] == "PASS", f"Fixture {fixture_id} failed: {res}"


def test_run_all_collision_fixtures_summary() -> None:
    """Verify batch runner executes all 48 fixtures with zero failures."""
    summary = run_all_collision_fixtures()
    assert summary["status"] == "PASS"
    assert summary["total_fixtures"] == len(COLLISION_FIXTURE_REGISTRY)
    assert summary["passed_fixtures"] == len(COLLISION_FIXTURE_REGISTRY)
