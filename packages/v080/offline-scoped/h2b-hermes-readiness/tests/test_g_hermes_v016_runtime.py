"""Hermes v0.16.0 actual runtime verification (run in /usr/local/lib/hermes-agent Py3.11 venv)."""

from __future__ import annotations

import json
import os
import shutil
import threading
from importlib.metadata import distributions
from pathlib import Path
from types import SimpleNamespace

import pytest

hermes_plugins = pytest.importorskip("hermes_cli.plugins")

import model_tools
from gateway.platforms.feishu import FeishuAdapter
from hermes_cli import plugins as plugins_mod
from lark_oapi.api.im.v1 import P2ImMessageReceiveV1
from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN
from quant_hermes_feishu_h1.facade import (
    QuantFacadeClient,
    QuantFacadeService,
    QuantUdsServer,
)
from quant_hermes_feishu_h1.feishu_outbound import isolated_hermes_feishu_env
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)
from tools.registry import registry

from quant_hermes_feishu_h2b.constants import QUANT_H2B_TOOLSET, V1_MODEL_READONLY_TOOLS
from quant_hermes_feishu_h2b.hermes_plugin.tools import configure_plugin_inbound_boundary
from quant_hermes_feishu_h2b.inbound_boundary import H2BInboundBoundary, InboundBinding, InboundDedupStore
from quant_hermes_feishu_h2b.outbound_sender import (
    H2BMockLarkRecorder,
    HermesSingleSenderService,
    OutboundBinding,
    deterministic_feishu_uuid,
    verify_hermes_standalone_send_compat,
)

H2B_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = H2B_ROOT.parent
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
PLUGIN_SRC = H2B_ROOT / "hermes-plugin/quant-v080-h2b-readonly"


def _reset_hermes() -> None:
    configure_plugin_inbound_boundary(None)
    for t in (*V1_MODEL_READONLY_TOOLS, "request_reprice"):
        registry.deregister(t)
    plugins_mod._plugin_manager = None


def _make_home(tmp_path: Path, *, enabled: bool) -> Path:
    home = tmp_path / ("on_home" if enabled else "off_home")
    home.mkdir(parents=True, exist_ok=True)
    pdir = home / "plugins"
    pdir.mkdir(exist_ok=True)
    shutil.copytree(PLUGIN_SRC, pdir / "quant-v080-h2b-readonly")
    cfg = "plugins:\n  enabled:\n    - quant-v080-h2b-readonly\n" if enabled else "plugins:\n  enabled: []\n"
    (home / "config.yaml").write_text(cfg, encoding="utf-8")
    return home


