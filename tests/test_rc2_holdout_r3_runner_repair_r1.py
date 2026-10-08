"""Unit and integration test suite for RC2 R3 Holdout Runner Repair R1.

Covers:
1. Exact execution SHA binding: wrong HEAD, wrong runner hash, dirty worktree rejected.
2. Cache authority: sidecar, embedded, source manifest, and payload content binding.
3. Full-window context audit: every decision step audited, defects fail closed.
4. Complete authority input manifest: canonical digests change on any consumed field change.
5. Reference exclusion: references never enter outcome aggregation.
6. Post-execution identity assertion: final evidence not published before verification.
7. Protected target network guard with real guarded downloader path.
"""

from __future__ import annotations

import gc
import gzip
import hashlib
import json
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.rc2.validation.r3_access_guard import (
    PROTECTED_R3_TARGETS,
    ConstructionAccessLedger,
    guarded_download,
)
from scripts.rc2.validation.run_holdout_r3 import (
    ACCEPTED_HARNESS_SHA,
    ACCEPTED_NORMALIZER_SHA256,
    BRANCH,
    DATA_END,
    FIRST_STEP,
    FROZEN_POLICY_SHA,
    LAST_STEP,
    ONE_MIN_START,
    START_SHA,
    VALIDATION_SCRIPTS,
    audit_full_window_context,
    build_dataset,
    check_execution_authorization,
    compute_canonical_payload_sha256,
    generate_authority_input_manifest,
    validate_r3_cache_authority,
    verify_freeze_repair_identity,
)
from scripts.rc2.validation.source_normalizer import (
    CacheAuthorityError,
    ProtectedSymbolFirewallViolation,
    RunnerIdentityMismatchError,
    capture_execution_identity,
    compute_cache_identity,
    save_authorized_cache,
    verify_execution_identity,
)

BURNED_FIXTURE_PATH = Path("/tmp/rc2_harness_r2_raw.json.gz")
_CACHED_BURNED_RAW: dict[str, Any] | None = None


def _get_burned_raw_data() -> dict[str, Any]:
    global _CACHED_BURNED_RAW
    if _CACHED_BURNED_RAW is not None:
        return _CACHED_BURNED_RAW
    if BURNED_FIXTURE_PATH.exists():
        with gzip.open(BURNED_FIXTURE_PATH, "rt", encoding="utf-8") as f:
            wrapped = json.load(f)
        if isinstance(wrapped, dict) and "payload" in wrapped:
            _CACHED_BURNED_RAW = wrapped["payload"]
            return _CACHED_BURNED_RAW
        if isinstance(wrapped, dict) and "data" in wrapped:
            _CACHED_BURNED_RAW = wrapped
            return _CACHED_BURNED_RAW
    r1_path = Path("/tmp/rc2_r1_1_raw.json.gz")
    if r1_path.exists():
        with gzip.open(r1_path, "rt", encoding="utf-8") as f:
            data = json.load(f)
            if "data" in data:
                _CACHED_BURNED_RAW = data
                return _CACHED_BURNED_RAW
    pytest.skip("No burned fixture available in /tmp")


# R1 Tests: Exact Execution SHA Binding
def test_r1_authorization_wrong_head_rejected() -> None:
    runner_path = ROOT / "scripts/rc2/validation/run_holdout_r3.py"
    runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    fake_head = "0123456789abcdef0123456789abcdef01234567"
    fake_dispatch = "abcdef0123456789abcdef0123456789abcdef01"

    ok, terminal, detail = check_execution_authorization(
        authorized_runner_sha=fake_head,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha=fake_dispatch,
        root=ROOT,
        expected_branch=BRANCH,
    )
    assert ok is False
    assert terminal == "RC2_HOLDOUT_R3_PREFLIGHT_FAIL"
    assert any("HEAD mismatch" in r for r in detail["reasons"])


def test_r1_authorization_wrong_runner_hash_rejected() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    fake_runner_sha256 = "0" * 64
    fake_dispatch = "abcdef0123456789abcdef0123456789abcdef01"

    ok, terminal, detail = check_execution_authorization(
        authorized_runner_sha=head,
        authorized_runner_sha256=fake_runner_sha256,
        execution_dispatch_sha=fake_dispatch,
        root=ROOT,
        expected_branch=BRANCH,
    )
    assert ok is False
    assert terminal == "RC2_HOLDOUT_R3_PREFLIGHT_FAIL"
    assert any("Runner SHA256 mismatch" in r for r in detail["reasons"])


def test_r1_authorization_wrong_branch_rejected() -> None:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runner_path = ROOT / "scripts/rc2/validation/run_holdout_r3.py"
    runner_sha256 = hashlib.sha256(runner_path.read_bytes()).hexdigest()
    fake_dispatch = "abcdef0123456789abcdef0123456789abcdef01"

    ok, terminal, detail = check_execution_authorization(
        authorized_runner_sha=head,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha=fake_dispatch,
        root=ROOT,
        expected_branch="invalid/wrong-branch",
    )
    assert ok is False
    assert terminal == "RC2_HOLDOUT_R3_PREFLIGHT_FAIL"
    assert any("Branch mismatch" in r for r in detail["reasons"])


