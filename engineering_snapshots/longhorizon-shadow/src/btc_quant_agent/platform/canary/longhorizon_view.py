"""Verified producer-to-view mapping; never acquisition or account authority.

Labels and evidence taxonomy reuse Support Observability's adapter contract.
Native JSON alone is not native origin: the finite runtime must supply its
signature/preflight-bound LongEngine. File import cannot enable a feed.
"""

from __future__ import annotations

import hashlib
import json
import math

from ..core import fingerprint, primitive, dec
from .public_policy import ROOT

SCHEMA = "L4_LONGHORIZON_SNAPSHOT_V1"
VIEW = "L4_SOURCE_SHADOW_VIEW_V1"
MANIFEST = ROOT / "configs/longhorizon/view_producer.json"
SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT")


def historical_source(root):
    """Narrow, read-only adapter for the Owner-accepted SEALED partial Session03.

    This whitelist is historical display evidence, never acquisition authority.
    Ordinary runtime snapshots do not read this path or inherit its grant.
    """
    from pathlib import Path

    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)):
        raise ValueError("HISTORICAL_SOURCE_SYMLINK")
    expected = "0463289f2bc5855a679a4d5b353ff8bf871e81554bb0b4434cfc34b2e280a052"
    seal_bytes = (root / "receipt_seal.json").read_bytes()
    if hashlib.sha256(seal_bytes).hexdigest() != expected:
        raise ValueError("HISTORICAL_SOURCE_NOT_ACCEPTED_SEAL")
    seal = json.loads(seal_bytes)
    for name, digest in seal.items():
        if name not in {"endpoint_policy.json", "launch_reservation.json", "owner_signed_grant.json",
                        "replay_manifest.json", "report.html", "report.json", "source_grant.json",
                        "source_sha256.json", "started.json"}:
            raise ValueError("HISTORICAL_SOURCE_SEAL_SCOPE")
        path = root / name
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("HISTORICAL_SOURCE_MUTATED")
    if (seal["owner_signed_grant.json"] !=
        "7776fa824aeb2fe18f62da3991b4476d17c3f601871a63cd3cf38aef562a83b6"
        or fingerprint(json.loads((root / "source_sha256.json").read_text())) !=
        "4ba50810c855e787aa3ee98393d60b60959275ba141d4b39877b60ce1074e1cc"):
        raise ValueError("HISTORICAL_SOURCE_AUTHORITY_MISMATCH")
    report = json.loads((root / "report.json").read_text())
    if (report.get("session_id") != "L4-NATIVE-CLOCK-V2-FLEX-SESSION03"
        or report.get("exposure") != "PUBLIC_CANARY" or report.get("status") != "PARTIAL"
        or report.get("stop_reason") != "BACKPRESSURE_BLOCKED"
        or any(report.get(k) is not False for k in (
            "source_qualified", "shadow_advisory_qualified", "economically_validated"))):
        raise ValueError("HISTORICAL_SOURCE_SCHEMA_OR_STATUS_MISMATCH")
    return {"schema": "ACCEPTED_SESSION03_PARTIAL_VIEW_V1", "status": "PARTIAL",
        "evidence_kind": "OBSERVED", "authority": "OWNER_ACCEPTED_IMMUTABLE_SESSION03_ONLY",
        "report_sha256": seal["report.json"], "seal_sha256": expected,
        "scope": "Historical clock/BBO-only capture, not current live state or Long-Horizon output",
        "start_utc_ms": report["started_wall_ms"], "end_utc_ms": report["stopped_wall_ms"],
        "receive_span_ms": report["actual_receive_span_ms"],
        "transport": {k: report["transport_metrics"].get(k) for k in (
            "rest_requests", "ws_frames", "ws_raw_messages", "ws_connections")},
        "clock_qualified_bbo_by_symbol": report["clock_validation_evidence"]["distinct_qualified_quotes"],
        "stop_reason": report["stop_reason"], "source_qualified": False,
        "shadow_advisory_qualified": False, "economically_validated": False,
        "market_side": "NOT_EVALUATED_CLOCK_BBO_ONLY", "account_side": "UNKNOWN/ACCOUNT_VETO",
        "current_quote_or_entry_readiness": "UNKNOWN_HISTORICAL_ONLY", "retry_authorized": False}


