"""Hermes v0.16.0 plugin handlers: UDS facade calls only, never direct QUANT SQLite or network."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from ..contract import (
    CONTRACT_ID,
    EVIDENCE_UNKNOWN,
    V1_ALL_TOOLS,
    ContractError,
    build_response_envelope,
    canonical_json,
)
from ..facade import QuantFacadeClient

_DEFAULT_SOCKET_ENV = "QUANT_FACADE_SOCKET"
_DEFAULT_PRINCIPAL_ENV = "QUANT_FACADE_PRINCIPAL"
_DEFAULT_SCOPE_ENV = "QUANT_FACADE_SCOPE"
_STRICT_SANDBOX_ENV = "QUANT_HERMES_STRICT_SANDBOX"


def _build_client_from_env() -> QuantFacadeClient:
    sock = os.environ.get(_DEFAULT_SOCKET_ENV, "").strip()
    if not sock:
        raise ContractError("SOURCE_UNAVAILABLE", f"{_DEFAULT_SOCKET_ENV} is not configured")
    principal = os.environ.get(_DEFAULT_PRINCIPAL_ENV, "hermes_quant_plugin").strip() or "hermes_quant_plugin"
    scope = os.environ.get(_DEFAULT_SCOPE_ENV, "owner_dm").strip() or "owner_dm"
    return QuantFacadeClient(Path(sock), principal_id=principal, recipient_scope=scope)


def make_tool_handler(tool_name: str, *, client: QuantFacadeClient | None = None):
    """Build a Hermes-compliant tool handler ``(args: dict, **kwargs) -> str``."""
    if tool_name not in V1_ALL_TOOLS:
        raise ValueError(f"Refused to create handler for non-V1 tool: {tool_name!r}")

    def _handler(args: dict[str, Any] | None = None, **kwargs: Any) -> str:
        del kwargs
        try:
            active_client = client if client is not None else _build_client_from_env()
            clean_args = dict(args) if isinstance(args, dict) else {}
            resp = active_client.call_tool(tool_name, clean_args)
            return canonical_json(resp)
        except ContractError as exc:
            return canonical_json(
                build_response_envelope(
                    request_id="plugin-error",
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
                    request_id="plugin-internal-error",
                    generated_at_ms=0,
                    status="ERROR",
                    server_as_of_ms=None,
                    source_evidence_class=EVIDENCE_UNKNOWN,
                    error=safe.to_dict(),
                )
            )

    _handler.__name__ = f"quant_v1_{tool_name}"
    return _handler


def pre_tool_call_sandbox_guard(tool_name: str, args: dict[str, Any] | None = None, **kwargs: Any) -> dict[str, str] | None:
    """Block privileged non-V1 Hermes built-in tools when QUANT_HERMES_STRICT_SANDBOX=1."""
    del args, kwargs
    if os.environ.get(_STRICT_SANDBOX_ENV, "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if tool_name in V1_ALL_TOOLS:
        return None
    return {
        "action": "block",
        "message": (
            f"Tool '{tool_name}' is blocked in QUANT H1 strict sandbox; "
            f"only {CONTRACT_ID} tools ({', '.join(V1_ALL_TOOLS)}) are permitted."
        ),
    }


def pre_gateway_dispatch_guard(event: Any = None, **kwargs: Any) -> dict[str, str] | None:
    """Defense-in-depth gateway inbound filter: private DM + allowlisted owner only when enabled."""
    del kwargs
    if os.environ.get("QUANT_FEISHU_GATEWAY_GUARD", "").strip().lower() not in {"1", "true", "yes", "on"}:
        return None
    if event is None:
        return {"action": "skip", "reason": "missing_event"}
    source = getattr(event, "source", None)
    if source is None:
        return {"action": "skip", "reason": "missing_source"}
    chat_type = str(getattr(source, "chat_type", "") or "").lower()
    if chat_type not in {"dm", "p2p", "private"}:
        return {"action": "skip", "reason": f"non_private_chat_type:{chat_type}"}
    allowed = {
        item.strip()
        for item in os.environ.get("QUANT_FEISHU_ALLOWED_OWNERS", "").split(",")
        if item.strip()
    }
    user_id = str(getattr(source, "user_id", "") or "")
    if not allowed or user_id not in allowed:
        return {"action": "skip", "reason": f"unauthorized_owner:{user_id or 'empty'}"}
    return {"action": "allow"}


def handle_quant_status_command(raw_args: str = "") -> str:
    """Slash command handler for ``/quant-status`` in CLI or gateway sessions."""
    del raw_args
    try:
        client = _build_client_from_env()
        resp = client.call_tool("list_active_signals", {"limit": 10})
        return json.dumps(resp, ensure_ascii=False, indent=2)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": f"QUANT facade unavailable: {exc}"}, ensure_ascii=False)
