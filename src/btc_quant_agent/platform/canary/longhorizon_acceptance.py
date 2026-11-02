"""Separate source, market shadow and account readiness observations."""

from __future__ import annotations


def capacity_plan():
    cap = 8 * 1024**3
    # Compression is not assumed. Wire payload alone, before clock/metadata,
    # already exceeds capacity at the permitted transport ceiling.
    return {"raw_cap_bytes": cap, "raw_minimum_hours": 36, "normalized_minimum_hours": 168,
            "estimate_kind": "CONSERVATIVE_UNCOMPRESSED_WIRE_CEILING_LOWER_THAN_RECORD_COST",
            "ws_ceiling_messages_per_second": 200, "ws_max_payload_bytes": 65536,
            "wire_ceiling_48h_bytes": 200 * 65536 * 48 * 3600,
            "wire_ceiling_36h_bytes": 200 * 65536 * 36 * 3600,
            "maximum_average_allocated_bytes_per_second_48h": cap / (48 * 3600),
            "maximum_average_allocated_bytes_per_second_36h": cap / (36 * 3600),
            "maximum_average_allocated_bytes_per_second_48h_plus_2h_audit": cap / (50 * 3600),
            "full_48h_plus_audit_capacity_proven": False,
            "full_window_raw_replay_commitment": "INCOMPLETE_FULL_RAW_REPLAY",
            "post_run_audit_option": {"duration_hours": 2, "activation": "SEPARATE_EXACT_OWNER_APPROVAL_REQUIRED",
                "network": False, "requires_complete_retained_raw": True,
                "requires_measured_peak_allocation_and_headroom": True, "quota_increase": False,
                "retention_increase_implemented": False},
            "stop_policy": "Stop before quota exhaustion; never delete raw before its 36h minimum"}


def replay_outcomes(replay):
    parity = (replay.get("status") == "PARITY_VERIFIED" and replay.get("checked_pairs", 0) > 0
              and replay.get("unpaired_raw_chunks") == 0)
    expired = replay.get("expired_raw_chunks", replay.get("expired_chunks", 0))
    full = parity and expired == 0 and replay.get("complete_retained_raw_replay") is True
    return {"retained_chunk_parity": "PARITY_VERIFIED" if parity else "NOT_VERIFIED",
            "full_window_raw_replay_status": "COMPLETE_CAPTURED_WINDOW" if full else "INCOMPLETE_FULL_RAW_REPLAY",
            "full_48h_coverage_established": False,
            "expired_raw_chunks": expired,
            "chunk_hashes_and_normalized_lineage_preserved": bool(parity and replay.get("manifest")),
            "tombstones_required_for_expiry": True}


def tier_outcomes(model, replay=None):
    native = model.get("exposure") == "PUBLIC_CANARY"
    faults = []
    if model.get("clock_epoch_failure"):
        faults.append("CLOCK_EPOCH_FAULT")
    if model.get("storage", {}).get("fault"):
        faults.append("RESOURCE_CAP_OR_RETENTION_FAULT")
    rows = model.get("source_lifecycle", {})
    if any(row.get("failed", 0) for row in rows.values()):
        faults.append("SOURCE_SCHEMA_OR_TRANSPORT_VETO_OBSERVED")
    if any(b.get("missing_count", 0) for symbol in model.get("per_symbol", {}).values()
           for b in symbol.get("bars", {}).values()):
        faults.append("CLOSED_BAR_COVERAGE_GAPS")
    source = "NOT_EVALUATED" if not native else "SOURCE_VETO" if faults else "UNKNOWN"
    funnel = model.get("opportunity_funnel", {})
    episodes = funnel.get("episodes", 0)
    scans = model.get("L23_scan_count", 0)
    observed = sum(r.get("known_evaluations", 0) for r in model.get("modeled_response_survival", {}).values())
    shadow = ("NOT_EVALUATED" if not native or not scans else "NO_SETUP" if not episodes
              else "SOURCE_VETO" if faults else "OBSERVED_MARKET_SIDE_ONLY" if observed else "UNKNOWN")
    return {"version": "L4_LONGHORIZON_THREE_TIER_ACCEPTANCE_V1",
            "TIER1_SOURCE_INTEGRITY": {"outcome": source, "reasons": faults if native else ["OFFLINE_EXPOSURE"],
                "unverified_fields": ["OI units", "mark/index/funding publication clock", "funding cadence"],
                "requires": ["native E/T, receipt/available/decision/commit clocks", "BBO", "closed native 1m/5m",
                             "source-specific OI/funding/mark/turnover lineage", "gaps/repair/TLS/rates/clock",
                             "resource caps", "reproducible raw/normalized replay"],
                "replay": replay_outcomes(replay or {}), "qualified": False},
            "TIER2_MARKET_SIDE_SHADOW": {"outcome": shadow, "episodes": episodes,
                "observed_modeled_native_quote_responses": observed if native else 0,
                "response_horizons_minutes": [1, 3, 5],
                "requires": ["WATCH/ARMED", "structural confirm/cancel/expiry",
                             "subsequently received native quotes", "veto attribution", "trailing"],
                "entry_filter_veto": "RANK_COVERAGE_BELOW_TEN_WATCH_ONLY", "qualified": False},
            "TIER3_ACCOUNT_EXECUTION_READINESS": {"outcome": "ACCOUNT_VETO", "readiness": "UNKNOWN",
                "missing": ["equity", "margin", "positions", "leverage entitlements", "verified fills"],
                "actual_fills_inferred": False, "economically_validated": False}}
