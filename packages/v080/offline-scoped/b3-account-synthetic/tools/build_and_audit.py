"""Build the sealed B3 wheel, run hash-pinned cold & mixed installs, reproduce demo/replay, and verify real OS crash recovery."""

from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence"
PACKAGE = "quant_personal_account_b3"
ENV = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C.UTF-8",
    "PIP_NO_INDEX": "1",
    "PIP_DISABLE_PIP_VERSION_CHECK": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
    "SOURCE_DATE_EPOCH": "1767225600",
}
B1_PIN = "19d89bd87721733dbe05a1298f157e8ea15258fd1d4b981dd5e11e34b05a544f"
B2_PIN = "29cce34ff2b751ef9a9d305d3b7591281a6028c0057e360c9eb666b0840fed64"

DENY_SOCKET = (
    "import sys; "
    "sys.addaudithook(lambda e,a: (_ for _ in ()).throw(RuntimeError(e)) "
    "if e.startswith(('socket.','urllib.','http.client.')) else None); "
)


def execute(*command: str, cwd: Path, env: dict[str, str], expected: int = 0, show: bool = True) -> str:
    print(f"cwd={cwd}\n$ {shlex.join(command)}", flush=True)
    proc = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True, check=False, timeout=90)
    if show and proc.stdout:
        print(proc.stdout, end="", flush=True)
    if proc.stderr:
        print(proc.stderr, end="", flush=True)
    print(f"exit_code={proc.returncode} expected={expected}", flush=True)
    assert proc.returncode == expected, f"Command failed: expected {expected}, got {proc.returncode}"
    return proc.stdout


