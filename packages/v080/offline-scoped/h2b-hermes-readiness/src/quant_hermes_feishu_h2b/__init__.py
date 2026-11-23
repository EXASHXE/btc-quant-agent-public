"""QUANT v0.8.0 H2-B Hermes + Feishu default-deny readiness package."""

from __future__ import annotations

from .constants import (
    ACCEPTED_H1_VERSION,
    H2B_TASK_ID,
    H2B_VERSION,
    QUANT_H2B_TOOLSET,
    V1_HUMAN_DISABLED_TOOLS,
    V1_MODEL_READONLY_TOOLS,
)

__version__ = H2B_VERSION

__all__ = [
    "ACCEPTED_H1_VERSION",
    "H2B_TASK_ID",
    "H2B_VERSION",
    "QUANT_H2B_TOOLSET",
    "V1_HUMAN_DISABLED_TOOLS",
    "V1_MODEL_READONLY_TOOLS",
    "__version__",
]