def producer_identity():
    if MANIFEST.is_symlink():
        raise ValueError("VIEW_PRODUCER_MANIFEST_SYMLINK")
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get("schema_id") != SCHEMA or manifest.get("version") != 1:
        raise ValueError("VIEW_PRODUCER_SCHEMA_UNREVIEWED")
    files = manifest["source_sha256"]
    expected = {
        "src/btc_quant_agent/platform/canary/" + n + ".py"
        for n in ("longhorizon_runtime", "public_runtime", "longhorizon_view")
    }
    if set(files) != expected:
        raise ValueError("VIEW_PRODUCER_SCOPE_MISMATCH")
    for name, digest in files.items():
        p = ROOT / name
        if p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest() != digest:
            raise ValueError("VIEW_PRODUCER_REVISION_MISMATCH")
    return {"schema_id": SCHEMA, "source_sha256": files, "mapping": VIEW}


def core_digest(model):
    # Finalization adds replay results to these two non-action sections only.
    return fingerprint({k: v for k, v in model.items() if k not in ("storage", "three_tier_acceptance")})


def _native_origin(model, producer):
    from .longhorizon import LongScope, verify_signature, source_hashes
    from .longhorizon_runtime import LongEngine

    if type(producer) is not LongEngine or type(producer.scope) is not LongScope:
        raise ValueError("NATIVE_VIEW_REQUIRES_BOUND_PRODUCER")
    scope = producer.scope
    if (
        scope.fabricated_authority
        or producer.exposure != "PUBLIC_CANARY"
        or scope.native_preflight_digest != fingerprint(scope.authorization)
        or scope.authorization.grant.source_sha256_fingerprint != fingerprint(source_hashes())
        or getattr(producer, "last_view_core_digest", None) != core_digest(model)
    ):
        raise ValueError("NATIVE_VIEW_ORIGIN_UNVERIFIED")
    verify_signature(scope.authorization)
    return scope.authorization.grant.authorization_reference


