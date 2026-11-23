"""Pinned constants and canonical security invariants for QUANT v0.8.0 H2-B."""

from __future__ import annotations

import re

H2B_VERSION = "0.8.0b2"
H2B_TASK_ID = "V080-NEON-H2B-HERMES-FEISHU-READINESS-01"
H2B_CONTROLLER_DISPATCH_SHA256 = "738588a5207bf35d22705e69b7df571c27069caa90bbb5163e6849898ab8af43"

ACCEPTED_H1_PACKAGE = "quant-hermes-feishu-h1"
ACCEPTED_H1_VERSION = "0.8.0.post1"
ACCEPTED_H1_WHEEL_SHA256 = "f8f43e21ea5c9e3155aecea1e0b66313e65c3bf20b3c56e1a8821eb9270e3e2e"
ACCEPTED_H1_MANIFEST_SHA256 = "90ff56de9175191e771b3de613aedf19267213ee842bec6f87b84817038268d4"
ACCEPTED_H1_REFERENCE_MANIFEST_SHA256 = "892e1a4ff908376f1e4b6351dd5aef922fc9a5448b0ae12396426cb49c581bea"

HERMES_EXPECTED_VERSION = "0.16.0"
HERMES_EXPECTED_COMMIT = "c2fa302e933aafc5f995696709a4179f54206c26"
HERMES_EXPECTED_LARK_OAPI_VERSION = "1.5.3"

QUANT_H2B_TOOLSET = "quant_v080_h2b_readonly"

# Strictly the six read-only V1 tools exposed to a model. request_reprice is excluded.
V1_MODEL_READONLY_TOOLS: tuple[str, ...] = (
    "list_active_signals",
    "get_signal_detail",
    "get_market_context",
    "get_latest_reprice",
    "get_signal_history",
    "get_strategy_summary",
)
V1_HUMAN_DISABLED_TOOLS: tuple[str, ...] = ("request_reprice",)

LIVE_CAPABILITY_EXIT_CODE = 3
LIVE_FEISHU_ERROR = "LIVE_FEISHU_GATE_NOT_AUTHORIZED"
LIVE_MODEL_ERROR = "LIVE_MODEL_GATE_NOT_AUTHORIZED"
LIVE_CAPABILITY_ERROR = "LIVE_CAPABILITY_NOT_AUTHORIZED"

FEISHU_TARGET_RE = re.compile(r"^(?:oc|ou|on|chat|open)_[A-Za-z0-9-]+$")
FEISHU_APP_ID_RE = re.compile(r"^cli_[A-Za-z0-9_-]{4,64}$")
FEISHU_TENANT_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{4,64}$")

H2B_CAPABILITIES: tuple[str, ...] = (
    "FEISHU_OUTBOUND_DM_ONCE",
    "FEISHU_INBOUND_DM_BOUNDED",
    "MODEL_EXPLANATION_OPTIONAL",
    "FEISHU_PERSISTENT_GATEWAY_AND_RECURRING",
)
