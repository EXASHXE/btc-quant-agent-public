# ruff: noqa: E402
# Source/bootstrap path is established before optional installed Quant imports.
"""End-to-end offline pytest suite for WSL handoff verifier + unmodified S1/C (runs inside WSL O_final_env)."""

from __future__ import annotations

from contextlib import closing
import ipaddress
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import time

import pytest

POC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = POC_ROOT.parent
PROGRAM_O_SRC = REPO_ROOT / "lt-program-o-clock-remediation-01" / "src"

for _p in (str(POC_ROOT), str(PROGRAM_O_SRC)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tests.fixtures import LoopbackMockVenue, TRIGGER
from win_capture.bundle import canonical_bytes, canonical_digest
from win_capture.capture import capture_session
from wsl_handoff.importer import (
    HandoffError,
    process_bundle_to_handoff,
    verify_and_load_bundle,
)


@pytest.fixture(autouse=True, scope="module")
def _loopback_only_socket_guard():
    orig_connect = socket.socket.connect
    orig_create = socket.create_connection

    def check_addr(address):
        if isinstance(address, tuple) and address:
            host = str(address[0])
            ip = ipaddress.ip_address(host)
            if not ip.is_loopback:
                raise RuntimeError(f"NON_LOOPBACK_FORBIDDEN:{host}")

    def guarded_connect(self, address):
        check_addr(address)
        return orig_connect(self, address)

    def guarded_create(address, *args, **kwargs):
        check_addr(address)
        return orig_create(address, *args, **kwargs)

    socket.socket.connect = guarded_connect  # type: ignore[method-assign]
    socket.create_connection = guarded_create
    try:
        yield
    finally:
        socket.socket.connect = orig_connect  # type: ignore[method-assign]
        socket.create_connection = orig_create


def _make_coherent_win_sampler(start_utc_ms: int = TRIGGER + 1_800_000):
    epoch = time.monotonic_ns()
    boot_id = "qa-win-boot-0001"
    offset = 10_000_000_000

    def sampler():
        el = time.monotonic_ns() - epoch
        qpc0 = offset + el
        unb0 = offset + el + 500
        qpc1 = qpc0 + 50_000
        unb1 = unb0 + 50_000
        win_ns = start_utc_ms * 1_000_000 + el
        return {
            "boot_session_id": boot_id,
            "qpc_freq": 10_000_000,
            "qpc_before_ns": qpc0,
            "qpc_after_ns": qpc1,
            "qpc_before_ms": qpc0 // 1_000_000,
            "qpc_after_ms": qpc1 // 1_000_000,
            "unbiased_before_ns": unb0,
            "unbiased_after_ns": unb1,
            "unbiased_before_ms": unb0 // 1_000_000,
            "unbiased_after_ms": unb1 // 1_000_000,
            "tick64_ms": (offset + el) // 1_000_000,
            "win_utc_ns": win_ns,
            "win_utc_ms": win_ns // 1_000_000,
            "strict_utc_qualified": False,
        }

    return sampler


@pytest.fixture
def make_qa_bundle(tmp_path):
    venues = []
    counter = 0

    def _create(*, flat=False, minutes=30, market_fault=None, wall_jump=False):
        nonlocal counter
        counter += 1
        cert_dir = tmp_path / f"certs_{counter}"
        bundle_dir = tmp_path / f"bundle_{counter}"
        venue = LoopbackMockVenue(cert_dir, flat=flat, minutes=minutes, market_fault=market_fault)
        venues.append(venue)
        base_sampler = _make_coherent_win_sampler()
        calls = 0

        def wrapped_sampler():
            nonlocal calls
            calls += 1
            s = base_sampler()
            if wall_jump and calls >= 5:
                s["win_utc_ns"] += 2_286_000_000
                s["win_utc_ms"] += 2286
            return s

        manifest = capture_session(bundle_dir, qa=venue.qa, clock_sampler=wrapped_sampler)
        return bundle_dir, manifest

    yield _create
    for v in venues:
        v.close()


def test_end_to_end_positive_watch_and_flat_decisions_and_c_boundary(make_qa_bundle, tmp_path):
    watch_dir, watch_manifest = make_qa_bundle(flat=False, wall_jump=True)
    assert len(watch_manifest["clock_guard"]["wall_jumps_observed"]) >= 1

    handoff_out = tmp_path / "handoff_watch"
    res = process_bundle_to_handoff(watch_dir, handoff_out)

    assert res["schema"] == "WSL_WINDOWS_BUNDLE_S1_HANDOFF_V1"
    assert res["strict_utc_qualified"] is False
    assert res["source_qualified"] is False
    assert res["shadow_advisory_qualified"] is False
    assert res["economically_validated"] is False
    assert res["account"] == "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    assert res["s2_status"] == "RESEARCH_ONLY_DISABLED"
    assert res["s3_status"] == "RESEARCH_ONLY_DISABLED"

    btc = res["decisions"]["BTCUSDT"]
    assert btc["market_state"] == "WATCH"
    assert btc["opportunity"] is not None
    assert btc["episode_id"] is not None
    assert btc["opportunity"]["planned_after_cost_r"] >= 2.0
    assert btc["opportunity"]["setup_close_ms"] == TRIGGER
    assert btc["decision_ms"] >= TRIGGER + 30 * 60_000
    assert btc["diagnostics"]["signal_issued_at_close"] is False
    assert res["decisions"]["ETHUSDT"]["market_state"] == "NO_SETUP"
    assert res["decisions"]["SOLUSDT"]["market_state"] == "NO_SETUP"

    c_gate = res["program_c_boundary"]
    assert c_gate["actual_C_validator_error"] == "SOURCE_CLASS_INVALID"
    assert c_gate["scientific_decision"] == "INSUFFICIENT_SUPPORT"
    assert c_gate["C_economic_ledger_executed"] is False
    assert c_gate["source_relabeling"] is False

    # Flat bundle -> all NO_SETUP
    flat_dir, _ = make_qa_bundle(flat=True)
    flat_res = process_bundle_to_handoff(flat_dir, tmp_path / "handoff_flat")
    assert [flat_res["decisions"][s]["market_state"] for s in ("BTCUSDT", "ETHUSDT", "SOLUSDT")] == [
        "NO_SETUP"
    ] * 3


@pytest.mark.parametrize(
    "fault,reason_substr",
    [
        ("chase", "SWING_PRICE_OUTSIDE_FROZEN_ENTRY_REGION_NO_CHASE"),
        ("pivot", "SWING_PROTECTIVE_PIVOT_INVALIDATED_SINCE_CLOSE"),
        ("target_hit", "SWING_TARGET_ALREADY_OBSERVED_NO_RETROSPECTIVE_ENTRY"),
    ],
)
def test_actionability_downgrades_positive_setup_to_no_setup(make_qa_bundle, tmp_path, fault, reason_substr):
    bundle_dir, _ = make_qa_bundle(flat=False, market_fault=fault)
    res = process_bundle_to_handoff(bundle_dir, tmp_path / f"out_{fault}")
    btc = res["decisions"]["BTCUSDT"]
    assert btc["market_state"] == "NO_SETUP"
    assert btc["opportunity"] is None
    assert btc["episode_id"] is None
    assert not btc["eligible_planned_r"]
    assert any(reason_substr in r for r in btc["reasons"])


def test_wsl_clock_skew_independence_proven_identical(make_qa_bundle, tmp_path, monkeypatch):
    bundle_dir, _ = make_qa_bundle(flat=False)

    # Forbid compile/verify path from using Linux monotonic or wall clocks for S1 decisions
    monkeypatch.setattr(
        time, "monotonic_ns", lambda: (_ for _ in ()).throw(AssertionError("WSL_MONO_FORBIDDEN"))
    )
    monkeypatch.setattr(
        time, "time_ns", lambda: (_ for _ in ()).throw(AssertionError("WSL_REALTIME_FORBIDDEN"))
    )

    def nominal_telemetry():
        return {
            "authoritative_for_s1": False,
            "adjtimex": {"tick": 10000, "freq_ppm": 0.0},
            "defect_isolated": False,
        }

    def degraded_telemetry():
        return {
            "authoritative_for_s1": False,
            "adjtimex": {"tick": 9000, "freq_ppm": -500.0},
            "mono_minus_raw_ms": -12500.0,
            "wall_minus_mono_ms": 2286.0,
            "defect_isolated": True,
        }

    res_a = process_bundle_to_handoff(bundle_dir, tmp_path / "out_nom", telemetry_fn=nominal_telemetry)
    res_b = process_bundle_to_handoff(bundle_dir, tmp_path / "out_deg", telemetry_fn=degraded_telemetry)

    assert res_a["decisions"] == res_b["decisions"]
    assert res_a["trigger_ms"] == res_b["trigger_ms"]
    assert res_a["review_bounds"] == res_b["review_bounds"]
    assert res_a["program_c_boundary"] == res_b["program_c_boundary"]
    assert res_b["wsl_clock_telemetry"]["defect_isolated"] is True


def test_bundle_tamper_and_security_rejections(make_qa_bundle, tmp_path):
    src_dir, manifest = make_qa_bundle(flat=False)

    # 1a. Tamper 1 byte in-place (same byte length) -> caught by raw binary SHA256
    d1a = tmp_path / "tamper_raw_sha"
    shutil.copytree(src_dir, d1a)
    first_bin_a = next((d1a / "responses").glob("*.bin"))
    orig_bytes = first_bin_a.read_bytes()
    flipped = orig_bytes[:-1] + (b"\n" if orig_bytes[-1:] != b"\n" else b"\t")
    first_bin_a.write_bytes(flipped)
    with pytest.raises(HandoffError, match="WSL_BUNDLE_RAW_SHA256_MISMATCH"):
        verify_and_load_bundle(d1a)

    # 1b. Append 1 byte -> caught by length mismatch
    d1b = tmp_path / "tamper_raw_len"
    shutil.copytree(src_dir, d1b)
    first_bin_b = next((d1b / "responses").glob("*.bin"))
    first_bin_b.write_bytes(first_bin_b.read_bytes() + b" ")
    with pytest.raises(HandoffError, match="WSL_BUNDLE_RAW_LEN_MISMATCH"):
        verify_and_load_bundle(d1b)

    # 2. Tamper authority flag & re-seal manifest hashes (still caught by SQLite BUNDLE_SEALED + authority check)
    d2 = tmp_path / "tamper_auth"
    shutil.copytree(src_dir, d2)
    m2 = json.loads((d2 / "bundle_manifest.json").read_text(encoding="utf-8"))
    m2["source_qualified"] = True
    (d2 / "bundle_manifest.json").write_bytes(canonical_bytes(m2))
    with pytest.raises(HandoffError, match="WSL_BUNDLE_AUTHORITY_BOUNDARY_VIOLATED"):
        verify_and_load_bundle(d2)

    # 3. Tamper SQLite row directly -> caught by file SHA256
    d3 = tmp_path / "tamper_sqlite"
    shutil.copytree(src_dir, d3)
    with closing(sqlite3.connect(d3 / "ledger.sqlite")) as db:
        with db:
            db.execute("UPDATE events SET kind='TAMPER' WHERE seq=1")
    with pytest.raises(HandoffError, match="WSL_BUNDLE_LEDGER_FILE_SHA256_MISMATCH"):
        verify_and_load_bundle(d3)

    # 4. Tamper Windows dual-clock sample AND re-sign manifest hashes while keeping sqlite unchanged -> caught by SQLite BUNDLE_SEALED!
    d4 = tmp_path / "tamper_clock"
    shutil.copytree(src_dir, d4)
    m4 = json.loads((d4 / "bundle_manifest.json").read_text(encoding="utf-8"))
    m4["clock_guard"]["last_sample"]["unbiased_before_ns"] -= 80_000_000
    m4["clock_guard"]["last_sample"]["unbiased_after_ns"] -= 80_000_000
    body_keys = [
        k
        for k in m4
        if k not in ("manifest_body_sha256", "ledger_head_sha256", "ledger_sqlite_sha256", "bundle_sha256")
    ]
    m4["manifest_body_sha256"] = canonical_digest({k: m4[k] for k in body_keys})
    m4_no_bundle = {k: v for k, v in m4.items() if k != "bundle_sha256"}
    m4["bundle_sha256"] = canonical_digest(m4_no_bundle)
    (d4 / "bundle_manifest.json").write_bytes(canonical_bytes(m4))
    with pytest.raises(HandoffError, match="WSL_BUNDLE_SEAL_PAYLOAD_MISMATCH"):
        verify_and_load_bundle(d4)

    # 5. Symlink directory rejection
    sym = tmp_path / "sym_bundle"
    os.symlink(src_dir, sym)
    with pytest.raises(HandoffError, match="WSL_SYMLINK_FORBIDDEN"):
        verify_and_load_bundle(sym)

    # 6. Holdout overlap rejection
    with pytest.raises(HandoffError, match="WSL_HOLDOUT_DATE_OVERLAP_FORBIDDEN"):
        verify_and_load_bundle(src_dir, exclusions=[(TRIGGER - 14_400_000, TRIGGER)])

    # 7. Output dir must be unused
    used = tmp_path / "already_used"
    used.mkdir()
    with pytest.raises(HandoffError, match="WSL_HANDOFF_OUTPUT_DIR_MUST_BE_UNUSED"):
        process_bundle_to_handoff(src_dir, used)


def test_real_windows_native_bundle_handoff_if_present(tmp_path):
    """Consume an actual native Windows-generated bundle artifact if created during cross-OS test run."""
    native_bundle = os.environ.get("QUANT_WIN_NATIVE_QA_BUNDLE")
    if not native_bundle:
        pytest.skip("Set QUANT_WIN_NATIVE_QA_BUNDLE to verify cross-OS Windows->WSL binary handoff")
    res = process_bundle_to_handoff(Path(native_bundle), tmp_path / "cross_os_handoff")
    assert res["decisions"]["BTCUSDT"]["market_state"] == "WATCH"
    assert res["program_c_boundary"]["actual_C_validator_error"] == "SOURCE_CLASS_INVALID"
    assert res["program_c_boundary"]["scientific_decision"] == "INSUFFICIENT_SUPPORT"
