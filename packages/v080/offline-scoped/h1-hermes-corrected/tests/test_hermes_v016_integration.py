"""Offline integration tests against installed Hermes Agent v0.16.0 (c2fa302e9)."""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import threading
from argparse import Namespace
from importlib.metadata import distributions
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

hermes_plugins = pytest.importorskip("hermes_cli.plugins")

from gateway.config import PlatformConfig
from gateway.platforms.feishu import FeishuAdapter
from hermes_cli import plugins as plugins_mod
from hermes_cli.send_cmd import cmd_send
from tools.registry import registry

from quant_hermes_feishu_h1.contract import SYNTHETIC_WARNING_TOKEN, V1_ALL_TOOLS
from quant_hermes_feishu_h1.facade import (
    QuantFacadeClient,
    QuantFacadeService,
    QuantUdsServer,
)
from quant_hermes_feishu_h1.feishu_chat import FeishuChatService, FeishuInboundEvent
from quant_hermes_feishu_h1.feishu_outbound import (
    HermesSendFeishuTransport,
    MockLarkClient,
    MockLarkResponse,
    invoke_hermes_send_message_tool_feishu,
    isolated_hermes_feishu_env,
)
from quant_hermes_feishu_h1.journal_reader import (
    ApprovedJournalRegistry,
    ApprovedJournalSource,
)
from quant_hermes_feishu_h1.outbox import DeterministicOutbox

H1_ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = H1_ROOT.parent
B5_JOURNAL = WORKSPACES / "lt-v080-personal-mvp-live-public-b5-01/evidence/replay-input/journal.sqlite"
DIR_PLUGIN_SRC = H1_ROOT / "hermes-plugin/quant-v080-readonly"


def _make_scratch_hermes_home(tmp_path: Path, *, enable_plugin: bool) -> Path:
    home = tmp_path / "scratch_hermes_home"
    home.mkdir(parents=True, exist_ok=True)
    plugins_dir = home / "plugins"
    plugins_dir.mkdir(exist_ok=True)
    shutil.copytree(DIR_PLUGIN_SRC, plugins_dir / "quant-v080-readonly")
    enabled_list = ["quant-v080-readonly"] if enable_plugin else []
    (home / "config.yaml").write_text(
        "plugins:\n  enabled:\n" + "".join(f"    - {x}\n" for x in enabled_list)
        if enabled_list
        else "plugins:\n  enabled: []\n",
        encoding="utf-8",
    )
    return home


def _reset_hermes_registries() -> None:
    for t in V1_ALL_TOOLS:
        registry.deregister(t)
    plugins_mod._plugin_manager = None


