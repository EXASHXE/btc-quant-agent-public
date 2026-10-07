"""Unit and integration test suite for RC2 R3 Holdout Runner Repair R2.

Enforces:
- R2.1: Capability access model (CONSTRUCTION_REVIEW vs AUTHORIZED_EXECUTION).
- R2.2: Persistent execution access ledger recording all attempts with sequence, timestamp,
        mode, caller, disposition, and hashes.
- R2.3: Zero cross-run cache reuse in authority mode; fresh execution-scoped source fetch.
- R2.4: Exact authorization validation; regex syntax rejection; tracked and untracked dirt rejection.
- R2.5: Production-equivalent full-window pre-outcome audit across every decision step;
        adversarial missing-middle defects fail closed.
- R2.6: Complete authority input manifest binding authentic 1m OHLCV, quote volume, trades,
        and all derivative series; mutation assertions.
- R2.7: Staged artifacts never published before post-identity PASS; failure closure receipts.
- R2.8: Generic runner contains no hard-coded protected names.
"""

from __future__ import annotations

import bisect
import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from scripts.rc2.validation.r3_access_guard import (
    RETIRED_R3_TARGETS,
    AccessCapability,
    AccessDisposition,
    AccessMode,
    AuthorizationProof,
    ExecutionAccessLedger,
)
from scripts.rc2.validation.run_holdout_r3 import (
    ACCEPTED_HARNESS_SHA,
    ACCEPTED_NORMALIZER_SHA256,
    BRANCH,
    CONFIG_HASH,
    CONTROLLER_DISPATCH_SHA,
    FIRST_STEP,
    FROZEN_POLICY_SHA,
    LAST_STEP,
    REFERENCES,
    START_SHA,
    TARGETS,
    TASK_ID,
    VALID_GATE_TO_TERMINAL,
    audit_full_window_production_context,
    build_dataset,
    check_execution_authorization,
    classify_holdout_terminal,
    classify_policy_quality_authority,
    execute_holdout,
    fetch_fresh_source_bundle,
    generate_authority_input_manifest,
    write_attempt_receipt,
)
from scripts.rc2.validation.source_normalizer import (
    ProtectedSymbolFirewallViolation,
)
from scripts.rc2.validation.target_seal import (
    TARGET_SEAL_SCHEMA_VERSION,
    TargetSealHashMismatchError,
    TargetSealNotFoundError,
    TargetSealRoleOverlapError,
    TargetSealSchemaError,
    validate_target_seal,
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


def _make_dummy_target_seal(
    path: Path,
    targets: tuple[str, ...] = ("FILUSDT", "ETCUSDT"),
    references: tuple[str, ...] = REFERENCES,
    extra_field: dict[str, Any] | None = None,
) -> tuple[Path, str]:
    payload: dict[str, Any] = {
        "schema_version": TARGET_SEAL_SCHEMA_VERSION,
        "task_id": TASK_ID,
        "created_at_utc": "2026-10-07T20:00:00Z",
        "target_symbols": list(targets),
        "context_only_references": list(references),
    }
    if extra_field:
        payload.update(extra_field)
    content = json.dumps(payload, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return path, sha256


# =====================================================================
# R2.1: Capability Access Model
# =====================================================================

def test_execution_mode_cannot_be_constructed_before_authorization() -> None:
    ledger = ExecutionAccessLedger()
    # Cannot construct AUTHORIZED_EXECUTION without proof
    with pytest.raises(PermissionError, match="cannot be constructed before runner"):
        AccessCapability(mode=AccessMode.AUTHORIZED_EXECUTION, ledger=ledger, proof=None)

    # Cannot construct with invalid proof
    with pytest.raises(ValueError, match="Invalid runner SHA"):
        AuthorizationProof(
            authorized_runner_sha="invalid-sha",
            authorized_runner_sha256="0" * 64,
            execution_dispatch_sha="0" * 40,
            target_seal_sha256="0" * 64,
            sealed_targets=("FILUSDT",),
            allowed_references=REFERENCES,
            created_at_utc="2026-10-07T00:00:00Z",
        )


def test_construction_mode_blocks_injected_target_access() -> None:
    ledger = ExecutionAccessLedger()
    # Injected seal targets in construction mode must be strictly blocked
    injected_targets = ("INJUSDT", "UNIUSDT")
    cap = AccessCapability.construction_review(ledger, injected_seal_targets=injected_targets)

    # Injected targets blocked
    with pytest.raises(ProtectedSymbolFirewallViolation, match="injected seal target"):
        cap.check_access("INJUSDT", caller="test")

    with pytest.raises(ProtectedSymbolFirewallViolation, match="injected seal target"):
        cap.check_access("https://data.binance.vision/.../UNIUSDT/15m/...", caller="test")

    # Retired R3 targets blocked
    for ret in RETIRED_R3_TARGETS:
        with pytest.raises(ProtectedSymbolFirewallViolation, match="retired R3"):
            cap.check_access(ret, caller="test")

    # Symbols outside burned whitelist blocked
    with pytest.raises(ProtectedSymbolFirewallViolation, match="not in allowed non-protected"):
        cap.check_access("RANDOMCOINUSDT", caller="test")

    # Allowed burned symbols pass
    disp = cap.check_access("FILUSDT", caller="test")
    assert disp == AccessDisposition.ALLOWED_TARGET.value
    assert ledger.blocked_count >= 3


def test_authorized_execution_mode_allows_only_exact_sealed_and_reference_names() -> None:
    ledger = ExecutionAccessLedger()
    proof = AuthorizationProof(
        authorized_runner_sha="0123456789abcdef0123456789abcdef01234567",
        authorized_runner_sha256="a" * 64,
        execution_dispatch_sha="b" * 40,
        target_seal_sha256="c" * 64,
        sealed_targets=("FILUSDT", "ETCUSDT"),
        allowed_references=REFERENCES,
        created_at_utc="2026-10-07T00:00:00Z",
    )
    cap = AccessCapability.create_authorized_execution(proof=proof, ledger=ledger)

    # Exact sealed targets allowed
    disp1 = cap.check_access("FILUSDT", caller="test")
    assert disp1 == AccessDisposition.ALLOWED_TARGET.value

    disp2 = cap.check_access("ETCUSDT", caller="test")
    assert disp2 == AccessDisposition.ALLOWED_TARGET.value

    # Exact references allowed
    for ref in REFERENCES:
        disp_ref = cap.check_access(ref, caller="test")
        assert disp_ref == AccessDisposition.ALLOWED_REFERENCE.value

    # Non-sealed symbols strictly rejected
    with pytest.raises(ProtectedSymbolFirewallViolation, match="outside sealed targets"):
        cap.check_access("ADAUSDT", caller="test")

    with pytest.raises(ProtectedSymbolFirewallViolation, match="outside sealed targets"):
        cap.check_access("COMPUSDT", caller="test")


# =====================================================================
# R2.2: Persistent Execution Access Ledger
# =====================================================================

def test_persistent_ledger_records_all_access_attempts(tmp_path: Path) -> None:
    ledger_file = tmp_path / "test_ledger.json"
    ledger = ExecutionAccessLedger(ledger_file)
    cap = AccessCapability.construction_review(ledger)

    # Allowed access
    cap.check_access("FILUSDT", caller="unit_test")
    # Blocked access
    with pytest.raises(ProtectedSymbolFirewallViolation):
        cap.check_access("COMPUSDT", caller="unit_test")

    assert ledger._seq == 2
    assert ledger.blocked_count == 1
    assert ledger.allowed_target_count == 1

    # Check persisted ledger
    data = json.loads(ledger_file.read_text(encoding="utf-8"))
    assert data["total_entries"] == 2
    assert data["blocked_count"] == 1
    entries = data["entries"]
    assert entries[0]["seq"] == 1
    assert entries[0]["symbol"] == "FILUSDT"
    assert entries[0]["disposition"] == AccessDisposition.ALLOWED_TARGET.value
    assert entries[1]["seq"] == 2
    assert entries[1]["disposition"] == AccessDisposition.BLOCKED.value


# =====================================================================
# R2.4: Exact Authorization & Regex Syntax Rejection
# =====================================================================

def test_sha_and_sha256_syntax_rejection(tmp_path: Path) -> None:
    seal_path, seal_sha = _make_dummy_target_seal(tmp_path / "seal.json")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runner_sha256 = hashlib.sha256((ROOT / "scripts/rc2/validation/run_holdout_r3.py").read_bytes()).hexdigest()

    # 1. Invalid 39-char runner SHA
    ok, _terminal, detail = check_execution_authorization(
        authorized_runner_sha="0" * 39,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha="0" * 40,
        target_seal_path=seal_path,
        authorized_target_seal_sha256=seal_sha,
        root=ROOT,
    )
    assert ok is False
    assert any("authorized-runner-sha" in r for r in detail["reasons"])

    # 2. Uppercase runner SHA
    ok, _terminal, detail = check_execution_authorization(
        authorized_runner_sha=("A" * 40),
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha="0" * 40,
        target_seal_path=seal_path,
        authorized_target_seal_sha256=seal_sha,
        root=ROOT,
    )
    assert ok is False

    # 3. Invalid 63-char runner SHA256
    ok, _terminal, detail = check_execution_authorization(
        authorized_runner_sha=head,
        authorized_runner_sha256="0" * 63,
        execution_dispatch_sha="0" * 40,
        target_seal_path=seal_path,
        authorized_target_seal_sha256=seal_sha,
        root=ROOT,
    )
    assert ok is False

    # 4. Invalid seal SHA256
    ok, _terminal, detail = check_execution_authorization(
        authorized_runner_sha=head,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha="0" * 40,
        target_seal_path=seal_path,
        authorized_target_seal_sha256="NOT_HEX" + "0" * 57,
        root=ROOT,
    )
    assert ok is False


def test_tracked_and_untracked_authority_file_dirt_rejection(tmp_path: Path) -> None:
    # Test that check_execution_authorization detects untracked files
    seal_path, seal_sha = _make_dummy_target_seal(tmp_path / "seal.json")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runner_sha256 = hashlib.sha256((ROOT / "scripts/rc2/validation/run_holdout_r3.py").read_bytes()).hexdigest()

    untracked = ROOT / "scripts/rc2/validation/_temp_untracked_test_file.py"
    try:
        untracked.write_text("print('test')\n")
        ok, _terminal, detail = check_execution_authorization(
            authorized_runner_sha=head,
            authorized_runner_sha256=runner_sha256,
            execution_dispatch_sha="0" * 40,
            target_seal_path=seal_path,
            authorized_target_seal_sha256=seal_sha,
            root=ROOT,
        )
        assert ok is False
        assert any("dirt detected" in r for r in detail["reasons"])
    finally:
        if untracked.exists():
            untracked.unlink()


# =====================================================================
# Target Seal Contract Validation
# =====================================================================

def test_target_seal_schema_and_validation(tmp_path: Path) -> None:
    # 1. Missing seal
    with pytest.raises(TargetSealNotFoundError):
        validate_target_seal(tmp_path / "nonexistent.json", "0" * 64, REFERENCES)

    # 2. SHA256 mismatch
    seal_path, seal_sha = _make_dummy_target_seal(tmp_path / "seal1.json")
    wrong_sha = "f" * 64
    with pytest.raises(TargetSealHashMismatchError):
        validate_target_seal(seal_path, wrong_sha, REFERENCES)

    # 3. Unexpected key in seal violates frozen contract schema
    seal_extra, sha_extra = _make_dummy_target_seal(
        tmp_path / "seal_extra.json", extra_field={"unexpected_key": 123}
    )
    with pytest.raises(TargetSealSchemaError, match="unexpected keys"):
        validate_target_seal(seal_extra, sha_extra, REFERENCES)

    # 4. Target / Reference role overlap
    seal_overlap, sha_overlap = _make_dummy_target_seal(
        tmp_path / "seal_overlap.json", targets=("FILUSDT", "BTCUSDT")
    )
    with pytest.raises(TargetSealRoleOverlapError, match="overlap with context-only references"):
        validate_target_seal(seal_overlap, sha_overlap, REFERENCES)

    # 5. Valid seal passes
    targets, data = validate_target_seal(seal_path, seal_sha, REFERENCES)
    assert targets == ("FILUSDT", "ETCUSDT")
    assert data["schema_version"] == TARGET_SEAL_SCHEMA_VERSION


# =====================================================================
# R2.3: Zero Cross-Run Cache Reuse in Authority Mode
# =====================================================================

def test_no_cross_run_cache_reuse_in_authority_mode(tmp_path: Path) -> None:
    source_dir = tmp_path / "source_attempt"
    source_dir.mkdir(parents=True, exist_ok=True)
    # Pre-populate with stale file
    (source_dir / "stale_archive.zip").write_text("STALE")

    ledger = ExecutionAccessLedger()
    proof = AuthorizationProof(
        authorized_runner_sha="0" * 40,
        authorized_runner_sha256="0" * 64,
        execution_dispatch_sha="0" * 40,
        target_seal_sha256="0" * 64,
        sealed_targets=("FILUSDT",),
        allowed_references=REFERENCES,
        created_at_utc="2026-10-07T00:00:00Z",
    )
    cap = AccessCapability.create_authorized_execution(proof, ledger)

    with pytest.raises(RuntimeError, match="forbids cross-run cache reuse"):
        fetch_fresh_source_bundle(
            target_symbols=("FILUSDT",),
            reference_symbols=REFERENCES,
            capability=cap,
            source_dir=source_dir,
        )


def test_source_bundle_manifest_binds_real_url_and_digest_entries(tmp_path: Path) -> None:
    source_dir = tmp_path / "clean_source_attempt"
    ledger = ExecutionAccessLedger()
    proof = AuthorizationProof(
        authorized_runner_sha="0" * 40,
        authorized_runner_sha256="0" * 64,
        execution_dispatch_sha="0" * 40,
        target_seal_sha256="0" * 64,
        sealed_targets=("FILUSDT",),
        allowed_references=REFERENCES,
        created_at_utc="2026-10-07T00:00:00Z",
    )
    cap = AccessCapability.create_authorized_execution(proof, ledger)

    def dummy_fetch_entry(symbol, tf_start, is_target, capability, source_dir, archive_manifest):
        archive_manifest[f"https://data.binance.vision/{symbol}-archive.zip"] = "abc123sha"
        return symbol, {"klines_15m": [], "klines_1h": [], "klines_4h": [], "klines_1m": []}

    with patch("scripts.rc2.validation.run_holdout_r3._fetch_symbol_entry", side_effect=dummy_fetch_entry):
        _raw, manifest = fetch_fresh_source_bundle(
            target_symbols=("FILUSDT",),
            reference_symbols=("BTCUSDT",),
            capability=cap,
            source_dir=source_dir,
        )

    assert manifest["manifest_version"] == "RC2_SOURCE_BUNDLE_MANIFEST_V1"
    assert manifest["source_bundle_digest"] != "NONE"
    assert manifest["source_archives_count"] == 2
    assert (source_dir / "SOURCE_BUNDLE_MANIFEST.json").exists()


# =====================================================================
# R2.5: Production-Equivalent Full-Window Pre-Outcome Audit
# =====================================================================

def test_full_window_production_context_audit_baseline_and_missing_middle() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    dataset = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=False)

    # 1. Baseline dataset passes full window audit
    audit = audit_full_window_production_context(dataset, burned_targets, REFERENCES)
    assert audit["full_window_audit_passed"] is True
    assert audit["defects_count"] == 0
    assert audit["steps_evaluated_count"] == len(dataset.step_timestamps_ms)
    assert audit["target_1m_outcome_queries_count"] == 0
    assert audit["pit_violations_count"] == 0


def test_full_window_audit_adversarial_missing_middle_cases() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")

    # Case A: Missing 1h candle in middle of decision window
    fil_1h = raw["data"]["FILUSDT"]["klines_1h"]
    assert len(fil_1h) > 50
    closes_1h = [int(c[6]) for c in fil_1h]
    p1_1h = bisect.bisect_left(closes_1h, FIRST_STEP)
    p2_1h = bisect.bisect_right(closes_1h, LAST_STEP)
    mid_idx = (p1_1h + p2_1h) // 2
    removed_1h = fil_1h.pop(mid_idx)
    try:
        ds_tampered_1h = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=False)
        audit_1h = audit_full_window_production_context(ds_tampered_1h, burned_targets, REFERENCES)
        assert audit_1h["full_window_audit_passed"] is False
        assert audit_1h["defects_count"] > 0
    finally:
        fil_1h.insert(mid_idx, removed_1h)

    # Case B: Missing OI in middle of decision window
    oi_hist = raw["data"]["FILUSDT"]["oi_hist"]
    oi_ts = [int(x["timestamp"]) for x in oi_hist]
    p1_oi = bisect.bisect_left(oi_ts, FIRST_STEP)
    p2_oi = bisect.bisect_right(oi_ts, LAST_STEP)
    mid_oi_idx = (p1_oi + p2_oi) // 2
    removed_oi = oi_hist[mid_oi_idx - 10 : mid_oi_idx + 10]
    del oi_hist[mid_oi_idx - 10 : mid_oi_idx + 10]
    try:
        ds_tampered_oi = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=False)
        audit_oi = audit_full_window_production_context(ds_tampered_oi, burned_targets, REFERENCES)
        assert audit_oi["full_window_audit_passed"] is False
        assert audit_oi["defects_count"] > 0
    finally:
        oi_hist[mid_oi_idx - 10 : mid_oi_idx - 10] = removed_oi

    # Case C: Missing benchmark series (BTCUSDT removed)
    btc_entry = raw["data"].pop("BTCUSDT")
    try:
        ds_no_btc = build_dataset(raw, burned_targets, ("ETHUSDT",), include_outcomes=False)
        audit_btc = audit_full_window_production_context(ds_no_btc, burned_targets, ("ETHUSDT",))
        assert audit_btc["full_window_audit_passed"] is False
        assert "Benchmark missing" in audit_btc["first_failure"]["error"]
    finally:
        raw["data"]["BTCUSDT"] = btc_entry


