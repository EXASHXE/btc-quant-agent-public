"""QUANT v0.8.0 H2-B CLI: fail-closed live gates, Hermes interface checks, golden checks, and offline demo."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from typing import Any

from quant_hermes_feishu_h1.contract import canonical_sha256_strict, compute_outbox_event_id
from quant_hermes_feishu_h1.facade import QuantFacadeClient, QuantFacadeService, QuantUdsServer
from quant_hermes_feishu_h1.journal_reader import ApprovedJournalRegistry, ApprovedJournalSource

from .activation_gate import GateDenialError, H2BActivationGate
from .constants import (
    H2B_VERSION,
    HERMES_EXPECTED_COMMIT,
    HERMES_EXPECTED_LARK_OAPI_VERSION,
    HERMES_EXPECTED_VERSION,
    LIVE_CAPABILITY_ERROR,
    LIVE_FEISHU_ERROR,
    LIVE_MODEL_ERROR,
    QUANT_H2B_TOOLSET,
    V1_MODEL_READONLY_TOOLS,
)
from .explainer_gate import (
    GatedAiExplanationPipeline,
    ScriptedModelProvider,
    ScriptedModelResponse,
)
from .inbound_boundary import H2BInboundBoundary, InboundBinding, InboundDedupStore, PrivateDmSessionManager
from .outbound_sender import (
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    OutboundBinding,
)
from .readonly_tools import AuthenticatedCallerContext, QuantV1ReadonlyToolGateway


def _cmd_check_live_gate(args: argparse.Namespace) -> int:
    # Arbitrary CLI flags or env vars never override PRODUCTION_TRUST_ROOT.
    del args.ignore_env_bypass
    gate = H2BActivationGate()
    cap_map = {
        "feishu-live": "FEISHU_OUTBOUND_DM_ONCE",
        "feishu-outbound": "FEISHU_OUTBOUND_DM_ONCE",
        "feishu-inbound": "FEISHU_INBOUND_DM_BOUNDED",
        "feishu-recurring": "FEISHU_PERSISTENT_GATEWAY_AND_RECURRING",
        "model-oauth": "MODEL_EXPLANATION_OPTIONAL",
    }
    target = args.target
    if target not in cap_map:
        print(LIVE_CAPABILITY_ERROR)
        return 3
    try:
        gate.authorize_capability(
            cap_map[target],
            app_id="cli_unprovisioned",
            tenant_key="unprovisioned",
            recipient_open_id="ou_unprovisioned",
            chat_id="oc_unprovisioned",
            sender_id="hermes-h2b-sole-sender",
            outbox_path="/dev/null",
            model_auth_scope="NONE" if target != "model-oauth" else "UNCONFIGURED",
        )
    except GateDenialError as exc:
        print(exc.code)
        return exc.exit_code
    expected = {
        "feishu-live": LIVE_FEISHU_ERROR,
        "model-oauth": LIVE_MODEL_ERROR,
    }.get(target, LIVE_CAPABILITY_ERROR)
    print(expected)
    return 3


def verify_hermes_interfaces() -> dict[str, Any]:
    """Inspect installed /usr/local/lib/hermes-agent interfaces and verify exact H2-B expectations."""
    hermes_root = Path("/usr/local/lib/hermes-agent")
    commit = subprocess.check_output(
        ["git", "--no-optional-locks", "rev-parse", "HEAD"],
        cwd=hermes_root,
        text=True,
    ).strip()
    if commit != HERMES_EXPECTED_COMMIT:
        raise RuntimeError(f"Hermes commit mismatch: {commit} != {HERMES_EXPECTED_COMMIT}")

    pyproject_txt = (hermes_root / "pyproject.toml").read_text(encoding="utf-8")
    if f'version = "{HERMES_EXPECTED_VERSION}"' not in pyproject_txt:
        raise RuntimeError("Hermes pyproject version mismatch")

    result: dict[str, Any] = {
        "hermes_root": str(hermes_root),
        "hermes_version": HERMES_EXPECTED_VERSION,
        "hermes_commit": commit,
        "python_version": sys.version.split()[0],
        "h2b_version": H2B_VERSION,
        "h2b_toolset": QUANT_H2B_TOOLSET,
        "h2b_readonly_tools": list(V1_MODEL_READONLY_TOOLS),
    }

    try:
        import importlib.metadata as meta

        import model_tools
        from gateway.platforms.feishu import FeishuAdapter
        from hermes_cli import plugins as plugins_mod
        from tools.registry import registry

        from tools import send_message_tool

        lark_ver = meta.version("lark-oapi")
        if lark_ver != HERMES_EXPECTED_LARK_OAPI_VERSION:
            raise RuntimeError(f"lark-oapi version mismatch: {lark_ver}")

        result["hermes_modules_imported"] = True
        result["lark_oapi_version"] = lark_ver
        result["plugin_ctx_methods"] = {
            "register_tool": str(inspect.signature(plugins_mod.PluginContext.register_tool)),
            "register_hook": str(inspect.signature(plugins_mod.PluginContext.register_hook)),
            "register_command": str(inspect.signature(plugins_mod.PluginContext.register_command)),
        }
        result["send_feishu_sig"] = str(inspect.signature(send_message_tool._send_feishu))
        result["feishu_adapter_methods"] = {
            "connect": str(inspect.signature(FeishuAdapter.connect)),
            "disconnect": str(inspect.signature(FeishuAdapter.disconnect)),
            "send": str(inspect.signature(FeishuAdapter.send)),
            "_build_create_message_body": str(inspect.signature(FeishuAdapter._build_create_message_body)),
            "_build_create_message_request": str(inspect.signature(FeishuAdapter._build_create_message_request)),
            "_finalize_send_result": str(inspect.signature(FeishuAdapter._finalize_send_result)),
        }
        result["model_tools_sigs"] = {
            "get_tool_definitions": str(inspect.signature(model_tools.get_tool_definitions)),
            "handle_function_call": str(inspect.signature(model_tools.handle_function_call)),
        }
        result["builtin_tool_count_in_registry"] = len(registry.get_all_tool_names())
    except ImportError as exc:
        result["hermes_modules_imported"] = False
        result["import_note"] = str(exc)

    return result


def verify_frozen_goldens(*, h1_root: Path, oracle_json: Path) -> dict[str, Any]:
    """Read-only comparison against Controller 7 goldens and sealed H1 reference-export."""
    oracle = json.loads(Path(oracle_json).read_text(encoding="utf-8"))
    data = oracle["data"]
    matched = 0
    for name, expected in data.items():
        obj = json.loads(expected["preimage"])
        sha = canonical_sha256_strict(obj)
        if sha != expected["sha256"]:
            raise RuntimeError(f"Oracle mismatch on {name}: {sha} != {expected['sha256']}")
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
            if eid != expected["sha256"]:
                raise RuntimeError(f"Event ID mismatch on {name}: {eid} != {expected['sha256']}")
        matched += 1

    ref_dir = Path(h1_root) / "reference-export"
    manifest = json.loads((ref_dir / "REFERENCE_EXPORT_MANIFEST.json").read_text(encoding="utf-8"))
    verified_files = 0
    for entry in manifest["files"]:
        f_sha = hashlib.sha256((ref_dir / entry["path"]).read_bytes()).hexdigest()
        if f_sha != entry["sha256"]:
            raise RuntimeError(f"H1 reference file tampered: {entry['path']}")
        verified_files += 1

    return {
        "status": "READONLY_GOLDEN_ORACLE_MATCH_OK",
        "oracle_cases_matched": matched,
        "h1_reference_files_verified": verified_files,
        "h1_reference_manifest_sha256": hashlib.sha256(
            (ref_dir / "REFERENCE_EXPORT_MANIFEST.json").read_bytes()
        ).hexdigest(),
    }


def run_offline_demo(*, journal_specs: list[tuple[str, Path]], output_dir: Path) -> dict[str, Any]:
    """Run an offline end-to-end H2-B mock Feishu outbound + inbound + fallback demo."""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    fixed_ts = 1735700400000
    sources = [ApprovedJournalSource(label, path) for label, path in journal_specs]
    reg = ApprovedJournalRegistry(sources)

    with tempfile.TemporaryDirectory(prefix="h2bs_") as run_tmp:
        tmp_root = Path(run_tmp)
        os.chmod(tmp_root, 0o700)
        sock_path = tmp_root / "f.sock"
        srv = QuantUdsServer(sock_path, QuantFacadeService(reg))
        threading.Thread(target=srv.serve_forever, daemon=True).start()

        try:
            out_binding = OutboundBinding(
                app_id="cli_h2boffline001",
                tenant_key="tenant_h2b_001",
                owner_open_id="ou_owner001",
                authorized_dm_chat_id="oc_dmowner001",
            )
            in_binding = InboundBinding(
                app_id="cli_h2boffline001",
                tenant_key="tenant_h2b_001",
                allowed_owner_open_ids=frozenset({"ou_owner001"}),
                owner_chat_bindings={"ou_owner001": "oc_dmowner001"},
            )

            # 1. Six-tool read-only gateway & denied request_reprice
            ro_client = QuantFacadeClient(sock_path, principal_id="hermes_quant_plugin", recipient_scope="owner_dm")
            gateway = QuantV1ReadonlyToolGateway(
                facade_client=ro_client,
                caller_context=AuthenticatedCallerContext(
                    principal_id="hermes_quant_plugin",
                    recipient_scope="owner_dm",
                    app_id=out_binding.app_id,
                    tenant_key=out_binding.tenant_key,
                    owner_open_id="ou_owner001",
                    chat_id="oc_dmowner001",
                ),
            )
            active = gateway.call_model_tool("list_active_signals", {"limit": 10})
            signals = active["data"]["signals"]

            # 2. Deterministic Outbox + Single-Attempt Mock Lark Sender + DeliveryLedger
            outbox_client = QuantFacadeClient(
                sock_path, principal_id="hermes_quant_plugin", recipient_scope="outbox_worker"
            )
            lark_mock = H2BMockLarkRecorder()
            sender = HermesSingleSenderService(
                state_dir=tmp_root / "sender_state",
                binding=out_binding,
                hermes_home=tmp_root / "fake_hermes_home",
                mock_lark_client=lark_mock,
                offline_mock_only=True,
                clock_ms_fn=lambda: fixed_ts,
            )
            send_results = []
            for sig in signals:
                det = gateway.call_model_tool("get_signal_detail", {"episode_id": sig["episode_id"]})["data"]["snapshot"]
                sender.enqueue(det, recipient="oc_dmowner001", now_ms=det["evaluated_at_ms"])
                res = sender.dispatch_next(facade_client=outbox_client, now_ms=det["evaluated_at_ms"] + 5)
                send_results.append({k: v for k, v in (res or {}).items() if k != "rendered_text"})

            # 3. Authenticated private-DM inbound transcript + rejection traces
            dedup = InboundDedupStore(tmp_root / "inbound_dedup.sqlite")
            boundary = H2BInboundBoundary(binding=in_binding, dedup_store=dedup)
            mgr = PrivateDmSessionManager(
                boundary=boundary,
                facade_client=ro_client,
                explanation_provider=ScriptedModelProvider(ScriptedModelResponse(mode="valid")),
            )
            ep0 = signals[0]["episode_id"]
            as_of_demo = signals[0]["evaluated_at_ms"]
            raw_events = [
                _make_raw_ev("ev-1", "msg-1", "oc_dmowner001", "p2p", "ou_owner001", "当前机会", fixed_ts),
                _make_raw_ev("ev-2", "msg-2", "oc_dmowner001", "p2p", "ou_owner001", f"查看 {ep0}", fixed_ts + 1),
                _make_raw_ev("ev-3", "msg-3", "oc_dmowner001", "p2p", "ou_owner001", "为什么 WATCH", fixed_ts + 2),
                _make_raw_ev("ev-4", "msg-4", "oc_dmowner001", "p2p", "ou_intruder", "当前机会", fixed_ts + 3),
                _make_raw_ev("ev-5", "msg-5", "oc_group999", "group", "ou_owner001", "当前机会", fixed_ts + 4),
                _make_raw_ev("ev-6", "msg-6", "oc_dmowner001", "p2p", "ou_owner001", "转发自 ou_other: 查看", fixed_ts + 5),
            ]
            transcripts = [mgr.handle_raw_event_sync(ev, now_ms=fixed_ts + 10, as_of_ms=as_of_demo) for ev in raw_events]

            # 4. Explanation fallback demo (timeout + hallucination)
            snap0 = gateway.call_model_tool("get_signal_detail", {"episode_id": ep0})["data"]["snapshot"]
            fb_timeout = GatedAiExplanationPipeline(
                provider=ScriptedModelProvider(ScriptedModelResponse(mode="timeout", delay_ms=120)),
                timeout_ms=20,
            ).explain_record(snap0)
            fb_halluc = GatedAiExplanationPipeline(
                provider=ScriptedModelProvider(ScriptedModelResponse(mode="hallucinated")),
            ).explain_record(snap0)

            # 5. Default-deny live gates check
            gate_denials = {}
            default_gate = H2BActivationGate()
            for cap, scope in (
                ("FEISHU_OUTBOUND_DM_ONCE", "NONE"),
                ("FEISHU_INBOUND_DM_BOUNDED", "NONE"),
                ("MODEL_EXPLANATION_OPTIONAL", "OPEN_API"),
                ("FEISHU_PERSISTENT_GATEWAY_AND_RECURRING", "NONE"),
            ):
                try:
                    default_gate.authorize_capability(
                        cap,
                        app_id=out_binding.app_id,
                        tenant_key=out_binding.tenant_key,
                        recipient_open_id="ou_owner001",
                        chat_id="oc_dmowner001",
                        sender_id=out_binding.sender_id,
                        outbox_path=sender.outbox_db_path,
                        model_auth_scope=scope,
                    )
                except GateDenialError as exc:
                    gate_denials[cap] = exc.code

            summary = {
                "task_id": "V080-NEON-H2B-HERMES-FEISHU-READINESS-01",
                "h2b_version": H2B_VERSION,
                "evidence_class": "SYNTHETIC_QA_ONLY",
                "real_feishu_delivery_measured": False,
                "real_model_api_used": False,
                "active_signals_count": len(signals),
                "lark_mock_requests": lark_mock.requests,
                "send_results": send_results,
                "ledger_entries_count": len(sender.ledger.all_entries()),
                "inbound_accepted_count": sum(1 for t in transcripts if t.get("accepted")),
                "inbound_rejected_count": sum(1 for t in transcripts if not t.get("accepted")),
                "explainer_fallbacks": [fb_timeout["provenance"], fb_halluc["provenance"]],
                "default_deny_gates": gate_denials,
                "request_reprice_human": gateway.invoke_human_request_reprice(
                    {"episode_id": ep0, "idempotency_key": "demo-1", "desired_delay_minutes": 5}
                ),
            }
            (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
            (out / "outbound_ledger.json").write_text(
                json.dumps(sender.ledger.all_entries(), ensure_ascii=False, indent=2), encoding="utf-8"
            )
            (out / "inbound_transcripts.json").write_text(
                json.dumps(transcripts, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            return summary
        finally:
            srv.shutdown()
            srv.server_close()


def _make_raw_ev(
    event_id: str,
    message_id: str,
    chat_id: str,
    chat_type: str,
    open_id: str,
    text: str,
    ts_ms: int,
) -> dict[str, Any]:
    return {
        "schema": "2.0",
        "header": {
            "event_id": event_id,
            "event_type": "im.message.receive_v1",
            "create_time": str(ts_ms),
            "app_id": "cli_h2boffline001",
            "tenant_key": "tenant_h2b_001",
        },
        "event": {
            "sender": {
                "sender_id": {"open_id": open_id, "union_id": f"on_{open_id}"},
                "sender_type": "user",
                "tenant_key": "tenant_h2b_001",
            },
            "message": {
                "message_id": message_id,
                "chat_id": chat_id,
                "chat_type": chat_type,
                "message_type": "text",
                "content": json.dumps({"text": text}, ensure_ascii=False),
                "create_time": str(ts_ms),
            },
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="quant-hermes-h2b")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_gate = sub.add_parser("check-live-gate", help="Verify default-deny live capability gate")
    p_gate.add_argument(
        "--target",
        required=True,
        choices=["feishu-live", "feishu-outbound", "feishu-inbound", "feishu-recurring", "model-oauth"],
    )
    p_gate.add_argument("--ignore-env-bypass", action="store_true")

    p_hermes = sub.add_parser("verify-hermes-interface", help="Inspect local Hermes v0.16.0 interfaces")
    p_hermes.add_argument("--output", type=Path, default=None)

    p_gold = sub.add_parser("verify-goldens", help="Verify read-only Controller 7 goldens + H1 reference pack")
    p_gold.add_argument("--h1-root", type=Path, required=True)
    p_gold.add_argument("--oracle", type=Path, required=True)

    p_demo = sub.add_parser("demo-offline", help="Run offline synthetic H2-B Feishu readiness demo")
    p_demo.add_argument("--output", type=Path, required=True)
    p_demo.add_argument("--journal", action="append", required=True, help="label=/path/to/journal.sqlite")

    args = parser.parse_args(argv)
    if args.cmd == "check-live-gate":
        return _cmd_check_live_gate(args)
    if args.cmd == "verify-hermes-interface":
        info = verify_hermes_interfaces()
        payload = json.dumps(info, ensure_ascii=False, indent=2)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(payload + "\n", encoding="utf-8")
        print(payload)
        return 0
    if args.cmd == "verify-goldens":
        res = verify_frozen_goldens(h1_root=args.h1_root, oracle_json=args.oracle)
        print(json.dumps(res, ensure_ascii=False))
        return 0
    if args.cmd == "demo-offline":
        specs: list[tuple[str, Path]] = []
        for item in args.journal:
            label, path_str = item.split("=", 1)
            specs.append((label, Path(path_str)))
        res = run_offline_demo(journal_specs=specs, output_dir=args.output)
        print(json.dumps({"status": "DEMO_OFFLINE_OK", "active": res["active_signals_count"]}, ensure_ascii=False))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
