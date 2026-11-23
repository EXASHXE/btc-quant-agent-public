"""Family B tests: read-only Controller golden oracle, H1 reference-export parity, and P0-C01/C02/C03 invariants."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from quant_hermes_feishu_h1.contract import (
    CONTRACT_ID,
    SYNTHETIC_BANNER,
    ContractError,
    canonical_sha256_strict,
    compute_outbox_event_id,
)
from quant_hermes_feishu_h1.facade import QuantFacadeService
from quant_hermes_feishu_h1.journal_reader import ApprovedJournalRegistry, ApprovedJournalSource
from quant_hermes_feishu_h1.renderer import render_signal_alert, render_suppressed_notice

from quant_hermes_feishu_h2b.cli import verify_frozen_goldens
from quant_hermes_feishu_h2b.constants import (
    ACCEPTED_H1_REFERENCE_MANIFEST_SHA256,
)
from quant_hermes_feishu_h2b.outbound_sender import (
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    OutboundBinding,
)

H2B_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = H2B_ROOT.parent
H1_ROOT = WORKSPACES / "lt-v080-gemini-neon-hermes-h1-p0-interop-fix-01"
DOCS_ROOT = WORKSPACES.parent.parent / "quant-docs-engineering"
ORACLE_PATH = DOCS_ROOT / "docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json"
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"

# Dynamically load H1 conformance builder cleanly via importlib path without modifying H1
import importlib.util


def _load_h1_fixtures():
    spec = importlib.util.spec_from_file_location(
        "h1_build_conformance_journals",
        H1_ROOT / "fixtures/build_conformance_journals.py",
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _req(tool: str, args: dict | None = None, *, principal: str = "hermes_quant_plugin", scope: str = "owner_dm"):
    return {
        "contract_id": CONTRACT_ID,
        "request_id": "h2b-b-req",
        "tool": tool,
        "args": args or {},
        "principal_id": principal,
        "recipient_scope": scope,
        "deadline_ms": 2000,
    }


def test_b1_frozen_controller_goldens_and_h1_reference_export_unchanged():
    res = verify_frozen_goldens(h1_root=H1_ROOT, oracle_json=ORACLE_PATH)
    assert res["status"] == "READONLY_GOLDEN_ORACLE_MATCH_OK"
    assert res["oracle_cases_matched"] == 7
    assert res["h1_reference_files_verified"] == 6
    assert res["h1_reference_manifest_sha256"] == ACCEPTED_H1_REFERENCE_MANIFEST_SHA256

    # Check H2-B renderer output matches frozen H1 reference bytes identically
    ref_dir = H1_ROOT / "reference-export"
    rendered_ref = json.loads((ref_dir / "rendered_cards_and_event_ids.json").read_text(encoding="utf-8"))
    envelopes_ref = json.loads((ref_dir / "facade_envelopes.json").read_text(encoding="utf-8"))["cases"]
    exec_snap = envelopes_ref["get_signal_detail_ok"]["envelope"]["data"]["snapshot"]
    rendered = render_signal_alert(exec_snap)
    assert rendered == rendered_ref["cards"][0]["rendered_utf8"]
    assert hashlib.sha256(rendered.encode("utf-8")).hexdigest() == rendered_ref["cards"][0]["rendered_sha256"]
    assert (
        compute_outbox_event_id(
            contract_id=CONTRACT_ID,
            channel="feishu",
            recipient="ou_owner001",
            episode_id=exec_snap["episode_id"],
            card_id=exec_snap["card_id"],
            card_version=exec_snap["card_version"],
            market_status=exec_snap["market_status"],
        )
        == rendered_ref["cards"][0]["event_id"]
    )
    assert canonical_sha256_strict(envelopes_ref["get_signal_detail_ok"]["envelope"]) == envelopes_ref["get_signal_detail_ok"]["sha256"]

    b2_es_svc = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b2_es", B2_DEMO / "early-short/decision.sqlite")]))
    inv_snap = b2_es_svc.handle_request(
        _req(
            "get_signal_detail",
            {
                "episode_id": "2106ced4abdfaeeb3e776b7fa97a58003e0eed8978c65c3098389d80e43ef00a",
                "as_of_ms": 1735700400000,
            },
        )
    )["data"]["snapshot"]
    assert render_suppressed_notice(inv_snap, suppression_reason="NON_AFFIRMATIVE_STATUS:INVALID") == rendered_ref["cards"][1]["rendered_utf8"]


def test_b2_p0_c01_c02_and_expiry_account_overlay_preserved(tmp_path):
    fixtures = _load_h1_fixtures()
    edge_db = fixtures.build_edge_case_journal(tmp_path / "edge.sqlite")
    gen_db = fixtures.build_edge_case_journal(
        tmp_path / "gen.sqlite",
        evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
        source_origin="BINANCE_OFFICIAL_PUBLIC",
        include_receipt_hashes=True,
        base_ts_ms=1735691000000,
    )
    empty_db = fixtures.build_empty_journal(tmp_path / "empty.sqlite")

    # P0-C01: NO_SETUP / NOT_EVALUATED null-episode diagnostics blocked from active signals & outbox
    svc_edge = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("edge", edge_db)]))
    active_diag = svc_edge.handle_request(_req("list_active_signals", {"statuses": ["NO_SETUP", "NOT_EVALUATED"]}))
    assert active_diag["status"] == "OK"
    assert active_diag["data"]["signals"] == []
    assert active_diag["data"]["diagnostic_omitted"] == 2
    assert active_diag["source_evidence_class"] == "UNKNOWN"
    assert active_diag["server_as_of_ms"] is None

    hist = svc_edge.handle_request(_req("get_signal_history", {"limit": 10}))["data"]["history"]
    diag_rows = [r for r in hist if r["episode_id"] is None]
    assert len(diag_rows) == 2
    assert all(r["diagnostic_only"] is True and r["not_eligible_for_alert"] is True for r in diag_rows)

    sender = HermesSingleSenderService(
        state_dir=tmp_path / "sender_state",
        binding=OutboundBinding(
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            owner_open_id="ou_owner001",
            authorized_dm_chat_id="oc_dmowner001",
        ),
        hermes_home=tmp_path / "hermes_home",
        mock_lark_client=H2BMockLarkRecorder(),
    )
    for drow in diag_rows:
        with pytest.raises(ContractError) as exc_d:
            sender.enqueue(drow)
        assert exc_d.value.code == "INVALID_ARGUMENT"

    # P0-C02: pre-source errors -> UNKNOWN, mixed aggregate -> UNKNOWN + HETEROGENEOUS_MIXED
    pre_err = svc_edge.handle_request(_req("list_active_signals", principal="rogue"))
    assert pre_err["status"] == "ERROR"
    assert pre_err["source_evidence_class"] == "UNKNOWN"
    assert pre_err["server_as_of_ms"] is None

    svc_mixed = QuantFacadeService(
        ApprovedJournalRegistry([
            ApprovedJournalSource("edge", edge_db),
            ApprovedJournalSource("gen", gen_db, allow_hypothetical_genuine=True),
        ])
    )
    mixed_resp = svc_mixed.handle_request(_req("list_active_signals", {"limit": 10}))
    assert mixed_resp["source_evidence_class"] == "UNKNOWN"
    assert mixed_resp["data"]["evidence_aggregation"] == "HETEROGENEOUS_MIXED"
    assert mixed_resp["data"]["affirmative_notification_allowed"] is False
    assert SYNTHETIC_BANNER not in mixed_resp["data"]["source_banner"]

    svc_empty = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("empty", empty_db)]))
    empty_resp = svc_empty.handle_request(_req("list_active_signals"))
    assert empty_resp["source_evidence_class"] == "UNKNOWN"
    assert empty_resp["server_as_of_ms"] is None

    # Account overlay remains UNAVAILABLE and synthetic signals stay tagged NOT_A_REAL_TRADE_SIGNAL
    b5_svc = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)]))
    b5_sig = b5_svc.handle_request(_req("list_active_signals"))["data"]["signals"][0]
    b5_det = b5_svc.handle_request(_req("get_signal_detail", {"episode_id": b5_sig["episode_id"]}))["data"]["snapshot"]
    assert b5_det["account_context_status"] == "UNAVAILABLE"
    assert b5_det["safe_position_size"] == "UNKNOWN"
    assert b5_det["not_a_real_trade_signal"] is True
