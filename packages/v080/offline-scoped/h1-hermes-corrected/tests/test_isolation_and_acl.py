"""OS-level UDS permissions, SO_PEERCRED cross-UID rejection, and B3 private DB isolation tests."""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest

from fixtures.build_conformance_journals import build_fake_b3_private_db
from quant_hermes_feishu_h1.contract import ContractError
from quant_hermes_feishu_h1.facade import (
    PrincipalPolicy,
    QuantFacadeClient,
    QuantFacadeService,
    QuantUdsServer,
)
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)

WORKSPACES = Path(__file__).resolve().parents[2]
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
B3_WORKSPACE = WORKSPACES / "lt-v080-personal-mvp-account-aware-b3-01"


def test_b3_private_db_refused_and_never_imported(tmp_path):
    # Path token refusal
    fake_b3 = build_fake_b3_private_db(tmp_path / "b3_private_account.sqlite")
    with pytest.raises(ContractError) as exc_info:
        ApprovedJournalRegistry([ApprovedJournalSource("b3_leak", fake_b3)])
    assert exc_info.value.code == "UNAUTHORIZED"

    # Even if filename is innocuous, schema verification refuses non-B2 private tables
    disguised = build_fake_b3_private_db(tmp_path / "innocent_looking.sqlite")
    reg = ApprovedJournalRegistry([ApprovedJournalSource("disguised", disguised)])
    with pytest.raises(ContractError) as exc2:
        reg.load_all_verified_cards()
    assert exc2.value.code == "INTEGRITY_FAILURE"

    # Also locate any real .sqlite under accepted B3 workspace (without reading account contents)
    # and prove our registry refuses it solely on path/boundary guard.
    if B3_WORKSPACE.exists():
        b3_dbs = list(B3_WORKSPACE.rglob("*.sqlite"))
        for b3_db in b3_dbs[:2]:
            with pytest.raises(ContractError) as exc3:
                ApprovedJournalRegistry([ApprovedJournalSource("b3_real_path", b3_db)])
            assert exc3.value.code == "UNAUTHORIZED"

    # Ensure no B3 module is imported by H1 runtime
    assert all(not name.startswith("quant_personal_account_b3") for name in sys.modules)


