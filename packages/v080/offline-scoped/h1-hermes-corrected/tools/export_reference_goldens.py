"""Export deterministic P0-C03 canonical V1 reference pack for Pi P2 consumption."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

FIX_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = FIX_ROOT.parent
DOCS_ROOT = WORKSPACES.parent.parent / "quant-docs-engineering"
ORACLE_PATH = DOCS_ROOT / "docs/architecture/V080_QUANT_AGENT_V1_P0_CROSS_LANGUAGE_GOLDENS_20261120.json"
V1_DOC_PATH = DOCS_ROOT / "docs/architecture/V080_QUANT_AGENT_CONTRACT_V1_20261120.md"
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
B2_DEMO = WORKSPACES / "lt-v080-sol62-personal-mvp-market-decision-b2-01/evidence/demo"

ORACLE_SHA256 = "5263e68a1f8c56353873d4f8f7c4342fad175bba416139e366733c819026d713"
V1_DOC_SHA256 = "622677b019120ed18d9bfea057589f7bf923f7f15e17adb3ac59831a0bfd8cc2"

if str(FIX_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(FIX_ROOT / "src"))
if str(FIX_ROOT) not in sys.path:
    sys.path.insert(0, str(FIX_ROOT))

from fixtures.build_conformance_journals import (
    build_edge_case_journal,
    build_empty_journal,
    build_two_card_and_no_episode_journal,
)
from quant_hermes_feishu_h1.contract import (
    CONTRACT_ID,
    SYNTHETIC_BANNER,
    ContractError,
    canonical_json_strict,
    canonical_sha256_strict,
    compute_outbox_event_id,
)
from quant_hermes_feishu_h1.explainer import MockValidExplainer
from quant_hermes_feishu_h1.facade import QuantFacadeService
from quant_hermes_feishu_h1.feishu_chat import FeishuChatService, FeishuInboundEvent
from quant_hermes_feishu_h1.feishu_outbound import MockFeishuTransport, ScriptedOutcome
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)
from quant_hermes_feishu_h1.outbox import DeterministicOutbox
from quant_hermes_feishu_h1.renderer import (
    render_signal_alert,
    render_suppressed_notice,
)


class _InProcessFacadeClient:
    """Deterministic local client shim over QuantFacadeService using fixed timestamps."""

    def __init__(self, service: QuantFacadeService, *, principal_id: str = "hermes_quant_plugin") -> None:
        self.service = service
        self.principal_id = principal_id
        self._seq = 0

    def call_tool(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        recipient_scope: str = "owner_dm",
    ) -> dict[str, Any]:
        self._seq += 1
        return self.service.handle_request({
            "contract_id": CONTRACT_ID,
            "request_id": f"ref-{self._seq:04d}",
            "tool": tool,
            "args": args or {},
            "principal_id": self.principal_id,
            "recipient_scope": recipient_scope,
            "deadline_ms": 2000,
        })


def _write_json(path: Path, payload: Any) -> dict[str, Any]:
    raw = json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    path.write_text(raw, encoding="utf-8", newline="\n")
    data = path.read_bytes()
    return {
        "path": path.name,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def export_reference_pack(output_dir: Path) -> dict[str, Any]:
    """Generate all sealed H1 canonical reference exports into ``output_dir``."""
    v1_sha = hashlib.sha256(V1_DOC_PATH.read_bytes()).hexdigest()
    oracle_sha = hashlib.sha256(ORACLE_PATH.read_bytes()).hexdigest()
    if v1_sha != V1_DOC_SHA256:
        raise SystemExit(f"Contract V1 hash mismatch: {v1_sha}")
    if oracle_sha != ORACLE_SHA256:
        raise SystemExit(f"Controller golden oracle hash mismatch: {oracle_sha}")

    oracle = json.loads(ORACLE_PATH.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    fixed_clock = lambda: 1735701000000

    # 1. Controller 7 golden vectors + negative canonical/identity rejection vectors
    controller_inputs: dict[str, Any] = {
        "ascii_watch": [
            CONTRACT_ID, "feishu", "ou_owner001", "abc", "f" * 64, "jseq:7:abcdef01:12345678", "WATCH",
        ],
        "status_changed": [
            CONTRACT_ID, "feishu", "ou_owner001", "abc", "f" * 64, "jseq:7:abcdef01:12345678", "INVALID",
        ],
        "version_changed": [
            CONTRACT_ID, "feishu", "ou_owner001", "abc", "f" * 64, "jseq:8:abcdef02:12345678", "WATCH",
        ],
        "recipient_changed": [
            CONTRACT_ID, "feishu", "ou_owner002", "abc", "f" * 64, "jseq:7:abcdef01:12345678", "WATCH",
        ],
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
    controller_cases: dict[str, Any] = {}
    for name, inp in controller_inputs.items():
        preimage = canonical_json_strict(inp)
        digest = canonical_sha256_strict(inp)
        if preimage != oracle["data"][name]["preimage"] or digest != oracle["data"][name]["sha256"]:
            raise AssertionError(f"Golden mismatch for {name}")
        controller_cases[name] = {
            "input_obj": inp,
            "preimage": preimage,
            "sha256": digest,
        }

    negative_specs: list[tuple[str, str, Any]] = [
        ("neg_non_ascii_key", "canonical", {"键": "v"}),
        ("neg_float_price", "canonical", {"price": 101.23}),
        ("neg_null_episode_event_id", "event_id", [CONTRACT_ID, "feishu", "ou_owner001", None, "c" * 64, "jseq:1:a:b", "NO_SETUP"]),
        ("neg_noep_event_id", "event_id", [CONTRACT_ID, "feishu", "ou_owner001", "noep:abc", "c" * 64, "jseq:1:a:b", "NO_SETUP"]),
        ("neg_whitespace_recipient", "event_id", [CONTRACT_ID, "feishu", " ou_owner001", "ep1", "c" * 64, "jseq:1:a:b", "WATCH"]),
        ("neg_numeric_version", "event_id", [CONTRACT_ID, "feishu", "ou_owner001", "ep1", "c" * 64, 7, "WATCH"]),
        ("neg_non_ascii_recipient", "event_id", [CONTRACT_ID, "feishu", "用户", "ep1", "c" * 64, "jseq:1:a:b", "WATCH"]),
    ]
    negative_cases: list[dict[str, Any]] = []
    for name, kind, raw_input in negative_specs:
        rejected = False
        try:
            if kind == "event_id":
                compute_outbox_event_id(
                    contract_id=raw_input[0],
                    channel=raw_input[1],
                    recipient=raw_input[2],
                    episode_id=raw_input[3],
                    card_id=raw_input[4],
                    card_version=raw_input[5],
                    market_status=raw_input[6],
                )
            else:
                canonical_json_strict(raw_input)
        except ContractError:
            rejected = True
        if not rejected:
            raise AssertionError(f"Expected ContractError for {name}")
        negative_cases.append({"name": name, "kind": kind, "raw_input": raw_input, "python_rejected": True})

    surrogate_rejected = False
    try:
        canonical_json_strict({"bad": "\ud800"})
    except ContractError:
        surrogate_rejected = True
    if not surrogate_rejected:
        raise AssertionError("Expected ContractError for neg_unpaired_surrogate")
    negative_cases.append(
        {
            "name": "neg_unpaired_surrogate",
            "kind": "canonical_surrogate_json_escape",
            "raw_input": {"raw_json_escape": '{"bad":"\\ud800"}'},
            "python_rejected": True,
        }
    )

    with tempfile.TemporaryDirectory(prefix="h1-ref-export-") as td:
        tmp = Path(td)
        db_base = build_two_card_and_no_episode_journal(tmp / "two_card_base.sqlite", append_unrelated_later_event=False)
        db_replay = build_two_card_and_no_episode_journal(tmp / "two_card_after.sqlite", append_unrelated_later_event=True)
        db_edge = build_edge_case_journal(tmp / "edge.sqlite")
        db_gen = build_edge_case_journal(
            tmp / "genuine.sqlite",
            evidence="PERSONAL_PUBLIC_MARKET_GENUINE",
            source_origin="BINANCE_OFFICIAL_PUBLIC",
            include_receipt_hashes=True,
            base_ts_ms=1735691000000,
        )
        db_empty = build_empty_journal(tmp / "empty.sqlite")
        outbox_db = tmp / "outbox_trace.sqlite"

        # 2. Version invariance before vs after unrelated later event
        svc_base = QuantFacadeService(
            ApprovedJournalRegistry([ApprovedJournalSource("two_base", db_base)], clock_ms_fn=fixed_clock),
            clock_ms_fn=fixed_clock,
        )
        svc_replay = QuantFacadeService(
            ApprovedJournalRegistry([ApprovedJournalSource("two_replay", db_replay)], clock_ms_fn=fixed_clock),
            clock_ms_fn=fixed_clock,
        )
        hist_base = svc_base.handle_request({
            "contract_id": CONTRACT_ID, "request_id": "v-b1", "tool": "get_signal_history",
            "args": {"limit": 10}, "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
        })
        hist_replay = svc_replay.handle_request({
            "contract_id": CONTRACT_ID, "request_id": "v-r1", "tool": "get_signal_history",
            "args": {"limit": 10}, "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
        })
        watch_b = next(h for h in hist_base["data"]["history"] if h["market_status"] == "WATCH")
        exec_b = next(h for h in hist_base["data"]["history"] if h["market_status"] == "EXECUTABLE")
        watch_r = next(h for h in hist_replay["data"]["history"] if h["market_status"] == "WATCH")
        exec_r = next(h for h in hist_replay["data"]["history"] if h["market_status"] == "EXECUTABLE")
        watch_eid_b = compute_outbox_event_id(
            contract_id=CONTRACT_ID, channel="feishu", recipient="ou_owner001",
            episode_id=watch_b["episode_id"], card_id=watch_b["card_id"],
            card_version=watch_b["card_version"], market_status="WATCH",
        )
        watch_eid_r = compute_outbox_event_id(
            contract_id=CONTRACT_ID, channel="feishu", recipient="ou_owner001",
            episode_id=watch_r["episode_id"], card_id=watch_r["card_id"],
            card_version=watch_r["card_version"], market_status="WATCH",
        )
        version_replay = {
            "version_rule": "jseq:<pub_seq>:<pub_sha[:16]>:<source_pub_sha[:16]|NONE>",
            "episode_id": exec_b["episode_id"],
            "as_of_ms_exec": exec_b["evaluated_at_ms"],
            "card_and_reprice_version_pairing": {
                "exec_card_id": exec_b["card_id"],
                "exec_card_version": exec_b["card_version"],
                "reprice": exec_b["reprice"],
            },
            "before_unrelated_event": {
                "watch_card_version": watch_b["card_version"],
                "exec_card_version": exec_b["card_version"],
                "watch_event_id": watch_eid_b,
            },
            "after_unrelated_event": {
                "watch_card_version": watch_r["card_version"],
                "exec_card_version": exec_r["card_version"],
                "watch_event_id": watch_eid_r,
            },
        }

        # 3. Canonical Facade Envelopes (7 tools + P0 negatives + heterogeneous/empty/noep)
        svc_b5_b2 = QuantFacadeService(
            ApprovedJournalRegistry([
                ApprovedJournalSource("b5", B5_JOURNAL),
                ApprovedJournalSource("b2_es", B2_DEMO / "early-short/decision.sqlite"),
            ], clock_ms_fn=fixed_clock),
            clock_ms_fn=fixed_clock,
        )
        svc_mixed = QuantFacadeService(
            ApprovedJournalRegistry([
                ApprovedJournalSource("edge", db_edge),
                ApprovedJournalSource("gen", db_gen, allow_hypothetical_genuine=True),
            ], clock_ms_fn=fixed_clock),
            clock_ms_fn=fixed_clock,
        )
        svc_empty = QuantFacadeService(
            ApprovedJournalRegistry([ApprovedJournalSource("empty", db_empty)]),
            clock_ms_fn=fixed_clock,
        )
        ep_two = exec_b["episode_id"]
        noep_row = next(h for h in hist_base["data"]["history"] if h["episode_id"] is None)

        envelope_raw: dict[str, dict[str, Any]] = {
            "list_active_signals_ok": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-01", "tool": "list_active_signals",
                "args": {"limit": 1, "statuses": ["EXECUTABLE", "WATCH", "NO_SETUP"]},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "list_active_signals_only_no_setup_excluded": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-02", "tool": "list_active_signals",
                "args": {"statuses": ["NO_SETUP", "NOT_EVALUATED"]},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "get_signal_detail_ok": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-03", "tool": "get_signal_detail",
                "args": {"episode_id": ep_two, "as_of_ms": exec_b["evaluated_at_ms"]},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "get_signal_detail_noep_rejected": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-04", "tool": "get_signal_detail",
                "args": {"episode_id": f"noep:{noep_row['card_id']}"},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "get_market_context_diagnostic_eth": svc_base.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-05", "tool": "get_market_context",
                "args": {"symbol": "ETHUSDT"},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "get_latest_reprice_available": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-06", "tool": "get_latest_reprice",
                "args": {"episode_id": ep_two},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "get_signal_history_page_1": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-07", "tool": "get_signal_history",
                "args": {"limit": 2},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "get_strategy_summary_ok": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-08", "tool": "get_strategy_summary",
                "args": {},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "request_reprice_disabled": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-09", "tool": "request_reprice",
                "args": {"episode_id": ep_two, "idempotency_key": "idem-1", "desired_delay_minutes": 5, "requested_by": "ou_owner001"},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "error_pre_source_unauthorized": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-10", "tool": "list_active_signals",
                "args": {}, "principal_id": "intruder", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "error_pre_source_unknown_tool": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-11", "tool": "terminal",
                "args": {}, "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "error_pre_source_invalid_arg": svc_replay.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-12", "tool": "get_market_context",
                "args": {"symbol": "DOGEUSDT"}, "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "mixed_heterogeneous_active_signals": svc_mixed.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-13", "tool": "list_active_signals",
                "args": {"limit": 10}, "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "empty_journal_active_signals": svc_empty.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-14", "tool": "list_active_signals",
                "args": {}, "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
            "b5_ordered_reasons_and_clock_skew": svc_b5_b2.handle_request({
                "contract_id": CONTRACT_ID, "request_id": "env-15", "tool": "get_signal_detail",
                "args": {"episode_id": "6a6c3316bba3c86c06b9f65de42b6af177be9bd10586ee0e49778f8c8ff42e18", "as_of_ms": 1735689600000},
                "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
            }),
        }
        envelopes_out: dict[str, Any] = {}
        for k, env_obj in envelope_raw.items():
            envelopes_out[k] = {
                "envelope": env_obj,
                "canonical_preimage": canonical_json_strict(env_obj),
                "sha256": canonical_sha256_strict(env_obj),
            }

        # 4. Deterministic rendering bytes + event_ids + duplicate IDs
        exec_snap = envelope_raw["get_signal_detail_ok"]["data"]["snapshot"]
        b2_es_detail = svc_b5_b2.handle_request({
            "contract_id": CONTRACT_ID, "request_id": "ren-1", "tool": "get_signal_detail",
            "args": {"episode_id": "2106ced4abdfaeeb3e776b7fa97a58003e0eed8978c65c3098389d80e43ef00a"},
            "principal_id": "hermes_quant_plugin", "recipient_scope": "owner_dm", "deadline_ms": 2000,
        })["data"]["snapshot"]
        render_exec = render_signal_alert(exec_snap)
        render_sup = render_suppressed_notice(b2_es_detail, suppression_reason="NON_AFFIRMATIVE_STATUS:INVALID")
        render_diag = render_signal_alert(svc_base._registry.project_diagnostic(  # type: ignore[arg-type]
            next(r for r in svc_base._registry.load_all_verified_cards()[0] if r.episode_id is None),
            reference_as_of_ms=exec_snap["evaluated_at_ms"],
            verified_at_ms=fixed_clock(),
        ))
        eid_comps = [
            CONTRACT_ID, "feishu", "ou_owner001", exec_snap["episode_id"],
            exec_snap["card_id"], exec_snap["card_version"], exec_snap["market_status"],
        ]
        rendered_cards_pack = {
            "source_banner_constant": SYNTHETIC_BANNER,
            "cards": [
                {
                    "label": "executable_synthetic_alert",
                    "rendered_utf8": render_exec,
                    "rendered_sha256": hashlib.sha256(render_exec.encode("utf-8")).hexdigest(),
                    "event_id_components": eid_comps,
                    "event_id": compute_outbox_event_id(
                        contract_id=eid_comps[0], channel=eid_comps[1], recipient=eid_comps[2],
                        episode_id=eid_comps[3], card_id=eid_comps[4], card_version=eid_comps[5],
                        market_status=eid_comps[6],
                    ),
                },
                {
                    "label": "suppressed_invalid_notice",
                    "rendered_utf8": render_sup,
                    "rendered_sha256": hashlib.sha256(render_sup.encode("utf-8")).hexdigest(),
                    "event_id_components": None,
                    "event_id": None,
                },
                {
                    "label": "diagnostic_no_setup_render_only",
                    "rendered_utf8": render_diag,
                    "rendered_sha256": hashlib.sha256(render_diag.encode("utf-8")).hexdigest(),
                    "event_id_components": None,
                    "event_id": None,
                },
            ],
        }

        # 5. Deterministic Mock Feishu Private DM Transcripts
        inproc_client = _InProcessFacadeClient(svc_replay)
        chat = FeishuChatService(
            facade_client=inproc_client,  # type: ignore[arg-type]
            allowed_owner_open_ids=frozenset({"ou_owner001"}),
            owner_chat_bindings={"ou_owner001": "oc_dmowner001"},
            explanation_provider=MockValidExplainer(),
        )
        t_chat = 1735700500000
        chat_inputs = [
            ("dm-1", "ou_owner001", "oc_dmowner001", "p2p", "当前机会"),
            ("dm-2", "ou_owner001", "oc_dmowner001", "p2p", f"查看 {ep_two}"),
            ("dm-3", "ou_owner001", "oc_dmowner001", "p2p", "为什么 WATCH"),
            ("dm-4", "ou_owner001", "oc_dmowner001", "p2p", f"复价 {ep_two}"),
            ("dm-5", "ou_owner001", "oc_dmowner001", "p2p", "最近信号"),
            ("dm-6", "ou_owner001", "oc_dmowner001", "p2p", "策略说明"),
            ("dm-7", "ou_intruder", "oc_dmowner001", "p2p", "当前机会"),
            ("dm-8", "ou_owner001", "oc_dmowner001", "p2p", "读取 b3_private"),
        ]
        transcripts: list[dict[str, Any]] = []
        for idx, (mid, uid, cid, ctype, text) in enumerate(chat_inputs, start=1):
            ev = FeishuInboundEvent(mid, cid, ctype, uid, "user", text, t_chat + idx)
            rep = chat.handle_inbound(ev, now_ms=t_chat + idx + 5, as_of_ms=exec_snap["evaluated_at_ms"])
            transcripts.append({
                "input": text,
                "sender": uid,
                "accepted": rep["accepted"],
                "intent": rep.get("intent"),
                "error_code": rep.get("error_code"),
                "reply_text": rep["reply_text"],
            })

        # 6. Outbox Crash -> UNKNOWN_DELIVERY -> Delayed PROVIDER_ACK trace
        worker_client = _InProcessFacadeClient(svc_replay)
        claim_tokens = iter(["00000000000000000000000000000001", "00000000000000000000000000000002"])
        outbox = DeterministicOutbox(
            outbox_db,
            allowed_recipients=frozenset({"ou_owner001"}),
            lease_ms=1000,
            clock_ms_fn=fixed_clock,
            claim_token_fn=lambda: next(claim_tokens),
        )
        enq = outbox.enqueue_snapshot(exec_snap, recipient="ou_owner001", now_ms=exec_snap["evaluated_at_ms"])
        dedup = outbox.enqueue_snapshot(exec_snap, recipient="ou_owner001", now_ms=exec_snap["evaluated_at_ms"] + 1)
        claim_c = outbox.claim_next(worker_id="trace-w1", now_ms=exec_snap["evaluated_at_ms"] + 2)
        crash_res = outbox.process_claimed(
            claim_c,
            facade_client=worker_client,  # type: ignore[arg-type]
            transport=MockFeishuTransport([ScriptedOutcome("PROVIDER_ACK", message_id="om_trace_lost")]),
            worker_id="trace-w1",
            now_ms=exec_snap["evaluated_at_ms"] + 3,
            simulate_crash_after_send=True,
        )
        reclaimed = outbox.reclaim_expired_leases(now_ms=exec_snap["evaluated_at_ms"] + 2000)
        reconciled = outbox.reconcile_delayed_ack(
            event_id=enq["event_id"],
            provider_message_id="om_trace_reconciled_001",
            ack_at_ms=exec_snap["evaluated_at_ms"] + 2500,
        )
        transitions = outbox.get_transitions(enq["event_id"])
        outbox_trace = {
            "enqueue": enq,
            "duplicate_enqueue": dedup,
            "simulated_crash": crash_res,
            "reclaimed_event_ids": reclaimed,
            "reconciled": {k: v for k, v in reconciled.items() if k != "rendered_text"},
            "transitions": transitions,
        }

    manifest_files: list[dict[str, Any]] = [
        _write_json(
            output_dir / "controller_seven_goldens_verification.json",
            {"oracle_sha256": oracle_sha, "controller_cases": controller_cases, "negative_cases": negative_cases},
        ),
        _write_json(output_dir / "version_invariance_replay.json", version_replay),
        _write_json(output_dir / "facade_envelopes.json", {"cases": envelopes_out}),
        _write_json(output_dir / "rendered_cards_and_event_ids.json", rendered_cards_pack),
        _write_json(output_dir / "feishu_dm_transcripts.json", {"transcripts": transcripts}),
        _write_json(output_dir / "outbox_crash_ack_trace.json", outbox_trace),
    ]
    manifest_payload = {
        "schema": "H1_P0_CANONICAL_REFERENCE_EXPORT_MANIFEST_V1",
        "contract_id": CONTRACT_ID,
        "contract_doc_sha256": V1_DOC_SHA256,
        "controller_oracle_sha256": ORACLE_SHA256,
        "files": manifest_files,
    }
    _write_json(output_dir / "REFERENCE_EXPORT_MANIFEST.json", manifest_payload)
    return manifest_payload


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=FIX_ROOT / "reference-export")
    args = parser.parse_args()
    manifest = export_reference_pack(args.output.resolve())
    print(f"EXPORTED {len(manifest['files'])} reference files to {args.output}")


if __name__ == "__main__":
    main()