# R2 Tests: Cache Authority Binding
def test_r2_cache_authority_reusable_and_tamper_rejection(tmp_path: Path) -> None:
    time_window = {
        "first_step": FIRST_STEP,
        "last_step": LAST_STEP,
        "data_end": DATA_END,
        "one_min_start": ONE_MIN_START,
    }
    symbol_roles = {
        "targets": ["FILUSDT"],
        "references": ["BTCUSDT"],
    }
    source_archives = [{"url": "https://data.binance.vision/archive.zip", "sha256": "123456"}]

    identity = compute_cache_identity(
        time_window=time_window,
        symbol_roles=symbol_roles,
        source_archives=source_archives,
        script_paths=VALIDATION_SCRIPTS,
    )

    dummy_data = {"FILUSDT": {"klines_15m": []}}
    raw_payload = {
        "symbols": ["FILUSDT", "BTCUSDT"],
        "anchor_end_ms": DATA_END,
        "data": dummy_data,
        "source_archives": source_archives,
    }

    cache_file = tmp_path / "test_r2_cache.json.gz"
    save_authorized_cache(cache_file, identity, raw_payload)
    payload_sha256 = compute_canonical_payload_sha256(dummy_data)

    # 1. Matching sidecar + embedded + source manifest + payload => reusable
    loaded, audit = validate_r3_cache_authority(
        cache_file, identity, expected_payload_sha256=payload_sha256
    )
    assert audit["cache_reusable"] is True
    assert loaded["data"] == dummy_data

    # 2. Sidecar vs embedded mismatch rejected
    identity_path = cache_file.with_name("test_r2_cache.identity.json")
    tampered_sidecar = dict(identity.to_dict())
    tampered_sidecar["schema_version"] = "TAMPERED_SCHEMA"
    identity_path.write_text(json.dumps(tampered_sidecar))
    with pytest.raises(CacheAuthorityError, match="Sidecar identity and embedded cache identity mismatch"):
        validate_r3_cache_authority(cache_file, identity)

    # 3. Payload content tampering rejected
    save_authorized_cache(cache_file, identity, raw_payload)
    bad_payload_sha256 = "f" * 64
    with pytest.raises(CacheAuthorityError, match="Payload canonical content digest mismatch"):
        validate_r3_cache_authority(cache_file, identity, expected_payload_sha256=bad_payload_sha256)

    # 4. Source archives manifest digest mismatch rejected
    tampered_archives_payload = dict(raw_payload)
    tampered_archives_payload["source_archives"] = [{"url": "https://other.com/archive.zip", "sha256": "wrong"}]
    save_authorized_cache(cache_file, identity, tampered_archives_payload)
    with pytest.raises(CacheAuthorityError, match="Payload source archives digest mismatch"):
        validate_r3_cache_authority(cache_file, identity)


# R3 Tests: Full-Window Context and Warm-Up Audit
def test_r3_full_window_context_audit_clean() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    burned_refs = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT")

    dataset = build_dataset(raw, burned_targets, burned_refs, include_outcomes=False)
    audit = audit_full_window_context(dataset, burned_targets, burned_refs)

    assert audit["full_window_audit_passed"] is True
    assert audit["defects_count"] == 0
    assert audit["total_decision_steps"] == 2689
    assert audit["symbols_audited_count"] == 10
    del dataset
    gc.collect()


def test_r3_full_window_context_audit_detects_defect() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    burned_refs = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT")

    dataset = build_dataset(raw, burned_targets, burned_refs, include_outcomes=False)
    # Deliberately empty out 1h klines for one symbol to simulate defective archive
    dataset.series_by_symbol["FILUSDT"] = replace(dataset.series_by_symbol["FILUSDT"], klines_1h=())

    audit = audit_full_window_context(dataset, burned_targets, burned_refs)
    assert audit["full_window_audit_passed"] is False
    assert audit["defects_count"] > 0
    assert audit["first_failure"]["symbol"] == "FILUSDT"
    del dataset
    gc.collect()