def _copy_pkg_world_readable(dst_parent: Path) -> Path:
    import quant_hermes_feishu_h1

    src_pkg = Path(quant_hermes_feishu_h1.__file__).resolve().parent
    pkg_root = dst_parent / "public_pkg"
    dst_pkg = pkg_root / "quant_hermes_feishu_h1"
    shutil.copytree(src_pkg, dst_pkg, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.chmod(pkg_root, 0o755)
    for item in [dst_pkg, *dst_pkg.rglob("*")]:
        os.chmod(item, 0o755 if item.is_dir() else 0o644)
    return pkg_root


def test_uds_acls_so_peercred_and_unprivileged_sandbox_isolation(tmp_path):
    audit_path = tmp_path / "audit.jsonl"
    # Use a world-traversable parent under /tmp so uid=65534 tests real socket ACLs / SO_PEERCRED
    # rather than blocked $TMPDIR traversal (umask 077).
    with tempfile.TemporaryDirectory(prefix="h1-uds-acl-", dir="/tmp") as raw_base:
        base = Path(raw_base)
        os.chmod(base, 0o755)
        sock_dir = base / "uds_restricted"
        sock_path = sock_dir / "quant.sock"

        registry = ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)])
        service = QuantFacadeService(registry, audit_log_path=audit_path)
        server = QuantUdsServer(sock_path, service, socket_mode=0o600)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            # 1. Verify restrictive 0700 parent / 0600 socket permissions
            assert stat.S_IMODE(sock_dir.stat().st_mode) == 0o700
            assert stat.S_IMODE(sock_path.stat().st_mode) == 0o600

            # 2. Same-UID authenticated UDS call succeeds and logs secret-free audit
            client = QuantFacadeClient(sock_path)
            resp = client.call_tool("list_active_signals", {"limit": 5})
            assert resp["status"] == "OK"
            assert audit_path.exists()
            assert stat.S_IMODE(audit_path.stat().st_mode) == 0o600
            audit_text = audit_path.read_text(encoding="utf-8")
            assert "app_secret" not in audit_text
            assert f'"peer_uid":{os.getuid()}' in audit_text

            if os.geteuid() != 0:
                pytest.skip("Cross-UID SO_PEERCRED test requires root to drop privileges to nobody")

            # 3. Real OS permission block: unprivileged user nobody (65534) cannot connect to 0700/0600 socket
            probe_code = (
                "import socket; "
                "s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); "
                f"s.connect({str(sock_path)!r})"
            )
            res_acl = subprocess.run(
                ["/usr/bin/python3", "-c", probe_code],
                user=65534,
                group=65534,
                cwd="/tmp",
                capture_output=True,
                text=True,
                check=False,
            )
            assert res_acl.returncode != 0
            assert "PermissionError" in res_acl.stderr
        finally:
            server.shutdown()
            server.server_close()

        # 4. Real kernel SO_PEERCRED rejection: open socket ACLs (0755/0666) so nobody can connect(),
        #    prove kernel SO_PEERCRED still rejects uid=65534 claiming root's principal!
        if os.geteuid() == 0:
            pkg_parent = str(_copy_pkg_world_readable(base))
            open_dir = base / "uds_open_for_peercred"
            open_sock = open_dir / "quant_peercred.sock"
            priv_journal_dir = base / "root_only_journals"
            priv_journal_dir.mkdir(mode=0o700)
            os.chmod(priv_journal_dir, 0o700)
            priv_copy = priv_journal_dir / "journal.sqlite"
            priv_copy.write_bytes(B5_JOURNAL.read_bytes())
            os.chmod(priv_copy, 0o600)

            reg2 = ApprovedJournalRegistry([ApprovedJournalSource("b5_priv", priv_copy)])
            svc2 = QuantFacadeService(
                reg2,
                principals=[
                    PrincipalPolicy("hermes_quant_plugin", frozenset({0}), frozenset({"owner_dm"})),
                    PrincipalPolicy("sandbox_plugin", frozenset({65534}), frozenset({"owner_dm"})),
                ],
            )
            srv2 = QuantUdsServer(open_sock, svc2, socket_mode=0o666)
            os.chmod(open_dir, 0o755)
            t2 = threading.Thread(target=srv2.serve_forever, daemon=True)
            t2.start()
            try:
                # Spoofing root's principal from uid=65534 -> rejected by SO_PEERCRED
                spoof_script = (
                    f"import sys; sys.path.insert(0, {pkg_parent!r}); "
                    "from pathlib import Path; import json; "
                    "from quant_hermes_feishu_h1.facade import QuantFacadeClient; "
                    f"c = QuantFacadeClient(Path({str(open_sock)!r}), principal_id='hermes_quant_plugin'); "
                    "print(json.dumps(c.call_tool('list_active_signals')))"
                )
                r_spoof = subprocess.run(
                    ["/usr/bin/python3", "-c", spoof_script],
                    user=65534,
                    group=65534,
                    cwd="/tmp",
                    capture_output=True,
                    text=True,
                    check=True,
                )
                spoof_resp = json.loads(r_spoof.stdout)
                assert spoof_resp["status"] == "ERROR"
                assert spoof_resp["error"]["code"] == "UNAUTHORIZED"
                assert "65534" in spoof_resp["error"]["message"]

                # Sandbox uid=65534 cannot open SQLite directly (0700/0600 root-owned),
                # yet CAN read verified SignalSnapshots via its authorized principal over UDS!
                sandbox_script = (
                    f"import sys, sqlite3, json; sys.path.insert(0, {pkg_parent!r}); "
                    "from pathlib import Path; "
                    "from quant_hermes_feishu_h1.facade import QuantFacadeClient; "
                    "direct_blocked = False\n"
                    "try:\n"
                    f"    sqlite3.connect('file:{priv_copy}?mode=ro', uri=True).execute('SELECT count(*) FROM cards')\n"
                    "except Exception:\n"
                    "    direct_blocked = True\n"
                    f"c = QuantFacadeClient(Path({str(open_sock)!r}), principal_id='sandbox_plugin'); "
                    "resp = c.call_tool('list_active_signals'); "
                    "print(json.dumps({'direct_blocked': direct_blocked, 'facade_status': resp['status'], 'count': len(resp['data']['signals'])}))"
                )
                r_sb = subprocess.run(
                    ["/usr/bin/python3", "-c", sandbox_script],
                    user=65534,
                    group=65534,
                    cwd="/tmp",
                    capture_output=True,
                    text=True,
                    check=True,
                )
                sb_out = json.loads(r_sb.stdout)
                assert sb_out["direct_blocked"] is True
                assert sb_out["facade_status"] == "OK"
                assert sb_out["count"] == 1
            finally:
                srv2.shutdown()
                srv2.server_close()
