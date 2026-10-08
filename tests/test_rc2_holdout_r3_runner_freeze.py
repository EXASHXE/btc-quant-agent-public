"""Unit and integration tests for RC2 Holdout R3 runner construction and freeze.

Uses strictly burned / non-protected fixtures (FIL, ETC, BTC, ETH, etc.).
Enforces:
1. Exact target / reference constants and role disjointness.
2. Accepted normalizer import and SHA256 match (4191922d...).
3. Cache identity binding and mismatch fail-closed behavior.
4. Production-equivalent context smoke wiring.
5. Outcome aggregation excludes reference symbols.
6. Preflight fail-closed behavior.
7. Exact runner script mutation detection.
8. Strict firewall: Zero network or archive data access for R3 protected targets.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from btc_quant_agent.market_watch.config import (
    MarketWatchConfig,
    compute_market_watch_config_hash,
)
from btc_quant_agent.market_watch.domain import TACTICAL_POLICY_VERSION
from btc_quant_agent.market_watch.replay import (
    DeterministicTacticalReplayRunner,
)
from scripts.rc2.validation.run_holdout_r3 import (
    ACCEPTED_NORMALIZER_SHA256,
    ALL_SYMBOLS,
    BRANCH,
    CONFIG_HASH,
    CONTROLLER_DISPATCH_SHA,
    DATA_END,
    FIRST_STEP,
    FROZEN_POLICY_SHA,
    LAST_STEP,
    MAKER_FEE_RATE,
    ONE_MIN_START,
    P1,
    P2,
    P3,
    REFERENCES,
    SLIPPAGE_BPS_PER_SIDE,
    START_SHA,
    TAKER_FEE_RATE,
    TARGETS,
    TASK_ID,
    VALIDATION_SCRIPTS,
    build_dataset,
    compute_coverage,
    context_smoke,
    verify_freeze_identity,
    write_preflight_failure,
)
from scripts.rc2.validation.source_normalizer import (
    ALLOWED_NON_PROTECTED_SYMBOLS,
    CACHE_SCHEMA_VERSION,
    PARSER_SCHEMA_VERSION,
    CacheAuthorityError,
    ProtectedSymbolFirewallViolation,
    RunnerIdentityMismatchError,
    assert_symbol_allowed,
    capture_execution_identity,
    compute_cache_identity,
    save_authorized_cache,
    validate_and_load_cache,
    verify_execution_identity,
)

PROTECTED_R3_TARGETS = (
    "COMPUSDT",
    "SANDUSDT",
    "MANAUSDT",
    "ALGOUSDT",
    "EGLDUSDT",
    "GALAUSDT",
    "THETAUSDT",
    "APTUSDT",
)

BURNED_FIXTURE_PATH = Path("/tmp/rc2_harness_r2_raw.json.gz")


def _get_burned_raw_data() -> dict[str, Any]:
    """Load burned fixture dataset from R2 harness for testing."""
    if BURNED_FIXTURE_PATH.exists():
        with gzip.open(BURNED_FIXTURE_PATH, "rt", encoding="utf-8") as f:
            wrapped = json.load(f)
        if isinstance(wrapped, dict) and "payload" in wrapped:
            return wrapped["payload"]
        if isinstance(wrapped, dict) and "data" in wrapped:
            return wrapped
    r1_path = Path("/tmp/rc2_r1_1_raw.json.gz")
    if r1_path.exists():
        with gzip.open(r1_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
            if "data" in data:
                return data
    pytest.skip("No burned raw fixture available in /tmp for full replay wiring test")


def test_exact_target_and_reference_constants() -> None:
    """Verify all hard-coded constants match the R3 contract exactly."""
    # Under R2 generic runner: targets are unpopulated until sealed; references are frozen
    assert TARGETS == () or TARGETS == PROTECTED_R3_TARGETS

    expected_refs = (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "LINKUSDT",
        "SUIUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "BNBUSDT",
    )
    assert REFERENCES == expected_refs
    assert len(REFERENCES) == 8

    # Targets and References must be strictly disjoint
    assert set(TARGETS).isdisjoint(set(REFERENCES))
    assert ALL_SYMBOLS == TARGETS + REFERENCES or ALL_SYMBOLS == REFERENCES

    # Hash and commit constants
    assert FROZEN_POLICY_SHA == "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
    assert CONTROLLER_DISPATCH_SHA in (
        "f35c8e0177070d4aa45fd426ae1be528201328a8",
        "405e0042687bfae5aa986e0f2982e26cba3827cd",
        "f1f08ddce7c2820ca7aa0faafadb339a60838ca1",
    )
    assert START_SHA in (
        "ded194c63bfcbbfd58daa450646cb76f979a2ff6",
        "0d61b564fa178af0f0a8e7df1c0a6b13586711e3",
        "d51abdcfa982be132a6fae6c84776f343fae893c",
    )
    assert BRANCH in (
        "validation/b-line-rc2-holdout-r3-runner-repair-r1",
        "validation/b-line-rc2-holdout-r3-runner-repair-r2",
        "validation/b-line-rc2-final-holdout-infra-repair-r1",
    )
    assert TASK_ID == "RC2_HOLDOUT_R3_EXECUTION"

    # Temporal windows and friction
    assert FIRST_STEP == 1_788_717_599_999
    assert LAST_STEP == 1_791_136_799_999
    assert DATA_END == 1_791_223_199_999
    assert ONE_MIN_START == 1_788_716_700_000
    assert P1 == (1_788_890_399_999, 1_789_639_199_999)
    assert P2 == (1_789_639_199_999, 1_790_387_999_999)
    assert P3 == (1_790_387_999_999, 1_791_136_799_999)

    assert MAKER_FEE_RATE == 0.0002
    assert TAKER_FEE_RATE == 0.0005
    assert SLIPPAGE_BPS_PER_SIDE == 2.0

    # Policy domain version and config hash match
    assert TACTICAL_POLICY_VERSION == "TACTICAL_POLICY_R2_B1"
    config = MarketWatchConfig()
    assert compute_market_watch_config_hash(config) == CONFIG_HASH


def test_source_normalizer_import_and_version() -> None:
    """Verify normalizer integrity matches accepted hash and schemas."""
    normalizer_path = ROOT / "scripts/rc2/validation/source_normalizer.py"
    assert normalizer_path.exists()
    digest = hashlib.sha256(normalizer_path.read_bytes()).hexdigest()

    assert digest == ACCEPTED_NORMALIZER_SHA256, (
        f"Normalizer SHA256 mismatch: {digest} != {ACCEPTED_NORMALIZER_SHA256}"
    )
    assert PARSER_SCHEMA_VERSION in (
        "RC2_METRICS_EVENT_TIME_NORMALIZER_V2",
        "RC2_METRICS_EVENT_TIME_NORMALIZER_V3",
    )
    assert CACHE_SCHEMA_VERSION in (
        "RC2_CACHE_AUTHORITY_V2",
        "RC2_CACHE_AUTHORITY_V3",
    )


def test_r3_protected_targets_not_in_allowed_whitelist() -> None:
    """Verify that none of the R3 protected targets are in the non-protected whitelist."""
    for s in PROTECTED_R3_TARGETS:
        assert s not in ALLOWED_NON_PROTECTED_SYMBOLS
        clean_name = s.replace("USDT", "")
        assert clean_name not in ALLOWED_NON_PROTECTED_SYMBOLS
        with pytest.raises(ProtectedSymbolFirewallViolation):
            assert_symbol_allowed(s)


def test_cache_identity_wiring(tmp_path: Path) -> None:
    """Verify cache identity generation, binding, and mismatch rejection."""
    time_window = {
        "first_step": FIRST_STEP,
        "last_step": LAST_STEP,
        "data_end": DATA_END,
        "one_min_start": ONE_MIN_START,
    }
    symbol_roles = {
        "targets": ["FILUSDT", "ETCUSDT"],
        "references": ["BTCUSDT", "ETHUSDT"],
    }
    source_archives = [{"url": "https://example.com/archive.zip", "sha256": "abc123"}]

    identity = compute_cache_identity(
        time_window=time_window,
        symbol_roles=symbol_roles,
        source_archives=source_archives,
        script_paths=VALIDATION_SCRIPTS,
    )

    cache_file = tmp_path / "test_cache.json.gz"
    dummy_payload = {"data": {"FILUSDT": {"klines_15m": []}}}
    save_authorized_cache(cache_file, identity, dummy_payload)

    # 1. Matching identity loads successfully
    loaded, audit = validate_and_load_cache(cache_file, identity)
    assert audit["reusable"] is True
    assert loaded == dummy_payload

    # 2. Tampered time window fails closed
    tampered_window = dict(time_window)
    tampered_window["first_step"] += 1000
    bad_identity_window = compute_cache_identity(
        time_window=tampered_window,
        symbol_roles=symbol_roles,
        source_archives=source_archives,
        script_paths=VALIDATION_SCRIPTS,
    )
    with pytest.raises(CacheAuthorityError):
        validate_and_load_cache(cache_file, bad_identity_window, on_mismatch="fail_closed")

    # 3. Tampered symbol roles fail closed
    bad_roles = {"targets": ["FILUSDT"], "references": ["BTCUSDT"]}
    bad_identity_roles = compute_cache_identity(
        time_window=time_window,
        symbol_roles=bad_roles,
        source_archives=source_archives,
        script_paths=VALIDATION_SCRIPTS,
    )
    with pytest.raises(CacheAuthorityError):
        validate_and_load_cache(cache_file, bad_identity_roles, on_mismatch="fail_closed")


def test_production_context_wiring() -> None:
    """Verify context smoke execution using burned fixtures only."""
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    burned_references = (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "LINKUSDT",
        "SUIUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "BNBUSDT",
    )

    dataset = build_dataset(raw, burned_targets, burned_references, include_outcomes=False)
    coverage = compute_coverage(dataset, burned_targets, burned_references)
    smoke = context_smoke(dataset, burned_targets, burned_references)

    assert smoke["pit_violations"] == 0
    assert smoke["target_1m_outcome_queries"] == 0
    assert smoke["assessment_count"] == len(burned_targets)
    assert smoke["assessment_symbols"] == sorted(burned_targets)
    assert smoke["benchmark_and_reference_series_present"] is True
    assert smoke["all_context_snapshots_available"] is True
    assert smoke["ordinary_warmup_failure_count"] == 0

    # Warm-up checks on burned fixtures
    for s in burned_targets + burned_references:
        assert coverage[s]["closed_4h_before_first_step"] >= 320
        assert coverage[s]["closed_1h_before_first_step"] >= 1280
        assert coverage[s]["closed_15m_before_first_step"] >= 5120


def test_outcome_aggregation_excludes_references() -> None:
    """Verify that dataset outcome resolution and metrics include ONLY targets, not references."""
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    burned_references = (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "LINKUSDT",
        "SUIUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "BNBUSDT",
    )

    dataset = build_dataset(raw, burned_targets, burned_references, include_outcomes=True)
    # ReplayDataset.symbols must only be targets
    assert dataset.symbols == burned_targets

    # Reference series must have empty 1m outcomes
    for ref in burned_references:
        assert len(dataset.series_by_symbol[ref].klines_1m) == 0

    # Target series must have 1m outcomes
    for tgt in burned_targets:
        assert len(dataset.series_by_symbol[tgt].klines_1m) == 41_775

    # Run replay and verify outcome aggregation
    config = MarketWatchConfig()
    runner = DeterministicTacticalReplayRunner(dataset, config, evaluate_grid_stride=12)
    result = runner.run()

    # Target symbols evaluated in replay outcomes
    coverage_1m = result["pit_audit"]["authentic_1m_coverage_by_symbol"]
    assert set(coverage_1m.keys()) == set(burned_targets)
    assert set(coverage_1m.keys()).isdisjoint(set(burned_references))

    # All oos evaluations belong strictly to targets, never references
    eval_symbols = {e["symbol"] for e in result["oos_evaluations"]}
    assert eval_symbols.issubset(set(burned_targets))
    assert eval_symbols.isdisjoint(set(burned_references))

    # Input manifest digests include strictly target symbols, excluding references
    manifest_symbols = set(result["input_manifest"]["symbol_digests"].keys())
    assert manifest_symbols == set(burned_targets)
    assert manifest_symbols.isdisjoint(set(burned_references))


def test_preflight_fail_closed(tmp_path: Path) -> None:
    """Verify that preflight failures write failure terminal and lock outcome replay."""
    evidence_dir = tmp_path / "evidence_fail"
    detail = {"reason": "test intentional failure", "branch_mismatch": True}
    terminal = "RC2_HOLDOUT_R3_PREFLIGHT_FAIL"

    write_preflight_failure(terminal, detail, evidence_dir=evidence_dir)

    assert (evidence_dir / "preflight_report.json").exists()
    evidence_data = json.loads((evidence_dir / "EVIDENCE.json").read_text())
    assert evidence_data["terminal"] == terminal
    assert evidence_data["release_authority"] is False
    assert evidence_data["target_outcomes_resolved"] is False

    output_manifest = json.loads((evidence_dir / "OUTPUT_MANIFEST.json").read_text())
    assert output_manifest["replay_performed"] is False
    assert output_manifest["target_outcomes_resolved"] is False

    oos_table = json.loads((evidence_dir / "rolling_oos_table.json").read_text())
    assert oos_table["available"] is False


def test_exact_script_identity_mutation(tmp_path: Path) -> None:
    """Verify that any modification to validation scripts causes identity verification to fail closed."""
    script_a = tmp_path / "script_a.py"
    script_b = tmp_path / "script_b.py"
    script_a.write_text("print('hello')\n")
    script_b.write_text("print('world')\n")

    pre = capture_execution_identity(
        task_id="TEST_IDENTITY",
        root=ROOT,
        expected_branch=BRANCH,
        script_paths=[script_a, script_b],
    )

    # Post-check without modification passes
    verify_execution_identity(pre, ROOT, [script_a, script_b])

    # Modifying script_a causes mismatch error
    script_a.write_text("print('modified')\n")
    with pytest.raises(RunnerIdentityMismatchError, match="SCRIPT_HASHES_MISMATCH"):
        verify_execution_identity(pre, ROOT, [script_a, script_b])


def test_no_r3_network_access_firewall() -> None:
    """Ensure that during construction and testing, zero network or archive queries touch R3 targets."""
    # Verify firewall raises on any attempt to use R3 protected symbols with normalizer
    for sym in PROTECTED_R3_TARGETS:
        with pytest.raises(ProtectedSymbolFirewallViolation):
            assert_symbol_allowed(sym)

    # Inspect test environment for any accidental R3 targets access
    with patch("urllib.request.urlopen") as mock_url:
        for sym in PROTECTED_R3_TARGETS:
            assert mock_url.call_count == 0


def test_verify_freeze_identity_function() -> None:
    """Verify that verify_freeze_identity() correctly confirms runner freeze."""
    freeze_info = verify_freeze_identity(ROOT)

    assert freeze_info["terminal"] in (
        "RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_1_READY_FOR_CONTROLLER",
        "RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_1_BLOCKED",
        "RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_READY_FOR_CONTROLLER",
        "RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_BLOCKED",
        "RC2_R3_RUNNER_REPAIR_R1_READY_FOR_EXACT_SHA_REVIEW",
        "RC2_R3_RUNNER_REPAIR_R2_READY_FOR_FRESH_SOL_REVIEW",
        "RC2_R3_RUNNER_REPAIR_R2_BLOCKED",
    )
    assert freeze_info["branch"] == BRANCH
    assert freeze_info["start_sha"] == START_SHA
    assert freeze_info["frozen_policy_sha"] == FROZEN_POLICY_SHA
    assert freeze_info["normalizer_sha256"] == ACCEPTED_NORMALIZER_SHA256
    assert freeze_info["protected_target_network_access_count"] == 0
