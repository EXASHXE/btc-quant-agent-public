"""Explicit read-only V1 archive translation. Historical publication time is unknown."""

from __future__ import annotations

from typing import Any

from .policy import require
from .runtime import initial_snapshot
from .store import Stamp, sha
from .wire import FIXTURE, json_body


def view_v1(raw: bytes, expected_sha256: str, observed: Stamp) -> dict[str, Any]:
    require(sha(raw) == expected_sha256, "R1_INPUT_DIGEST_MISMATCH")
    v1 = json_body(raw)
    require(isinstance(v1, dict) and v1.get("schema") == "PERSONAL_PUBLIC_MARKET_SNAPSHOT_V1"
            and v1.get("data_origin") == "DETERMINISTIC_OFFLINE_FIXTURE", "R1_INPUT_NOT_FIXTURE_V1")
    assert isinstance(v1, dict)
    view = initial_snapshot(FIXTURE, v1["scan_id"], tuple(v1["symbols"]))
    view.update(
        data_ready=v1["data_ready"], source_status="DATA_READY" if v1["data_ready"] else "SOURCE_BLOCKED",
        archival=True, historical_replay_eligible=False, archived_original_sha256=expected_sha256,
        archive_observed=observed.data(), durable_availability=None, decision_as_of_venue_ms=None,
        note="V1 archive availability cannot be reconstructed. Original market outcomes remain in the V1 bytes.",
        archived_v1_markets=v1["markets"],
    )
    return view
