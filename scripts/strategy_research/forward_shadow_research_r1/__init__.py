"""Prospective BTC 4-24h Shadow Opportunity Engine and Pre-Registration R1.

TASK_ID: V06_GEMINI_GOAL_B_FORWARD_SHADOW_SCIENCE_R1
CONTROLLER_DISPATCH_SHA: e35724f1d1ee7458709e003dfc5673c826c68ffd
"""
from __future__ import annotations

from .account import PaperAccount, ShadowPosition
from .adapter import PublicFeedAdapter
from .contract import BookIntegrityV1, Channel, MarketEventV1, Quality
from .execution import ShadowExecutionEngine, ShadowExecutionSummary
from .registry import (
    SELECTABLE_OBSERVATION_CELLS,
    Horizon,
    SampleReadinessGate,
    SignalFamily,
    compute_policy_fingerprint,
    get_default_hypotheses,
)
from .signals import SignalEngine, SignalProposal

__all__ = [
    "SELECTABLE_OBSERVATION_CELLS",
    "BookIntegrityV1",
    "Channel",
    "Horizon",
    "MarketEventV1",
    "PaperAccount",
    "PublicFeedAdapter",
    "Quality",
    "SampleReadinessGate",
    "ShadowExecutionEngine",
    "ShadowExecutionSummary",
    "ShadowPosition",
    "SignalEngine",
    "SignalFamily",
    "SignalProposal",
    "compute_policy_fingerprint",
    "get_default_hypotheses",
]