def run_real_os_crash_recovery(python: str, temp: Path, env: dict[str, str]) -> dict[str, object]:
    """Prove real OS process crash (os._exit(63)) rollback and idempotent restart for pagination and overlay journal."""
    crash_dir = temp / "crash_recovery"
    crash_dir.mkdir()
    priv_db = crash_dir / "private_crash.sqlite"
    ov_db = crash_dir / "overlay_crash.sqlite"
    b2_dir = crash_dir / "b2_src"

    # 1. Generate a small clean B2 journal inside crash_dir.
    b2_code = (
        DENY_SOCKET
        + "from pathlib import Path; "
        + "from quant_personal_decision_b2.cli import demo; "
        + f"demo(Path({str(b2_dir)!r}))"
    )
    execute(python, "-B", "-I", "-c", b2_code, cwd=crash_dir, env=env, show=False)
    b2_db = b2_dir / "pullback-long" / "decision.sqlite"

    # 2. Pagination child crash via os._exit(63) before page 2 commit -> page 1 durable, page 2 rolled back!
    pag_crash_script = "\n".join(
        [
            DENY_SOCKET,
            "import json, os",
            "from pathlib import Path",
            "from quant_personal_account_b3.client import (",
            "    DeterministicFakeClock, DeterministicFakeSigner, FakeCredentialProvider,",
            "    OfflineFixtureTransport, PrivateUserDataClient, TransportResponse,",
            ")",
            "from quant_personal_account_b3.pagination import HistoryPaginator",
            "from quant_personal_account_b3.storage import PrivateAccountStore",
            "as_of = 1735691600000",
            "t0 = as_of - 20000",
            "rows = [",
            "    {'symbol':'BTCUSDT','id':100+i,'orderId':1000+i,'side':'SELL','positionSide':'BOTH',",
            "     'price':'101.0','qty':'0.1','quoteQty':'10.1','realizedPnl':'1.0',",
            "     'commission':'0.005','commissionAsset':'USDT','time':t0+i*1000,'maker':False,'buyer':False}",
            "    for i in range(1, 6)",
            "]",
            "def handler(req):",
            "    q = dict(p.split('=', 1) for p in req.canonical_unsigned_query.split('&'))",
            "    fid = int(q.get('fromId', '0'))",
            "    lim = int(q.get('limit', '2'))",
            "    return TransportResponse(200, json.dumps([r for r in rows if r['id'] >= fid][:lim]).encode())",
            "clk = DeterministicFakeClock(wall_ms=as_of - 500, venue_offset_ms=100)",
            "client = PrivateUserDataClient(",
            "    transport=OfflineFixtureTransport(handler=handler, clock=clk),",
            "    credentials=FakeCredentialProvider(), signer=DeterministicFakeSigner(), clock=clk,",
            ")",
            f"store = PrivateAccountStore(Path({str(priv_db)!r}), create=True)",
            "pag = HistoryPaginator(client=client, store=store)",
            "pag.sync_user_trades(",
            "    symbol='BTCUSDT', start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of,",
            "    page_limit=2, use_from_id=True, initial_from_id=101,",
            "    before_page_commit=lambda p: os._exit(63) if p == 2 else None,",
            ")",
        ]
    )
    execute(python, "-B", "-I", "-c", pag_crash_script, cwd=crash_dir, env=env, expected=63, show=False)

    # Verify mid-crash state and complete restart recovery.
    pag_resume_script = "\n".join(
        [
            DENY_SOCKET,
            "import json",
            "from pathlib import Path",
            "from quant_personal_account_b3.client import (",
            "    DeterministicFakeClock, DeterministicFakeSigner, FakeCredentialProvider,",
            "    OfflineFixtureTransport, PrivateUserDataClient, TransportResponse,",
            ")",
            "from quant_personal_account_b3.pagination import HistoryPaginator",
            "from quant_personal_account_b3.storage import PrivateAccountStore",
            "as_of = 1735691600000",
            "t0 = as_of - 20000",
            "rows = [",
            "    {'symbol':'BTCUSDT','id':100+i,'orderId':1000+i,'side':'SELL','positionSide':'BOTH',",
            "     'price':'101.0','qty':'0.1','quoteQty':'10.1','realizedPnl':'1.0',",
            "     'commission':'0.005','commissionAsset':'USDT','time':t0+i*1000,'maker':False,'buyer':False}",
            "    for i in range(1, 6)",
            "]",
            "def handler(req):",
            "    q = dict(p.split('=', 1) for p in req.canonical_unsigned_query.split('&'))",
            "    fid = int(q.get('fromId', '0'))",
            "    lim = int(q.get('limit', '2'))",
            "    return TransportResponse(200, json.dumps([r for r in rows if r['id'] >= fid][:lim]).encode())",
            f"store = PrivateAccountStore(Path({str(priv_db)!r}), create=False)",
            "before_ids = [f.trade_id for f in store.load_all_fills(symbol='BTCUSDT')]",
            "clk = DeterministicFakeClock(wall_ms=as_of - 500, venue_offset_ms=100)",
            "client = PrivateUserDataClient(",
            "    transport=OfflineFixtureTransport(handler=handler, clock=clk),",
            "    credentials=FakeCredentialProvider(), signer=DeterministicFakeSigner(), clock=clk,",
            ")",
            "res = HistoryPaginator(client=client, store=store).sync_user_trades(",
            "    symbol='BTCUSDT', start_ms=t0, end_ms=as_of, as_of_venue_ms=as_of,",
            "    page_limit=2, use_from_id=True, initial_from_id=101,",
            ")",
            "after_ids = [f.trade_id for f in store.load_all_fills(symbol='BTCUSDT')]",
            "print(json.dumps({'before_resume_ids': before_ids, 'after_resume_ids': after_ids, 'checkpoint_status': res.checkpoint.status}))",
        ]
    )
    pag_rec = json.loads(execute(python, "-B", "-I", "-c", pag_resume_script, cwd=crash_dir, env=env, show=False))
    assert pag_rec["before_resume_ids"] == [101, 102]
    assert pag_rec["after_resume_ids"] == [101, 102, 103, 104, 105]
    assert pag_rec["checkpoint_status"] == "COMPLETE"

    # 3. OverlayJournal child crash via os._exit(63) right before commit -> clean rollback + idempotent restart!
    ov_crash_script = (
        DENY_SOCKET
        + "import os; from pathlib import Path; "
        + "from quant_personal_account_b3.b2_reader import ReadOnlyB2JournalReader; "
        + "from quant_personal_account_b3.overlay import build_account_overlay; "
        + "from quant_personal_account_b3.storage import OverlayJournal; "
        + f"view = ReadOnlyB2JournalReader(Path({str(b2_db)!r})).load_and_verify(); "
        + "card = [c for c in view.cards if c.market_status == 'EXECUTABLE'][0]; "
        + "ov = build_account_overlay(card=card, snapshot=None, recorded_wall_ms=1795026000000); "
        + f"j = OverlayJournal(Path({str(ov_db)!r}), create=True); "
        + "j.publish(ov, before_commit=lambda: os._exit(63))"
    )
    execute(python, "-B", "-I", "-c", ov_crash_script, cwd=crash_dir, env=env, expected=63, show=False)

    ov_resume_script = (
        DENY_SOCKET
        + "import json; from pathlib import Path; "
        + "from quant_personal_account_b3.b2_reader import ReadOnlyB2JournalReader; "
        + "from quant_personal_account_b3.overlay import build_account_overlay; "
        + "from quant_personal_account_b3.storage import OverlayJournal; "
        + f"j = OverlayJournal(Path({str(ov_db)!r}), create=False); "
        + "before_count = len(j.list_overlays()); before_events = len(j.events()); "
        + f"view = ReadOnlyB2JournalReader(Path({str(b2_db)!r})).load_and_verify(); "
        + "card = [c for c in view.cards if c.market_status == 'EXECUTABLE'][0]; "
        + "ov = build_account_overlay(card=card, snapshot=None, recorded_wall_ms=1795026000000); "
        + "pub1 = j.publish(ov); pub2 = j.publish(ov); rep = j.replay(); "
        + "print(json.dumps({'before_restart_overlays': before_count, 'before_restart_events': before_events, 'after_restart_overlays': rep['overlay_count'], 'after_restart_events': rep['event_count'], 'idempotent_equal': pub1 == pub2 == rep['overlays'][0], 'replay_verified': rep['verified']}))"
    )
    ov_rec = json.loads(execute(python, "-B", "-I", "-c", ov_resume_script, cwd=crash_dir, env=env, show=False))
    assert ov_rec["before_restart_overlays"] == 0
    assert ov_rec["before_restart_events"] == 0
    assert ov_rec["after_restart_overlays"] == 1
    assert ov_rec["after_restart_events"] == 1
    assert ov_rec["idempotent_equal"] is True
    assert ov_rec["replay_verified"] is True

    return {
        "child_exit_code": 63,
        "socket_audit_hook_active": True,
        "pagination_crash_recovery": pag_rec,
        "overlay_journal_crash_recovery": ov_rec,
    }


