"""Actual Hermes v0.16 agent assembly and a scripted, checked model boundary."""

import asyncio
import json
import os
from importlib.metadata import version
from types import SimpleNamespace

from quant_hermes_feishu_h1.contract import ContractError
from quant_hermes_feishu_h1.explainer import (
    build_explanation_context,
    explain_snapshot,
    validate_explanation_payload,
)
from quant_hermes_feishu_h2b.constants import QUANT_H2B_TOOLSET, V1_MODEL_READONLY_TOOLS
from quant_hermes_feishu_h2b.explainer_gate import ScriptedModelProvider, ScriptedModelResponse

from .facade import PRINCIPAL, SOCKET
from .safety import Blocked, isolated
from .telemetry import correlate

NAMES = sorted(V1_MODEL_READONLY_TOOLS)
PLUGIN = "quant-v080-h2b-readonly"


def configure(home):
    """Load only the H2-B entry-point in a newly created synthetic Hermes home."""
    if version("hermes-agent") != "0.16.0" or version("lark-oapi") != "1.5.3":
        raise Blocked("HERMES_OR_LARK_VERSION_MISMATCH")
    if os.environ.get("HERMES_HOME") != str(home):
        raise Blocked("HERMES_HOME_NOT_ISOLATED")
    os.environ.update(
        QUANT_FACADE_SOCKET=str(SOCKET),
        QUANT_FACADE_PRINCIPAL=PRINCIPAL,
        QUANT_FACADE_SCOPE="owner_dm",
    )
    from hermes_cli import plugins

    plugins.discover_plugins(force=True)
    selected = [p for p in plugins.get_plugin_manager().list_plugins() if p["name"] == PLUGIN]
    if len(selected) != 1 or not selected[0]["enabled"]:
        raise Blocked("H2B_PLUGIN_NOT_SELECTED")


class LocalSession:
    def __init__(self, binding_key, measurements):
        isolated()
        from run_agent import AIAgent

        self.measurements = measurements
        self.session_id = correlate("h3-qa-hermes-session", *binding_key)
        self.agent = AIAgent(
            provider="custom",
            api_mode="chat_completions",
            base_url="http://127.0.0.1:1/v1",
            api_key="offline-unused",
            model="h3-offline-scripted",
            enabled_toolsets=[QUANT_H2B_TOOLSET],
            session_id=self.session_id,
            platform="feishu",
            user_id=binding_key[2],
            chat_id=binding_key[3],
            chat_type="dm",
            gateway_session_key=self.session_id,
            skip_context_files=True,
            skip_memory=True,
            save_trajectories=False,
            quiet_mode=True,
            max_iterations=2,
            tool_delay=0,
        )
        try:
            if self.inventory() != NAMES:
                raise Blocked("HERMES_MODEL_TOOL_INVENTORY_MISMATCH")
        except BaseException:
            self.agent.close()
            raise

    def close(self):
        self.agent.close()

    def inventory(self):
        request = self.agent._build_api_kwargs([{"role": "user", "content": "Offline inventory"}])
        names = sorted(tool["function"]["name"] for tool in request.get("tools", []))
        if names != sorted(self.agent.valid_tool_names) or self.agent.enabled_toolsets != [
            QUANT_H2B_TOOLSET
        ]:
            raise Blocked("HERMES_DISCOVERY_CALLABILITY_MISMATCH")
        return names

    def call(self, name, args, *, turn, index=0):
        """Dispatch one mock model tool call through the configured Hermes session."""
        if name not in NAMES or self.inventory() != NAMES or not isinstance(args, dict):
            raise ContractError("UNAUTHORIZED", "Tool outside frozen QUANT session")
        key = correlate(turn, "agent-tool", index)
        tool_call = SimpleNamespace(
            id=f"call_h3_{index}",
            type="function",
            function=SimpleNamespace(name=name, arguments=json.dumps(args)),
        )
        messages = []
        self.measurements.record("TOOL_BEGIN", key)
        try:
            self.agent._execute_tool_calls(
                SimpleNamespace(tool_calls=[tool_call]),
                messages,
                turn,
            )
            replies = [message for message in messages if message["role"] == "tool"]
            if len(replies) != 1:
                raise ContractError("INTEGRITY_FAILURE", "Hermes tool response count mismatch")
            return json.loads(replies[0]["content"])
        finally:
            self.measurements.record("TOOL_END", key)


def _checked_explanation(snapshot, raw):
    output = validate_explanation_payload(snapshot, raw)
    context = build_explanation_context(snapshot)
    allowed_text = ScriptedModelProvider().generate(context, timeout_ms=1)["summary_zh"]
    fields = {
        "schema_version",
        "card_id",
        "card_version",
        "market_status",
        "referenced_reason_codes",
        "summary_zh",
        "advisory_only",
    }
    # Freeze the one QA explanation template. Loose numeric matching would permit
    # swapping a real TP and SL or claiming an incompatible account state.
    if set(output) != fields or output["summary_zh"] != allowed_text:
        raise ContractError("INTEGRITY_FAILURE", "Scripted text is not the verified template")
    return output


async def explain(session, script, *, snapshot, turn, measurements, timeout_ms=30):
    """A side-effect-free scripted provider. Late output is never attached to a DM."""
    if type(script) is not ScriptedModelResponse or not 1 <= timeout_ms <= 100:
        raise ValueError("INVALID_OFFLINE_MODEL_SCRIPT")
    fallback = explain_snapshot(snapshot).explanation
    if snapshot["is_expired"] or snapshot["freshness_state"] != "CURRENT":
        return None, "EXPIRED_OR_STALE_CORE_CARD"
    tool = script.tool_choice or "get_signal_detail"
    args = (
        script.tool_args if script.tool_args is not None else {"episode_id": snapshot["episode_id"]}
    )
    measurements.record("MODEL_BEGIN", turn, code="MOCK")
    outcome = "FALLBACK"
    try:
        envelope = session.call(tool, args, turn=turn)
        if envelope.get("status") != "OK":
            return fallback, "TOOL_REJECTED"
        target = (envelope.get("data") or {}).get("snapshot") or {}
        if (
            tool != "get_signal_detail"
            or target.get("card_version") != snapshot["card_version"]
            or target.get("card_id") != snapshot["card_id"]
        ):
            return fallback, "WRONG_MODEL_CONTEXT"
        if script.mode in {"timeout", "delayed_cancel"}:
            await asyncio.wait_for(
                asyncio.sleep(max(0.05, script.delay_ms / 1000)), timeout_ms / 1000
            )
            return fallback, "LATE_RESPONSE_DISCARDED"
        if script.delay_ms:
            await asyncio.wait_for(asyncio.sleep(script.delay_ms / 1000), timeout_ms / 1000)
        provider = ScriptedModelProvider(script)
        raw = provider.generate(build_explanation_context(target), timeout_ms=timeout_ms)
        result = _checked_explanation(snapshot, raw)
        outcome = "OK"
        return result, "MOCK_MODEL_VALIDATED"
    except TimeoutError:
        return fallback, "MODEL_TIMEOUT"
    except asyncio.CancelledError:
        outcome = "CANCELLED"
        raise
    except ContractError:
        return fallback, "MODEL_OR_TOOL_INTEGRITY_FAILURE"
    except RuntimeError as exc:
        return fallback, "MODEL_QUOTA" if "quota" in str(exc).lower() else "MODEL_UNAVAILABLE"
    except (ConnectionError, ValueError, TypeError):
        return fallback, "MODEL_UNAVAILABLE_OR_MALFORMED"
    finally:
        measurements.record("MODEL_END", turn, code=outcome)
