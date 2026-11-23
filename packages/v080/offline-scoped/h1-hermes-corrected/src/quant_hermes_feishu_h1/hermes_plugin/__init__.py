"""Hermes Agent v0.16.0 plugin entrypoint exposing ONLY the seven Contract V1 tools."""

from __future__ import annotations

from typing import Any

from .schemas import QUANT_TOOLSET, TOOL_SCHEMAS, V1_ALL_TOOLS
from .tools import (
    handle_quant_status_command,
    make_tool_handler,
    pre_gateway_dispatch_guard,
    pre_tool_call_sandbox_guard,
)


def register(ctx: Any) -> None:
    """Register the 7 Contract V1 QUANT tools, sandbox hooks, and slash command with Hermes."""
    for tool_name in V1_ALL_TOOLS:
        schema = TOOL_SCHEMAS[tool_name]
        ctx.register_tool(
            name=tool_name,
            toolset=QUANT_TOOLSET,
            schema=schema,
            handler=make_tool_handler(tool_name),
            description=schema["description"],
        )

    ctx.register_hook("pre_tool_call", pre_tool_call_sandbox_guard)
    ctx.register_hook("pre_gateway_dispatch", pre_gateway_dispatch_guard)
    ctx.register_command(
        "quant-status",
        handler=handle_quant_status_command,
        description="Read-only QUANT V1 active signals status via authenticated facade",
    )


__all__ = ["register"]
