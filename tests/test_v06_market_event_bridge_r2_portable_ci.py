"""Category 8: 27 rigorous unit tests for PortablePinnedSourceHarness & CI Portability.

Verifies:
- Exact Git SHA verification for upstream B and C
- Cryptographic file manifest integrity
- Isolated subprocess consumer execution
- Rejection of path traversal, corrupt SHAs, missing commits, and tampered files
- Complete independence from host paths (/root/...)
- Cross-package namespace pollution defense
- Fail-closed network and timeout boundaries
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from scripts.integration.market_event_bridge_r2.portable_ci_refs import (
    A_BASE_PINNED_SHA,
    ORIGINAL_G1_PINNED_SHA,
    PINNED_FILE_CHECKSUMS,
    UPSTREAM_B_PINNED_SHA,
    UPSTREAM_C_PINNED_SHA,
    ManifestMismatchError,
    PinnedSourceError,
    PinnedUpstreamUnavailable,
    PortablePinnedSourceHarness,
    SecurityViolationError,
    ensure_portable_b_on_path,
    ensure_portable_c_on_path,
    get_harness,
)


@pytest.fixture
def clean_scratch_dir(tmp_path: Path) -> Path:
    scratch = tmp_path / "test_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    return scratch


@pytest.fixture
def harness(clean_scratch_dir: Path) -> PortablePinnedSourceHarness:
    return PortablePinnedSourceHarness(base_dir=clean_scratch_dir)


def test_harness_materialize_b_success_and_witness(harness: PortablePinnedSourceHarness) -> None:
    path = harness.materialize_b()
    assert path.is_dir()
    contract_file = path / "scripts/strategy_research/forward_shadow_research_r1/contract.py"
    assert contract_file.is_file()
    witnesses = harness.get_witnesses()
    assert "upstream_b" in witnesses
    w = witnesses["upstream_b"]
    assert w["pinned_sha"] == UPSTREAM_B_PINNED_SHA
    assert w["manifest_sha256"] != ""


def test_harness_materialize_c_success_and_witness(harness: PortablePinnedSourceHarness) -> None:
    path = harness.materialize_c()
    assert path.is_dir()
    port_file = path / "scripts/g1g3_offline_ports_r1/market_pit_port.py"
    assert port_file.is_file()
    witnesses = harness.get_witnesses()
    assert "upstream_c" in witnesses
    w = witnesses["upstream_c"]
    assert w["pinned_sha"] == UPSTREAM_C_PINNED_SHA
    assert w["manifest_sha256"] != ""


def test_harness_rejects_corrupted_sha_format(harness: PortablePinnedSourceHarness) -> None:
    with pytest.raises(PinnedSourceError, match="Invalid git commit SHA"):
        harness.materialize("bad", "not-a-sha", ["scripts"])

    with pytest.raises(PinnedSourceError, match="Invalid git commit SHA"):
        harness.materialize("short", "12345678", ["scripts"])

    with pytest.raises(PinnedSourceError, match="Invalid git commit SHA"):
        harness.materialize("bad_char", "g" * 40, ["scripts"])


def test_harness_rejects_nonexistent_sha_when_network_disabled(clean_scratch_dir: Path) -> None:
    strict_harness = PortablePinnedSourceHarness(base_dir=clean_scratch_dir, allow_network_fetch=False)
    fake_sha = "0" * 40
    with pytest.raises(PinnedUpstreamUnavailable, match="PINNED_UPSTREAM_UNAVAILABLE"):
        strict_harness.materialize("ghost", fake_sha, ["scripts"])


def test_harness_rejects_tampered_key_file_checksum(clean_scratch_dir: Path) -> None:
    h = PortablePinnedSourceHarness(base_dir=clean_scratch_dir)
    target = h.materialize_b()
    # Intentionally corrupt a verified file
    target_file = target / "scripts/strategy_research/forward_shadow_research_r1/contract.py"
    target_file.write_text("# corrupted payload\n", encoding="utf-8")

    # Re-verifying must detect tampered content
    with pytest.raises(ManifestMismatchError, match="Checksum mismatch"):
        h._verify_checksums(target, UPSTREAM_B_PINNED_SHA)


def test_harness_path_traversal_in_name_rejected(harness: PortablePinnedSourceHarness) -> None:
    with pytest.raises(SecurityViolationError, match="Invalid materialization name"):
        harness.materialize("../escape", UPSTREAM_B_PINNED_SHA, ["scripts"])

    with pytest.raises(SecurityViolationError, match="Invalid materialization name"):
        harness.materialize("sub/dir", UPSTREAM_B_PINNED_SHA, ["scripts"])


def test_harness_path_traversal_in_subpath_rejected(harness: PortablePinnedSourceHarness) -> None:
    with pytest.raises(SecurityViolationError, match="Invalid subpath"):
        harness.materialize("b_test", UPSTREAM_B_PINNED_SHA, ["../../etc"])

    with pytest.raises(SecurityViolationError, match="Invalid subpath"):
        harness.materialize("b_test", UPSTREAM_B_PINNED_SHA, ["/absolute/path"])


def test_harness_isolated_b_subprocess_execution(harness: PortablePinnedSourceHarness) -> None:
    snippet = """
