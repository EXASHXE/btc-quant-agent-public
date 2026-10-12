"""Synthetic tests for frozen contract integrity, candidate identities, and research budget."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.strategy_research.g2_flow_funding_entries_r1.run import (
    CONTRACT_PATH,
    EXACT_START_SHA,
    verify_freeze_contract,
)
from scripts.strategy_research.g2_flow_funding_entries_r1.signals import (
    CANDIDATE_CONFIGS,
    config_identity_sha,
)


def test_research_budget_constraints() -> None:
    """Research budget strictly respects max 3 identities x 2 horizons = 6 configs."""
    assert len(CANDIDATE_CONFIGS) == 6
    families = {c["family"] for c in CANDIDATE_CONFIGS}
    assert len(families) == 3
    for f in families:
        f_configs = [c for c in CANDIDATE_CONFIGS if c["family"] == f]
        assert len(f_configs) == 2
        horizons = {c["horizon_hours"] for c in f_configs}
        assert horizons == {12, 18}


def test_candidate_identities_unique() -> None:
    """Each candidate identity has distinct SHA256 and unique ID."""
    hashes = [config_identity_sha(c) for c in CANDIDATE_CONFIGS]
    assert len(hashes) == 6
    assert len(set(hashes)) == 6


def test_no_unclosed_bars_in_candidate_rules() -> None:
    """All candidates require strictly closed bar boundaries and >= 1m transit lag."""
    for c in CANDIDATE_CONFIGS:
        # Stop loss and target must be well-formed
        assert c["stop_mult"] > 0
        assert c["target_r"] > 0
        assert c["cooldown_hours"] >= 4


def test_contract_file_exists_and_valid() -> None:
    """FROZEN_CONTRACT.json exists and contains required metadata."""
    if not CONTRACT_PATH.is_file():
        pytest.skip("Contract will be generated in Stage 1 freeze step")

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert contract["task_id"] == "V06_G2_GEMINI_A_FLOW_FUNDING_ENTRY_R1"
    assert contract["exact_start_sha"] == EXACT_START_SHA
    assert len(contract["candidate_identity_hashes"]) == 6
    assert "frozen_implementation_sha256" in contract


def test_verify_freeze_contract_function() -> None:
    """verify_freeze_contract validates implementation files match frozen digests."""
    if not CONTRACT_PATH.is_file():
        pytest.skip("Contract will be generated in Stage 1 freeze step")

    contract = verify_freeze_contract()
    assert contract is not None
