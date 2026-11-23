"""End-to-end local WSL2 CLI, origin classification, Core immutability, and negative security tests."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from quant_personal_decision_b2.adapter import MarketSnapshotAdapter
from quant_personal_decision_b2.engine import Engine
from quant_personal_decision_b2.fixtures import AFTER_TRIGGER, INITIAL, PULLBACK, FabricatedMarket
from quant_personal_decision_b2.journal import Journal
from quant_personal_decision_b2.model import DEFAULT_POLICY
from quant_personal_decision_b2.model import digest as b2_digest

from quant_optional_risk_cli.core_reader import (
    build_card_presentation,
    classify_source_evidence,
    load_verified_core_journal,
)
from quant_optional_risk_cli.models import (
    CoreJournalError,
    LiveCapabilityBlockedError,
    OptionalRiskBoundaryError,
    canonical_sha256,
    install_offline_network_guard,
)

WORKROOT = Path(os.environ["OPT_RISK_WORKROOT"])
CORE_CLI_SITE = Path(os.environ["CORE_CLI_SITE"])
FULL_CLI_SITE = Path(os.environ["FULL_CLI_SITE"])
EVIDENCE_OUT = Path(os.environ["OPT_RISK_EVIDENCE_OUT"])


def _run_cli(site_dir: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LC_ALL": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(site_dir),
    }
    return subprocess.run(
        [sys.executable, "-P", "-m", "quant_optional_risk_cli", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _build_journals(tmp_path: Path) -> dict[str, object]:
    # 1. Standard journal with WATCH, EXECUTABLE, INVALID
    feed = FabricatedMarket(tmp_path / "b1.sqlite", PULLBACK, "LONG")
    feed.scan(INITIAL)
    std_db = tmp_path / "std_decision.sqlite"
    std_journal = Journal(std_db, create=True, policy=DEFAULT_POLICY)
    std_engine = Engine(MarketSnapshotAdapter(feed.path, "fixture"), std_journal)
    c_watch = std_engine.evaluate("BTCUSDT")
    feed.scan(AFTER_TRIGGER)
    c_exec = std_engine.evaluate("BTCUSDT")
    s_inv = feed.scan(AFTER_TRIGGER + 5 * 60_000 + 1000, "invalid")
    c_inv = std_engine.evaluate(
        "BTCUSDT",
        scan=s_inv["scan_id"],
        as_of_ms=s_inv["decision_as_of_venue_ms"],
        reprice_minutes=5,
        episode_id=c_exec["episode_id"],
    )

    # 2. NO_SETUP journal (choppy 4h market produces NO_SETUP / 4H_CHOP or similar non-setup)
    ns_feed = FabricatedMarket(tmp_path / "b1_ns.sqlite", PULLBACK, "LONG", setup="chop")
    ns_scan = ns_feed.scan(INITIAL)
    ns_db = tmp_path / "ns_decision.sqlite"
    ns_journal = Journal(ns_db, create=True, policy=DEFAULT_POLICY)
    ns_engine = Engine(MarketSnapshotAdapter(ns_feed.path, "fixture"), ns_journal)
    c_nosetup = ns_engine.evaluate(
        "BTCUSDT", scan=ns_scan["scan_id"], as_of_ms=ns_scan["decision_as_of_venue_ms"]
    )
    assert c_nosetup["market_status"] == "NO_SETUP"

    # 3. SOURCE_BLOCKED journal (query at as_of_ms earlier than any durable scan -> NO_DURABLE_PUBLICATION_AS_OF)
    blk_feed = FabricatedMarket(tmp_path / "b1_blk.sqlite", PULLBACK, "LONG")
    blk_feed.scan(AFTER_TRIGGER)
    blk_db = tmp_path / "blk_decision.sqlite"
    blk_journal = Journal(blk_db, create=True, policy=DEFAULT_POLICY)
    blk_engine = Engine(MarketSnapshotAdapter(blk_feed.path, "fixture"), blk_journal)
    c_blocked = blk_engine.evaluate("BTCUSDT", as_of_ms=1_700_000_000_000)
    assert c_blocked["market_status"] == "SOURCE_BLOCKED"

    return {
        "std_db": std_db,
        "ns_db": ns_db,
        "blk_db": blk_db,
        "c_watch": c_watch,
        "c_exec": c_exec,
        "c_inv": c_inv,
        "c_nosetup": c_nosetup,
        "c_blocked": c_blocked,
    }


def test_core_only_cli_without_hermes_or_feishu_and_config_flags(tmp_path: Path) -> None:
    # CORE_CLI_SITE must contain zero Hermes, Feishu, B3, or B5 modules.
    installed_pkgs = {p.name for p in CORE_CLI_SITE.iterdir()}
    assert {
        "quant_hermes_feishu_h1",
        "quant_hermes_feishu_h2b",
        "quant_hermes_h3",
        "quant_h4",
        "quant_personal_account_b3",
        "quant_personal_live_public_b5",
        "lark_oapi",
    }.isdisjoint(installed_pkgs)

    cfg_out = _run_cli(CORE_CLI_SITE, ["config-show", "--json"])
    assert cfg_out.returncode == 0
    parsed_cfg = json.loads(cfg_out.stdout)
    assert parsed_cfg["account_risk"]["enabled"] is False
    assert parsed_cfg["layer2_private_user_data"] == "DISABLED"
    assert parsed_cfg["layer3_trade_execution"] == "DISABLED"

    # Restart safety: loading enabled YAML via CLI without --allow-synthetic-opt-in fails exit 2.
    opt_cfg_path = WORKROOT / "configs/synthetic_opt_in_fixture_example.yaml"
    denied_opt = _run_cli(CORE_CLI_SITE, ["config-validate", "--config", str(opt_cfg_path)])
    assert denied_opt.returncode == 2
    assert "AUTO_ENABLE_AFTER_RESTART_FORBIDDEN" in denied_opt.stdout

    # Malformed YAML or wrong version exits 2 cleanly with zero fallback.
    bad_cfg = tmp_path / "bad.yaml"
    bad_cfg.write_text("account_risk: {}\n", encoding="utf-8")
    assert _run_cli(CORE_CLI_SITE, ["config-validate", "--config", str(bad_cfg)]).returncode == 2


def test_local_cli_reads_all_card_states_origin_classes_and_synthetic_opt_in(
    tmp_path: Path,
) -> None:
    data = _build_journals(tmp_path)
    std_db = data["std_db"]
    ns_db = data["ns_db"]
    blk_db = data["blk_db"]
    assert isinstance(std_db, Path) and isinstance(ns_db, Path) and isinstance(blk_db, Path)
    std_sha_before = hashlib.sha256(std_db.read_bytes()).hexdigest()

    # 1. List cards cleanly on Core-only site.
    list_res = _run_cli(CORE_CLI_SITE, ["cards", "--journal", str(std_db), "--json"])
    assert list_res.returncode == 0
    cards_summary = json.loads(list_res.stdout)
    assert len(cards_summary) == 3

    # 2. Human-readable disabled inspection of EXECUTABLE card (shows immutable Core plan & disabled overlay).
    exec_card = data["c_exec"]
    assert isinstance(exec_card, dict)
    human_res = _run_cli(
        CORE_CLI_SITE,
        ["inspect-card", "--journal", str(std_db), "--card", str(exec_card["card_id"])],
    )
    assert human_res.returncode == 0
    for needle in (
        "Symbol: BTCUSDT",
        "Market Status: EXECUTABLE",
        "Data Origin Category: SYNTHETIC_QA_ONLY",
        "Immutable Core Plan: Entry",
        "Overlay Mode: DISABLED",
        "Approved Real Position Size: None",
        "Layer2 PRIVATE_USER_DATA: DISABLED | Layer3 TRADE: DISABLED",
    ):
        assert needle in human_res.stdout

    # 3. Stale freshness vs expired display.
    stale_json = _run_cli(
        CORE_CLI_SITE,
        [
            "inspect-card",
            "--journal",
            str(std_db),
            "--card",
            str(exec_card["card_id"]),
            "--as-of",
            str(int(exec_card["evaluated_ms"]) + 500_000),
            "--json",
        ],
    )
    assert stale_json.returncode == 0
    stale_obj = json.loads(stale_json.stdout)
    assert stale_obj["presentation"]["freshness_state"] == "STALE"

    # 4. Explicit NO_SETUP and SOURCE_BLOCKED outcomes (no plan invented!).
    blk_json = _run_cli(CORE_CLI_SITE, ["inspect-card", "--journal", str(blk_db), "--json"])
    assert blk_json.returncode == 0
    blk_obj = json.loads(blk_json.stdout)
    assert blk_obj["presentation"]["market_status"] == "SOURCE_BLOCKED"
    assert blk_obj["presentation"]["evidence_category"] == "MISSING_DATA"
    assert blk_obj["presentation"]["immutable_core_plan"] is None

    c_ns = data["c_nosetup"]
    assert isinstance(c_ns, dict) and c_ns["market_status"] == "NO_SETUP"
    ns_json = _run_cli(CORE_CLI_SITE, ["inspect-card", "--journal", str(ns_db), "--json"])
    assert ns_json.returncode == 0
    ns_obj = json.loads(ns_json.stdout)
    assert ns_obj["presentation"]["market_status"] == "NO_SETUP"
    assert ns_obj["presentation"]["immutable_core_plan"] is None

    # 5. CLI synthetic fixture opt-in run against EXECUTABLE card & persistent latch DB.
    fix_file = tmp_path / "syn_fix.json"
    fix_file.write_text(
        json.dumps(
            {
                "fixture_evidence_class": "SYNTHETIC_ACCOUNT_FIXTURE_ONLY",
                "risk_day_id": "2025-01-01",
                "equity_currency": "USDT",
                "snapshot_ts_ms": int(exec_card["evaluated_ms"]),
                "margin_mode": "ISOLATED",
                "opening_equity": "10000",
                "current_equity": "10000",
                "external_net_cashflow": "0",
                "realized_pnl": "0",
                "unrealized_pnl": "0",
                "booked_fees": "0",
                "booked_funding": "0",
                "available_margin": "5000",
                "positions_verified": True,
                "open_positions": [],
                "fee_schedule": {"taker_fee_rate": "0.0005", "maker_fee_rate": "0.0002"},
                "offline_gap_unverified": False,
            }
        ),
        encoding="utf-8",
    )
    opt_res = _run_cli(
        CORE_CLI_SITE,
        [
            "inspect-card",
            "--journal",
            str(std_db),
            "--card",
            str(exec_card["card_id"]),
            "--config",
            str(WORKROOT / "configs/synthetic_opt_in_fixture_example.yaml"),
            "--allow-synthetic-opt-in",
            "--synthetic-fixture",
            str(fix_file),
            "--latch-db",
            str(tmp_path / "latch.sqlite"),
            "--as-of",
            str(int(exec_card["evaluated_ms"])),
            "--json",
        ],
    )
    assert opt_res.returncode == 0
    opt_obj = json.loads(opt_res.stdout)
    assert opt_obj["overlay"]["overlay_mode"] == "SYNTHETIC_OPT_IN_MODELED_PASS"
    assert opt_obj["overlay"]["approved_real_position_size"] is None
    assert opt_obj["overlay"]["core_market_status_unchanged"] is True

    # Core journal bytes NEVER changed across all CLI invocations.
    assert hashlib.sha256(std_db.read_bytes()).hexdigest() == std_sha_before


def test_source_origin_classification_integrity_tamper_secret_and_network_guards(
    tmp_path: Path,
) -> None:
    data = _build_journals(tmp_path)
    base_card = data["c_exec"]
    assert isinstance(base_card, dict)

    # 1. Distinguish HISTORICAL_REPLAY and QUALIFIED_GENUINE_SOURCE offline cleanly.
    hist_card = json.loads(json.dumps(base_card))
    hist_card["evidence"] = "HISTORICAL_REPLAY"
    hist_card["source_lane"] = "HISTORICAL_REPLAY"
    hist_card["evaluation_receipt"]["source_origin"] = "HISTORICAL_REPLAY"
    hist_info = classify_source_evidence(hist_card)
    assert hist_info["evidence_category"] == "HISTORICAL_REPLAY"
    assert hist_info["is_genuine_qualified"] is False

    gen_card = json.loads(json.dumps(base_card))
    gen_card["evidence"] = "PERSONAL_PUBLIC_MARKET_GENUINE"
    gen_card["source_lane"] = "PERSONAL_PUBLIC_MARKET_GENUINE"
    gen_card["evaluation_receipt"]["source_origin"] = "PERSONAL_PUBLIC_MARKET_GENUINE"
    gen_card["evaluation_receipt"]["source_publication_sha256"] = "a" * 64
    gen_info = classify_source_evidence(gen_card)
    assert gen_info["evidence_category"] == "QUALIFIED_GENUINE_SOURCE"
    assert gen_info["is_genuine_qualified"] is True

    # Inconsistent origin/lane claim fails closed.
    bad_claim = json.loads(json.dumps(gen_card))
    bad_claim["evaluation_receipt"]["source_origin"] = "SYNTHETIC_QA_ONLY"
    with pytest.raises(CoreJournalError, match="INCONSISTENT_SOURCE_EVIDENCE"):
        classify_source_evidence(bad_claim)

    # 2. Tampered SQLite card triggers CORE_CARD_DIGEST_MISMATCH (after dropping trigger in test copy).
    tampered_db = tmp_path / "tampered.sqlite"
    tampered_db.write_bytes(Path(str(data["std_db"])).read_bytes())
    conn = sqlite3.connect(str(tampered_db))
    conn.execute("DROP TRIGGER lock_cards_UPDATE")
    conn.execute("UPDATE cards SET payload_sha = ? WHERE id = ?", ("0" * 64, base_card["card_id"]))
    conn.commit()
    conn.close()
    with pytest.raises(CoreJournalError, match="CORE_CARD_DIGEST_MISMATCH"):
        load_verified_core_journal(tampered_db)

    # 3. Secret key inside fixture rejected fail-closed before evaluation.
    sec_fix = tmp_path / "secret_fixture.json"
    sec_fix.write_text(
        json.dumps({"fixture_evidence_class": "SYNTHETIC_ACCOUNT_FIXTURE_ONLY", "api_key": "fake"}),
        encoding="utf-8",
    )
    sec_cli = _run_cli(
        CORE_CLI_SITE,
        [
            "inspect-card",
            "--journal",
            str(data["std_db"]),
            "--synthetic-fixture",
            str(sec_fix),
        ],
    )
    assert sec_cli.returncode == 2
    assert "FORBIDDEN_SECRET_OR_LIVE_CREDENTIAL_INPUT" in sec_cli.stdout

    # 4. Network guard denies AF_INET socket attempts in offline runtime.
    install_offline_network_guard()
    import socket

    with pytest.raises(LiveCapabilityBlockedError, match="OFFLINE_NETWORK_DISABLED"):
        socket.create_connection(("127.0.0.1", 80), timeout=0.1)

    EVIDENCE_OUT.mkdir(parents=True, exist_ok=True)
    _ = (OptionalRiskBoundaryError, build_card_presentation, canonical_sha256, b2_digest)
    (EVIDENCE_OUT / "qa-cli-evidence.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "core_only_without_hermes_or_feishu": True,
                "origin_categories_verified": [
                    "SYNTHETIC_QA_ONLY",
                    "HISTORICAL_REPLAY",
                    "MISSING_DATA",
                    "QUALIFIED_GENUINE_SOURCE",
                ],
                "offline_network_guard_verified": True,
                "tampered_journal_rejected": True,
                "secret_input_rejected": True,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def test_b5_enveloped_journal_compatibility_with_disabled_cli(tmp_path: Path) -> None:
    from quant_personal_live_public_b5.offline import run_case

    b5_root = tmp_path / "b5_case"
    case = run_case(b5_root, "trend_pullback-long")
    b5_journal = b5_root / "journal.sqlite"
    sha_before = hashlib.sha256(b5_journal.read_bytes()).hexdigest()

    exec_b5 = case["cards"][1]
    assert exec_b5["market_status"] == "EXECUTABLE"
    cli_res = _run_cli(
        FULL_CLI_SITE,
        ["inspect-card", "--journal", str(b5_journal), "--card", exec_b5["card_id"], "--json"],
    )
    assert cli_res.returncode == 0
    out = json.loads(cli_res.stdout)
    assert out["presentation"]["market_status"] == "EXECUTABLE"
    assert out["presentation"]["evidence_category"] == "SYNTHETIC_QA_ONLY"
    assert out["overlay"]["overlay_mode"] == "DISABLED"
    assert hashlib.sha256(b5_journal.read_bytes()).hexdigest() == sha_before
