"""Versioned acquisition contract. Policy, documentation and a grant never open a socket."""

from __future__ import annotations

import json
from math import ceil
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..core import fingerprint

VERSION = "L4-ACQUISITION-1"
ROOT = Path(__file__).resolve().parents[4]


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class Endpoint(Model):
    id: str
    provider: Literal["binance", "okx"]
    host: str
    region: str
    market: Literal["USD_M", "SPOT", "OKX_SWAP", "OKX_SPOT"]
    instrument_contract: str
    transport: Literal["REST", "WS"]
    endpoint: str
    authentication: Literal["PUBLIC"] = "PUBLIC"
    native_fields_units: dict[str, str]
    timestamp_field: str | None
    timestamp_semantics: str
    instrument_rules: dict
    native_cadence: str
    completion_rule: str
    freshness_ttl_ms: int = Field(gt=0)
    weight_formula: str
    documented_rate_limits: dict
    websocket: dict
    proposed_cadence_seconds: float = Field(ge=0)
    failover_policy: str
    l23_features: tuple[str, ...]
    bytes_per_message_estimate: int = Field(gt=0)
    messages_per_symbol_second_estimate: float = Field(ge=0)
    storage_estimate_status: str = "ENGINEERING_ASSUMPTION_NOT_OBSERVED"
    retention: dict
    documentation: dict
    permission_terms_review: dict
    status: Literal[
        "OFFLINE_SCHEMA_REVIEWED",
        "UNVERIFIED_NATIVE",
        "SOURCE_CLOCK_BLOCKED",
        "READY_FOR_OWNER_GRANT",
        "DISABLED",
    ]
    enabled_in_proposal: bool = False

    @model_validator(mode="after")
    def safe_identity(self):
        parsed = urlsplit(self.host)
        if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
            raise ValueError("EXACT_PUBLIC_HOST_REQUIRED")
        hosts = {
            "binance": {"fapi.binance.com", "fstream.binance.com", "api.binance.com", "stream.binance.com"},
            "okx": {"www.okx.com", "openapi.okx.com", "ws.okx.com", "eea.okx.com", "us.okx.com"},
        }
        if parsed.hostname not in hosts[self.provider] or parsed.scheme != (
            "https" if self.transport == "REST" else "wss"
        ):
            raise ValueError("UNVERIFIED_OR_PRIVATE_HOST")
        if self.market == "USD_M" and (
            parsed.hostname not in {"fapi.binance.com", "fstream.binance.com"}
            or (self.transport == "REST" and not self.endpoint.startswith("/fapi/v1/"))
        ):
            raise ValueError("USD_M_CANNOT_ALIAS_COIN_M_OR_SPOT")
        if any(
            k in self.endpoint.lower() for k in ("private", "user-data", "listenkey", "/order", "/account")
        ):
            raise ValueError("PRIVATE_OR_ORDER_ENDPOINT_FORBIDDEN")
        return self


class StoragePolicy(Model):
    raw_retention_hours: int = Field(36, ge=1, le=168)
    normalized_retention_hours: int = Field(168, ge=1, le=168)
    raw_quota_bytes: int = Field(16 * 1024**2, gt=0)
    normalized_quota_bytes: int = Field(32 * 1024**2, gt=0)
    total_disk_quota_bytes: int = Field(64 * 1024**2, gt=0)
    symbol_quota_bytes: int = Field(32 * 1024**2, gt=0)
    chunk_bytes: int = Field(512 * 1024, gt=0)
    max_chunks: int = Field(1024, gt=0)
    metadata_reserve_per_chunk: int = Field(8192, ge=4096)
    metadata_base_reserve: int = Field(1024 * 1024, ge=65536)

    @model_validator(mode="after")
    def quotas_consistent(self):
        if self.normalized_retention_hours < self.raw_retention_hours:
            raise ValueError("NORMALIZED_RETENTION_SHORTER_THAN_RAW")
        if (
            self.raw_quota_bytes + self.normalized_quota_bytes + self.metadata_base_reserve
            > self.total_disk_quota_bytes
        ):
            raise ValueError("TOTAL_STORAGE_QUOTA_INCONSISTENT")
        return self