# R4 Tests: Complete Authority Input Manifest
def test_r4_complete_authority_manifest_changes_on_consumed_field_mutation() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    burned_refs = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "LINKUSDT", "SUIUSDT", "XRPUSDT", "DOGEUSDT", "BNBUSDT")

    dataset = build_dataset(raw, burned_targets, burned_refs, include_outcomes=True)
    script_hashes = {"test.py": "abc"}
    manifest1 = generate_authority_input_manifest(dataset, raw, burned_targets, burned_refs, script_hashes)
    h1 = manifest1["authority_input_manifest_hash"]

    # Identical call gives identical hash
    manifest2 = generate_authority_input_manifest(dataset, raw, burned_targets, burned_refs, script_hashes)
    assert manifest2["authority_input_manifest_hash"] == h1

    # Mutate a 15m candle volume via replace (preserving OHLC bounds)
    original_c = dataset.series_by_symbol["FILUSDT"].klines_15m[0]
    mutated_c = replace(original_c, volume=original_c.volume + 10.0)
    dataset.series_by_symbol["FILUSDT"] = replace(
        dataset.series_by_symbol["FILUSDT"],
        klines_15m=(mutated_c,) + dataset.series_by_symbol["FILUSDT"].klines_15m[1:],
    )
    manifest_mutated = generate_authority_input_manifest(dataset, raw, burned_targets, burned_refs, script_hashes)
    h_mutated = manifest_mutated["authority_input_manifest_hash"]
    assert h_mutated != h1

    # Restore
    dataset.series_by_symbol["FILUSDT"] = replace(
        dataset.series_by_symbol["FILUSDT"],
        klines_15m=(original_c,) + dataset.series_by_symbol["FILUSDT"].klines_15m[1:],
    )
    del dataset
    gc.collect()


# R5 Tests: Post-execution identity assertion
def test_r5_post_execution_identity_mutation_fails(tmp_path: Path) -> None:
    script = tmp_path / "test_script.py"
    script.write_text("print(1)\n")
    pre = capture_execution_identity(
        task_id="TEST_IDENTITY",
        root=ROOT,
        expected_branch=BRANCH,
        script_paths=[script],
    )
    # Modifying script before post verification raises RunnerIdentityMismatchError
    script.write_text("print(2)\n")
    with pytest.raises(RunnerIdentityMismatchError, match="SCRIPT_HASHES_MISMATCH"):
        verify_execution_identity(pre, ROOT, [script])


# R6 Tests: Protected Target Network Guard
def test_r6_network_guard_allows_burned_and_blocks_protected(tmp_path: Path) -> None:
    ledger_file = tmp_path / "test_ledger.json"
    ledger = ConstructionAccessLedger(ledger_file=ledger_file)

    # 1. Burned symbols allowed
    ledger.check_and_log("https://data.binance.vision/klines/FILUSDT/15m/FILUSDT-15m-2026-09.zip")
    ledger.check_and_log("https://data.binance.vision/klines/BTCUSDT/1h/BTCUSDT-1h-2026-09.zip")
    assert ledger.allowed_attempts_count == 2
    assert ledger.protected_attempts_count == 0

    # 2. Protected targets strictly blocked with ProtectedSymbolFirewallViolation
    for sym in PROTECTED_R3_TARGETS:
        with pytest.raises(ProtectedSymbolFirewallViolation):
            ledger.check_and_log(f"https://data.binance.vision/daily/metrics/{sym}/{sym}-metrics-2026-09-01.zip")

    assert ledger.protected_attempts_count == len(PROTECTED_R3_TARGETS)
    summary = ledger.summary()
    assert summary["protected_attempts_count"] == len(PROTECTED_R3_TARGETS)


def test_r6_real_guarded_downloader_with_burned_symbol() -> None:
    test_ledger = ConstructionAccessLedger()
    # Test guarded download with mocked response
    with patch("urllib.request.urlopen") as mock_url:
        mock_resp = mock_url.return_value.__enter__.return_value
        mock_resp.read.return_value = b"MOCK_ARCHIVE_BYTES"

        data = guarded_download(
            "https://data.binance.vision/data/futures/um/daily/klines/FILUSDT/15m/FILUSDT-15m-2026-09-01.zip",
            ledger=test_ledger,
        )
        assert data == b"MOCK_ARCHIVE_BYTES"
        assert test_ledger.allowed_attempts_count == 1
        assert test_ledger.protected_attempts_count == 0

        # Attempting protected symbol is blocked before urlopen
        with pytest.raises(ProtectedSymbolFirewallViolation):
            guarded_download(
                "https://data.binance.vision/data/futures/um/daily/klines/COMPUSDT/15m/COMPUSDT-15m-2026-09-01.zip",
                ledger=test_ledger,
            )
        assert test_ledger.protected_attempts_count == 1


def test_freeze_repair_identity_function() -> None:
    info = verify_freeze_repair_identity(ROOT)
    assert info["terminal"] in (
        "RC2_R3_RUNNER_REPAIR_R1_READY_FOR_EXACT_SHA_REVIEW",
        "RC2_R3_RUNNER_REPAIR_R2_READY_FOR_FRESH_SOL_REVIEW",
        "RC2_R3_RUNNER_REPAIR_R2_BLOCKED",
        "RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_READY_FOR_CONTROLLER",
        "RC2_FINAL_HOLDOUT_INFRA_REPAIR_R1_BLOCKED",
    )
    assert info["branch"] == BRANCH
    assert info["start_sha"] == START_SHA
    assert info["frozen_policy_sha"] == FROZEN_POLICY_SHA
    assert info["accepted_harness_sha"] == ACCEPTED_HARNESS_SHA
    assert info["normalizer_sha256"] == ACCEPTED_NORMALIZER_SHA256
    assert info["protected_target_network_access_count"] == 0
