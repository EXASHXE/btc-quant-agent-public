"""Hermes v0.16.0 plugin entrypoint exposing ONLY the 6 read-only V1 tools and fail-closed H2-B guards."""

from __future__ import annotations

from typing import Any

from ..constants import QUANT_H2B_TOOLSET, V1_MODEL_READONLY_TOOLS
from .tools import (
    always_on_pre_tool_call_guard,
    handle_quant_h2b_status_command,
    make_readonly_tool_handler,
    pre_gateway_dispatch_guard,
    readonly_tool_schemas,
)


def register(ctx: Any) -> None:
    """Register strictly the 6 read-only QUANT V1 tools, always-on guards, and status command."""
    schemas = readonly_tool_schemas()
    for tool_name in V1_MODEL_READONLY_TOOLS:
        schema = schemas[tool_name]
        ctx.register_tool(
            name=tool_name,
            toolset=QUANT_H2B_TOOLSET,
            schema=schema,
            handler=make_readonly_tool_handler(tool_name),
            description=schema["description"],
        )

    ctx.register_hook("pre_tool_call", always_on_pre_tool_call_guard)
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch_guard)
    ctx.register_command(
        "quant-h2b-status",
        handler=handle_quant_h2b_status_command,
        description="Read-only QUANT v0.8.0 H2-B active signals status via authenticated facade",
    )


__all__ = ["register"]