class Policy(Model):
    version: Literal["L4-ACQUISITION-1"] = "L4-ACQUISITION-1"
    mode: Literal["OFFLINE_FABRICATED_ONLY"] = "OFFLINE_FABRICATED_ONLY"
    network_enabled: Literal[False] = False
    symbols: tuple[str, ...] = ("BTCUSDT", "ETHUSDT", "SOLUSDT")
    benchmark: str = "BTCUSDT"
    endpoint_ids: tuple[str, ...]
    synthetic_start_ms: int = Field(1_800_000_000_000, gt=0)
    duration_ms: int = Field(26 * 3_600_000, gt=0)
    ip_weight_per_minute: int = Field(60, gt=0)
    retry_weight_reserve_per_minute: int = Field(10, ge=0)
    endpoint_calls_per_minute: dict[str, int] = Field(
        default_factory=lambda: {
            "binance_usdm_exchange_info": 3,
            "binance_usdm_server_time": 2,
            "binance_usdm_klines_rest": 12,
            "binance_usdm_oi": 6,
            "binance_usdm_premium": 3,
            "binance_usdm_funding_info": 2,
            "binance_usdm_turnover": 1,
            "binance_usdm_bbo_rest": 3,
        }
    )
    controls_per_second: int = Field(2, gt=0)
    max_subscriptions: int = Field(128, gt=0, le=1024)
    max_connections: int = Field(2, gt=0)
    max_reconnects_per_hour: int = Field(3, gt=0)
    max_messages_per_second: int = Field(200, gt=0)
    max_pending_records: int = Field(128, gt=0)
    max_retries: int = Field(3, ge=0, le=5)
    max_backoff_ms: int = Field(60_000, gt=0)
    wall_drift_ms: int = Field(50, ge=0)
    max_clock_uncertainty_ms: int = Field(100, gt=0, le=5000)
    gap_tolerance_ms: int = Field(0, ge=0)
    recovery_distinct_updates: int = Field(2, ge=2)
    full_beta_reference_required: bool = False
    storage: StoragePolicy = Field(default_factory=lambda: StoragePolicy.model_validate({}))

    @model_validator(mode="after")
    def consistent(self):
        if any(type(v) is not int or v <= 0 for v in self.endpoint_calls_per_minute.values()):
            raise ValueError("ENDPOINT_HARD_CAP_INVALID")
        if len(set(self.symbols)) != len(self.symbols) or self.benchmark not in self.symbols:
            raise ValueError("FROZEN_UNIVERSE_INVALID")
        if self.retry_weight_reserve_per_minute >= self.ip_weight_per_minute:
            raise ValueError("RETRY_RESERVE_EXHAUSTS_HARD_BUDGET")
        return self

    @property
    def hash(self):
        return fingerprint(self)

    @property
    def end_ms(self):
        return self.synthetic_start_ms + self.duration_ms


class SourceGrant(Model):
    grant_id: str
    authority: Literal["OWNER_EXACT_SOURCE_GRANT", "FABRICATED_TEST_GRANT"]
    provider: str
    region: str
    market: str
    hosts: tuple[str, ...]
    endpoint_ids: tuple[str, ...]
    fields: dict[str, tuple[str, ...]]
    symbols: tuple[str, ...]
    start_utc_ms: int
    end_utc_ms: int
    ip_weight_per_minute: int
    endpoint_calls_per_minute: dict[str, int]
    controls_per_second: int
    subscriptions: int
    connections: int
    reconnects_per_hour: int
    bytes_total: int
    raw_retention_hours: int
    normalized_retention_hours: int
    output_path: str
    permitted_use_status: Literal["EXPLICITLY_OWNER_CONFIRMED", "FABRICATED_TEST_ONLY"]
    policy_hash: str
    documentation_fingerprint: str
    approval_source_reference: str


