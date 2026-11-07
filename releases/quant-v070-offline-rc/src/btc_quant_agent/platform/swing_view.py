"""Read-only legacy migration and current snapshot display; no history is rewritten."""

from __future__ import annotations

import json
from typing import Any

from .core import fingerprint
from .swing import SCHEMA, INTERVALS, AdvisorySnapshot, State, timestamp

LEGACY_STATES = {
    "NO_SETUP": State.NO_SETUP, "WATCH": State.WATCH, "DISCOVERED": State.WATCH,
    "ARMED": State.WATCH, "ENTRY_ELIGIBLE": State.WATCH,
    "CANCELED": State.INVALIDATED, "CANCELLED": State.INVALIDATED,
    "INVALIDATED": State.INVALIDATED, "EXPIRED": State.EXPIRED,
    "DATA_UNAVAILABLE": State.DATA_UNAVAILABLE, "SOURCE_BLOCKED": State.SOURCE_BLOCKED,
    "ACCOUNT_UNKNOWN": State.ACCOUNT_UNKNOWN, "VETO": State.VETO,
}


def view(raw: dict[str, Any], *, now_ms: int) -> dict[str, Any]:
    timestamp(now_ms)
    if raw.get("schema_version") != SCHEMA:
        legacy = str(raw.get("state", raw.get("status", "UNKNOWN")))
        return {
            "scope": "HISTORICAL_FROZEN / OUT_OF_ACTIVE_SCOPE", "legacy_state": legacy,
            "legacy_schema": raw.get("schema_version", raw.get("schema", "UNKNOWN")),
            "legacy_content_hash": fingerprint(raw), "state": LEGACY_STATES.get(legacy, State.SOURCE_BLOCKED),
            "actionability": "NOT_ACTIONABLE", "source_qualified": False,
            "reasons": ["LEGACY_STATE_IS_NOT_A_NEW_SWING_ACTIVATION"],
        }
    snapshot = AdvisorySnapshot.model_validate_json(json.dumps(raw))
    result = snapshot.model_dump(mode="json")
    result["scope"] = "OFFLINE_SWING_CONTRACT / LT_B_INTEGRATION_PENDING"
    if now_ms < snapshot.decision_ms:
        result.update(state=State.SOURCE_BLOCKED, actionability="NOT_ACTIONABLE",
                      reasons=["DISPLAY_CLOCK_PRECEDES_DECISION"])
    elif snapshot.opportunity and (now_ms >= snapshot.opportunity.expires_ms
                                  or now_ms > snapshot.opportunity.review_deadline_ms):
        result.update(state=State.EXPIRED, actionability="NOT_ACTIONABLE",
                      reasons=["REVIEW_VALIDITY_ELAPSED"])
    elif now_ms // INTERVALS["4H"] * INTERVALS["4H"] > snapshot.trigger_close_ms:
        result.update(state=State.DATA_UNAVAILABLE, actionability="NOT_ACTIONABLE",
                      reasons=["NEWER_COMPLETED_DECISION_BAR_NOT_PROCESSED"])
    return result
