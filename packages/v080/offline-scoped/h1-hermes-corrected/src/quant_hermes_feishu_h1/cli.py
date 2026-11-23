"""CLI entrypoint for QUANT v0.8.0 H1 offline facade, demo, and fail-closed live gate."""

from __future__ import annotations

import argparse
import json
import threading
import time
from pathlib import Path
from typing import Any

from .contract import CONTRACT_DOC_SHA256, CONTRACT_ID, V1_ALL_TOOLS, canonical_json
from .explainer import (
    MockFailingExplainer,
    MockHallucinatingExplainer,
    MockValidExplainer,
)
from .facade import QuantFacadeClient, QuantFacadeService, QuantUdsServer
from .feishu_chat import FeishuChatService, FeishuInboundEvent
from .feishu_outbound import MockFeishuTransport, ScriptedOutcome
from .journal_reader import ApprovedJournalRegistry, ApprovedJournalSource
from .metrics import AlertTimelineMeasurement, LocalPerformanceReport
from .outbox import DeterministicOutbox

LIVE_CAPABILITY_EXIT_CODE = 3
LIVE_CAPABILITY_ERROR = "LIVE_CAPABILITY_NOT_AUTHORIZED"


def run_offline_demo(
    *,
    journal_paths: list[tuple[str, Path]],
    output_dir: Path,
) -> dict[str, Any]:
    """Run complete offline H1 facade + outbox + renderer + chat + explainer + telemetry demo."""
    import tempfile

    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    sock_tmpdir = tempfile.TemporaryDirectory(prefix="h1_demo_sock_")
    socket_path = Path(sock_tmpdir.name) / "quant_v1.sock"
    audit_path = output_dir / "facade_audit.jsonl"
    outbox_db = output_dir / "outbox.sqlite"
    if outbox_db.exists():
        outbox_db.unlink()
    if audit_path.exists():
        audit_path.unlink()

    sources = [ApprovedJournalSource(source_id=sid, path=p) for sid, p in journal_paths]
    registry = ApprovedJournalRegistry(sources)
    service = QuantFacadeService(registry, audit_log_path=audit_path)
    server = QuantUdsServer(socket_path, service)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        plugin_client = QuantFacadeClient(socket_path, principal_id="hermes_quant_plugin", recipient_scope="owner_dm")
        worker_client = QuantFacadeClient(socket_path, principal_id="hermes_quant_plugin", recipient_scope="outbox_worker")

        # 1. Tool survey over UDS
        t0 = time.monotonic_ns()
        active_resp = plugin_client.call_tool("list_active_signals", {"limit": 20})
        tool_ms = round((time.monotonic_ns() - t0) / 1_000_000.0, 3)
        history_resp = plugin_client.call_tool("get_signal_history", {"limit": 50})
        summary_resp = plugin_client.call_tool("get_strategy_summary", {})
        market_resp = plugin_client.call_tool("get_market_context", {"symbol": "BTCUSDT"})
        reprice_disabled_resp = plugin_client.call_tool(
            "request_reprice",
            {
                "episode_id": "6a6c3316bba3c86c06b9f65de42b6af177be9bd10586ee0e49778f8c8ff42e18",
                "idempotency_key": "demo-disabled-1",
                "desired_delay_minutes": 5,
                "requested_by": "ou_owner_001",
            },
        )

        # 2. Deterministic outbox + mocked outbound across verified cards
        report = LocalPerformanceReport()
        history_items = history_resp["data"]["history"]
        report.inc("cards_verified", len(history_items))

        # Select latest card per episode + inspect +5/+10 reprices
        by_episode: dict[str, list[dict[str, Any]]] = {}
        for item in history_items:
            if item.get("episode_id"):
                by_episode.setdefault(item["episode_id"], []).append(item)

        report.synthetic_actionability_denominator = len(by_episode)
        outbox = DeterministicOutbox(
            outbox_db,
            allowed_recipients=frozenset({"ou_owner_001"}),
        )
        transport = MockFeishuTransport([
            ScriptedOutcome("PROVIDER_ACK", message_id="om_demo_001", http_status=200),
            ScriptedOutcome("RETRYABLE", http_status=429, error_code="429", error_detail="rate limit"),
            ScriptedOutcome("PROVIDER_ACK", message_id="om_demo_002", http_status=200),
        ])

        rendered_cards: dict[str, str] = {}
        outbox_records: list[dict[str, Any]] = []
        now_venue_ms = active_resp["data"]["as_of_ms"]

        for ep_id, ep_cards in sorted(by_episode.items()):
            ordered = sorted(ep_cards, key=lambda c: c["evaluated_at_ms"])
            for c in ordered:
                rp = c.get("reprice")
                if isinstance(rp, dict):
                    if rp.get("requested_delay_minutes") == 5 and c["market_status"] == "EXECUTABLE":
                        report.synthetic_plus5_actionable_numerator += 1
                    if rp.get("requested_delay_minutes") == 10 and c["market_status"] == "EXECUTABLE":
                        report.synthetic_plus10_actionable_numerator += 1

            latest_summary = ordered[-1]
            detail_resp = worker_client.call_tool(
                "get_signal_detail",
                {"episode_id": ep_id, "card_id": latest_summary["card_id"], "as_of_ms": now_venue_ms},
            )
            snap = detail_resp["data"]["snapshot"]
            outbox.enqueue_snapshot(snap, recipient="ou_owner_001", now_ms=now_venue_ms)
            report.inc("alerts_enqueued")

            # Duplicate enqueue test
            dup = outbox.enqueue_snapshot(snap, recipient="ou_owner_001", now_ms=now_venue_ms)
            if dup["deduplicated"]:
                report.inc("alerts_deduplicated")

            claimed = outbox.claim_next(worker_id="demo-worker-1", now_ms=now_venue_ms + 20)
            res = outbox.process_claimed(
                claimed,
                facade_client=worker_client,
                transport=transport,
                worker_id="demo-worker-1",
                now_ms=now_venue_ms + 30,
            )
            if res["state"] == "RETRYABLE":
                report.inc("alerts_retryable")
                claimed2 = outbox.claim_next(worker_id="demo-worker-1", now_ms=res["next_retry_at_ms"] + 5)
                res = outbox.process_claimed(
                    claimed2,
                    facade_client=worker_client,
                    transport=transport,
                    worker_id="demo-worker-1",
                    now_ms=res["next_retry_at_ms"] + 10,
                )

            if res["state"] == "PROVIDER_ACK":
                report.inc("alerts_provider_ack")
            elif res["state"] == "SUPPRESSED":
                report.inc("alerts_suppressed_stale_or_superseded")
            elif res["state"] == "EXPIRED":
                report.inc("alerts_expired")

            if res.get("rendered_text"):
                rendered_cards[f"{snap['symbol']}_{ep_id[:10]}_{snap['market_status']}"] = res["rendered_text"]
            outbox_records.append({
                "event_id": res["event_id"],
                "episode_id": ep_id,
                "card_id": snap["card_id"],
                "market_status": snap["market_status"],
                "final_state": res["state"],
                "provider_message_id": res.get("provider_message_id"),
                "suppression_reason": res.get("suppression_reason"),
            })

            report.add_timeline(
                AlertTimelineMeasurement(
                    episode_id=ep_id,
                    card_id=snap["card_id"],
                    symbol=snap["symbol"],
                    market_status=snap["market_status"],
                    source_as_of_ms=snap["source_as_of_ms"],
                    verified_card_at_ms=snap["verified_at_ms"],
                    outbox_created_at_ms=now_venue_ms,
                    attempt_start_at_ms=now_venue_ms + 20,
                    provider_ack_at_ms=res.get("provider_ack_at_ms"),
                    inbound_request_at_ms=None,
                    status_recheck_at_ms=None,
                    reply_sent_at_ms=None,
                    tool_latency_ms=tool_ms,
                    queue_delay_ms=20.0,
                    model_latency_ms=0.0,
                    delivery_state=res["state"],
                )
            )

        # 3. Simulated Feishu private DM conversations + optional explainer + mock model failures
        chat_valid = FeishuChatService(
            facade_client=plugin_client,
            allowed_owner_open_ids=frozenset({"ou_owner_001"}),
            owner_chat_bindings={"ou_owner_001": "oc_owner_dm_001"},
            explanation_provider=MockValidExplainer(),
        )
        sample_ep = min(by_episode.keys())
        conversations: list[dict[str, Any]] = []
        demo_cmds = [
            "当前机会",
            "查看 BTCUSDT",
            f"查看 {sample_ep}",
            "为什么 WATCH",
            f"复价 {sample_ep}",
            "最近信号",
            "策略说明",
        ]
        base_ts = int(time.time_ns() // 1_000_000)
        for idx, cmd_text in enumerate(demo_cmds, start=1):
            ev = FeishuInboundEvent(
                message_id=f"om_demo_in_{idx}",
                chat_id="oc_owner_dm_001",
                chat_type="p2p",
                sender_open_id="ou_owner_001",
                sender_type="user",
                text=cmd_text,
                event_ts_ms=base_ts + idx,
            )
            reply = chat_valid.handle_inbound(ev, now_ms=base_ts + idx + 5, as_of_ms=now_venue_ms)
            report.inc("inbound_commands_ok" if reply["accepted"] else "inbound_commands_rejected")
            if reply.get("explanation_provenance"):
                report.inc("explanation_validated")
            conversations.append({"input": cmd_text, "reply": reply})

        # 4. Model failure / hallucination fallback proofs
        model_failures: list[dict[str, Any]] = []
        for idx, (label, prov) in enumerate([
            ("quota_exhausted", MockFailingExplainer(mode="quota_exhausted")),
            ("timeout", MockFailingExplainer(mode="timeout")),
            ("hallucinated_price", MockHallucinatingExplainer(mode="invented_price")),
            ("status_upgrade_attempt", MockHallucinatingExplainer(mode="status_upgrade")),
        ], start=1):
            chat_fail = FeishuChatService(
                facade_client=plugin_client,
                allowed_owner_open_ids=frozenset({"ou_owner_001"}),
                owner_chat_bindings={"ou_owner_001": "oc_owner_dm_001"},
                explanation_provider=prov,
            )
            ev = FeishuInboundEvent(
                message_id=f"om_demo_fail_{idx}",
                chat_id="oc_owner_dm_001",
                chat_type="p2p",
                sender_open_id="ou_owner_001",
                sender_type="user",
                text="为什么 WATCH",
                event_ts_ms=base_ts + 100 + idx,
            )
            res = chat_fail.handle_inbound(ev, now_ms=base_ts + 105 + idx, as_of_ms=now_venue_ms)
            report.inc("explanation_fallbacks")
            if label in {"quota_exhausted", "timeout"}:
                report.inc("model_quota_or_provider_errors")
            model_failures.append({
                "scenario": label,
                "accepted": res["accepted"],
                "provenance": res.get("explanation_provenance"),
                "explanation": res.get("explanation"),
                "reply_text": res["reply_text"],
            })

        summary_payload = {
            "contract_id": CONTRACT_ID,
            "contract_doc_sha256": CONTRACT_DOC_SHA256,
            "sources": [{"source_id": sid, "path": str(p)} for sid, p in journal_paths],
            "active_signals": active_resp,
            "market_context_btcusdt": market_resp,
            "strategy_summary": summary_resp,
            "request_reprice_disabled": reprice_disabled_resp,
            "outbox_records": outbox_records,
            "metrics": report.summary(),
        }

        (output_dir / "summary.json").write_text(json.dumps(summary_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "rendered_cards.json").write_text(json.dumps(rendered_cards, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "conversations.json").write_text(json.dumps(conversations, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "model_mock_failures.json").write_text(json.dumps(model_failures, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        (output_dir / "telemetry_report.json").write_text(json.dumps(report.summary(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return summary_payload
    finally:
        server.shutdown()
        server.server_close()
        sock_tmpdir.cleanup()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-hermes-h1", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("info", help="Show Contract V1 pin and tool list")

    demo_cmd = sub.add_parser("demo", help="Run full offline synthetic H1 demo")
    demo_cmd.add_argument("--output", type=Path, required=True)
    demo_cmd.add_argument(
        "--journal",
        action="append",
        required=True,
        help="Approved read-only journal spec as source_id=path",
    )

    serve_cmd = sub.add_parser("serve-facade", help="Run authenticated local QuantFacade UDS server")
    serve_cmd.add_argument("--socket", type=Path, required=True)
    serve_cmd.add_argument("--journal", action="append", required=True)
    serve_cmd.add_argument("--audit-log", type=Path)

    gate_cmd = sub.add_parser("check-live-gate", help="Verify live Feishu/Binance/model gates remain disabled")
    gate_cmd.add_argument("--target", choices=("feishu-live", "binance-live", "model-oauth"), default="feishu-live")

    args = parser.parse_args(argv)
    if args.command == "info":
        print(canonical_json({
            "contract_id": CONTRACT_ID,
            "contract_doc_sha256": CONTRACT_DOC_SHA256,
            "v1_tools": list(V1_ALL_TOOLS),
            "offline_only": True,
        }))
        return 0

    if args.command == "check-live-gate":
        print(LIVE_CAPABILITY_ERROR)
        return LIVE_CAPABILITY_EXIT_CODE

    if args.command == "demo":
        pairs: list[tuple[str, Path]] = []
        for spec in args.journal:
            sid, path_str = spec.split("=", 1)
            pairs.append((sid, Path(path_str)))
        res = run_offline_demo(journal_paths=pairs, output_dir=args.output)
        print(canonical_json({"status": "OK", "outbox_events": len(res["outbox_records"]), "metrics": res["metrics"]["counters"]}))
        return 0

    if args.command == "serve-facade":
        pairs = []
        for spec in args.journal:
            sid, path_str = spec.split("=", 1)
            pairs.append((sid, Path(path_str)))
        registry = ApprovedJournalRegistry([ApprovedJournalSource(source_id=s, path=p) for s, p in pairs])
        svc = QuantFacadeService(registry, audit_log_path=args.audit_log)
        srv = QuantUdsServer(args.socket, svc)
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            srv.server_close()
        return 0

    return 2