def _time(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("VIEW_INVALID_TIMESTAMP")
    return value


def _count(value):
    if value is not None and (type(value) is not int or value < 0):
        raise ValueError("VIEW_INVALID_COUNT")
    return value


def _price(value):
    if value is not None and (not dec(value).is_finite() or dec(value) <= 0):
        raise ValueError("VIEW_INVALID_PRICE")
    return value


def adapt(model, *, now_ms=None, producer=None):
    """Pure local mapping, explicit UNKNOWN; no source/strategy qualification promotion."""
    model = primitive(model)
    identity = producer_identity()
    manifest = json.loads(MANIFEST.read_text())
    if (
        model.get("snapshot_schema_id") != SCHEMA
        or model.get("producer_identity") != identity
        or model.get("profile") != "L4_LONGHORIZON_V1"
        or set(model) - set(manifest["top_level_fields"])
    ):
        raise ValueError("VIEW_UNVERIFIED_PRODUCER_SCHEMA")
    exposure = model.get("exposure")
    if exposure not in ("SYNTHETIC", "PUBLIC_CANARY"):
        raise ValueError("VIEW_EXPOSURE_UNKNOWN")
    for key in ("source_qualified", "shadow_advisory_qualified", "economically_validated"):
        if model.get(key) is not None and type(model[key]) is not bool:
            raise ValueError("VIEW_INVALID_QUALIFICATION")
    if model.get("economically_validated") or (
        exposure == "SYNTHETIC" and (model.get("source_qualified") or model.get("shadow_advisory_qualified"))
    ):
        raise ValueError("VIEW_UNSUPPORTED_QUALIFICATION_CLAIM")
    authority = "FABRICATED_PRODUCER_FIXTURE" if exposure == "SYNTHETIC" else _native_origin(model, producer)
    kind = "SYNTHETIC" if exposure == "SYNTHETIC" else "OBSERVED"
    asof = _time(model.get("as_of_utc_ms"))
    if asof is None:
        raise ValueError("VIEW_ASOF_REQUIRED")
    now = asof if now_ms is None else _time(now_ms)
    if now < asof:
        raise ValueError("VIEW_FUTURE_SNAPSHOT")
    stale = now - asof > 5000
    clock = model.get("clock_readiness") or {}
    for name in ("probe_age_ms", "uncertainty_ms", "independent_probes"):
        value = clock.get(name)
        if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
            raise ValueError("VIEW_CLOCK_EVIDENCE_INVALID")
    clock_missing = any(
        clock.get(k) is None for k in ("probe_age_ms", "uncertainty_ms", "independent_probes")
    )
    clock_blocked = bool(
        model.get("clock_epoch_failure")
        or clock.get("epoch_fault")
        or (
            not clock_missing
            and (
                clock["probe_age_ms"] > 300000
                or clock["uncertainty_ms"] > 100
                or clock["independent_probes"] < 2
            )
        )
    )
    digest = fingerprint(model)

    def fact(pointer, value, state=None, evidence_kind=kind, reason=None):
        return {
            "value": value,
            "state": state or ("UNKNOWN" if value is None else "AVAILABLE"),
            "evidence_kind": evidence_kind,
            "authority": authority,
            "input_sha256": digest,
            "pointer": pointer,
            "as_of_utc_ms": asof,
            "reason": reason,
        }

    qualifications = {
        key.upper(): fact(
            "/" + key,
            model.get(key),
            "UNKNOWN" if model.get(key) is None else "TRUE" if model[key] else "FALSE",
        )
        for key in ("source_qualified", "shadow_advisory_qualified", "economically_validated")
    }
    symbols = model.get("per_symbol") or {}
    if set(symbols) - set(SYMBOLS):
        raise ValueError("VIEW_SYMBOL_SCOPE_MISMATCH")
    rows = []
    for symbol in SYMBOLS:
        raw = symbols.get(symbol) or {}
        q = raw.get("quote") or {}
        bars = raw.get("bars") or {}
        if set(raw) - {"quote", "bars", "structure", "fields"} or set(q) - {
            "status",
            "reason",
            "bid",
            "ask",
            "native_E",
            "native_T",
            "local_receipt_utc_ms",
            "available_utc_ms",
            "provenance",
            "native_sizes",
            "receipt",
        }:
            raise ValueError("VIEW_NESTED_SCHEMA_UNREVIEWED")
        for key in ("native_E", "native_T", "local_receipt_utc_ms", "available_utc_ms"):
            _time(q.get(key))
        for key in ("bid", "ask"):
            _price(q.get(key))
        if q.get("status") not in (None, "MISSING", "STALE", "QUALIFIED_PRICE_ONLY"):
            raise ValueError("VIEW_QUOTE_STATE_UNSUPPORTED")
        regime = (raw.get("structure") or {}).get("regime")
        if regime not in (
            None,
            "UNKNOWN",
            "RANGE",
            "TREND_UP",
            "TREND_DOWN",
            "HIGH_VOLATILITY",
            "DELEVERAGING_SHOCK",
        ):
            raise ValueError("VIEW_REGIME_UNSUPPORTED")
        if q.get("bid") is not None and q.get("ask") is not None and dec(q["ask"]) < dec(q["bid"]):
            raise ValueError("VIEW_CROSSED_QUOTE")
        for b in bars.values():
            for field in (
                "expected_completed",
                "retained_history_count",
                "missing_count",
                "trailing_contiguous",
            ):
                _count(b.get(field))
        state = (
            "STALE_SNAPSHOT"
            if stale
            else "SOURCE_VETO"
            if clock_blocked
            else "UNKNOWN_CLOCK"
            if clock_missing
            else q.get("status", "UNKNOWN")
        )
        path = "/per_symbol/" + symbol
        rows.append(
            {
                "symbol": symbol,
                "quote": fact(
                    path + "/quote",
                    q or None,
                    state,
                    reason="SNAPSHOT_OLDER_THAN_5S" if stale else q.get("reason"),
                ),
                "bars": fact(path + "/bars", bars or None),
                "warmup": fact("/symbols/" + symbol, (model.get("symbols") or {}).get(symbol)),
                "regime": fact(path + "/structure/regime", (raw.get("structure") or {}).get("regime")),
                "fields": fact(path + "/fields", raw.get("fields")),
            }
        )
    episodes: list[dict] = []
    for item in model.get("advisory_episodes") or []:
        a = item["anchors"]
        symbol = a["symbol"]
        if symbol not in SYMBOLS or a["side"] not in ("LONG", "SHORT"):
            raise ValueError("VIEW_EPISODE_IDENTITY_INVALID")
        if item["status"] not in ("WATCH", "ARMED", "ENTRY_ELIGIBLE", "CANCELLED", "EXPIRED", "DISCOVERED"):
            raise ValueError("VIEW_EPISODE_STATE_INVALID")
        _time(item.get("known_at_utc_ms"))
        _time(a.get("expiry"))
        for field in ("zone_low", "zone_high", "stop", "chase_cap", "target"):
            _price(a.get(field))
        episodes.append(
            fact(
                "/advisory_episodes/" + str(len(episodes)),
                item,
                "SOURCE_VETO"
                if stale or clock_blocked or clock_missing
                else "ACCOUNT_VETO"
                if item["status"] == "ENTRY_ELIGIBLE"
                else item["status"],
                evidence_kind="PROJECTED" if kind == "OBSERVED" else "SYNTHETIC",
                reason="DERIVED_SETUP_NOT_EXCHANGE_ORDER; RANK_AND_ACCOUNT_ENTRY_VETO",
            )
        )
    responses: list[dict] = []
    for item in model.get("response_sensitivity") or []:
        if item.get("response_minutes") not in (1, 3, 5) or item.get("actual_delivery_or_ack") is not False:
            raise ValueError("VIEW_RESPONSE_ASSUMPTION_INVALID")
        if item.get("modeled_fill") is not False:
            raise ValueError("VIEW_NO_FILL_AUTHORITY")
        ack = _time(item.get("modeled_ack_ts"))
        received = _time(item.get("subsequently_received_quote_ts"))
        revalidated = _time(item.get("revalidated_ts"))
        state = item.get("conditional_market_survival", "UNKNOWN")
        if received is not None and (ack is None or received <= ack):
            raise ValueError("VIEW_RESPONSE_QUOTE_NOT_SUBSEQUENT")
        if received is not None and (revalidated is None or received > revalidated):
            raise ValueError("VIEW_RESPONSE_AVAILABILITY_INVALID")
        if state in ("SURVIVED_CONDITIONALLY", "FAILED") and (
            received is None or item.get("quote_chronology") != "POST_MODELED_ACK_NATIVE_AND_RECEIPT_VERIFIED"
        ):
            raise ValueError("VIEW_RESPONSE_NATIVE_CHRONOLOGY_MISSING")
        responses.append(
            fact(
                "/response_sensitivity/" + str(len(responses)),
                item,
                state,
                "PROJECTED" if kind == "OBSERVED" else "SYNTHETIC",
                "Modeled response; actual delivery/ack/fill UNKNOWN",
            )
        )
        responses[-1]["quote_observation"] = fact(
            "/response_sensitivity/" + str(len(responses) - 1) + "/quote_provenance",
            item.get("quote_provenance"), evidence_kind=kind,
            reason="Independent quote evidence, separate from modeled human delay",
        )
        responses[-1]["actual_acknowledgment"] = fact(
            "/response_sensitivity/" + str(len(responses) - 1), None, "UNKNOWN", "NOT_EVALUATED",
            "No actual notification delivery, user acknowledgment or execution observed",
        )
    positions = model.get("user_reported_positions") or {}
    risk = []
    for action in model.get("risk_recommendations") or []:
        position = positions.get(action.get("position_id")) or {}
        timestamp = _time(action.get("decision_ts"))
        if (
            position.get("source") == "USER_REPORTED"
            and position.get("status") != "CLOSED"
            and timestamp is not None
            and position.get("updated_ts") is not None
            and position["updated_ts"] <= timestamp <= asof
            and action.get("execution_status") == "UNCONFIRMED"
        ):
            _price(action.get("suggested_stop"))
            risk.append(action)
    return {
        "view_schema": VIEW,
        "producer_identity": identity,
        "input_sha256": digest,
        "exposure": exposure,
        "evidence_kind": kind,
        "as_of_utc_ms": asof,
        "snapshot_state": "STALE" if stale else "AS_OF_SNAPSHOT_NOT_LIVE_BROWSER",
        "qualifications": qualifications,
        "symbols": rows,
        "episodes": episodes,
        "responses": responses,
        "clock": fact(
            "/clock_estimate",
            {"estimate": model.get("clock_estimate"), "readiness": clock},
            "SOURCE_VETO" if clock_blocked else "UNKNOWN" if clock_missing else "AVAILABLE",
        ),
        "funnel": fact("/opportunity_funnel", model.get("opportunity_funnel")),
        "usage": fact("/source_lifecycle", model.get("source_lifecycle")),
        "retention": fact("/storage", model.get("storage")),
        "market_side": fact(
            "/three_tier_acceptance/TIER2_MARKET_SIDE_SHADOW",
            (model.get("three_tier_acceptance") or {}).get("TIER2_MARKET_SIDE_SHADOW"),
        ),
        "account_side": fact(
            "/risk", None, "ACCOUNT_VETO", reason="CURRENT_ACCOUNT_AND_FILL_AUTHORITY_UNKNOWN"
        ),
        "position_risk": fact(
            "/risk_recommendations",
            risk or None,
            "USER_REPORTED_RISK_ONLY" if risk else "UNKNOWN",
            "PROJECTED" if kind == "OBSERVED" else "SYNTHETIC",
            reason="RECOMMENDATIONS_NEVER_CONFIRM_EXECUTION"
            if risk
            else "NO_SEPARATELY_VERIFIED_USER_REPORTED_POSITION_PROVENANCE",
        ),
        "ranking": {
            "members": 3,
            "required": 10,
            "qualified": False,
            "state": "RANK_COVERAGE_BELOW_TEN_WATCH_ONLY",
        },
        "external_sends": 0,
        "actual_fills": None,
    }
