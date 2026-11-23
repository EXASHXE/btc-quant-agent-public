"""P0-C01, P0-C02, and P0-C03 regression and cross-language conformance tests."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from fixtures.build_conformance_journals import (
    build_edge_case_journal,
    build_empty_journal,
    build_two_card_and_no_episode_journal,
)
from quant_hermes_feishu_h1.contract import (
    CONTRACT_ID,
    SYNTHETIC_BANNER,
    ContractError,
    canonical_json,
    compute_outbox_event_id,
    validate_signal_snapshot,
)
from quant_hermes_feishu_h1.facade import QuantFacadeService
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)
from quant_hermes_feishu_h1.outbox import DeterministicOutbox

FIX_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = FIX_ROOT.parent
DOCS_ROOT = WORKSPACES.parent.parent / "quant-docs-engineering"
ORACLE_PATH = DOCS_ROOT / "docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json"
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"


def _req(
    tool: str,
    args: dict | None = None,
    *,
    req_id: str = "p0-req-1",
    principal: str = "hermes_quant_plugin",
    scope: str = "owner_dm",
    deadline_ms: int = 2000,
) -> dict:
    return {
        "contract_id": CONTRACT_ID,
        "request_id": req_id,
        "tool": tool,
        "args": args or {},
        "principal_id": principal,
        "recipient_scope": scope,
        "deadline_ms": deadline_ms,
    }


def test_p0_c01_no_episode_diagnostics_excluded_from_active_signals_and_outbox(tmp_path):
    edge_db = build_edge_case_journal(tmp_path / "edge.sqlite")
    reg = ApprovedJournalRegistry([ApprovedJournalSource("edge", edge_db)])
    svc = QuantFacadeService(reg)

    # 1. list_active_signals MUST NEVER emit null-episode cards, even when explicitly filtering NO_SETUP/NOT_EVALUATED.
    active_all = svc.handle_request(_req("list_active_signals", {"limit": 50}))
    assert active_all["status"] == "OK"
    assert active_all["data"]["diagnostic_omitted"] == 2
    assert all(s["episode_id"] is not None for s in active_all["data"]["signals"])

    active_diag_filter = svc.handle_request(
        _req("list_active_signals", {"statuses": ["NO_SETUP", "NOT_EVALUATED"]})
    )
    assert active_diag_filter["status"] == "OK"
    assert active_diag_filter["data"]["signals"] == []
    assert active_diag_filter["data"]["total_matching"] == 0
    assert active_diag_filter["source_evidence_class"] == "UNKNOWN"
    assert active_diag_filter["server_as_of_ms"] is None

    # 2. Internal registry key map must never synthesize 'noep:<card_id>' keys.
    recs, _ = reg.load_all_verified_cards()
    latest_map = reg.latest_records_by_episode(recs)
    assert all(not k.startswith("noep:") for k in latest_map)

    # 3. Null-episode records remain queryable in get_signal_history and get_market_context with diagnostic flags.
    hist = svc.handle_request(_req("get_signal_history", {"limit": 20}))
    assert hist["status"] == "OK"
    items = hist["data"]["history"]
    diag_rows = [it for it in items if it["episode_id"] is None]
    assert len(diag_rows) == 2
    assert {it["market_status"] for it in diag_rows} == {"NO_SETUP", "NOT_EVALUATED"}
    for row in diag_rows:
        assert row["diagnostic_only"] is True
        assert row["not_eligible_for_alert"] is True
        assert row["card_id"]
        assert row["status_reason_codes"]

    ctx_sol = svc.handle_request(_req("get_market_context", {"symbol": "SOLUSDT"}))
    assert ctx_sol["status"] == "OK"
    assert ctx_sol["data"]["episode_id"] is None
    assert ctx_sol["data"]["diagnostic_only"] is True
    assert ctx_sol["data"]["not_eligible_for_alert"] is True
    assert ctx_sol["data"]["market_status"] == "NO_SETUP"

    # 4. get_signal_detail refuses fabricated 'noep:<card_id>' identifiers.
    fake_ep = f"noep:{diag_rows[0]['card_id']}"
    bad_detail = svc.handle_request(_req("get_signal_detail", {"episode_id": fake_ep}))
    assert bad_detail["status"] == "ERROR"
    assert bad_detail["error"]["code"] == "INVALID_ARGUMENT"
    assert bad_detail["source_evidence_class"] == "UNKNOWN"
    assert bad_detail["server_as_of_ms"] is None

    # 5. Outbox MUST refuse null-episode / noep: / NO_SETUP / NOT_EVALUATED without creating SQLite row or event_id.
    outbox_db = tmp_path / "outbox.sqlite"
    outbox = DeterministicOutbox(outbox_db, allowed_recipients=frozenset({"ou_owner001"}))
    for bad_snap in (
        {"episode_id": None, "card_id": diag_rows[0]["card_id"], "card_version": diag_rows[0]["card_version"], "market_status": "NO_SETUP", "source_evidence_class": "SYNTHETIC_QA_ONLY"},
        {"episode_id": fake_ep, "card_id": diag_rows[0]["card_id"], "card_version": diag_rows[0]["card_version"], "market_status": "NO_SETUP", "source_evidence_class": "SYNTHETIC_QA_ONLY"},
        {"episode_id": "abc", "card_id": "f" * 64, "card_version": "jseq:1:a:b", "market_status": "NOT_EVALUATED", "source_evidence_class": "SYNTHETIC_QA_ONLY"},
        {"episode_id": "abc", "card_id": "f" * 64, "card_version": "jseq:1:a:b", "market_status": "WATCH", "source_evidence_class": "SYNTHETIC_QA_ONLY", "diagnostic_only": True, "not_eligible_for_alert": True},
    ):
        with pytest.raises(ContractError) as exc_info:
            outbox.enqueue_snapshot(bad_snap, recipient="ou_owner001")
        assert exc_info.value.code == "INVALID_ARGUMENT"
    conn = sqlite3.connect(str(outbox_db))
    assert conn.execute("SELECT COUNT(*) FROM outbox_events").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM outbox_transitions").fetchone()[0] == 0
    conn.close()


def test_p0_c02_pre_source_errors_and_heterogeneous_empty_aggregates(tmp_path):
    edge_db = build_edge_case_journal(tmp_path / "edge.sqlite")
    gen_db = build_edge_case_journal(
        tmp_path / "genuine.sqlite",
        evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
        source_origin="BINANCE_OFFICIAL_PUBLIC",
        include_receipt_hashes=True,
        base_ts_ms=1735691000000,
    )
    empty_db = build_empty_journal(tmp_path / "empty.sqlite")

    svc = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("edge", edge_db)]))

    # 1. Pre-source errors MUST report source_evidence_class="UNKNOWN" and server_as_of_ms=None (never SYNTHETIC_QA_ONLY).
    pre_source_cases = [
        _req("list_active_signals", {}, principal="unknown_principal"),
        _req("list_active_signals", {}, scope="public_group"),
        _req("terminal", {}),
        _req("get_market_context", {"symbol": "DOGEUSDT"}),
        _req("get_signal_detail", {"episode_id": "bad; DROP TABLE cards"}),
        {
            "contract_id": CONTRACT_ID,
            "request_id": "r-timeout",
            "tool": "list_active_signals",
            "args": {},
            "principal_id": "hermes_quant_plugin",
            "recipient_scope": "owner_dm",
            "deadline_ms": 1,
        },
        _req(
            "request_reprice",
            {
                "episode_id": "abc",
                "idempotency_key": "k1",
                "desired_delay_minutes": 5,
                "requested_by": "ou_owner001",
            },
        ),
    ]
    for bad_req in pre_source_cases:
        resp = svc.handle_request(bad_req)
        assert resp["status"] == "ERROR"
        assert resp["source_evidence_class"] == "UNKNOWN"
        assert resp["server_as_of_ms"] is None
        assert SYNTHETIC_BANNER not in json.dumps(resp, ensure_ascii=False)

    # Missing DB / corrupted DB failures before source verification -> UNKNOWN & null as-of
    missing_path = tmp_path / "nonexistent.sqlite"
    svc_missing = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("miss", missing_path)]))
    err_miss = svc_missing.handle_request(_req("list_active_signals"))
    assert err_miss["status"] == "ERROR"
    assert err_miss["error"]["code"] == "SOURCE_UNAVAILABLE"
    assert err_miss["source_evidence_class"] == "UNKNOWN"
    assert err_miss["server_as_of_ms"] is None

    corrupt_db = build_edge_case_journal(tmp_path / "corrupt.sqlite")
    c_conn = sqlite3.connect(str(corrupt_db))
    c_conn.execute("DROP TRIGGER lock_cards_UPDATE")
    c_conn.execute("UPDATE cards SET payload_sha = 'deadbeef'")
    c_conn.commit()
    c_conn.close()
    svc_corrupt = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("corrupt", corrupt_db)]))
    err_corrupt = svc_corrupt.handle_request(_req("list_active_signals"))
    assert err_corrupt["status"] == "ERROR"
    assert err_corrupt["error"]["code"] == "INTEGRITY_FAILURE"
    assert err_corrupt["source_evidence_class"] == "UNKNOWN"
    assert err_corrupt["server_as_of_ms"] is None

    # 2. SignalSnapshot rejects UNKNOWN evidence class
    with pytest.raises(ContractError) as exc_unk:
        validate_signal_snapshot({
            "episode_id": "ep-1",
            "card_id": "c" * 64,
            "card_version": "jseq:1:a:b",
            "symbol": "BTCUSDT",
            "direction": "LONG",
            "strategy_family": "TREND_PULLBACK",
            "market_status": "WATCH",
            "status_reason_codes": ["TEST"],
            "source_evidence_class": "UNKNOWN",
            "source_origin": "UNKNOWN",
            "source_receipt_sha256": None,
            "source_publication_sha256": None,
            "source_as_of_ms": None,
            "evaluated_at_ms": 1,
            "observed_at_ms": 1,
            "absolute_expiry_ms": None,
            "expiry_status": "EXPIRY_UNKNOWN",
            "freshness_state": "UNKNOWN",
            "account_context_status": "UNAVAILABLE",
            "account_overlay": "MANUAL_ACCOUNT_CHECK_REQUIRED",
            "portfolio_exposure_limits": "UNKNOWN",
            "safe_position_size": "UNKNOWN",
            "plan": None,
            "latest_reprice": None,
            "reasons": ["TEST"],
            "human_action": "",
            "verified_at_ms": 1,
            "contract_version": CONTRACT_ID,
            "source_banner": "UNKNOWN",
            "not_a_real_trade_signal": True,
        })
    assert exc_unk.value.code == "INTEGRITY_FAILURE"

    # 3. Two-source heterogeneous page: envelope source_evidence_class="UNKNOWN", heterogeneous notice, per-item classes intact!
    svc_mixed = QuantFacadeService(
        ApprovedJournalRegistry([
            ApprovedJournalSource("edge", edge_db),
            ApprovedJournalSource("gen", gen_db, allow_hypothetical_genuine=True),
        ])
    )
    mixed_active = svc_mixed.handle_request(_req("list_active_signals", {"limit": 10}))
    assert mixed_active["status"] == "OK"
    assert mixed_active["source_evidence_class"] == "UNKNOWN"
    assert mixed_active["data"]["evidence_aggregation"] == "HETEROGENEOUS_MIXED"
    assert mixed_active["data"]["heterogeneous_evidence"] is True
    assert mixed_active["data"]["affirmative_notification_allowed"] is False
    assert mixed_active["data"]["evidence_classes_present"] == ["PERSONAL_PUBLIC_MARKET_GENUINE", "SYNTHETIC_QA_ONLY"]
    assert SYNTHETIC_BANNER not in mixed_active["data"]["source_banner"]
    assert {s["source_evidence_class"] for s in mixed_active["data"]["signals"]} == {
        "PERSONAL_PUBLIC_MARKET_GENUINE",
        "SYNTHETIC_QA_ONLY",
    }

    mixed_hist = svc_mixed.handle_request(_req("get_signal_history", {"limit": 20}))
    assert mixed_hist["source_evidence_class"] == "UNKNOWN"
    assert mixed_hist["data"]["heterogeneous_evidence"] is True

    mixed_sum = svc_mixed.handle_request(_req("get_strategy_summary"))
    assert mixed_sum["source_evidence_class"] == "UNKNOWN"
    assert mixed_sum["data"]["heterogeneous_evidence"] is True

    # 4. Empty unqualified journal -> UNKNOWN and server_as_of_ms=None (never fabricated clock)
    svc_empty = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("empty", empty_db)]))
    empty_active = svc_empty.handle_request(_req("list_active_signals"))
    assert empty_active["status"] == "OK"
    assert empty_active["source_evidence_class"] == "UNKNOWN"
    assert empty_active["server_as_of_ms"] is None
    assert empty_active["data"]["as_of_ms"] is None
    assert empty_active["data"]["signals"] == []
    assert empty_active["data"]["affirmative_notification_allowed"] is False

    empty_hist = svc_empty.handle_request(_req("get_signal_history"))
    assert empty_hist["source_evidence_class"] == "UNKNOWN"
    assert empty_hist["server_as_of_ms"] is None


def test_p0_c03_controller_goldens_version_invariance_and_node_cross_language(tmp_path):
    # 1. Verify Controller's 7 golden vectors in Python + strict canonical rejection cases
    oracle = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    vectors = {
        "ascii_watch": [CONTRACT_ID, "feishu", "ou_owner001", "abc", "f" * 64, "jseq:7:abcdef01:12345678", "WATCH"],
        "status_changed": [CONTRACT_ID, "feishu", "ou_owner001", "abc", "f" * 64, "jseq:7:abcdef01:12345678", "INVALID"],
        "version_changed": [CONTRACT_ID, "feishu", "ou_owner001", "abc", "f" * 64, "jseq:8:abcdef02:12345678", "WATCH"],
        "recipient_changed": [CONTRACT_ID, "feishu", "ou_owner002", "abc", "f" * 64, "jseq:7:abcdef01:12345678", "WATCH"],
        "real_b2_style": [
            CONTRACT_ID,
            "feishu",
            "ou_owner001",
            "aad84b894b7548da9c0e93d6fca324c0f4ccb4273b0ea7b5cd1c185a5db5bc53",
            "61021d22326d9d85dd8962c790c2745f69580a7c5db183ec6fb973643eac1a00",
            "jseq:13:ae85486779f47312:3ec61364d9d6677c",
            "EXECUTABLE",
        ],
        "utf8_value": {
            "card_version": "jseq:7:abcdef01:12345678",
            "market_status": "WATCH",
            "price": "101.2300",
            "reasons": ["未触发", "复价 +5m"],
            "source_evidence_class": "SYNTHETIC_QA_ONLY",
        },
        "key_order": {"z": "末", "a": "首", "k": {"b": "乙", "a": "甲"}, "ints": [1, 2, 3]},
    }
    for name, obj in vectors.items():
        pre = canonical_json(obj)
        sha = hashlib.sha256(pre.encode("utf-8")).hexdigest()
        assert pre == oracle["data"][name]["preimage"]
        assert sha == oracle["data"][name]["sha256"]
        if isinstance(obj, list):
            eid = compute_outbox_event_id(
                contract_id=obj[0],
                channel=obj[1],
                recipient=obj[2],
                episode_id=obj[3],
                card_id=obj[4],
                card_version=obj[5],
                market_status=obj[6],
            )
            assert eid == oracle["data"][name]["sha256"]

    # Reject invalid / trimmed / non-ASCII / numeric / noep: components in event_id
    for bad_kwargs in (
        {"contract_id": CONTRACT_ID, "channel": "feishu", "recipient": " ou_owner001", "episode_id": "ep", "card_id": "c", "card_version": "jseq:1:a:b", "market_status": "WATCH"},
        {"contract_id": CONTRACT_ID, "channel": "feishu", "recipient": "ou_owner001", "episode_id": "noep:123", "card_id": "c", "card_version": "jseq:1:a:b", "market_status": "NO_SETUP"},
        {"contract_id": CONTRACT_ID, "channel": "feishu", "recipient": "ou_owner001", "episode_id": None, "card_id": "c", "card_version": "jseq:1:a:b", "market_status": "NO_SETUP"},
        {"contract_id": CONTRACT_ID, "channel": "feishu", "recipient": "ou_owner001", "episode_id": "ep", "card_id": "c", "card_version": 7, "market_status": "WATCH"},
        {"contract_id": CONTRACT_ID, "channel": "feishu", "recipient": "用户", "episode_id": "ep", "card_id": "c", "card_version": "jseq:1:a:b", "market_status": "WATCH"},
    ):
        with pytest.raises(ContractError) as exc_id:
            compute_outbox_event_id(**bad_kwargs)
        assert exc_id.value.code == "INVALID_ARGUMENT"

    # 2. Version invariance: unrelated later journal event must NEVER change existing card_version or event_id
    db_before = build_two_card_and_no_episode_journal(tmp_path / "base.sqlite", append_unrelated_later_event=False)
    db_after = build_two_card_and_no_episode_journal(tmp_path / "after.sqlite", append_unrelated_later_event=True)
    svc_before = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b", db_before)]))
    svc_after = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("a", db_after)]))

    hb = svc_before.handle_request(_req("get_signal_history", {"limit": 10}))["data"]["history"]
    ha = svc_after.handle_request(_req("get_signal_history", {"limit": 10}))["data"]["history"]
    assert len(ha) == len(hb) + 1

    wb = next(x for x in hb if x["market_status"] == "WATCH")
    wa = next(x for x in ha if x["market_status"] == "WATCH")
    eb = next(x for x in hb if x["market_status"] == "EXECUTABLE")
    ea = next(x for x in ha if x["market_status"] == "EXECUTABLE")
    assert wb["card_version"] == wa["card_version"]
    assert eb["card_version"] == ea["card_version"]
    assert (
        compute_outbox_event_id(
            contract_id=CONTRACT_ID,
            channel="feishu",
            recipient="ou_owner001",
            episode_id=wb["episode_id"],
            card_id=wb["card_id"],
            card_version=wb["card_version"],
            market_status="WATCH",
        )
        == compute_outbox_event_id(
            contract_id=CONTRACT_ID,
            channel="feishu",
            recipient="ou_owner001",
            episode_id=wa["episode_id"],
            card_id=wa["card_id"],
            card_version=wa["card_version"],
            market_status="WATCH",
        )
    )

    # 3. Export Python pack & verify byte-for-byte with Node 24 TypeScript comparator in isolated dir
    if os.environ.get("H1_SKIP_SUBPROCESS_EXPORT") != "1":
        export_dir = tmp_path / "ref_export"
        subprocess.run(
            [sys.executable, str(FIX_ROOT / "tools/export_reference_goldens.py"), "--output", str(export_dir)],
            check=True,
            capture_output=True,
            text=True,
        )
        cmp_proc = subprocess.run(
            [
                "node",
                str(FIX_ROOT / "tools/compare_goldens.ts"),
                "--export-dir",
                str(export_dir),
                "--oracle",
                str(ORACLE_PATH),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
        node_res = json.loads(cmp_proc.stdout)
        assert node_res["status"] == "CROSS_LANGUAGE_MATCH_OK"
        assert node_res["oracle_cases_matched"] == 7
