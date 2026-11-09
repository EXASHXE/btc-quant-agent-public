"""Explicit RC snapshot version; never activates a legacy or native snapshot."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import Field, JsonValue, model_validator

from .core import fingerprint
from .swing import Contract, INTERVALS, Opportunity, SwingPolicy, timestamp

PRODUCT = "V070_PROGRAM_A_OFFLINE_RC_V1"
SCHEMA = "V070_PROGRAM_A_SNAPSHOT_V1"
STRATEGY_VERSION = "PROGRAM_A_S1_CAUSAL_V1"
CONTRACT_SHA256 = "0487e72fe8c655ee457d6779e9e9c7b98630d279d955a6e0f3793534dbdc1d13"


def frozen_contract():
    data = (Path(__file__).resolve().parents[1] / "resources" / "contracts/rc_v1.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != CONTRACT_SHA256:
        raise ValueError("FROZEN_RC_CONTRACT_CHANGED")
    return json.loads(data)


class RCPlan(Opportunity):
    """RC extension of the inherited geometry; original LT-A 8h minimum is unchanged."""

    holding_hours: int = Field(default=24, ge=4, le=120)


class RCDecision(Contract):
    schema_version: Literal["V070_PROGRAM_A_SNAPSHOT_V1"] = SCHEMA
    product_version: Literal["V070_PROGRAM_A_OFFLINE_RC_V1"] = PRODUCT
    contract_sha256: Literal["0487e72fe8c655ee457d6779e9e9c7b98630d279d955a6e0f3793534dbdc1d13"] = CONTRACT_SHA256
    exposure: Literal["SYNTHETIC"] = "SYNTHETIC"
    strategy: Literal["trend_pullback"] = "trend_pullback"
    strategy_version: Literal["PROGRAM_A_S1_CAUSAL_V1"] = STRATEGY_VERSION
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    market_state: Literal["NO_SETUP", "WATCH", "ARMED", "DATA_UNAVAILABLE", "SOURCE_BLOCKED"]
    account: Literal["ACCOUNT_UNKNOWN/ACCOUNT_VETO"] = "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    actionability: Literal["NOT_ACTIONABLE_ACCOUNT_VETO"] = "NOT_ACTIONABLE_ACCOUNT_VETO"
    source_type: Literal["SYNTHETIC_COMPLETED_CANDLES"] = "SYNTHETIC_COMPLETED_CANDLES"
    source_qualified: Literal[False] = False
    shadow_advisory_qualified: Literal[False] = False
    economically_validated: Literal[False] = False
    trigger_close_ms: int
    decision_ms: int
    scheduled_review_ms: int
    prefix_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_ids: tuple[str, ...]
    reasons: tuple[str, ...] = Field(min_length=1)
    confidence: Literal["RULE_EVIDENCE_ONLY_NOT_PROBABILITY"] = "RULE_EVIDENCE_ONLY_NOT_PROBABILITY"
    gaps: tuple[str, ...] = ("NO_NATIVE_SOURCE", "ACCOUNT_UNVERIFIED", "NO_EXECUTABLE_QUOTE", "NO_ECONOMIC_EVIDENCE")
    diagnostics: dict[str, JsonValue]
    opportunity: RCPlan | None = None
    episode_id: str | None = None
    eligible_planned_r: tuple[int, ...] = ()

    @model_validator(mode="after")
    def consistency(self):
        for t in (self.trigger_close_ms, self.decision_ms, self.scheduled_review_ms):
            timestamp(t)
        if self.scheduled_review_ms != SwingPolicy().next_review(self.decision_ms):
            raise ValueError("REVIEW_CLOCK_POLICY_MISMATCH")
        positive = self.market_state in ("WATCH", "ARMED")
        if positive != (self.opportunity is not None) or positive != (self.episode_id is not None):
            raise ValueError("RC_CANDIDATE_STATE_MISMATCH")
        if self.opportunity:
            o = self.opportunity
            identity = fingerprint([PRODUCT, STRATEGY_VERSION, self.symbol, self.trigger_close_ms,
                                    self.prefix_sha256])
            if self.episode_id != identity or o.symbol != self.symbol:
                raise ValueError("RC_EPISODE_IDENTITY_MISMATCH")
            if (o.account_status != "UNKNOWN" or o.setup_close_ms != self.trigger_close_ms
                    or o.available_ms > self.decision_ms
                    or self.trigger_close_ms % INTERVALS["4H"]
                    or not 0 <= self.decision_ms - self.trigger_close_ms <= 300000
                    or not self.decision_ms < self.scheduled_review_ms < o.expires_ms
                    or self.scheduled_review_ms > o.review_deadline_ms
                    or o.planned_after_cost_r < 2):
                raise ValueError("RC_CAUSAL_RISK_OR_ACCOUNT_VETO_INVALID")
            eligible = tuple(r for r in (2, 3, 4) if r <= o.planned_after_cost_r)
            if self.eligible_planned_r != eligible:
                raise ValueError("RC_PLANNED_R_LABEL_MISMATCH")
        elif self.eligible_planned_r:
            raise ValueError("RC_NEGATIVE_HAS_R_LABEL")
        return self


class BShadowState(Contract):
    """New append-only B lifecycle envelope; old Program A snapshots remain V1."""
    schema_version: Literal["V070_B_SHADOW_STATE_V1"] = "V070_B_SHADOW_STATE_V1"
    state_id: str
    episode_id: str | None = None
    decision_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    revision: int = Field(ge=0)
    status: Literal["NO_SETUP", "WATCH", "ARMED", "CANCELED", "INVALIDATED", "EXPIRED",
                    "SOURCE_BLOCKED", "UNKNOWN", "NO_CHASE", "MISSED_ENTRY", "NO_FILL", "TIME_STOP"]
    source_status: Literal["SYNTHETIC", "NATIVE_UNQUALIFIED", "UNKNOWN"]
    reason: str = Field(min_length=1)
    at_ms: int = Field(gt=0)
    account: Literal["ACCOUNT_UNKNOWN/ACCOUNT_VETO"] = "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    actual_fill: Literal[False] = False
