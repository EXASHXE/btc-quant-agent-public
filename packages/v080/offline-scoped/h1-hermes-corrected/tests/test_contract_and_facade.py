"""Contract V1 schema, B2/B4/B5 journal fidelity, evidence classification, and 7-tool facade tests."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from fixtures.build_conformance_journals import build_edge_case_journal
from quant_hermes_feishu_h1.contract import (
    CONTRACT_DOC_SHA256,
    CONTRACT_ID,
    EVIDENCE_SYNTHETIC,
    TYPED_ERROR_CODES,
    V1_ALL_TOOLS,
    V1_READ_ONLY_TOOLS,
    validate_signal_snapshot,
)
from quant_hermes_feishu_h1.facade import PrincipalPolicy, QuantFacadeService
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)

WORKSPACES = Path(__file__).resolve().parents[2]
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
B4_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-public-source-bridge-b4-01/evidence/replay-input/journal.sqlite"
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"


def _make_req(tool: str, args: dict | None = None, *, req_id: str = "req-1", scope: str = "owner_dm") -> dict:
    return {
        "contract_id": CONTRACT_ID,
        "request_id": req_id,
        "tool": tool,
        "args": args or {},
        "principal_id": "hermes_quant_plugin",
        "recipient_scope": scope,
        "deadline_ms": 2000,
    }


def _b2_four_sources() -> list[ApprovedJournalSource]:
    return [
        ApprovedJournalSource("b2_pullback_long", B2_DEMO / "pullback-long/decision.sqlite"),
        ApprovedJournalSource("b2_pullback_short", B2_DEMO / "pullback-short/decision.sqlite"),
        ApprovedJournalSource("b2_early_long", B2_DEMO / "early-long/decision.sqlite"),
        ApprovedJournalSource("b2_early_short", B2_DEMO / "early-short/decision.sqlite"),
    ]


def test_contract_v1_pinned_hash_and_tool_allowlist():
    doc = WORKSPACES.parents[1] / "quant-docs-engineering/docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md"
    assert hashlib.sha256(doc.read_bytes()).hexdigest() == CONTRACT_DOC_SHA256
    assert len(V1_READ_ONLY_TOOLS) == 6
    assert V1_ALL_TOOLS == (
        "list_active_signals",
        "get_signal_detail",
        "get_market_context",
        "get_latest_reprice",
        "get_signal_history",
        "get_strategy_summary",
        "request_reprice",
    )
    assert len(TYPED_ERROR_CODES) == 13


def test_facade_reads_b5_b4_and_all_four_b2_journals_with_decimal_exactness():
    # Verify B5 physical-binding envelope + B2 remaining 3 cases together
    reg_b5_mix = ApprovedJournalRegistry([
        ApprovedJournalSource("b5_pullback_long", B5_JOURNAL),
        ApprovedJournalSource("b2_pullback_short", B2_DEMO / "pullback-short/decision.sqlite"),
        ApprovedJournalSource("b2_early_long", B2_DEMO / "early-long/decision.sqlite"),
        ApprovedJournalSource("b2_early_short", B2_DEMO / "early-short/decision.sqlite"),
    ])
    svc = QuantFacadeService(reg_b5_mix)

    active = svc.handle_request(_make_req("list_active_signals", {"limit": 50}))
    assert active["status"] == "OK"
    assert active["source_evidence_class"] == EVIDENCE_SYNTHETIC
    assert active["data"]["account_context_status"] == "UNAVAILABLE"
    signals = active["data"]["signals"]
    # Latest per episode: b5_pullback_long (EXECUTABLE), early_long (EXECUTABLE), pullback_short (INVALID), early_short (INVALID)
    assert len(signals) == 2
    assert all(s["market_status"] == "EXECUTABLE" for s in signals)
    assert all(s["not_a_real_trade_signal"] is True for s in signals)

    # Check B4 journal independently too
    reg_b4 = ApprovedJournalRegistry([ApprovedJournalSource("b4_pullback_long", B4_JOURNAL)])
    svc_b4 = QuantFacadeService(reg_b4)
    hist_b4 = svc_b4.handle_request(_make_req("get_signal_history", {"limit": 10}))
    assert hist_b4["status"] == "OK"
    assert len(hist_b4["data"]["history"]) == 4

    # Check all 4 B2 cases: WATCH, EXECUTABLE, INVALID, SOURCE_BLOCKED, Decimal strings, reprices
    svc_b2 = QuantFacadeService(ApprovedJournalRegistry(_b2_four_sources()))
    all_hist = svc_b2.handle_request(_make_req("get_signal_history", {"limit": 50}))
    assert all_hist["status"] == "OK"
    items = all_hist["data"]["history"]
    assert len(items) == 16
    statuses = {it["market_status"] for it in items}
    assert statuses == {"WATCH", "EXECUTABLE", "INVALID", "SOURCE_BLOCKED"}

    # Check exact Decimal preservation & zero float on a full EXECUTABLE detail
    exec_item = next(it for it in items if it["market_status"] == "EXECUTABLE")
    detail = svc_b2.handle_request(
        _make_req("get_signal_detail", {"episode_id": exec_item["episode_id"], "card_id": exec_item["card_id"]})
    )
    assert detail["status"] == "OK"
    snap = detail["data"]["snapshot"]
    validate_signal_snapshot(snap)
    assert snap["account_context_status"] == "UNAVAILABLE"
    assert snap["account_overlay"] == "MANUAL_ACCOUNT_CHECK_REQUIRED"
    assert snap["portfolio_exposure_limits"] == "UNKNOWN"
    assert snap["safe_position_size"] == "UNKNOWN"
    assert type(snap["plan"]["entry_low"]) is str
    assert type(snap["plan"]["hard_stop"]) is str
    assert type(snap["plan"]["targets"][0]["net_r"]) is str
    assert "jseq:" in snap["card_version"]

    # Check superseded detection: requesting card_0 (WATCH) when card_3 exists
    early_cards = [it for it in items if it["episode_id"] == exec_item["episode_id"]]
    oldest = min(early_cards, key=lambda x: x["evaluated_at_ms"])
    old_detail = svc_b2.handle_request(
        _make_req("get_signal_detail", {"episode_id": oldest["episode_id"], "card_id": oldest["card_id"]})
    )
    assert old_detail["data"]["is_superseded"] is True
    assert old_detail["data"]["latest_card_id"] != oldest["card_id"]

    # Check get_market_context & get_latest_reprice & get_strategy_summary
    ctx = svc_b2.handle_request(_make_req("get_market_context", {"symbol": "BTCUSDT"}))
    assert ctx["status"] == "OK"
    assert ctx["data"]["account_context_status"] == "UNAVAILABLE"
    assert "quote" in ctx["data"]["market_context"]

    rp = svc_b2.handle_request(_make_req("get_latest_reprice", {"episode_id": exec_item["episode_id"]}))
    assert rp["status"] == "OK"
    assert rp["data"]["status"] == "AVAILABLE"
    assert rp["data"]["latest_reprice"]["reprice"]["requested_delay_minutes"] == 10

    strat = svc_b2.handle_request(_make_req("get_strategy_summary", {}))
    assert strat["status"] == "OK"
    assert strat["data"]["profitability_claim"] is False
    assert strat["data"]["recorded_counts"]["cards"] == 16
    assert strat["data"]["recorded_counts"]["episodes"] == 4


def test_no_setup_not_evaluated_expired_and_reprice_not_available(tmp_path):
    db = build_edge_case_journal(tmp_path / "edge.sqlite")
    svc = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("edge", db)]))

    all_cards = svc.handle_request(_make_req("get_signal_history", {"limit": 50}))["data"]["history"]
    assert {c["market_status"] for c in all_cards} == {"NOT_EVALUATED", "NO_SETUP", "EXECUTABLE"}

    # Check get_latest_reprice returns NOT_AVAILABLE when no reprice recorded
    ep_id = next(c["episode_id"] for c in all_cards if c["episode_id"])
    rp = svc.handle_request(_make_req("get_latest_reprice", {"episode_id": ep_id}))
    assert rp["status"] == "OK"
    assert rp["data"]["status"] == "NOT_AVAILABLE"
    assert rp["data"]["latest_reprice"] is None

    # Check expiry filtering when as_of_ms >= expires_at_ms
    future_ms = 1735689720000 + 7_200_000 + 1
    active_exp = svc.handle_request(_make_req("list_active_signals", {"as_of_ms": future_ms}))
    assert active_exp["data"]["signals"] == []
    assert active_exp["data"]["expired_omitted"] == 1

    detail_exp = svc.handle_request(_make_req("get_signal_detail", {"episode_id": ep_id, "as_of_ms": future_ms}))
    assert detail_exp["data"]["snapshot"]["is_expired"] is True
    assert detail_exp["data"]["snapshot"]["expiry_status"] == "EXPIRED"


def test_forged_genuine_label_and_hypothetical_genuine_and_clock_skew(tmp_path):
    # 1. Forged genuine label on QA origin MUST fail closed even if allow_hypothetical_genuine=True
    forged_db = build_edge_case_journal(
        tmp_path / "forged_qa.sqlite",
        evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
        source_origin="OFFLINE_FIXTURE_V2",
    )
    svc_forged = QuantFacadeService(
        ApprovedJournalRegistry([ApprovedJournalSource("forged", forged_db, allow_hypothetical_genuine=True)])
    )
    resp = svc_forged.handle_request(_make_req("list_active_signals"))
    assert resp["status"] == "ERROR"
    assert resp["error"]["code"] == "INTEGRITY_FAILURE"

    # 2. Missing critical SHA refs on genuine claim MUST fail closed
    missing_refs_db = build_edge_case_journal(
        tmp_path / "missing_refs.sqlite",
        evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
        source_origin="BINANCE_OFFICIAL_PUBLIC",
        include_receipt_hashes=False,
    )
    svc_missing = QuantFacadeService(
        ApprovedJournalRegistry([ApprovedJournalSource("missing", missing_refs_db, allow_hypothetical_genuine=True)])
    )
    resp2 = svc_missing.handle_request(_make_req("list_active_signals"))
    assert resp2["status"] == "ERROR"
    assert resp2["error"]["code"] == "INTEGRITY_FAILURE"

    # 3. Hypothetical valid genuine card fails closed by default (SOURCE_BLOCKED), passes only when explicitly configured
    hyp_db = build_edge_case_journal(
        tmp_path / "hyp_genuine.sqlite",
        evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
        source_origin="BINANCE_OFFICIAL_PUBLIC",
        include_receipt_hashes=True,
    )
    svc_default = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("hyp", hyp_db)]))
    resp3 = svc_default.handle_request(_make_req("list_active_signals"))
    assert resp3["status"] == "ERROR"
    assert resp3["error"]["code"] == "SOURCE_BLOCKED"

    svc_hyp_ok = QuantFacadeService(
        ApprovedJournalRegistry([ApprovedJournalSource("hyp", hyp_db, allow_hypothetical_genuine=True)])
    )
    resp4 = svc_hyp_ok.handle_request(_make_req("list_active_signals"))
    assert resp4["status"] == "OK"
    assert resp4["data"]["signals"][0]["source_evidence_class"] == "PERSONAL_PUBLIC_MARKET_GENUINE"
    assert resp4["data"]["signals"][0]["not_a_real_trade_signal"] is False

    # 4. Missing source timestamps & clock skew -> freshness_state == UNKNOWN
    no_ts_db = build_edge_case_journal(tmp_path / "no_ts.sqlite", omit_source_as_of=True)
    svc_nots = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("nots", no_ts_db)]))
    hist_nots = svc_nots.handle_request(_make_req("get_signal_history", {"limit": 10}))["data"]["history"]
    assert all(h["freshness_state"] == "UNKNOWN" for h in hist_nots)

    # Clock skew (reference_as_of_ms 60 seconds behind source_as_of_ms) -> UNKNOWN
    skew_svc = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)]))
    b5_hist = skew_svc.handle_request(_make_req("get_signal_history", {"limit": 5}))["data"]["history"]
    b5_ep = b5_hist[0]["episode_id"]
    skew_detail = skew_svc.handle_request(
        _make_req("get_signal_detail", {"episode_id": b5_ep, "as_of_ms": 1735689600000})
    )
    assert skew_detail["data"]["snapshot"]["freshness_state"] == "UNKNOWN"


def test_tampered_journal_and_request_reprice_disabled_and_negative_inputs(tmp_path):
    # Tamper payload_sha in an isolated copy -> INTEGRITY_FAILURE
    db = build_edge_case_journal(tmp_path / "tamper.sqlite")
    conn = sqlite3.connect(str(db))
    conn.execute("DROP TRIGGER lock_cards_UPDATE")
    conn.execute("UPDATE cards SET payload_sha = '0000000000000000000000000000000000000000000000000000000000000000'")
    conn.commit()
    conn.close()

    svc_tamp = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("tamp", db)]))
    res_tamp = svc_tamp.handle_request(_make_req("list_active_signals"))
    assert res_tamp["status"] == "ERROR"
    assert res_tamp["error"]["code"] == "INTEGRITY_FAILURE"

    # request_reprice hard-disabled without touching journal
    b5_sha_before = hashlib.sha256(B5_JOURNAL.read_bytes()).hexdigest()
    svc = QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)]))
    rr = svc.handle_request(
        _make_req("request_reprice", {
            "episode_id": "6a6c3316bba3c86c06b9f65de42b6af177be9bd10586ee0e49778f8c8ff42e18",
            "idempotency_key": "key-1",
            "desired_delay_minutes": 5,
            "requested_by": "ou_owner_001",
        })
    )
    assert rr["status"] == "ERROR"
    assert rr["error"]["code"] == "REPRICE_NOT_AUTHORIZED"
    assert hashlib.sha256(B5_JOURNAL.read_bytes()).hexdigest() == b5_sha_before

    # Negative: unknown tool, raw SQL, path traversal, bad symbol, limit > 50, unauthorized principal
    for tool_name in ("terminal", "execute_code", "read_file", "send_message", "place_order"):
        bad_tool = svc.handle_request(_make_req(tool_name))
        assert bad_tool["error"]["code"] == "UNKNOWN_TOOL"

    bad_sql = svc.handle_request(_make_req("get_signal_detail", {"episode_id": "abc; DROP TABLE cards; --"}))
    assert bad_sql["error"]["code"] == "INVALID_ARGUMENT"

    bad_key = svc.handle_request(_make_req("list_active_signals", {"sql": "SELECT * FROM cards"}))
    assert bad_key["error"]["code"] == "INVALID_ARGUMENT"

    bad_sym = svc.handle_request(_make_req("get_market_context", {"symbol": "DOGEUSDT"}))
    assert bad_sym["error"]["code"] == "INVALID_ARGUMENT"

    bad_limit = svc.handle_request(_make_req("list_active_signals", {"limit": 51}))
    assert bad_limit["error"]["code"] == "INVALID_ARGUMENT"

    bad_scope = svc.handle_request(_make_req("list_active_signals", {}, scope="public_group_broadcast"))
    assert bad_scope["error"]["code"] == "UNAUTHORIZED"

    bad_principal = svc.handle_request({
        "contract_id": CONTRACT_ID,
        "request_id": "r-bad-p",
        "tool": "list_active_signals",
        "args": {},
        "principal_id": "attacker_bot",
        "recipient_scope": "owner_dm",
        "deadline_ms": 2000,
    })
    assert bad_principal["error"]["code"] == "UNAUTHORIZED"

    # Rate limit check
    limited_svc = QuantFacadeService(
        ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)]),
        principals=[PrincipalPolicy("hermes_quant_plugin", frozenset({0, 1000, 65534}), frozenset({"owner_dm"}), max_requests_per_minute=2)],
    )
    assert limited_svc.handle_request(_make_req("list_active_signals"))["status"] == "OK"
    assert limited_svc.handle_request(_make_req("list_active_signals"))["status"] == "OK"
    rl = limited_svc.handle_request(_make_req("list_active_signals"))
    assert rl["status"] == "ERROR"
    assert rl["error"]["code"] == "RATE_LIMITED"
