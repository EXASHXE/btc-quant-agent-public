"""Category 5: Subprocess Crash Recovery (os._exit(91)), Torn WAL Quarantine, and Security Guards."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import urllib.request
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.g1_offline_preview_r1.model import SafetyViolation
from scripts.g1g3_offline_ports_r1.__main__ import VALID_CRASH_BOUNDARIES
from scripts.g1g3_offline_ports_r1.__main__ import main as cli_main
from scripts.g1g3_offline_ports_r1.durable_supervisor import (
    DurableSidecarSupervisor,
)
from scripts.g1g3_offline_ports_r1.loopback_servers import (
    FakeLoopbackLLMServer,
)
from scripts.g1g3_offline_ports_r1.market_pit_port import (
    MarketPitPort,
    make_synthetic_funding_envelope,
)
from scripts.g1g3_offline_ports_r1.no_order_port import (
    OWN_SCRATCH,
    LoopbackSocketGuard,
    NoOrderPort,
    guard_lexical_path,
    verify_static_ast_and_core_immutability,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("crash_boundary", list(VALID_CRASH_BOUNDARIES))
def test_subprocess_crash_91_and_idempotent_recovery_all_10_boundaries(
    crash_boundary: str,
) -> None:
    run_dir = OWN_SCRATCH / f"pytest_crash_{crash_boundary}_{os.getpid()}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    try:
        scenario_type = (
            "DUAL_PENDING_ACK" if crash_boundary == "double_pending_ack" else "STANDARD_24H"
        )
        env = dict(os.environ)
        existing_py = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = os.pathsep.join(
            [str(REPO_ROOT), str(REPO_ROOT / "src"), *([existing_py] if existing_py else [])]
        )
        cmd = [
            sys.executable,
            "-m",
            "scripts.g1g3_offline_ports_r1",
            "--side",
            "LONG",
            "--scenario-type",
            scenario_type,
            "--output",
            str(run_dir),
            "--crash-boundary",
            crash_boundary,
        ]
        proc = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert proc.returncode == 91, (
            f"Expected exit code 91 for {crash_boundary}, got {proc.returncode}: {proc.stderr}"
        )

        # Resume in-process on the exact same run_dir without crash_boundary
        sup = DurableSidecarSupervisor(run_dir)
        receipt = sup.run_scenario(side="LONG", scenario_type=scenario_type)
        assert receipt["sidecar_terminal"] == "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED"
        assert receipt["phase"] == "CLOSED"
        assert receipt["remaining_qty"] == "0.000"
        assert receipt["reserved_notional"] == "0.0000"
        assert receipt["settled_simulated_intent_count"] == 1
        if scenario_type == "STANDARD_24H":
            assert receipt["cash"] == "1000.33834810"
            assert receipt["available_cash"] == "1000.33834810"
            assert receipt["mark_equity"] == "1000.33834810"
            assert receipt["journal_effects"] == 6
    finally:
        if run_dir.exists():
            shutil.rmtree(run_dir)


def test_restart_same_fixture_unchanged_is_pure_idempotent_noop(tmp_path: Path) -> None:
    state_dir = tmp_path / "idempotent_restart_state"
    sup1 = DurableSidecarSupervisor(state_dir, temporary=True)
    r1 = sup1.run_scenario(side="LONG", allow_loopback=False)
    assert r1["cash"] == "1000.33834810"
    assert r1["journal_effects"] == 6
    assert r1["settled_simulated_intent_count"] == 1
    wal_seq_after_first = sup1.seq

    # Second restart on the exact same state_dir
    sup2 = DurableSidecarSupervisor(state_dir, temporary=True)
    r2 = sup2.run_scenario(side="LONG", allow_loopback=False)
    assert r2["cash"] == "1000.33834810"
    assert r2["mark_equity"] == "1000.33834810"
    assert r2["journal_effects"] == 6
    assert r2["settled_simulated_intent_count"] == 1
    assert sup2.seq == wal_seq_after_first


def test_torn_sidecar_wal_tail_quarantined_without_unsafe_replay(tmp_path: Path) -> None:
    state_dir = tmp_path / "torn_sidecar_wal"
    sup1 = DurableSidecarSupervisor(state_dir, temporary=True)
    sup1.run_scenario(side="LONG", allow_loopback=False)

    # Append a torn partial JSON line without trailing newline to sidecar.wal.jsonl
    with (state_dir / "sidecar.wal.jsonl").open("ab") as f:
        f.write(b'{"seq": 99, "previous": "bad", "kind": "TORN"')

    with pytest.raises(SafetyViolation) as exc:
        DurableSidecarSupervisor(state_dir, temporary=True)
    assert exc.value.code == "SIDECAR_WAL_TRUNCATED"

    qfiles = list((state_dir / "quarantine").glob("*.sidecar.json"))
    assert len(qfiles) == 1
    qmeta = json.loads(qfiles[0].read_text(encoding="utf-8"))
    assert qmeta["code"] == "SIDECAR_WAL_TRUNCATED"
    assert qmeta["unsafe_effects_replayed"] is False

    # Also verify mid-file WAL payload/hash-chain corruption is caught and quarantined
    mid_dir = tmp_path / "mid_corrupt_sidecar_wal"
    sup_mid = DurableSidecarSupervisor(mid_dir, temporary=True)
    sup_mid.run_scenario(side="LONG", allow_loopback=False)
    wal_file = mid_dir / "sidecar.wal.jsonl"
    lines = wal_file.read_text(encoding="utf-8").splitlines()
    rec1 = json.loads(lines[1])
    rec1["payload"]["tampered"] = True
    lines[1] = json.dumps(rec1, sort_keys=True)
    wal_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(SafetyViolation) as exc_mid:
        DurableSidecarSupervisor(mid_dir, temporary=True)
    assert exc_mid.value.code == "SIDECAR_WAL_CHAIN_CORRUPT"


def test_torn_g1_wal_tail_quarantined_without_unsafe_replay(tmp_path: Path) -> None:
    state_dir = tmp_path / "torn_g1_wal"
    sup1 = DurableSidecarSupervisor(state_dir, temporary=True)
    sup1.run_scenario(side="LONG", allow_loopback=False)

    # Append torn partial bytes to g1_engine/events.wal.jsonl
    with (state_dir / "g1_engine" / "events.wal.jsonl").open("ab") as f:
        f.write(b'{"seq": 999, "partial": ')

    sup2 = DurableSidecarSupervisor(state_dir, temporary=True)
    with pytest.raises(SafetyViolation) as exc:
        sup2.run_scenario(side="LONG", allow_loopback=False)
    assert exc.value.code == "WAL_TRUNCATED"
    qfiles = list((state_dir / "g1_engine" / "quarantine").glob("*.json"))
    assert len(qfiles) == 1


@pytest.mark.parametrize(
    ("method_name", "expected_prefix"),
    [
        ("submit_order", "NO_ORDER_PORT_FORBIDDEN:SUBMIT_ORDER"),
        ("place_order", "NO_ORDER_PORT_FORBIDDEN:PLACE_ORDER"),
        ("cancel_order", "NO_ORDER_PORT_FORBIDDEN:CANCEL_ORDER"),
        ("modify_order", "NO_ORDER_PORT_FORBIDDEN:MODIFY_ORDER"),
        ("transfer_funds", "NO_ORDER_PORT_FORBIDDEN:TRANSFER_FUNDS"),
        ("create_listen_key", "NO_ACCOUNT_PORT_FORBIDDEN:CREATE_LISTEN_KEY"),
        ("read_account_balance", "NO_ACCOUNT_PORT_FORBIDDEN:READ_ACCOUNT_BALANCE"),
        ("load_signed_client", "NO_ACCOUNT_PORT_FORBIDDEN:LOAD_SIGNED_CLIENT"),
    ],
)
def test_no_order_port_blocks_all_order_and_account_operations(
    method_name: str, expected_prefix: str
) -> None:
    port = NoOrderPort()
    fn = getattr(port, method_name)
    with pytest.raises(SafetyViolation) as exc:
        fn("BTCUSDT", qty="0.02")
    assert exc.value.code == expected_prefix
    tel = port.telemetry()
    assert tel["actual_private_or_network_calls"] == 0
    assert (tel["rejected_order_attempts"] + tel["rejected_account_attempts"]) == 1


@pytest.mark.parametrize(
    ("forbidden_path", "expected_code"),
    [
        ("/root/workspace/project/Quant-agent/data/btc_15m.parquet", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/Quant-agent-sanitized/bars.csv", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/final_holdout/test.json", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/h39_validation/config.json", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/data/forward/stream.jsonl", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/var/quant.db", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/.env", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/.ssh/id_ed25519", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/forward_public_feed_r1/out.json", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/forward_shadow_research_r1/out.json", "PROTECTED_PATH_FORBIDDEN"),
        ("/tmp/btc-g1g3_offline_ports_r1/../secret", "PATH_TRAVERSAL_FORBIDDEN"),
    ],
)
def test_lexical_protected_path_guard_denies_before_stat(
    monkeypatch: pytest.MonkeyPatch, forbidden_path: str, expected_code: str
) -> None:
    def _forbidden_stat(*args: object, **kwargs: object) -> None:
        raise AssertionError("os.stat / Path.stat must NEVER be called on protected paths")

    monkeypatch.setattr(os, "stat", _forbidden_stat)
    monkeypatch.setattr(Path, "stat", _forbidden_stat)

    with pytest.raises(SafetyViolation) as exc:
        guard_lexical_path(forbidden_path)
    assert exc.value.code == expected_code


def test_static_ast_and_c4_core_immutability_verification(tmp_path: Path) -> None:
    report = verify_static_ast_and_core_immutability(REPO_ROOT)
    assert report["core_immutability"]["verified_count"] == 13
    assert report["core_immutability"]["all_matched"] is True
    assert report["forbidden_imports_found"] == 0
    assert report["forbidden_calls_found"] == 0
    assert report["production_src_imported"] is False

    # Verify AST scanner catches forbidden import in a synthetic temp repo
    fake_repo = tmp_path / "fake_repo"
    for rel_path in report["core_immutability"]["files"]:
        src_file = REPO_ROOT / rel_path
        dst_file = fake_repo / rel_path
        dst_file.parent.mkdir(parents=True, exist_ok=True)
        dst_file.write_bytes(src_file.read_bytes())
    bad_pkg = fake_repo / "scripts" / "g1g3_offline_ports_r1"
    bad_pkg.mkdir(parents=True, exist_ok=True)
    (bad_pkg / "bad_mod.py").write_text("import binance\n", encoding="utf-8")
    with pytest.raises(SafetyViolation) as exc:
        verify_static_ast_and_core_immutability(fake_repo)
    assert exc.value.code == "FORBIDDEN_IMPORT:bad_mod.py:binance"


def test_loopback_socket_guard_blocks_external_and_allows_allowlisted_local_server() -> None:
    with FakeLoopbackLLMServer() as llm_srv:
        allowed = {("127.0.0.1", llm_srv.port)}
        with LoopbackSocketGuard(allow_loopback=True, allowed_endpoints=allowed) as guard:
            # Non-loopback IPv4 and domain must be blocked
            for bad_addr in [("8.8.8.8", 443), ("1.1.1.1", 80), ("api.binance.com", 443)]:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    with pytest.raises(SafetyViolation) as exc:
                        s.connect(bad_addr)
                    assert exc.value.code == "NON_LOOPBACK_HOST_FORBIDDEN"
                finally:
                    s.close()

            # Unallowlisted loopback port must be blocked
            s_unlisted = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                with pytest.raises(SafetyViolation) as exc_port:
                    s_unlisted.connect(("127.0.0.1", 65534))
                assert exc_port.value.code == "LOOPBACK_PORT_NOT_ALLOWLISTED"
            finally:
                s_unlisted.close()

            # Direct urllib.request.urlopen must be blocked
            with pytest.raises(SafetyViolation) as exc_url:
                urllib.request.urlopen("http://127.0.0.1:8080")
            assert exc_url.value.code == "URLOPEN_DIRECT_FORBIDDEN"

            # Allowlisted local 127.0.0.1 server succeeds
            s_ok = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s_ok.settimeout(2.0)
                s_ok.connect(("127.0.0.1", llm_srv.port))
            finally:
                s_ok.close()

            assert ("127.0.0.1", llm_srv.port) in guard.allowed_loopback_calls
            assert len(guard.blocked_attempts) == 5


def test_cli_invalid_argument_never_echoes_secret_and_valid_cli_runs_cleanly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    secret_arg = "--unknown-flag=SUPER_SECRET_TOKEN_VALUE_999"
    with pytest.raises(SystemExit) as exc:
        cli_main([secret_arg])
    assert exc.value.code == 3
    captured = capsys.readouterr()
    assert "SUPER_SECRET_TOKEN_VALUE_999" not in captured.out
    assert "SUPER_SECRET_TOKEN_VALUE_999" not in captured.err

    run_dir = OWN_SCRATCH / f"pytest_cli_valid_{os.getpid()}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    try:
        rc = cli_main(["--side", "LONG", "--output", str(run_dir), "--allow-loopback"])
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["sidecar_terminal"] == "G1G3_OFFLINE_PORTS_BOUNDED_VERIFIED"
        assert out["cash"] == "1000.33834810"
    finally:
        if run_dir.exists():
            shutil.rmtree(run_dir)


def test_market_pit_funding_reconnect_and_clock_regression_fail_closed() -> None:
    port = MarketPitPort()
    env1 = make_synthetic_funding_envelope(
        settlement_id="s-regress-1",
        settlement_at_ms=480_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=481_000,
        available_at_ms=481_000,
        sequence=1,
        monotonic_ns=10_000_000,
        connection_epoch=2,
    )
    res = port.ingest_envelope(env1, reference_at_ms=481_000)
    assert res["status"] == "ACCEPTED"

    # 1. Monotonic clock regression on funding channel
    env_mono_regress = make_synthetic_funding_envelope(
        settlement_id="s-regress-2",
        settlement_at_ms=480_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=482_000,
        available_at_ms=482_000,
        sequence=2,
        monotonic_ns=9_000_000,
        connection_epoch=2,
    )
    with pytest.raises(SafetyViolation) as exc_mono:
        port.ingest_envelope(env_mono_regress, reference_at_ms=482_000)
    assert exc_mono.value.code == "MONOTONIC_REGRESSION"

    # 2. Wall clock regression on funding channel
    env_wall_regress = make_synthetic_funding_envelope(
        settlement_id="s-regress-3",
        settlement_at_ms=480_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=480_500,
        available_at_ms=481_500,
        sequence=3,
        monotonic_ns=20_000_000,
        connection_epoch=2,
    )
    with pytest.raises(SafetyViolation) as exc_wall:
        port.ingest_envelope(env_wall_regress, reference_at_ms=482_000)
    assert exc_wall.value.code == "CLOCK_UNCERTAIN"

    # 3. Connection epoch regression
    env_epoch_regress = make_synthetic_funding_envelope(
        settlement_id="s-regress-4",
        settlement_at_ms=480_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=483_000,
        available_at_ms=483_000,
        sequence=4,
        monotonic_ns=30_000_000,
        connection_epoch=1,
    )
    with pytest.raises(SafetyViolation) as exc_epoch:
        port.ingest_envelope(env_epoch_regress, reference_at_ms=483_000)
    assert exc_epoch.value.code == "CONNECTION_EPOCH_REGRESSION"

    # 4. Reason codes include CLOCK_UNCERTAIN
    env_clock_uncertain = make_synthetic_funding_envelope(
        settlement_id="s-regress-5",
        settlement_at_ms=480_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=484_000,
        available_at_ms=484_000,
        sequence=5,
        monotonic_ns=40_000_000,
        connection_epoch=2,
        reason_codes=["CLOCK_UNCERTAIN"],
    )
    with pytest.raises(SafetyViolation) as exc_cu:
        port.ingest_envelope(env_clock_uncertain, reference_at_ms=484_000)
    assert exc_cu.value.code == "CLOCK_UNCERTAIN"


def test_market_pit_funding_same_clock_different_id_collision_fail_closed() -> None:
    port = MarketPitPort()
    env_a = make_synthetic_funding_envelope(
        settlement_id="settlement-primary-alpha",
        settlement_at_ms=720_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=721_000,
        available_at_ms=721_000,
        sequence=1,
        monotonic_ns=1_000_000,
    )
    res = port.ingest_envelope(env_a, reference_at_ms=721_000)
    assert res["status"] == "ACCEPTED"

    # Same settlement timestamp (720_000) with DIFFERENT settlement ID => hard collision
    env_b = make_synthetic_funding_envelope(
        settlement_id="settlement-secondary-beta",
        settlement_at_ms=720_000,
        rate_fraction="0.0001",
        observed_wall_utc_ms=722_000,
        available_at_ms=722_000,
        sequence=2,
        monotonic_ns=2_000_000,
    )
    with pytest.raises(SafetyViolation) as exc:
        port.ingest_envelope(env_b, reference_at_ms=722_000)
    assert exc.value.code == "FUNDING_SETTLEMENT_COLLISION"
