"""Offline-only pytest configuration with Python audit-hook network/socket denial and portable B2 fixtures."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
from quant_personal_decision_b2.engine import Engine
from quant_personal_decision_b2.fixtures import (
    AFTER_TRIGGER,
    INITIAL,
    PULLBACK,
    FabricatedMarket,
)
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import DEFAULT_POLICY

_FORBIDDEN_AUDIT_PREFIXES = (
    "socket.",
    "urllib.",
    "http.client.",
)
_AUDIT_HOOK_INSTALLED = False


def _offline_audit_hook(event: str, _args: tuple[Any, ...]) -> None:
    for prefix in _FORBIDDEN_AUDIT_PREFIXES:
        if event.startswith(prefix):
            raise RuntimeError(f"FORBIDDEN_NETWORK_AUDIT_EVENT:{event}")


def pytest_configure(config: pytest.Config) -> None:
    global _AUDIT_HOOK_INSTALLED
    if not _AUDIT_HOOK_INSTALLED:
        sys.addaudithook(_offline_audit_hook)
        _AUDIT_HOOK_INSTALLED = True


@pytest.fixture(scope="session")
def b2_pullback_long_journal(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Any]:
    """Generate a self-contained, verified B2 pullback-long journal (100% portable in isolated review copies)."""
    work = tmp_path_factory.mktemp("b2_pullback_long")
    feed = FabricatedMarket(work / "b1_fixture.sqlite", PULLBACK, "LONG")
    feed.scan(INITIAL)
    db_path = work / "decision.sqlite"
    journal = Journal(db_path, create=True, policy=DEFAULT_POLICY)
    engine = Engine(MarketSnapshotAdapter(feed.path, "fixture"), journal)
    card_watch = engine.evaluate("BTCUSDT")
    feed.scan(AFTER_TRIGGER)
    card_exec = engine.evaluate("BTCUSDT")
    assert card_watch["market_status"] == "WATCH"
    assert card_exec["market_status"] == "EXECUTABLE"
    return {
        "journal_path": db_path,
        "watch_card": card_watch,
        "executable_card": card_exec,
        "episode_id": card_exec["episode_id"],
    }


@pytest.fixture()
def accepted_or_generated_b2_db(
    b2_pullback_long_journal: dict[str, Any],
) -> Path:
    """Use explicit B3_ACCEPTED_B2_DB if configured and present, else the portable generated B2 journal."""
    explicit = os.environ.get("B3_ACCEPTED_B2_DB")
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate
    return Path(b2_pullback_long_journal["journal_path"])