def weight(endpoint: Endpoint, params: dict) -> int:
    formula = endpoint.weight_formula
    if formula == "KLINE_LIMIT_TIERS":
        limit = params.get("limit", 500)
        if type(limit) is not int or not 1 <= limit <= 1500:
            raise ValueError("KLINE_LIMIT_INVALID")
        return 1 if limit < 100 else 2 if limit < 500 else 5 if limit <= 1000 else 10
    if formula == "BOOK_SINGLE_2_ALL_5":
        return 2 if params.get("symbol") else 5
    if formula == "PREMIUM_SINGLE_1_ALL_10":
        return 1 if params.get("symbol") else 10
    if formula == "TICKER_SINGLE_1_ALL_40":
        return 1 if params.get("symbol") else 40
    if formula.startswith("FIXED_"):
        return int(formula.removeprefix("FIXED_"))
    if formula == "WS_NOT_REST":
        return 0
    raise ValueError("REQUEST_WEIGHT_UNKNOWN")


def load_policy(path: str | Path) -> Policy:
    return Policy.model_validate(yaml.safe_load(Path(path).read_text()))


def load_catalog(path: str | Path) -> dict[str, Endpoint]:
    raw = json.loads(Path(path).read_text())
    rows = [Endpoint.model_validate(row) for row in raw["endpoints"]]
    if len({row.id for row in rows}) != len(rows):
        raise ValueError("DUPLICATE_ENDPOINT_ID")
    return {row.id: row for row in rows}


def budget_plan(policy: Policy, endpoints: dict[str, Endpoint]) -> dict:
    rows, rest_total, ws_subscriptions, expected_messages, bytes_second = [], 0.0, 0, 0.0, 0.0
    for id in policy.endpoint_ids:
        e = endpoints[id]
        per_symbol = e.instrument_rules.get("request_scope") != "ALL_METADATA"
        symbols = len(policy.symbols) if per_symbol else 1
        if e.transport == "WS":
            channels = int(e.websocket.get("channels_per_symbol", 1))
            subs = channels * symbols
            expected = e.messages_per_symbol_second_estimate * symbols
            ws_subscriptions += subs
            expected_messages += expected
            rows.append(
                {
                    "id": id,
                    "subscriptions": subs,
                    "expected_data_messages_per_second": expected,
                    "weight_per_minute": 0,
                    "observed_message_rate": None,
                }
            )
            bytes_second += expected * e.bytes_per_message_estimate
        else:
            cadence = e.proposed_cadence_seconds
            calls = symbols * 60 / cadence if cadence else 0
            unit = weight(e, {"symbol": policy.symbols[0], "limit": 99})
            rest_total += calls * unit
            bytes_second += calls / 60 * e.bytes_per_message_estimate
            rows.append(
                {
                    "id": id,
                    "weight_per_call": unit,
                    "calls_per_minute": calls,
                    "weight_per_minute": calls * unit,
                    "official_cap_status": e.documented_rate_limits.get("ceiling_verification", "UNKNOWN"),
                }
            )
    projected = ceil(rest_total) + policy.retry_weight_reserve_per_minute
    return {
        "rows": rows,
        "projected_rest_weight_per_minute": rest_total,
        "retry_gap_repair_reserve_per_minute": policy.retry_weight_reserve_per_minute,
        "hard_budget_including_reserve": policy.ip_weight_per_minute,
        "projected_with_reserve": projected,
        "within_proposed_budget": projected <= policy.ip_weight_per_minute,
        "ws_subscriptions": ws_subscriptions,
        "ws_expected_messages_per_second": expected_messages,
        "estimated_raw_bytes_per_second": bytes_second,
        "estimated_26h_raw_bytes": ceil(bytes_second * policy.duration_ms / 1000),
        "estimated_36h_raw_bytes": ceil(bytes_second * 36 * 3600),
        "raw_quota_sufficient_for_estimate": ceil(bytes_second * 36 * 3600) <= policy.storage.raw_quota_bytes,
        "storage_status": "SYNTHETIC_QUOTA_ONLY; real pilot requires explicit larger grant or lower predeclared cadence",
        "estimate_kind": "UNOBSERVED_ENGINEERING_ASSUMPTION; burst and storage qualification required",
        "owner_budget_approved": False,
        "network_activation": False,
    }