def main() -> None:
    assert {name for _, name in socket.if_nameindex()} == {"lo"}, "Must run in loopback-only isolated network namespace"
    wheel_dir = EVIDENCE / "wheel"
    wheel_dir.mkdir(exist_ok=False)

    b1 = EVIDENCE / "dependencies" / "quant_personal_public_b1-0.8.0b1-py3-none-any.whl"
    b2 = EVIDENCE / "dependencies" / "quant_personal_decision_b2-0.8.0b2-py3-none-any.whl"
    assert hashlib.sha256(b1.read_bytes()).hexdigest() == B1_PIN
    assert hashlib.sha256(b2.read_bytes()).hexdigest() == B2_PIN

    with tempfile.TemporaryDirectory(prefix=".b3-build-", dir=ROOT) as tmp:
        temp = Path(tmp)
        env = {**ENV, "TMPDIR": tmp}
        pkg = temp / "package"
        pkg.mkdir()
        shutil.copyfile(ROOT / "pyproject.toml", pkg / "pyproject.toml")
        shutil.copytree(ROOT / "src", pkg / "src", ignore=shutil.ignore_patterns("__pycache__"))

        execute(
            sys.executable,
            "-B",
            "-m",
            "pip",
            "wheel",
            "--no-index",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            ".",
            cwd=pkg,
            env=env,
        )
        wheel, = wheel_dir.glob("*.whl")
        b3_hash = hashlib.sha256(wheel.read_bytes()).hexdigest()
        with zipfile.ZipFile(wheel) as z:
            inventory = sorted(z.namelist())
            assert all(path.split("/")[0].startswith(PACKAGE) for path in inventory)
            assert not any("quant_personal_decision_b2" in p or "quant_personal_public_b1" in p or "btc_quant_agent" in p for p in inventory)

        requirements = EVIDENCE / "offline_requirements.txt"
        requirements.write_text(
            f"quant-personal-public-b1==0.8.0b1 --hash=sha256:{B1_PIN}\n"
            f"quant-personal-decision-b2==0.8.0b2 --hash=sha256:{B2_PIN}\n"
            f"quant-personal-account-b3==0.8.0b3 --hash=sha256:{b3_hash}\n",
            encoding="utf-8",
        )

        clean = temp / "clean"
        venv.EnvBuilder(with_pip=False).create(clean)
        python = str(clean / "bin/python")
        pip_cmd = (sys.executable, "-B", "-m", "pip", "--python", python, "install", "--no-index")
        execute(
            *pip_cmd,
            "--require-hashes",
            "--find-links",
            str(b1.parent),
            "--find-links",
            str(wheel_dir),
            "-r",
            str(requirements),
            cwd=temp,
            env=env,
        )

        audit_script = str(ROOT / "tools/audit_install.py")
        cold = json.loads(execute(python, "-B", "-I", audit_script, str(b1), str(b2), cwd=temp, env=env, show=False))
        assert not cold["legacy_installed"] and cold["isolated"]
        cold.update(wheel_name=wheel.name, wheel_sha256=b3_hash, wheel_inventory=inventory)
        (EVIDENCE / "cold_install.json").write_text(json.dumps(cold, indent=2) + "\n", encoding="utf-8")

        # Run installed demo under socket-denying audit hook.
        demo_dir = EVIDENCE / "demo"
        demo_code = DENY_SOCKET + f"from {PACKAGE}.cli import main; raise SystemExit(main(['demo','--output',{str(demo_dir)!r}]))"
        demo_summary = json.loads(execute(python, "-B", "-I", "-c", demo_code, cwd=temp, env=env, show=False))
        assert demo_summary["b2_journal_immutable"] is True
        assert demo_summary["all_replays_equal"] is True
        assert demo_summary["scenario_count"] == 17
        assert demo_summary["real_account_connected"] is False

        # Replay one overlay journal from the installed package under socket-denying hook.
        sample_ov_db = demo_dir / "scenarios" / "partial_fills_multi_leg" / "overlay_journal.sqlite"
        replay_args = ["journal-replay", "--overlay-journal", str(sample_ov_db), "--json"]
        replay_code = DENY_SOCKET + f"from {PACKAGE}.cli import main; raise SystemExit(main({replay_args!r}))"
        replay_1 = json.loads(execute(python, "-B", "-I", "-c", replay_code, cwd=temp, env=env, show=False))
        assert replay_1["verified"] is True and replay_1["overlay_count"] == 1

        # Verify real accepted B2 demo DB read-only invariance when adjacent in workspace.
        accepted_b2_demo = ROOT.parent / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo/pullback-long/decision.sqlite"
        accepted_b2_check: dict[str, object] = {"checked": False}
        if accepted_b2_demo.is_file():
            sha_before = hashlib.sha256(accepted_b2_demo.read_bytes()).hexdigest()
            probe_ov = temp / "accepted_b2_probe_overlay.sqlite"
            probe_args = ["overlay", "--b2-journal", str(accepted_b2_demo), "--overlay-journal", str(probe_ov), "--json"]
            probe_code = DENY_SOCKET + f"from {PACKAGE}.cli import main; raise SystemExit(main({probe_args!r}))"
            probe_out = json.loads(execute(python, "-B", "-I", "-c", probe_code, cwd=temp, env=env, show=False))
            sha_after = hashlib.sha256(accepted_b2_demo.read_bytes()).hexdigest()
            assert sha_before == sha_after
            assert probe_out["account_context_status"] == "UNAVAILABLE"
            accepted_b2_check = {
                "checked": True,
                "accepted_b2_db": str(accepted_b2_demo),
                "sha256_before": sha_before,
                "sha256_after": sha_after,
                "byte_identical": True,
                "b2_card_id": probe_out["b2_card_id"],
                "market_setup_status": probe_out["market_setup_status"],
            }

        # Real OS child-process crash recovery proof (os._exit(63)).
        crash_receipt = run_real_os_crash_recovery(python, temp, env)
        crash_receipt["accepted_b2_readonly_probe"] = accepted_b2_check
        (EVIDENCE / "crash_recovery.json").write_text(json.dumps(crash_receipt, indent=2) + "\n", encoding="utf-8")

        # Mixed-install hostile-environment audit (legacy R1 wheel + shadow traps + fake env secrets).
        legacy_wheels = list((ROOT.parent / "lt-v080-sol62-personal-mvp-layer1-public-01/evidence/wheel").glob("*.whl"))
        if legacy_wheels:
            execute(*pip_cmd, "--no-deps", str(legacy_wheels[0]), cwd=temp, env=env)
        shadow = temp / "shadow"
        for ns in (PACKAGE, "quant_personal_decision_b2", "quant_personal_public_b1", "btc_quant_agent"):
            trap = shadow / ns / "__init__.py"
            trap.parent.mkdir(parents=True)
            trap.write_text("raise RuntimeError('shadow module executed')\n", encoding="utf-8")
        hostile = {
            **env,
            "PYTHONPATH": str(shadow),
            "QUANT_LIVE": "1",
            "ENABLE_TRADE": "1",
            "BINANCE_API_KEY": "HOSTILE_ENV_KEY_MUST_NEVER_BE_READ",
            "BINANCE_API_SECRET": "HOSTILE_ENV_SECRET_MUST_NEVER_BE_READ",
            "HTTPS_PROXY": "http://127.0.0.1:9",
        }
        mixed = json.loads(execute(python, "-B", "-I", audit_script, str(b1), str(b2), cwd=shadow, env=hostile, show=False))
        assert mixed["isolated"] and not mixed["legacy_imported"]
        if legacy_wheels:
            assert mixed["legacy_installed"]
        replay_2 = json.loads(execute(python, "-B", "-I", "-c", replay_code, cwd=shadow, env=hostile, show=False))
        assert replay_2 == replay_1
        denied_code = DENY_SOCKET + f"from {PACKAGE}.cli import main; raise SystemExit(main(['live-connect']))"
        denied = json.loads(execute(python, "-B", "-I", "-c", denied_code, cwd=shadow, env=hostile, expected=2, show=False))
        assert denied["error"] == "PRIVATE_CONNECTION_NOT_ACTIVATED"
        assert "HOSTILE_ENV_KEY_MUST_NEVER_BE_READ" not in json.dumps(denied)
        assert "HOSTILE_ENV_SECRET_MUST_NEVER_BE_READ" not in json.dumps(denied)
        mixed.update(
            live_connect_gate=denied,
            replay_with_socket_audit_equal=True,
            hostile_env_ignored=True,
        )
        (EVIDENCE / "mixed_install.json").write_text(json.dumps(mixed, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