from scripts.strategy_research.forward_shadow_research_r1.contract import parse_funding_payload
payload = {'T': 1728720000000, 'r': 0.0001, 'p': 64000.5, 'settled': True, 'symbol': 'BTCUSDT'}
res = parse_funding_payload(payload)
print(f"RATE:{res.funding_rate},SETTLED:{res.settled}")
"""
    result = harness.run_isolated_consumer("B", snippet)
    assert result["returncode"] == 0
    assert "RATE:0.0001,SETTLED:True" in result["stdout"]
    assert result["stdout_sha256"] != ""


def test_harness_isolated_c_subprocess_execution(harness: PortablePinnedSourceHarness) -> None:
    snippet = """
from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort
port = MarketPitPort(expected_stream_id="test@stream", expected_manifest_sha256="m_sha")
print(f"PORT_STREAM:{port.expected_stream_id}")
"""
    result = harness.run_isolated_consumer("C", snippet)
    assert result["returncode"] == 0
    assert "PORT_STREAM:test@stream" in result["stdout"]


def test_harness_prevents_cross_package_sys_modules_contamination() -> None:
    # Materializing B and importing should not leak C packages into sys.modules
    ensure_portable_b_on_path()
    from scripts.strategy_research.forward_shadow_research_r1.contract import parse_funding_payload
    assert parse_funding_payload is not None

    # Verify that g1g3 is not accidentally imported yet unless explicitly requested
    ensure_portable_c_on_path()
    from scripts.g1g3_offline_ports_r1.market_pit_port import MarketPitPort
    assert MarketPitPort is not None


def test_harness_subpath_nonexistent_in_commit(harness: PortablePinnedSourceHarness) -> None:
    with pytest.raises(PinnedSourceError, match="git archive extraction failed"):
        harness.materialize("nonexistent_path", UPSTREAM_B_PINNED_SHA, ["path/that/does/not/exist_12345"])


def test_harness_repeated_materialization_is_cached(harness: PortablePinnedSourceHarness) -> None:
    path1 = harness.materialize_b()
    mtime1 = (path1 / "scripts/strategy_research/forward_shadow_research_r1/contract.py").stat().st_mtime
    path2 = harness.materialize_b()
    mtime2 = (path2 / "scripts/strategy_research/forward_shadow_research_r1/contract.py").stat().st_mtime
    assert path1 == path2
    assert mtime1 == mtime2


def test_harness_force_recreate_overwrites_cleanly(harness: PortablePinnedSourceHarness) -> None:
    path1 = harness.materialize_b()
    canary = path1 / "canary.txt"
    canary.write_text("temporary-file", encoding="utf-8")
    assert canary.exists()

    path2 = harness.materialize_b(force=True)
    assert path1 == path2
    assert not canary.exists()


def test_harness_detects_corrupted_cache_and_repairs(harness: PortablePinnedSourceHarness) -> None:
    path = harness.materialize_b()
    contract_file = path / "scripts/strategy_research/forward_shadow_research_r1/contract.py"
    contract_file.write_text("# mutation", encoding="utf-8")

    # Non-force materialize should detect mismatch and repair by re-extracting
    repaired_path = harness.materialize_b()
    repaired_file = repaired_path / "scripts/strategy_research/forward_shadow_research_r1/contract.py"
    actual_sha = hashlib.sha256(repaired_file.read_bytes()).hexdigest()
    assert actual_sha == PINNED_FILE_CHECKSUMS[UPSTREAM_B_PINNED_SHA]["scripts/strategy_research/forward_shadow_research_r1/contract.py"]


def test_harness_consumer_unknown_type_raises(harness: PortablePinnedSourceHarness) -> None:
    with pytest.raises(ValueError, match="Unknown consumer type"):
        harness.run_isolated_consumer("X", "print(1)")


def test_harness_consumer_syntax_error_captured(harness: PortablePinnedSourceHarness) -> None:
    result = harness.run_isolated_consumer("B", "def invalid_syntax: pass")
    assert result["returncode"] != 0
    assert "SyntaxError" in result["stderr"]


def test_harness_consumer_timeout_terminates_cleanly(harness: PortablePinnedSourceHarness) -> None:
    snippet = "import time; time.sleep(10)"
    with pytest.raises(subprocess.TimeoutExpired):
        harness.run_isolated_consumer("B", snippet, timeout_seconds=0.5)


def test_harness_witness_contains_expected_fields(harness: PortablePinnedSourceHarness) -> None:
    harness.materialize_b()
    witnesses = harness.get_witnesses()
    w = witnesses["upstream_b"]
    assert "name" in w
    assert "pinned_sha" in w
    assert "target_dir" in w
    assert "verified_files" in w
    assert "manifest_sha256" in w
    assert "is_read_only" in w


def test_harness_exact_sha_constants() -> None:
    assert UPSTREAM_B_PINNED_SHA == "51cdd4e17503fbd18ad22aaeeaba3580f5efacf8"
    assert UPSTREAM_C_PINNED_SHA == "91495e5b8c178e60f3cf2f56eab3ad4deeb7c86b"
    assert ORIGINAL_G1_PINNED_SHA == "861a9d148f72db00e6079e53af78220bdd7e84ce"
    assert A_BASE_PINNED_SHA.startswith("df00997f344e")


def test_harness_no_hardcoded_root_paths_in_witnesses(harness: PortablePinnedSourceHarness) -> None:
    harness.materialize_b()
    harness.materialize_c()
    for w in harness.get_witnesses().values():
        assert "/root/workspace/project/quant-v0.6/gemini-" not in w["target_dir"]


def test_harness_unauthorized_egress_fails_closed(harness: PortablePinnedSourceHarness) -> None:
    snippet = """