def test_hermes_v016_plugin_opt_in_and_v1_tool_dispatch_and_hooks(tmp_path, monkeypatch):
    _reset_hermes_registries()
    # 1. Opt-in disabled by default when not listed in plugins.enabled
    home_off = _make_scratch_hermes_home(tmp_path / "off", enable_plugin=False)
    with isolated_hermes_feishu_env(home_off):
        mgr_off = plugins_mod.PluginManager()
        mgr_off.discover_and_load()
        entry_off = mgr_off._plugins["quant-v080-readonly"]
        assert entry_off.enabled is False
        assert "not enabled in config" in (entry_off.error or "")

    # 2. Opt-in enabled loads all 7 V1 tools, hooks, and /quant-status against live UDS facade
    home_on = _make_scratch_hermes_home(tmp_path / "on", enable_plugin=True)
    sock_path = tmp_path / "sock/hermes_facade.sock"
    srv = QuantUdsServer(sock_path, QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    try:
        with isolated_hermes_feishu_env(home_on):
            monkeypatch.setenv("QUANT_FACADE_SOCKET", str(sock_path))
            monkeypatch.setenv("QUANT_HERMES_STRICT_SANDBOX", "1")
            monkeypatch.setenv("QUANT_FEISHU_GATEWAY_GUARD", "1")
            monkeypatch.setenv("QUANT_FEISHU_ALLOWED_OWNERS", "ou_owner_001")

            mgr = plugins_mod.PluginManager()
            plugins_mod._plugin_manager = mgr
            mgr.discover_and_load()
            loaded = mgr._plugins["quant-v080-readonly"]
            assert loaded.enabled is True
            assert set(loaded.tools_registered) == set(V1_ALL_TOOLS)
            assert "pre_tool_call" in loaded.hooks_registered
            assert "pre_gateway_dispatch" in loaded.hooks_registered
            assert "quant-status" in loaded.commands_registered

            # Verify tool definitions in Hermes global registry
            defs = registry.get_definitions(set(V1_ALL_TOOLS), quiet=True)
            assert {d["function"]["name"] for d in defs} == set(V1_ALL_TOOLS)

            # Dispatch all 7 V1 tools via Hermes registry
            r_list = json.loads(registry.dispatch("list_active_signals", {"limit": 10}))
            assert r_list["status"] == "OK"
            ep_id = r_list["data"]["signals"][0]["episode_id"]

            for t_name, t_args in (
                ("get_signal_detail", {"episode_id": ep_id}),
                ("get_market_context", {"symbol": "BTCUSDT"}),
                ("get_latest_reprice", {"episode_id": ep_id}),
                ("get_signal_history", {"limit": 10}),
                ("get_strategy_summary", {}),
            ):
                res = json.loads(registry.dispatch(t_name, t_args))
                assert res["status"] == "OK", f"{t_name} failed: {res}"

            r_rep = json.loads(
                registry.dispatch(
                    "request_reprice",
                    {
                        "episode_id": ep_id,
                        "idempotency_key": "hermes-1",
                        "desired_delay_minutes": 5,
                        "requested_by": "ou_owner_001",
                    },
                )
            )
            assert r_rep["status"] == "ERROR"
            assert r_rep["error"]["code"] == "REPRICE_NOT_AUTHORIZED"

            # Verify pre_tool_call blocks privileged built-ins in strict sandbox
            for blocked_tool in ("terminal", "read_file", "write_file", "send_message", "browser_navigate"):
                msg = plugins_mod.get_pre_tool_call_block_message(blocked_tool, {})
                assert msg is not None and "blocked in QUANT H1 strict sandbox" in msg
            assert plugins_mod.get_pre_tool_call_block_message("list_active_signals", {}) is None

            # Verify pre_gateway_dispatch guard
            ev_group = SimpleNamespace(source=SimpleNamespace(chat_type="group", user_id="ou_owner_001"))
            ev_intruder = SimpleNamespace(source=SimpleNamespace(chat_type="p2p", user_id="ou_intruder"))
            ev_ok = SimpleNamespace(source=SimpleNamespace(chat_type="p2p", user_id="ou_owner_001"))
            assert plugins_mod.invoke_hook("pre_gateway_dispatch", event=ev_group)[0]["action"] == "skip"
            assert plugins_mod.invoke_hook("pre_gateway_dispatch", event=ev_intruder)[0]["action"] == "skip"
            assert plugins_mod.invoke_hook("pre_gateway_dispatch", event=ev_ok)[0]["action"] == "allow"

            # Verify slash command /quant-status
            slash_fn = plugins_mod.get_plugin_command_handler("quant-status")
            assert slash_fn is not None
            slash_out = json.loads(slash_fn(""))
            assert slash_out["status"] == "OK"
    finally:
        _reset_hermes_registries()
        srv.shutdown()
        srv.server_close()


def test_hermes_v016_entrypoint_discovery_and_path_a_send_feishu(tmp_path):
    _reset_hermes_registries()
    # Entry-point scan if wheel/editable package is installed in current Python env
    has_dist = any(d.metadata.get("Name") == "quant-hermes-feishu-h1" for d in distributions())
    require_ep = os.environ.get("H1_REQUIRE_ENTRYPOINT") == "1"
    if has_dist or require_ep:
        home_ep = tmp_path / "ep_home"
        home_ep.mkdir()
        (home_ep / "config.yaml").write_text("plugins:\n  enabled:\n    - quant-v080-readonly\n", encoding="utf-8")
        with isolated_hermes_feishu_env(home_ep):
            mgr = plugins_mod.PluginManager()
            ep_manifests = mgr._scan_entry_points()
            assert any(m.name == "quant-v080-readonly" for m in ep_manifests), "Expected quant-v080-readonly entrypoint"
            mgr.discover_and_load()
            assert mgr._plugins["quant-v080-readonly"].enabled is True
        _reset_hermes_registries()

    # Path A: Standalone _send_feishu + send_message_tool + hermes_cli.send_cmd (NO running gateway!)
    home_send = tmp_path / "send_home"
    sock_path = tmp_path / "sock/send_facade.sock"
    srv = QuantUdsServer(sock_path, QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = QuantFacadeClient(sock_path, recipient_scope="outbox_worker")
        sig = client.call_tool("list_active_signals")["data"]["signals"][0]
        snap = client.call_tool("get_signal_detail", {"episode_id": sig["episode_id"]})["data"]["snapshot"]

        # 1. Drive Outbox via HermesSendFeishuTransport (mocked lark_oapi Client)
        mock_lark = MockLarkClient([
            MockLarkResponse(ok=False, code=99991400, msg="429 too many requests"),
            MockLarkResponse(ok=True, code=0, msg="ok", message_id="om_hermes_ack_42"),
        ])
        hermes_transport = HermesSendFeishuTransport(hermes_home=home_send, mock_lark_client=mock_lark)
        outbox = DeterministicOutbox(tmp_path / "outbox_hermes.sqlite", allowed_recipients=frozenset({"ou_owner001"}), base_backoff_ms=10)
        now_ms = snap["evaluated_at_ms"] + 100
        outbox.enqueue_snapshot(snap, recipient="ou_owner001", now_ms=now_ms)

        c1 = outbox.claim_next(worker_id="hermes-send-w", now_ms=now_ms + 5)
        r1 = outbox.process_claimed(c1, facade_client=client, transport=hermes_transport, worker_id="hermes-send-w", now_ms=now_ms + 10)
        assert r1["state"] == "RETRYABLE"

        c2 = outbox.claim_next(worker_id="hermes-send-w", now_ms=r1["next_retry_at_ms"] + 5)
        r2 = outbox.process_claimed(c2, facade_client=client, transport=hermes_transport, worker_id="hermes-send-w", now_ms=r1["next_retry_at_ms"] + 10)
        assert r2["state"] == "PROVIDER_ACK"
        assert r2["provider_message_id"] == "om_hermes_ack_42"
        assert len(mock_lark.requests) == 2
        assert SYNTHETIC_WARNING_TOKEN in mock_lark.requests[1]["content"]

        # Negative check: synthetic ID with extra underscore ('ou_owner_001') is rejected by both
        # HermesSendFeishuTransport and Hermes v0.16.0 send_message_tool._FEISHU_TARGET_RE.
        bad_deliv = hermes_transport.send_text(
            channel="feishu",
            recipient="ou_owner_001",
            text="[SYNTHETIC_QA_ONLY] rejected id",
            event_id="ev-neg",
            attempt=1,
        )
        assert bad_deliv.classification == "PERMANENT"
        assert bad_deliv.error_code == "INVALID_FEISHU_RECIPIENT"
        bad_sm = invoke_hermes_send_message_tool_feishu(
            hermes_home=home_send,
            recipient="ou_owner_001",
            message="[SYNTHETIC_QA_ONLY] rejected id",
        )
        assert "error" in bad_sm["tool_result"]
        assert len(bad_sm["lark_requests"]) == 0

        # 2. Direct send_message_tool(action="send", target="feishu:ou_owner001")
        sm_res = invoke_hermes_send_message_tool_feishu(
            hermes_home=home_send,
            recipient="ou_owner001",
            message="[SYNTHETIC_QA_ONLY / NOT_A_REAL_TRADE_SIGNAL] test notice",
        )
        assert sm_res["tool_result"]["success"] is True
        assert sm_res["tool_result"]["platform"] == "feishu"
        assert sm_res["lark_requests"][0]["receive_id_type"] == "open_id"

        # 3. Direct hermes_cli.send_cmd.cmd_send
        cli_lark = MockLarkClient()
        with (
            isolated_hermes_feishu_env(home_send, allowed_users=("ou_owner001",)),
            patch.object(FeishuAdapter, "_build_lark_client", return_value=cli_lark),
        ):
            with pytest.raises(SystemExit) as exit_info:
                cmd_send(
                    Namespace(
                        list_targets=False,
                        to="feishu:ou_owner001",
                        message="SYNTHETIC_QA_ONLY CLI send check",
                        file=None,
                        subject=None,
                        json=True,
                        quiet=False,
                    )
                )
            assert exit_info.value.code == 0
        assert len(cli_lark.requests) == 1
        assert cli_lark.requests[0]["receive_id_type"] == "open_id"
    finally:
        srv.shutdown()
        srv.server_close()


def test_hermes_v016_path_b_feishu_gateway_inbound_dedup_and_restart(tmp_path):
    home_gw = tmp_path / "gw_home"
    sock_path = tmp_path / "sock/gw_facade.sock"
    srv = QuantUdsServer(sock_path, QuantFacadeService(ApprovedJournalRegistry([ApprovedJournalSource("b5", B5_JOURNAL)])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    try:
        client = QuantFacadeClient(sock_path, recipient_scope="owner_dm")
        chat = FeishuChatService(
            facade_client=client,
            allowed_owner_open_ids=frozenset({"ou_owner_001"}),
            owner_chat_bindings={"ou_owner_001": "oc_dm_owner_001"},
        )
        replies: list[dict] = []

        async def _run_gateway_sim() -> None:
            with isolated_hermes_feishu_env(home_gw, allowed_users=("ou_owner_001",)):
                pconfig = PlatformConfig(
                    enabled=True,
                    extra={
                        "app_id": "cli_offline_mock_app",
                        "app_secret": "offline_mock_secret",
                        "domain": "feishu",
                        "connection_mode": "websocket",
                        "text_batch_delay_seconds": 0.01,
                    },
                )
                adapter = FeishuAdapter(pconfig)
                adapter._running = True
                adapter._bot_open_id = "ou_quant_bot_self"
                adapter._text_batch_delay_seconds = 0.0
                adapter._text_batch_split_delay_seconds = 0.0

                async def _mock_get_chat_info(chat_id: str) -> dict:
                    return {"name": "Owner DM", "chat_mode": "p2p", "chat_id": chat_id}

                async def _mock_sender_profile(sender_id, is_bot: bool = False) -> dict:
                    return {"user_id": sender_id.open_id, "user_name": "Owner", "user_id_alt": sender_id.union_id}

                async def _on_msg(msg_event) -> None:
                    res = chat.handle_inbound(
                        FeishuInboundEvent(
                            message_id=msg_event.message_id,
                            chat_id=msg_event.source.chat_id,
                            chat_type="p2p" if str(msg_event.source.chat_type) == "dm" else "group",
                            sender_open_id=msg_event.source.user_id,
                            sender_type="bot" if msg_event.source.is_bot else "user",
                            text=msg_event.text,
                            event_ts_ms=int(msg_event.timestamp.timestamp() * 1000),
                        )
                    )
                    replies.append(res)

                adapter.get_chat_info = _mock_get_chat_info  # type: ignore[method-assign]
                adapter._resolve_sender_profile = _mock_sender_profile  # type: ignore[method-assign]
                adapter.set_message_handler(_on_msg)

                def _make_raw(msg_id: str, chat_id: str, chat_type: str, open_id: str, sender_type: str, text: str):
                    return SimpleNamespace(
                        event=SimpleNamespace(
                            sender=SimpleNamespace(
                                sender_type=sender_type,
                                sender_id=SimpleNamespace(open_id=open_id, user_id=None, union_id="on_owner_001"),
                            ),
                            message=SimpleNamespace(
                                message_id=msg_id,
                                chat_id=chat_id,
                                chat_type=chat_type,
                                message_type="text",
                                content=json.dumps({"text": text}),
                                mentions=None,
                                thread_id=None,
                                root_id=None,
                                parent_id=None,
                                upper_message_id=None,
                            ),
                        )
                    )

                # 1. Authorized p2p DM reaches FeishuChatService
                await adapter._handle_message_event_data(
                    _make_raw("om_gw_1", "oc_dm_owner_001", "p2p", "ou_owner_001", "user", "当前机会")
                )
                # Give tiny event loop yield for batch timer (0s)
                await asyncio.sleep(0.05)

                # 2. Bot-self event rejected by FeishuAdapter._admit
                await adapter._handle_message_event_data(
                    _make_raw("om_gw_bot", "oc_dm_owner_001", "p2p", "ou_quant_bot_self", "bot", "当前机会")
                )
                # 3. Unauthorized group rejected by FeishuAdapter._admit
                await adapter._handle_message_event_data(
                    _make_raw("om_gw_grp", "oc_grp_unauth", "group", "ou_intruder", "user", "当前机会")
                )
                # 4. Duplicate message_id ignored by FeishuAdapter
                await adapter._handle_message_event_data(
                    _make_raw("om_gw_1", "oc_dm_owner_001", "p2p", "ou_owner_001", "user", "当前机会")
                )
                await asyncio.sleep(0.05)

                # Persist dedup state & simulate gateway restart
                adapter._persist_seen_message_ids()
                adapter._running = False
                adapter2 = FeishuAdapter(pconfig)
                adapter2._running = True
                adapter2._bot_open_id = "ou_quant_bot_self"
                adapter2._text_batch_delay_seconds = 0.0
                adapter2._text_batch_split_delay_seconds = 0.0
                adapter2.get_chat_info = _mock_get_chat_info  # type: ignore[method-assign]
                adapter2._resolve_sender_profile = _mock_sender_profile  # type: ignore[method-assign]
                adapter2.set_message_handler(_on_msg)

                # Replay already-seen message after restart -> deduplicated!
                await adapter2._handle_message_event_data(
                    _make_raw("om_gw_1", "oc_dm_owner_001", "p2p", "ou_owner_001", "user", "当前机会")
                )
                # New message after restart -> accepted!
                await adapter2._handle_message_event_data(
                    _make_raw("om_gw_2", "oc_dm_owner_001", "p2p", "ou_owner_001", "user", "策略说明")
                )
                await asyncio.sleep(0.05)

                # 5. Queued inbound replay during brief loop unavailability (reconnect window)
                adapter2._loop = None
                adapter2._on_message_event(
                    _make_raw("om_gw_3", "oc_dm_owner_001", "p2p", "ou_owner_001", "user", "最近信号")
                )
                adapter2._loop = asyncio.get_running_loop()
                for _ in range(20):
                    if len(replies) >= 3:
                        break
                    await asyncio.sleep(0.05)
                adapter2._running = False

        asyncio.run(_run_gateway_sim())
        assert len(replies) == 3
        assert replies[0]["intent"] == "list_active_signals"
        assert replies[1]["intent"] == "get_strategy_summary"
        assert replies[2]["intent"] == "get_signal_history"
        assert all(r["accepted"] is True for r in replies)
    finally:
        srv.shutdown()
        srv.server_close()