def test_g1_hermes_plugin_advertised_vs_callable_tools_and_always_on_guard(tmp_path, monkeypatch):
    _reset_hermes()

    # 1. Opt-in disabled by default when plugins.enabled=[]
    home_off = _make_home(tmp_path, enabled=False)
    with isolated_hermes_feishu_env(home_off):
        mgr_off = plugins_mod.PluginManager()
        mgr_off.discover_and_load()
        assert mgr_off._plugins["quant-v080-h2b-readonly"].enabled is False

    # 2. Entrypoint check when H2-B wheel installed into --target
    if any(d.metadata.get("Name") == "quant-hermes-feishu-h2b" for d in distributions()) or os.environ.get("H2B_REQUIRE_ENTRYPOINT") == "1":
        ep_home = tmp_path / "ep_home"
        ep_home.mkdir()
        (ep_home / "config.yaml").write_text("plugins:\n  enabled:\n    - quant-v080-h2b-readonly\n", encoding="utf-8")
        with isolated_hermes_feishu_env(ep_home):
            mgr_ep = plugins_mod.PluginManager()
            eps = mgr_ep._scan_entry_points()
            assert any(m.name == "quant-v080-h2b-readonly" for m in eps)
            mgr_ep.discover_and_load()
            assert mgr_ep._plugins["quant-v080-h2b-readonly"].enabled is True
        _reset_hermes()

    # 3. Loaded H2-B plugin: verify BOTH advertised and actually callable tools via model_tools!
    sock = tmp_path / "s/facade.sock"
    srv = QuantUdsServer(sock, QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    home_on = _make_home(tmp_path, enabled=True)

    try:
        with isolated_hermes_feishu_env(home_on):
            monkeypatch.setenv("QUANT_FACADE_SOCKET", str(sock))
            mgr = plugins_mod.PluginManager()
            plugins_mod._plugin_manager = mgr
            mgr.discover_and_load()
            loaded = mgr._plugins["quant-v080-h2b-readonly"]
            assert loaded.enabled is True
            assert sorted(loaded.tools_registered) == sorted(V1_MODEL_READONLY_TOOLS)
            assert len(loaded.tools_registered) == len(V1_MODEL_READONLY_TOOLS)
            assert "request_reprice" not in loaded.tools_registered

            # Advertised inventory scoped to QUANT_H2B_TOOLSET: strictly 6 read-only tools
            advertised = model_tools.get_tool_definitions(enabled_toolsets=[QUANT_H2B_TOOLSET], quiet_mode=True)
            assert [d["function"]["name"] for d in advertised] == sorted(V1_MODEL_READONLY_TOOLS)

            # Actually callable via model_tools.handle_function_call: ONLY the 6 allowed tools work
            raw_list = model_tools.handle_function_call("list_active_signals", {"limit": 10})
            list_obj = json.loads(raw_list)
            assert list_obj["status"] == "OK"

            # Privileged built-ins & request_reprice MUST be blocked by always_on_pre_tool_call_guard
            # even though no special env flag is set and built-ins exist in global Hermes registry!
            for blocked in (
                "request_reprice",
                "terminal",
                "read_file",
                "write_file",
                "send_message",
                "browser_navigate",
                "execute_code",
            ):
                blk_res = json.loads(model_tools.handle_function_call(blocked, {}))
                assert "error" in blk_res, f"{blocked} unexpectedly allowed: {blk_res}"
                assert "blocked by QUANT H2-B fail-closed boundary" in blk_res["error"]

            # Attempting to spoof caller identity in model args fails inside handler
            spoof_res = json.loads(
                model_tools.handle_function_call("list_active_signals", {"principal_id": "admin"})
            )
            assert spoof_res["status"] == "ERROR"
            assert spoof_res["error"]["code"] == "INVALID_ARGUMENT"
    finally:
        _reset_hermes()
        srv.shutdown()
        srv.server_close()


def test_g2_hermes_single_sender_adapter_standalone_send_and_p2_inbound_hook(tmp_path):
    _reset_hermes()
    sock = tmp_path / "s2/f.sock"
    srv = QuantUdsServer(sock, QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    home = _make_home(tmp_path, enabled=True)

    try:
        out_binding = OutboundBinding(
            app_id="cli_h2boffline001",
            tenant_key="tenant_h2b_001",
            owner_open_id="ou_owner001",
            authorized_dm_chat_id="oc_dmowner001",
        )
        client = QuantFacadeClient(sock, principal_id="hermes_quant_plugin", recipient_scope="outbox_worker")
        sig = client.call_tool("list_active_signals")["data"]["signals"][0]
        snap = client.call_tool("get_signal_detail", {"episode_id": sig["episode_id"]})["data"]["snapshot"]

        # 1. H2-B single-attempt sender exercises real FeishuAdapter request builders
        recorder = H2BMockLarkRecorder()
        sender = HermesSingleSenderService(
            state_dir=tmp_path / "sender_state",
            binding=out_binding,
            hermes_home=home,
            mock_lark_client=recorder,
            offline_mock_only=True,
        )
        enq = sender.enqueue(snap, recipient="oc_dmowner001", now_ms=snap["evaluated_at_ms"])
        res = sender.dispatch_next(facade_client=client, now_ms=snap["evaluated_at_ms"] + 5)
        assert res["state"] == "PROVIDER_ACK"
        assert sender.transport.used_hermes_adapter is True
        assert recorder.requests[0]["uuid"] == deterministic_feishu_uuid(enq["event_id"])
        assert SYNTHETIC_WARNING_TOKEN in json.loads(recorder.requests[0]["content"])["text"]

        # 2. Standalone Hermes tools.send_message_tool._send_feishu compatibility check (offline mocked)
        standalone = verify_hermes_standalone_send_compat(
            hermes_home=home,
            binding=out_binding,
            text="[SYNTHETIC_QA_ONLY / NOT_A_REAL_TRADE_SIGNAL] standalone compat",
        )
        assert standalone["hermes_result"]["success"] is True

        # 3. Hermes pre_gateway_dispatch_guard + real P2ImMessageReceiveV1 SDK object
        with isolated_hermes_feishu_env(home, app_id=out_binding.app_id, allowed_users=("ou_owner001",)):
            mgr = plugins_mod.PluginManager()
            plugins_mod._plugin_manager = mgr
            mgr.discover_and_load()

            p2_ok = P2ImMessageReceiveV1({
                "schema": "2.0",
                "header": {
                    "event_id": "p2_ev_1",
                    "event_type": "im.message.receive_v1",
                    "create_time": "1735700500000",
                    "app_id": "cli_h2boffline001",
                    "tenant_key": "tenant_h2b_001",
                },
                "event": {
                    "sender": {
                        "sender_id": {"open_id": "ou_owner001", "union_id": "on_owner001"},
                        "sender_type": "user",
                        "tenant_key": "tenant_h2b_001",
                    },
                    "message": {
                        "message_id": "om_p2_1",
                        "chat_id": "oc_dmowner001",
                        "chat_type": "p2p",
                        "message_type": "text",
                        "content": json.dumps({"text": "当前机会"}, ensure_ascii=False),
                        "create_time": 1735700500000,
                    },
                },
            })
            src_ok = SimpleNamespace(chat_id="oc_dmowner001", chat_type="dm", user_id="ou_owner001")
            ev_hermes = SimpleNamespace(source=src_ok, raw_message=p2_ok)

            # Without inbound boundary configured, pre_gateway_dispatch MUST fail closed!
            res_unconf = plugins_mod.invoke_hook("pre_gateway_dispatch", event=ev_hermes)[0]
            assert res_unconf["action"] == "skip"
            assert res_unconf["reason"] == "H2B_INBOUND_BINDING_NOT_CONFIGURED"

            # Attach inbound boundary with controlled clock (or fresh event time matching boundary window)
            dedup = InboundDedupStore(tmp_path / "p2_dedup.sqlite")
            boundary = H2BInboundBoundary(
                binding=InboundBinding(
                    app_id="cli_h2boffline001",
                    tenant_key="tenant_h2b_001",
                    allowed_owner_open_ids=frozenset({"ou_owner001"}),
                    owner_chat_bindings={"ou_owner001": "oc_dmowner001"},
                    max_event_age_ms=10_000_000_000_000,
                ),
                dedup_store=dedup,
            )
            configure_plugin_inbound_boundary(boundary)
            res_allow = plugins_mod.invoke_hook("pre_gateway_dispatch", event=ev_hermes)[0]
            assert res_allow["action"] == "allow"

            # Duplicate event_id is skipped cleanly
            res_dup = plugins_mod.invoke_hook("pre_gateway_dispatch", event=ev_hermes)[0]
            assert res_dup["action"] == "skip" and res_dup["reason"] == "DUPLICATE_EVENT_ID"
            assert FeishuAdapter is not None
    finally:
        _reset_hermes()
        srv.shutdown()
        srv.server_close()