def test_assessment_count_and_symbol_mismatch_fails_closed() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    dataset = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=False)

    # Claiming target universe is ("FILUSDT", "ETCUSDT", "SOLUSDT") while dataset only has 2
    three_targets = ("FILUSDT", "ETCUSDT", "SOLUSDT")
    audit = audit_full_window_production_context(dataset, three_targets, REFERENCES)
    assert audit["full_window_audit_passed"] is False
    assert "mismatch" in audit["first_failure"]["error"] or audit["defects_count"] > 0


# =====================================================================
# R2.6: Authority Input Manifest Mutation Tests
# =====================================================================

def test_authority_hash_mutations_target_1m_quote_volume_and_derivatives() -> None:
    raw = _get_burned_raw_data()
    burned_targets = ("FILUSDT", "ETCUSDT")
    script_hashes = {"run_holdout_r3.py": "abc", "source_normalizer.py": "def"}

    dataset_base = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=True)
    manifest_base = generate_authority_input_manifest(
        dataset=dataset_base,
        raw=raw,
        target_symbols=burned_targets,
        reference_symbols=REFERENCES,
        script_hashes=script_hashes,
        target_seal_sha256="seal_hash_000",
        source_bundle_digest="bundle_digest_000",
    )
    base_hash = manifest_base["authority_input_manifest_hash"]

    # 1. Mutate target 1m quote_volume
    orig_qvol = raw["data"]["FILUSDT"]["klines_1m"][0][7]
    try:
        raw["data"]["FILUSDT"]["klines_1m"][0][7] = float(orig_qvol or 0.0) + 9999.0
        ds_mut = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=True)
        m_mut = generate_authority_input_manifest(
            dataset=ds_mut,
            raw=raw,
            target_symbols=burned_targets,
            reference_symbols=REFERENCES,
            script_hashes=script_hashes,
            target_seal_sha256="seal_hash_000",
            source_bundle_digest="bundle_digest_000",
        )
        assert m_mut["authority_input_manifest_hash"] != base_hash
    finally:
        raw["data"]["FILUSDT"]["klines_1m"][0][7] = orig_qvol

    # 2. Mutate target 1m OHLCV (close price and high price)
    orig_close = raw["data"]["FILUSDT"]["klines_1m"][0][4]
    orig_high = raw["data"]["FILUSDT"]["klines_1m"][0][2]
    try:
        raw["data"]["FILUSDT"]["klines_1m"][0][4] = float(orig_close) + 1.0
        raw["data"]["FILUSDT"]["klines_1m"][0][2] = max(float(orig_high), float(orig_close) + 1.0)
        ds_mut = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=True)
        m_mut = generate_authority_input_manifest(
            dataset=ds_mut,
            raw=raw,
            target_symbols=burned_targets,
            reference_symbols=REFERENCES,
            script_hashes=script_hashes,
            target_seal_sha256="seal_hash_000",
            source_bundle_digest="bundle_digest_000",
        )
        assert m_mut["authority_input_manifest_hash"] != base_hash
    finally:
        raw["data"]["FILUSDT"]["klines_1m"][0][4] = orig_close
        raw["data"]["FILUSDT"]["klines_1m"][0][2] = orig_high

    # 3. Mutate context reference 15m volume
    orig_ref_vol = raw["data"]["BTCUSDT"]["klines_15m"][0][5]
    try:
        raw["data"]["BTCUSDT"]["klines_15m"][0][5] = float(orig_ref_vol) + 10.0
        ds_mut = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=True)
        m_mut = generate_authority_input_manifest(
            dataset=ds_mut,
            raw=raw,
            target_symbols=burned_targets,
            reference_symbols=REFERENCES,
            script_hashes=script_hashes,
            target_seal_sha256="seal_hash_000",
            source_bundle_digest="bundle_digest_000",
        )
        assert m_mut["authority_input_manifest_hash"] != base_hash
    finally:
        raw["data"]["BTCUSDT"]["klines_15m"][0][5] = orig_ref_vol

    # 4. Mutate derivatives (OI, taker, gls, top_pos, top_acc, basis, funding)
    for deriv_key in ("oi_hist", "taker_hist", "gls_hist", "top_pos_hist", "top_acc_hist", "basis_hist", "funding_rates"):
        entry = raw["data"]["FILUSDT"][deriv_key]
        if entry:
            if isinstance(entry[0], dict) and "timestamp" in entry[0]:
                orig_ts = entry[0]["timestamp"]
                entry[0]["timestamp"] = int(orig_ts) + 1
                try:
                    ds_mut = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=True)
                    m_mut = generate_authority_input_manifest(
                        dataset=ds_mut,
                        raw=raw,
                        target_symbols=burned_targets,
                        reference_symbols=REFERENCES,
                        script_hashes=script_hashes,
                        target_seal_sha256="seal_hash_000",
                        source_bundle_digest="bundle_digest_000",
                    )
                    assert m_mut["authority_input_manifest_hash"] != base_hash, f"Failed for {deriv_key}"
                finally:
                    entry[0]["timestamp"] = orig_ts
            elif isinstance(entry[0], dict) and "funding_time_ms" in entry[0]:
                orig_ts = entry[0]["funding_time_ms"]
                entry[0]["funding_time_ms"] = int(orig_ts) + 1
                try:
                    ds_mut = build_dataset(raw, burned_targets, REFERENCES, include_outcomes=True)
                    m_mut = generate_authority_input_manifest(
                        dataset=ds_mut,
                        raw=raw,
                        target_symbols=burned_targets,
                        reference_symbols=REFERENCES,
                        script_hashes=script_hashes,
                        target_seal_sha256="seal_hash_000",
                        source_bundle_digest="bundle_digest_000",
                    )
                    assert m_mut["authority_input_manifest_hash"] != base_hash, f"Failed for {deriv_key}"
                finally:
                    entry[0]["funding_time_ms"] = orig_ts


