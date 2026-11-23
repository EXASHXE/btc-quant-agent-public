"""QUANT V1 strictly bounded 6-tool read-only gateway with out-of-band authenticated caller identity."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from quant_hermes_feishu_h1.contract import TOOL_SCHEMAS, ContractError

from .constants import V1_MODEL_READONLY_TOOLS

_FORBIDDEN_MODEL_ARG_KEYS = frozenset({
    "principal_id",
    "recipient_scope",
    "peer_uid",
    "app_id",
    "tenant_key",
    "open_id",
    "owner_open_id",
    "chat_id",
    "db_path",
    "sql",
    "query",
    "file_path",
    "path",
})


class FacadeCallerProtocol(Protocol):
    """Protocol implemented by H1 QuantFacadeClient (or in-process test adapter)."""

    def call_tool(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
        deadline_ms: int = 2_000,
        recipient_scope: str | list[str] | None = None,
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class AuthenticatedCallerContext:
    """Host-derived immutable caller binding supplied completely outside model-controlled args."""

    principal_id: str
    recipient_scope: str
    app_id: str
    tenant_key: str
    owner_open_id: str
    chat_id: str


def build_model_readonly_schemas() -> dict[str, dict[str, Any]]:
    """Return deep copies of schemas for ONLY the six model-allowed read-only V1 tools."""
    return {name: dict(TOOL_SCHEMAS[name]) for name in V1_MODEL_READONLY_TOOLS}


class QuantV1ReadonlyToolGateway:
    """Enforces 6-tool model inventory, strips/refuses caller spoofing, and disables request_reprice."""

    def __init__(
        self,
        *,
        facade_client: FacadeCallerProtocol,
        caller_context: AuthenticatedCallerContext,
    ) -> None:
        self._client = facade_client
        self._ctx = caller_context
        self._schemas = build_model_readonly_schemas()

    @property
    def caller_context(self) -> AuthenticatedCallerContext:
        return self._ctx

    def advertised_tool_names(self) -> tuple[str, ...]:
        """Exact tool names discoverable by an optional model/explanation planner."""
        return V1_MODEL_READONLY_TOOLS

    def get_tool_definitions(self) -> list[dict[str, Any]]:
        """Return OpenAI-format schema list containing ONLY the 6 model-readable V1 tools."""
        return [{"type": "function", "function": dict(self._schemas[name])} for name in V1_MODEL_READONLY_TOOLS]

    def call_model_tool(self, tool_name: str, model_args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute one of the 6 read-only V1 tools using host-bound identity, refusing all others."""
        if tool_name not in self._schemas:
            raise ContractError(
                "UNAUTHORIZED",
                f"MODEL_TOOL_NOT_ALLOWED: Tool {tool_name!r} is outside the H2-B 6-tool read-only model inventory",
            )
        if model_args is None:
            clean_args: dict[str, Any] = {}
        elif not isinstance(model_args, dict):
            raise ContractError("INVALID_ARGUMENT", "Model tool arguments must be a JSON object")
        else:
            bad_keys = sorted(set(model_args.keys()) & _FORBIDDEN_MODEL_ARG_KEYS)
            if bad_keys:
                raise ContractError(
                    "INVALID_ARGUMENT",
                    f"Model arguments may not supply caller identity, SQL, or file paths: {bad_keys}",
                )
            clean_args = dict(model_args)

        return self._client.call_tool(
            tool_name,
            clean_args,
            recipient_scope=self._ctx.recipient_scope,
        )

    def invoke_human_request_reprice(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        """Explicitly call human-facing request_reprice, which MUST remain disabled in Core (REPRICE_NOT_AUTHORIZED)."""
        payload = dict(args or {})
        payload.setdefault("requested_by", self._ctx.owner_open_id)
        return self._client.call_tool(
            "request_reprice",
            payload,
            recipient_scope=self._ctx.recipient_scope,
        )