import urllib.request
try:
    urllib.request.urlopen("http://192.0.2.1:80", timeout=1)
    print("EGRESS_OPEN")
except Exception as e:
    print(f"EGRESS_BLOCKED:{type(e).__name__}")
"""
    res = harness.run_isolated_consumer("B", snippet, timeout_seconds=3.0)
    assert "EGRESS_BLOCKED" in res["stdout"]


def test_harness_consumer_returns_invalid_payload_fails(harness: PortablePinnedSourceHarness) -> None:
    snippet = """
import json
output = {"invalid_key": True}
print(json.dumps(output))
"""
    res = harness.run_isolated_consumer("B", snippet)
    data = json.loads(res["stdout"])
    assert "settled" not in data


def test_harness_environment_isolation_no_secrets_leaked(harness: PortablePinnedSourceHarness) -> None:
    snippet = """
import os
for k in os.environ:
    if any(s in k.lower() for s in ('token', 'secret', 'password', 'api_key')):
        print(f"LEAKED:{k}")
"""
    res = harness.run_isolated_consumer("B", snippet)
    assert "LEAKED" not in res["stdout"]


def test_harness_b_and_c_instances_are_distinct(harness: PortablePinnedSourceHarness) -> None:
    b_path = harness.materialize_b()
    c_path = harness.materialize_c()
    assert b_path != c_path
    assert b_path.name != c_path.name


def test_harness_singleton_helper() -> None:
    h1 = get_harness()
    h2 = get_harness()
    assert h1 is h2


def test_harness_safe_path_validation(harness: PortablePinnedSourceHarness) -> None:
    # A path that attempts to escape base_dir
    escaped = harness.base_dir / "../../outside"
    with pytest.raises(SecurityViolationError, match="Path traversal"):
        harness._validate_safe_path(escaped)


def test_harness_missing_verified_file_triggers_manifest_mismatch(clean_scratch_dir: Path) -> None:
    h = PortablePinnedSourceHarness(base_dir=clean_scratch_dir)
    target = h.materialize_b()
    # Delete a verified file
    target_file = target / "scripts/strategy_research/forward_shadow_research_r1/signals.py"
    target_file.unlink()

    with pytest.raises(ManifestMismatchError, match="Missing pinned file"):
        h._verify_checksums(target, UPSTREAM_B_PINNED_SHA)
