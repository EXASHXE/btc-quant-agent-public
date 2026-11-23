"""Hermes v0.16.0 H2-B plugin handlers: strictly 6 read-only V1 tools and fail-closed always-on guards."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from quant_hermes_feishu_h1.contract import (
    CONTRACT_ID,
    EVIDENCE_UNKNOWN,
    TOOL_SCHEMAS,
    ContractError,
    build_response_envelope,
    canonical_json,
)
from quant_hermes_feishu_h1.facade import QuantFacadeClient

from ..constants import QUANT_H2B_TOOLSET, V1_MODEL_READONLY_TOOLS
from ..inbound_boundary import H2BInboundBoundary, InboundBinding, InboundDedupStore

_DEFAULT_SOCKET_ENV = "QUANT_FACADE_SOCKET"
_DEFAULT_PRINCIPAL_ENV = "QUANT_FACADE_PRINCIPAL"
_DEFAULT_SCOPE_ENV = "QUANT_FACADE_SCOPE"
_INBOUND_BINDING_JSON_ENV = "QUANT_H2B_INBOUND_BINDING_JSON"
_INBOUND_DEDUP_DB_ENV = "QUANT_H2B_INBOUND_DEDUP_DB"

_RUNTIME_BOUNDARY_LOCK = False
_CONFIGURED_BOUNDARY: H2BInboundBoundary | None = None


def configure_plugin_inbound_boundary(boundary: H2BInboundBoundary | None) -> None:
    """Attach (or clear) the active H2-B inbound boundary used by ``pre_gateway_dispatch_guard``."""
    global _CONFIGURED_BOUNDARY
    _CONFIGURED_BOUNDARY = boundary


def _load_inbound_boundary() -> tuple[H2BInboundBoundary | None, str | None]:
    if _CONFIGURED_BOUNDARY is not None:
        return _CONFIGURED_BOUNDARY, None
    raw_json = os.environ.get(_INBOUND_BINDING_JSON_ENV, "").strip()
    dedup_path = os.environ.get(_INBOUND_DEDUP_DB_ENV, "").strip()
    if not raw_json or not dedup_path:
        return None, "H2B_INBOUND_BINDING_NOT_CONFIGURED"
    try:
        cfg = json.loads(raw_json)
        binding = InboundBinding(
            app_id=str(cfg["app_id"]),
            tenant_key=str(cfg["tenant_key"]),
            allowed_owner_open_ids=frozenset(cfg["allowed_owner_open_ids"]),
            owner_chat_bindings=dict(cfg["owner_chat_bindings"]),
            bot_open_id=str(cfg.get("bot_open_id") or "ou_quant_bot_self"),
            connection_mode=str(cfg.get("connection_mode") or "websocket"),
            allow_webhook_mode=bool(cfg.get("allow_webhook_mode", False)),
            verification_token=str(cfg.get("verification_token") or ""),
            encrypt_key=str(cfg.get("encrypt_key") or ""),
        )
        return H2BInboundBoundary(binding=binding, dedup_store=InboundDedupStore(Path(dedup_path))), None
    except Exception as exc:  # noqa: BLE001
        return None, f"INVALID_INBOUND_BINDING:{exc}"


def _build_client_from_env() -> QuantFacadeClient:
    sock = os.environ.get(_DEFAULT_SOCKET_ENV, "").strip()
    if not sock:
        raise ContractError("SOURCE_UNAVAILABLE", f"{_DEFAULT_SOCKET_ENV} is not configured")
    principal = os.environ.get(_DEFAULT_PRINCIPAL_ENV, "hermes_quant_plugin").strip() or "hermes_quant_plugin"
    scope = os.environ.get(_DEFAULT_SCOPE_ENV, "owner_dm").strip() or "owner_dm"
    return QuantFacadeClient(Path(sock), principal_id=principal, recipient_scope=scope)


def make_readonly_tool_handler(tool_name: str, *, client: QuantFacadeClient | None = None):
    """Build a Hermes tool handler restricted strictly to the 6 read-only V1 tools."""
    if tool_name not in V1_MODEL_READONLY_TOOLS:
        raise ValueError(f"Refused to create H2-B model handler for non-readonly tool: {tool_name!r}")

    forbidden_identity_keys = frozenset({"principal_id", "recipient_scope", "peer_uid", "sql", "query", "db_path"})

    def _handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
        del kwargs
        try:
            clean_args = dict(args) if isinstance(args, dict) else {}
            bad = sorted(set(clean_args.keys()) & forbidden_identity_keys)
            if bad:
                raise ContractError("INVALID_ARGUMENT", f"Model cannot override identity/path keys: {bad}")
            active_client = client if client is not None else _build_client_from_env()
            resp = active_client.call_tool(tool_name, clean_args)
            return canonical_json(resp)
        except ContractError as exc:
            return canonical_json(
                build_response_envelope(
                    request_id="h2b-plugin-error",
                    generated_at_ms=0,
                    status="ERROR",
                    server_as_of_ms=None,
                    source_evidence_class=EVIDENCE_UNKNOWN,
                    error=exc.to_dict(),
                )
            )
        except Exception as exc:  # noqa: BLE001
            safe = ContractError("INTERNAL_REDACTED", str(exc))
            return canonical_json(
                build_response_envelope(
                    request_id="h2b-plugin-internal-error",
                    generated_at_ms=0,
                    status="ERROR",
                    server_as_of_ms=None,
                    source_evidence_class=EVIDENCE_UNKNOWN,
                    error=safe.to_dict(),
                )
            )

    _handler.__name__ = f"quant_h2b_v1_{tool_name}"
    return _handler


def always_on_pre_tool_call_guard(
    tool_name: str,
    args: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, str] | None:
    """ALWAYS-ON sandbox hook blocking every tool outside the 6 read-only V1 tools.

    Prevents ``handle_function_call`` / registry dispatch from invoking ``request_reprice``,
    ``terminal``, ``send_message``, ``read_file``, ``write_file``, ``browser_*``, ``execute_code``,
    ``tool_search``, or any other built-in/plugin tool even if present in Hermes's global registry.
    """
    del args, kwargs
    if tool_name in V1_MODEL_READONLY_TOOLS:
        return None
    return {
        "action": "block",
        "message": (
            f"Tool '{tool_name}' is blocked by QUANT H2-B fail-closed boundary; "
            f"only the 6 {CONTRACT_ID} read-only tools ({', '.join(V1_MODEL_READONLY_TOOLS)}) are callable."
        ),
    }


def pre_gateway_dispatch_guard(event: Any = None, **kwargs: Any) -> dict[str, Any]:
    """Fail-closed Hermes gateway hook requiring verified app/tenant/owner/chat/event_id/p2p/text."""
    del kwargs
    boundary, err = _load_inbound_boundary()
    if boundary is None:
        return {"action": "skip", "reason": err or "H2B_INBOUND_BINDING_NOT_CONFIGURED"}
    decision = boundary.check_hermes_message_event(event)
    if decision.get("action") == "allow":
        return {"action": "allow"}
    return {"action": "skip", "reason": str(decision.get("reason") or "UNVERIFIED_FEISHU_EVENT")}


def handle_quant_h2b_status_command(raw_args: str = "") -> str:
    """Slash command ``/quant-h2b-status`` returning read-only facade active signals summary."""
    del raw_args
    try:
        client = _build_client_from_env()
        resp = client.call_tool("list_active_signals", {"limit": 10})
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"QUANT H2-B facade unavailable: {exc}"}, ensure_ascii=False)


def readonly_tool_schemas() -> dict[str, dict[str, Any]]:
    return {name: dict(TOOL_SCHEMAS[name]) for name in V1_MODEL_READONLY_TOOLS}


__all__ = [
    "QUANT_H2B_TOOLSET",
    "always_on_pre_tool_call_guard",
    "configure_plugin_inbound_boundary",
    "handle_quant_h2b_status_command",
    "make_readonly_tool_handler",
    "pre_gateway_dispatch_guard",
    "readonly_tool_schemas",
]
