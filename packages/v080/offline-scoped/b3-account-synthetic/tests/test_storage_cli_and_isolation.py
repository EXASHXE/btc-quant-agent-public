"""Tests for separate B3 persistence, restrictive ACLs, journal crash recovery, CLI commands, and static isolation."""

from __future__ import annotations

import ast
import json
import os
import sqlite3
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from quant_personal_decision_b2.journal import APP_ID as B2_APP_ID

from quant_personal_account_b3.b2_reader import ReadOnlyB2JournalReader
from quant_personal_account_b3.cli import main as cli_main
from quant_personal_account_b3.models import (
    PRIVATE_CONNECTION_NOT_ACTIVATED,
    SYNTHETIC_BANNER_TEXT,
    AccountB3Error,
    raw_sha256,
)
from quant_personal_account_b3.overlay import build_account_overlay
from quant_personal_account_b3.service import load_synthetic_scenario_into_store
from quant_personal_account_b3.storage import (
    OVERLAY_JOURNAL_APP_ID,
    PRIVATE_STORE_APP_ID,
    OverlayJournal,
    PrivateAccountStore,
)


def test_separate_b3_sqlite_identities_restrictive_permissions_and_append_only_triggers(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    priv_dir = tmp_path / "private_vault"
    priv_db = priv_dir / "private.sqlite"
    ov_db = priv_dir / "overlay.sqlite"

    store = PrivateAccountStore(priv_db, create=True)
    journal = OverlayJournal(ov_db, create=True)

    # Distinct SQLite application IDs (separate from B2 and from each other!).
    assert PRIVATE_STORE_APP_ID != B2_APP_ID
    assert OVERLAY_JOURNAL_APP_ID != B2_APP_ID
    assert PRIVATE_STORE_APP_ID != OVERLAY_JOURNAL_APP_ID

    # Restrictive permissions applied on POSIX/Linux (0o700 dir, 0o600 DB files).
    if os.name == "posix":
        assert stat.S_IMODE(priv_dir.stat().st_mode) == 0o700
        assert stat.S_IMODE(priv_db.stat().st_mode) == 0o600
        assert stat.S_IMODE(ov_db.stat().st_mode) == 0o600

    # Cross-opening wrong DB type fails closed.
    with pytest.raises(AccountB3Error):
        OverlayJournal(priv_db, create=False)
    with pytest.raises(AccountB3Error):
        PrivateAccountStore(ov_db, create=False)
    with pytest.raises(AccountB3Error):
        PrivateAccountStore(Path(b2_pullback_long_journal["journal_path"]), create=False)

    # Publish one overlay and verify UPDATE/DELETE triggers block mutation!
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    snap = load_synthetic_scenario_into_store(
        scenario="one_way_protected",
        private_db=priv_db,
        symbol="BTCUSDT",
        episode_id=card.episode_id,
    )
    overlay = build_account_overlay(card=card, snapshot=snap)
    published = journal.publish(overlay)
    assert published == overlay

    conn = sqlite3.connect(str(ov_db))
    try:
        for sql in (
            "UPDATE overlays SET market_setup_status='HACKED'",
            "DELETE FROM overlays",
            "UPDATE overlay_events SET kind='HACKED'",
            "DELETE FROM overlay_events",
            "UPDATE journal_identity SET evidence_class='REAL'",
            "DELETE FROM journal_identity",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="B3_APPEND_ONLY"):
                conn.execute(sql)
    finally:
        conn.close()

    # Manual association table also blocks UPDATE/DELETE via trigger.
    assert card.episode_id is not None
    store.record_manual_association(
        operator_id="op-lock-1",
        b2_episode_id=card.episode_id,
        b2_card_id=card.card_id,
        symbol="BTCUSDT",
        target_type="ORDER",
        target_id="10001",
        owner_reported_venue_ms=card.as_of_ms + 1000,
    )
    pconn = sqlite3.connect(str(priv_db))
    try:
        with pytest.raises(sqlite3.IntegrityError, match="B3_OWNER_LINK_APPEND_ONLY"):
            pconn.execute("DELETE FROM manual_associations")
        with pytest.raises(sqlite3.IntegrityError, match="B3_OWNER_LINK_APPEND_ONLY"):
            pconn.execute("UPDATE manual_associations SET note='tampered'")
    finally:
        pconn.close()


def test_overlay_journal_crash_before_commit_rollback_and_idempotent_replay(
    tmp_path: Path, b2_pullback_long_journal: dict[str, Any]
) -> None:
    b2_view = ReadOnlyB2JournalReader(b2_pullback_long_journal["journal_path"]).load_and_verify()
    card = b2_view.get_card(card_id=b2_pullback_long_journal["executable_card"]["card_id"])
    snap = load_synthetic_scenario_into_store(
        scenario="one_way_protected",
        private_db=tmp_path / "priv.sqlite",
        symbol="BTCUSDT",
        episode_id=card.episode_id,
    )
    ov1 = build_account_overlay(card=card, snapshot=snap, recorded_wall_ms=1_795_026_000_000)
    journal = OverlayJournal(tmp_path / "ov.sqlite", create=True)

    class SimulatedAbort(RuntimeError):
        pass

    def abort_before_commit() -> None:
        raise SimulatedAbort("crash right before sqlite commit")

    with pytest.raises(SimulatedAbort):
        journal.publish(ov1, before_commit=abort_before_commit)

    # Journal remains completely empty after rollback!
    assert journal.list_overlays() == []
    assert journal.events() == []

    # Retry succeeds atomically; exact second retry is idempotent!
    saved = journal.publish(ov1)
    assert saved == ov1
    again = journal.publish(ov1)
    assert again == ov1
    assert len(journal.list_overlays()) == 1
    assert len(journal.events()) == 1

    replay = journal.replay()
    assert replay["verified"] is True
    assert replay["overlay_count"] == 1
    assert replay["event_count"] == 1
    assert replay["overlays"][0] == ov1


def test_cli_end_to_end_commands_and_disabled_live_connect(
    tmp_path: Path,
    accepted_or_generated_b2_db: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    b2_before_sha = raw_sha256(accepted_or_generated_b2_db.read_bytes())
    b2_view = ReadOnlyB2JournalReader(accepted_or_generated_b2_db).load_and_verify()
    exec_card = next((c for c in b2_view.cards if c.market_status == "EXECUTABLE"), b2_view.cards[-1])

    priv_db = tmp_path / "cli_vault" / "private.sqlite"
    ov_db = tmp_path / "cli_vault" / "overlay.sqlite"

    # 1. live-connect ALWAYS fails closed with PRIVATE_CONNECTION_NOT_ACTIVATED!
    rc_live = cli_main(["live-connect"])
    assert rc_live == 2
    live_out = json.loads(capsys.readouterr().out)
    assert live_out["error"] == PRIVATE_CONNECTION_NOT_ACTIVATED

    # 2. load-snapshot
    rc_load = cli_main(
        [
            "load-snapshot",
            "--scenario",
            "partial_fills_multi_leg",
            "--private-db",
            str(priv_db),
            "--symbol",
            exec_card.symbol,
            "--episode-id",
            exec_card.episode_id or "",
            "--json",
        ]
    )
    assert rc_load == 0
    snap_out = json.loads(capsys.readouterr().out)
    assert snap_out["overall_status"] == "SYNTHETIC_CONNECTED"
    assert snap_out["synthetic_banner"] == SYNTHETIC_BANNER_TEXT

    # 3. show-account & coverage & reconcile
    assert cli_main(["show-account", "--private-db", str(priv_db), "--json"]) == 0
    acct_out = json.loads(capsys.readouterr().out)
    assert acct_out["snapshot_id"] == snap_out["snapshot_id"]

    assert cli_main(["coverage", "--private-db", str(priv_db), "--json"]) == 0
    cov_out = json.loads(capsys.readouterr().out)
    assert cov_out["snapshot_mode"] == "NON_ATOMIC"
    assert len(cov_out["endpoint_coverage"]) == 8

    assert (
        cli_main(
            [
                "reconcile",
                "--private-db",
                str(priv_db),
                "--symbol",
                exec_card.symbol,
                "--b2-journal",
                str(accepted_or_generated_b2_db),
                "--card-id",
                exec_card.card_id,
                "--json",
            ]
        )
        == 0
    )
    rec_out = json.loads(capsys.readouterr().out)
    assert rec_out["reconciliation_cross_check"]["status"] == "RECONCILED"

    # 4. manual-link
    assert exec_card.episode_id is not None
    assert (
        cli_main(
            [
                "manual-link",
                "--private-db",
                str(priv_db),
                "--operator-id",
                "cli-op-1",
                "--episode-id",
                exec_card.episode_id,
                "--card-id",
                exec_card.card_id,
                "--symbol",
                exec_card.symbol,
                "--target-type",
                "ORDER",
                "--target-id",
                "30001",
                "--time",
                str(exec_card.as_of_ms + 50_000),
                "--note",
                "CLI manual link test",
            ]
        )
        == 0
    )
    ml_out = json.loads(capsys.readouterr().out)
    assert ml_out["evidence"] == "OWNER_ENTERED"

    # 5. overlay (with private DB AND public-only fallback)
    assert (
        cli_main(
            [
                "overlay",
                "--b2-journal",
                str(accepted_or_generated_b2_db),
                "--overlay-journal",
                str(ov_db),
                "--private-db",
                str(priv_db),
                "--card-id",
                exec_card.card_id,
                "--json",
            ]
        )
        == 0
    )
    ov_out = json.loads(capsys.readouterr().out)
    assert ov_out["market_setup_status"] == exec_card.market_status
    assert ov_out["signal_trade_match"] == "MATCHED"
    assert ov_out["real_account_connected"] is False

    # Human-readable text rendering via journal-read
    assert cli_main(["journal-read", "--overlay-journal", str(ov_db), "--overlay-id", ov_out["overlay_id"]]) == 0
    text_out = capsys.readouterr().out
    assert SYNTHETIC_BANNER_TEXT in text_out
    assert "DISABLED_UNREACHABLE" in text_out

    # journal-replay verifies full SHA-linked chain
    assert cli_main(["journal-replay", "--overlay-journal", str(ov_db), "--json"]) == 0
    rep_out = json.loads(capsys.readouterr().out)
    assert rep_out["verified"] is True
    assert rep_out["overlay_count"] == 1

    # 6. Public-only fallback via CLI (no --private-db)
    ov_pub_db = tmp_path / "cli_vault" / "overlay_public_only.sqlite"
    assert (
        cli_main(
            [
                "overlay",
                "--b2-journal",
                str(accepted_or_generated_b2_db),
                "--overlay-journal",
                str(ov_pub_db),
                "--card-id",
                exec_card.card_id,
                "--json",
            ]
        )
        == 0
    )
    pub_out = json.loads(capsys.readouterr().out)
    assert pub_out["market_setup_status"] == exec_card.market_status
    assert pub_out["account_context_status"] == "UNAVAILABLE"

    # 7. Full CLI demo
    demo_dir = tmp_path / "cli_demo_out"
    assert cli_main(["demo", "--output", str(demo_dir), "--b2-journal", str(accepted_or_generated_b2_db)]) == 0
    demo_out = json.loads(capsys.readouterr().out)
    assert demo_out["b2_journal_immutable"] is True
    assert demo_out["all_replays_equal"] is True
    assert demo_out["scenario_count"] == 17
    assert demo_out["real_account_connected"] is False

    # Confirm B2 DB file hash remained 100% byte-identical!
    assert raw_sha256(accepted_or_generated_b2_db.read_bytes()) == b2_before_sha


def test_static_ast_zero_network_zero_layer3_zero_legacy_and_zero_secret_store() -> None:
    src_dir = Path(__file__).resolve().parents[1] / "src" / "quant_personal_account_b3"
    py_files = sorted(src_dir.glob("*.py"))
    assert len(py_files) >= 12

    forbidden_roots = {
        "socket",
        "ssl",
        "http",
        "urllib",
        "requests",
        "httpx",
        "aiohttp",
        "websockets",
        "subprocess",
        "ctypes",
        "keyring",
        "win32crypt",
        "btc_quant_agent",
        "quant_personal_public_b1",
    }
    forbidden_calls = {"__import__", "exec", "eval", "import_module"}
    forbidden_layer3_literals = (
        "/fapi/v1/order",
        "/fapi/v1/batchOrders",
        "/fapi/v1/leverage",
        "/fapi/v1/marginType",
        "/fapi/v1/listenKey",
        "/sapi/v1/capital/withdraw",
    )

    for path in py_files:
        source_text = path.read_text(encoding="utf-8")
        # Ensure zero Layer 3 routes appear anywhere in production package code.
        for bad_route in forbidden_layer3_literals:
            assert bad_route not in source_text, f"Forbidden Layer 3 literal {bad_route} found in {path.name}"

        tree = ast.parse(source_text, filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in forbidden_roots, f"Forbidden import {alias.name} in {path.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    root = node.module.split(".")[0]
                    assert root not in forbidden_roots, f"Forbidden import {node.module} in {path.name}"
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    assert node.func.id not in forbidden_calls, f"Forbidden dynamic call {node.func.id} in {path.name}"
                elif isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "import_module", f"Forbidden import_module in {path.name}"
                    # Ensure no env-reading secret access in production source!
                    if node.func.attr in ("environ", "getenv"):
                        raise AssertionError(f"Forbidden env secret lookup in {path.name}")
            elif isinstance(node, ast.Attribute) and node.attr == "environ":
                raise AssertionError(f"Forbidden os.environ access in {path.name}")

    # Verify btc_quant_agent is not imported at runtime either.
    assert not any(k == "btc_quant_agent" or k.startswith("btc_quant_agent.") for k in sys.modules)