def grant_reasons(
    grant: SourceGrant | None,
    policy: Policy,
    catalog: dict[str, Endpoint],
    now: int,
    output: Path,
    *,
    fabricated_test: bool = False,
) -> tuple[str, ...]:
    if grant is None:
        return ("OWNER_SOURCE_GRANT_ABSENT",)
    reasons = []
    if grant.authority != ("FABRICATED_TEST_GRANT" if fabricated_test else "OWNER_EXACT_SOURCE_GRANT"):
        reasons.append("GRANT_AUTHORITY_MISMATCH")
    if grant.permitted_use_status != (
        "FABRICATED_TEST_ONLY" if fabricated_test else "EXPLICITLY_OWNER_CONFIRMED"
    ):
        reasons.append("PERMITTED_USE_NOT_EXPLICIT")
    if not grant.start_utc_ms <= now < grant.end_utc_ms:
        reasons.append("GRANT_NOT_ACTIVE_OR_EXPIRED")
    if grant.start_utc_ms != policy.synthetic_start_ms or grant.end_utc_ms != policy.end_ms:
        reasons.append("GRANT_TIME_SCOPE_MISMATCH")
    if set(grant.endpoint_ids) != set(policy.endpoint_ids) or set(grant.symbols) != set(policy.symbols):
        reasons.append("GRANT_ENDPOINT_OR_SYMBOL_MISMATCH")
    selected = [catalog[id] for id in policy.endpoint_ids]
    if any(
        e.provider != grant.provider
        or e.region != grant.region
        or e.market != grant.market
        or e.host not in grant.hosts
        for e in selected
    ):
        reasons.append("GRANT_PROVIDER_REGION_MARKET_HOST_MISMATCH")
    if any(set(grant.fields.get(e.id, ())) != set(e.native_fields_units) for e in selected):
        reasons.append("GRANT_FIELD_SCOPE_MISMATCH")
    if any(e.id not in grant.endpoint_calls_per_minute for e in selected if e.transport == "REST"):
        reasons.append("GRANT_ENDPOINT_BUDGET_MISSING")
    if any(
        grant.endpoint_calls_per_minute.get(e.id) != policy.endpoint_calls_per_minute.get(e.id)
        for e in selected
        if e.transport == "REST"
    ):
        reasons.append("GRANT_ENDPOINT_HARD_BUDGET_MISMATCH")
    if (
        grant.ip_weight_per_minute != policy.ip_weight_per_minute
        or grant.controls_per_second != policy.controls_per_second
        or grant.subscriptions != policy.max_subscriptions
        or grant.connections != policy.max_connections
        or grant.reconnects_per_hour != policy.max_reconnects_per_hour
    ):
        reasons.append("GRANT_HARD_BUDGET_MISMATCH")
    if (
        grant.bytes_total != policy.storage.total_disk_quota_bytes
        or grant.raw_retention_hours != policy.storage.raw_retention_hours
        or grant.normalized_retention_hours != policy.storage.normalized_retention_hours
    ):
        reasons.append("GRANT_STORAGE_OR_RETENTION_MISMATCH")
    if Path(grant.output_path).resolve() != output.resolve() or grant.policy_hash != policy.hash:
        reasons.append("GRANT_OUTPUT_OR_POLICY_MISMATCH")
    if grant.documentation_fingerprint != fingerprint(selected) or not grant.approval_source_reference:
        reasons.append("GRANT_DOCUMENTATION_OR_APPROVAL_REFERENCE_MISMATCH")
    planned = budget_plan(policy, catalog)
    for row in planned["rows"]:
        if (
            row["id"] in grant.endpoint_calls_per_minute
            and row.get("calls_per_minute", 0) > grant.endpoint_calls_per_minute[row["id"]]
        ):
            reasons.append("GRANT_ENDPOINT_CALL_BUDGET_INSUFFICIENT:" + row["id"])
    if not fabricated_test:
        if any(
            e.documented_rate_limits.get("ceiling_verification") != "CURRENT_OFFICIAL_VERIFIED"
            for e in selected
            if e.transport == "REST"
        ):
            reasons.append("CURRENT_OFFICIAL_RATE_CEILING_UNVERIFIED")
        if any(e.permission_terms_review.get("result") != "EXPLICITLY_CONFIRMED" for e in selected):
            reasons.append("REGION_TERMS_REVIEW_UNVERIFIED")
        if not planned["raw_quota_sufficient_for_estimate"]:
            reasons.append("PROPOSED_REAL_RAW_RETENTION_QUOTA_INSUFFICIENT")
    return tuple(reasons)