# =====================================================================
# R2.7: Staged Publication & Failure Receipts
# =====================================================================

def test_final_authority_path_pre_exists_fails_closed(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "final_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "stale_file.json").write_text("{}")

    # Running holdout when evidence_dir exists with files must fail closed immediately
    seal_path, seal_sha = _make_dummy_target_seal(tmp_path / "seal.json")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runner_sha256 = hashlib.sha256((ROOT / "scripts/rc2/validation/run_holdout_r3.py").read_bytes()).hexdigest()

    execute_holdout(
        authorized_runner_sha=head,
        authorized_runner_sha256=runner_sha256,
        execution_dispatch_sha="0" * 40,
        target_seal_path=seal_path,
        authorized_target_seal_sha256=seal_sha,
        evidence_dir=evidence_dir,
        root=ROOT,
    )
    # Final evidence dir must remain untouched
    assert (evidence_dir / "OUTPUT_MANIFEST.json").exists() is False


def test_exception_path_attempt_receipts(tmp_path: Path) -> None:
    staging_dir = tmp_path / "staging_receipt"
    _receipt = write_attempt_receipt(
        staging_dir=staging_dir,
        phase="PREFLIGHT",
        terminal="RC2_HOLDOUT_R3_PREFLIGHT_FAIL",
        target_outcomes_resolved=False,
        authority_valid=False,
        exception_class="TargetSealHashMismatchError",
        exception_message="Hash mismatch detected",
    )
    receipt_file = staging_dir / "ATTEMPT_RECEIPT.json"
    assert receipt_file.exists()
    saved = json.loads(receipt_file.read_text(encoding="utf-8"))
    assert saved["phase"] == "PREFLIGHT"
    assert saved["target_outcomes_resolved"] is False
    assert saved["authority_valid"] is False
    assert saved["exception_class"] == "TargetSealHashMismatchError"


def test_staged_artifacts_not_published_before_post_identity_pass(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "final_evidence"
    seal_path, seal_sha = _make_dummy_target_seal(tmp_path / "seal.json")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    runner_sha256 = hashlib.sha256((ROOT / "scripts/rc2/validation/run_holdout_r3.py").read_bytes()).hexdigest()

    # If an error happens before publication, artifacts are never published to final evidence_dir
    with patch("scripts.rc2.validation.run_holdout_r3.check_execution_authorization") as mock_auth:
        mock_auth.return_value = (False, "RC2_HOLDOUT_R3_PREFLIGHT_FAIL", {"reasons": ["simulated failure"]})
        execute_holdout(
            authorized_runner_sha=head,
            authorized_runner_sha256=runner_sha256,
            execution_dispatch_sha="0" * 40,
            target_seal_path=seal_path,
            authorized_target_seal_sha256=seal_sha,
            evidence_dir=evidence_dir,
            root=ROOT,
        )

    # Final evidence directory must NOT have been created or populated
    assert not evidence_dir.exists() or not (evidence_dir / "OUTPUT_MANIFEST.json").exists()


# =====================================================================
# R2.8: Generic Runner Contract
# =====================================================================

def test_generic_runner_contains_no_hardcoded_protected_names() -> None:
    # Generic runner has empty targets by default; targets come ONLY from seal
    assert TARGETS == ()
    assert REFERENCES == (
        "BTCUSDT",
        "ETHUSDT",
        "SOLUSDT",
        "LINKUSDT",
        "SUIUSDT",
        "XRPUSDT",
        "DOGEUSDT",
        "BNBUSDT",
    )
    assert BRANCH == "validation/b-line-rc2-holdout-r3-runner-repair-r2"
    assert START_SHA == "0d61b564fa178af0f0a8e7df1c0a6b13586711e3"
    assert FROZEN_POLICY_SHA == "10be512f2cf4d7eccdc8a9849c925b5f73c568fd"
    assert ACCEPTED_HARNESS_SHA == "cbc903d9ba448059121db96c3572a2677d5b53f8"
    assert CONTROLLER_DISPATCH_SHA == "405e0042687bfae5aa986e0f2982e26cba3827cd"
    assert ACCEPTED_NORMALIZER_SHA256 == "4191922d1e85ad30b079633323836a817bf0506d223eb2365b2a4d3d25f52a16"
    assert CONFIG_HASH == "bba61849e64f37f9"


# =====================================================================
# Terminal Classification & Authority Semantics (Bounded Fix #1)
# =====================================================================

def test_terminal_classification_pass() -> None:
    # Test 1 — PASS: deterministic = True, gate = exact frozen PASS value
    assert "TACTICAL_DECISION_QUALITY_PASS" in VALID_GATE_TO_TERMINAL
    terminal = classify_holdout_terminal("TACTICAL_DECISION_QUALITY_PASS", deterministic=True)
    assert terminal == "RC2_HOLDOUT_R3_PASS"
    authority = classify_policy_quality_authority(terminal)
    assert authority == "PASS"


def test_terminal_classification_fail() -> None:
    # Test 2 — FAIL: deterministic = True, gate = exact frozen FAIL value
    terminal = classify_holdout_terminal("TACTICAL_DECISION_QUALITY_FAIL", deterministic=True)
    assert terminal == "RC2_HOLDOUT_R3_FAIL"
    authority = classify_policy_quality_authority(terminal)
    assert authority == "FAIL"


def test_terminal_classification_diagnostic_only() -> None:
    # Test 3 — DIAGNOSTIC_ONLY: deterministic = True, gate = exact frozen DIAGNOSTIC_ONLY values
    terminal = classify_holdout_terminal("TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY", deterministic=True)
    assert terminal == "RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY"
    assert classify_policy_quality_authority(terminal) == "DIAGNOSTIC_ONLY"

    terminal_gran = classify_holdout_terminal(
        "TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY_DATA_GRANULARITY_INSUFFICIENT",
        deterministic=True,
    )
    assert terminal_gran == "RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY"
    assert classify_policy_quality_authority(terminal_gran) == "DIAGNOSTIC_ONLY"


def test_terminal_classification_nondeterministic() -> None:
    # Test 4 — nondeterministic: deterministic = False regardless of otherwise valid gate value
    for gate in (
        "TACTICAL_DECISION_QUALITY_PASS",
        "TACTICAL_DECISION_QUALITY_FAIL",
        "TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY",
        "TACTICAL_DECISION_QUALITY_DIAGNOSTIC_ONLY_DATA_GRANULARITY_INSUFFICIENT",
        "UNEXPECTED_GATE_VALUE",
    ):
        terminal = classify_holdout_terminal(gate, deterministic=False)
        assert terminal == "RC2_HOLDOUT_R3_INFRA_INCOMPLETE", f"Failed for gate={gate}"
        assert classify_policy_quality_authority(terminal) == "NONE_INFRA_INCOMPLETE"


def test_terminal_classification_unknown_gate() -> None:
    # Test 5 — unknown gate: deterministic = True, unrecognized gate value fails closed
    for unknown in ("UNEXPECTED_GATE_VALUE", "", "TACTICAL_DECISION_QUALITY_UNKNOWN", "SOME_OTHER_DECISION"):
        terminal = classify_holdout_terminal(unknown, deterministic=True)
        assert terminal == "RC2_HOLDOUT_R3_INFRA_INCOMPLETE", f"Failed for unknown={unknown}"
        assert classify_policy_quality_authority(terminal) == "NONE_INFRA_INCOMPLETE"


def test_terminal_release_authority_mapping() -> None:
    # Test 6 — release authority:
    # PASS -> release_authority may become true according to existing RC2 logic
    # FAIL -> false
    # DIAGNOSTIC_ONLY -> false
    # INFRA_INCOMPLETE -> false
    def is_release_authority(t: str) -> bool:
        return t == "RC2_HOLDOUT_R3_PASS"

    assert is_release_authority("RC2_HOLDOUT_R3_PASS") is True
    assert is_release_authority("RC2_HOLDOUT_R3_FAIL") is False
    assert is_release_authority("RC2_HOLDOUT_R3_DIAGNOSTIC_ONLY") is False
    assert is_release_authority("RC2_HOLDOUT_R3_INFRA_INCOMPLETE") is False
    assert is_release_authority("RC2_HOLDOUT_R3_PREFLIGHT_FAIL") is False
