"""Versioned J contracts. A public REST receipt is not an exchange signature."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from ..core import Candle, fingerprint
from ..native.contract import Strict, digest, require, strict
from ..rc_models import RCPlan, STRATEGY_VERSION
from ..swing import Contract, INTERVALS, SwingPolicy
from ..mvp.models import Sample as LocalSample

POLICY = strict((Path(__file__).parent / "policy.json").read_bytes())
POLICY_HASH = digest(POLICY)
PUBLIC = "J_PUBLIC_MARKET_ADVISORY_V1"
QA = "J_LOCAL_HTTP_QA_V1"
PRODUCT = "J_PUBLIC_S1_V1"


class Blocked(ValueError):
    def __init__(self, reason, status="LIVE_SOURCE_UNAVAILABLE"):
        super().__init__(reason)
        self.status = status


def ensure(condition, reason, status="LIVE_SOURCE_UNAVAILABLE"):
    if not condition:
        raise Blocked(reason, status)


def path_guard(value):
    p = Path(value).absolute()
    ensure(".." not in p.parts, "LIVE_PARENT_TRAVERSAL_FORBIDDEN")
    ensure(not any(x.is_symlink() for x in (p, *p.parents)), "LIVE_SYMLINK_FORBIDDEN")
    ensure(
        not any(
            "holdout" in s.lower()
            or s.lower().startswith("l4-")
            or s in (".git", ".aws", ".agents", ".codex")
            or (s.startswith("lt-program-") and s != "lt-program-j-realtime-advisory-01")
            for s in p.parts
        ),
        "LIVE_PROTECTED_OR_ORIGINAL_PATH_FORBIDDEN",
    )
    return p


def sample():
    a = time.monotonic_ns() // 1000000
    wall = time.time_ns() // 1000000
    b = time.monotonic_ns() // 1000000
    ensure(b - a <= 5, "LIVE_SAMPLE_BRACKET_UNCERTAIN", "LIVE_CLOCK_DEGRADED_BLOCKED")
    return {
        "wall_ms": wall,
        "mono_before_ms": a,
        "mono_after_ms": b,
        "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
    }


def offset_step(a, b):
    return (
        a["boot_id"] != b["boot_id"]
        or b["mono_before_ms"] < a["mono_before_ms"]
        or abs((b["wall_ms"] - b["mono_before_ms"]) - (a["wall_ms"] - a["mono_before_ms"]))
        > 50 + (a["mono_after_ms"] - a["mono_before_ms"]) + (b["mono_after_ms"] - b["mono_before_ms"])
    )


class Access(Strict):
    """Ordinary reviewed operational access record, not a Strict signed grant."""

    schema_version: Literal["J_OPERATIONAL_ACCESS_V1"] = "J_OPERATIONAL_ACCESS_V1"
    status: Literal["VERIFIED"]
    policy_sha256: str
    region: str
    reviewer_reference: str
    eligibility: dict
    advisory_use_and_cache: dict
    holdout_exclusions: dict
    retention_days: int = Field(ge=1, le=30)
    operational_rolling_lookback_only: Literal[True]
    proxy: dict | None = None

    @classmethod
    def load(cls, value):
        p = path_guard(value)
        ensure(p.is_file() and p.stat().st_size <= 65536, "LIVE_ACCESS_RECORD_MISSING")
        try:
            a = cls.model_validate(strict(p.read_bytes()))
        except ValueError as e:
            raise Blocked("LIVE_ACCESS_OR_REGION_NOT_VERIFIED") from e
        ensure(
            a.policy_sha256 == POLICY_HASH and a.region not in ("", "UNKNOWN"), "LIVE_ACCESS_SCOPE_MISMATCH"
        )
        ensure(bool(a.reviewer_reference.strip()), "LIVE_INDEPENDENT_RIGHTS_REVIEW_MISSING")
        for field in (a.eligibility, a.advisory_use_and_cache, a.holdout_exclusions):
            ref = path_guard(p.parent / field["path"])
            ensure(ref.is_file() and ref.stat().st_size <= 1048576, "LIVE_ACCESS_EVIDENCE_MISSING")
            ensure(
                hashlib.sha256(ref.read_bytes()).hexdigest() == field["sha256"],
                "LIVE_ACCESS_EVIDENCE_HASH_MISMATCH",
            )
        exclusions = strict(path_guard(p.parent / a.holdout_exclusions["path"]).read_bytes())
        ensure(
            exclusions.get("metadata_complete") is True
            and isinstance(exclusions.get("excluded_UTC_ms_ranges"), list),
            "LIVE_HOLDOUT_EXCLUSION_METADATA_MISSING",
        )
        for lo, hi in exclusions["excluded_UTC_ms_ranges"]:
            ensure(
                type(lo) is int and type(hi) is int and 0 < lo < hi, "LIVE_HOLDOUT_EXCLUSION_RANGE_INVALID"
            )
        if a.proxy:
            ensure(
                set(a.proxy) == {"host", "port", "permitted_reference"}
                and bool(a.proxy["permitted_reference"])
                and isinstance(a.proxy["host"], str)
                and not any(c in a.proxy["host"] for c in "/@:\\")
                and type(a.proxy["port"]) is int
                and 1 <= a.proxy["port"] <= 65535,
                "LIVE_PROXY_NOT_APPROVED_NO_DIRECT_FALLBACK",
            )
        return a, exclusions


class Bar(Contract):
    candle: Any
    source_id: str
    source_event_ms: None = None
    received_ms: int
    available_ms: int
    durable_ms: int
    revision: int = 0
    exposure: Literal["J_OPERATIONAL_MATH_VIEW"] = "J_OPERATIONAL_MATH_VIEW"

    @property
    def end_ms(self):
        return self.candle.close_time_ms + 1

    def reason(self, cutoff_ms, policy):
        c = self.candle
        size = INTERVALS.get(c.interval)
        if size is None or c.open_time_ms % size or self.end_ms - c.open_time_ms != size:
            return "BAR_BOUNDARY_INVALID"
        if not c.closed:
            return "BAR_NOT_EXPLICITLY_COMPLETED"
        clocks = [self.end_ms, self.received_ms, self.available_ms, self.durable_ms, cutoff_ms]
        if clocks != sorted(clocks) or c.available_at_ms != self.available_ms:
            return "CAUSAL_CLOCK_ORDER_INVALID"
        if self.revision or min(c.open, c.high, c.low, c.close) <= 0:
            return "BAR_REVISION_OR_PRICE_INVALID"
        # REST supplies no event/publication timestamp. Backfill is first observed
        # at receipt, never fabricated as historically available at candle close.
        return None


class Receipt:
    def __init__(self, value):
        self.value = value
        self.bar = Bar(candle=Candle(**value["candle"]), **value["view"])

    @property
    def identity(self):
        return self.value["identity"]

    @property
    def raw_sha256(self):
        return self.value["content_sha256"]

    def model_dump(self, mode="json"):
        return self.value


class Decision(Contract):
    schema_version: Literal["J_PUBLIC_DECISION_V1"] = "J_PUBLIC_DECISION_V1"
    product_version: Literal["J_PUBLIC_S1_V1"] = "J_PUBLIC_S1_V1"
    exposure: Literal["J_PUBLIC_MARKET_ADVISORY_V1", "J_LOCAL_HTTP_QA_V1"]
    contract_sha256: str = POLICY_HASH
    strategy: Literal["trend_pullback"] = "trend_pullback"
    strategy_version: Literal["PROGRAM_A_S1_CAUSAL_V1"] = "PROGRAM_A_S1_CAUSAL_V1"
    symbol: Literal["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    market_state: Literal["NO_SETUP", "WATCH", "ARMED", "DATA_UNAVAILABLE", "SOURCE_BLOCKED"]
    source_qualified: Literal[False] = False
    shadow_advisory_qualified: Literal[False] = False
    economically_validated: Literal[False] = False
    account: Literal["ACCOUNT_UNKNOWN/ACCOUNT_VETO"] = "ACCOUNT_UNKNOWN/ACCOUNT_VETO"
    actionability: Literal["HYPOTHETICAL_MARKET_SIDE_ONLY_ACCOUNT_VETO"] = (
        "HYPOTHETICAL_MARKET_SIDE_ONLY_ACCOUNT_VETO"
    )
    snapshot_sha256: str
    admitted_prefix: tuple[dict, ...]
    review_local: LocalSample
    review_source_bounds_ms: tuple[int, int]
    clock_condition: str
    data_status: str
    trigger_close_ms: int
    decision_ms: int
    scheduled_review_ms: int
    prefix_sha256: str
    receipt_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    diagnostics: dict[str, Any]
    opportunity: RCPlan | None = None
    episode_id: str | None = None
    eligible_planned_r: tuple[int, ...] = ()

    @model_validator(mode="after")
    def integrity(self):
        require(self.contract_sha256 == POLICY_HASH, "J_POLICY_CHANGED")
        require(fingerprint(list(self.admitted_prefix)) == self.prefix_sha256, "J_PREFIX_TAMPER")
        require(
            self.decision_ms == self.review_source_bounds_ms[0] <= self.review_source_bounds_ms[1],
            "J_REVIEW_REFERENCE",
        )
        require(self.scheduled_review_ms == SwingPolicy().next_review(self.decision_ms), "J_SCHEDULED_REVIEW")
        positive = self.market_state in ("WATCH", "ARMED")
        require(positive == (self.opportunity is not None) == (self.episode_id is not None), "J_PLAN_STATE")
        if self.opportunity:
            p = self.opportunity
            require(
                4 <= p.holding_hours <= 48
                and p.symbol == self.symbol
                and p.account_status == "UNKNOWN"
                and p.planned_after_cost_r >= 2
                and p.available_ms <= self.decision_ms < self.scheduled_review_ms < p.expires_ms,
                "J_CAUSAL_GEOMETRY_OR_ACCOUNT",
            )
            require(
                self.episode_id
                == fingerprint(
                    [PRODUCT, STRATEGY_VERSION, self.symbol, self.trigger_close_ms, self.prefix_sha256]
                ),
                "J_EPISODE_ID",
            )
            require(
                self.eligible_planned_r == tuple(r for r in (2, 3, 4) if r <= p.planned_after_cost_r),
                "J_R_LABEL",
            )
            require(self.clock_condition != "CLOCK_DEGRADED_HOLD", "J_HELD_CLOCK_PLAN")
        return self


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
