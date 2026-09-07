"""Label-free required-input contract for corrected H39 validation."""

from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

H39_INPUT_CONTRACT_VERSION = "H39_REQUIRED_INPUT_V1"
H39_SLOT_MS = 15 * 60_000
H39_FEATURE_FIELDS = (
    "m1_trade_imbalance_5m",
    "m2_trade_imbalance_15m",
    "m3_ofi_5m",
    "m4_top5_depth_imbalance_5m",
    "m5_top20_depth_imbalance_5m",
    "m6_microprice_deviation_1m",
    "m7_pressure_agreement",
    "m8_pressure_divergence",
)
H39_BASELINE_FIELDS = (
    "trailing_return_15m",
    "trailing_return_60m",
    "trailing_atr_ratio_15m",
    "trailing_atr_15m",
    "decision_close_price",
)


@dataclass(frozen=True)
class H39InputCheck:
    formal_test_ready: bool
    baseline_complete: bool
    reasons: tuple[str, ...]


def _mapping(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    return dict(row)


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _json_object(value: Any, expected: type[list[Any] | dict[str, Any]]) -> Any:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, expected) else None


def check_h39_required_input(row: Mapping[str, Any] | Any) -> H39InputCheck:
    """Validate every field needed before labels may be loaded.

    No future price, return, or direction-label field is accessed here.
    """
    r = _mapping(row)
    reasons: list[str] = []
    if not bool(r.get("eligible")):
        reasons.append("MICROSTRUCTURE_INELIGIBLE")

    missing_features = [field for field in H39_FEATURE_FIELDS if not _finite(r.get(field))]
    if missing_features:
        reasons.append("MICROSTRUCTURE_FEATURE_MISSING_OR_NONFINITE")

    baseline_complete = all(_finite(r.get(field)) for field in H39_BASELINE_FIELDS)
    if not baseline_complete:
        reasons.append("BASELINE_MISSING_OR_NONFINITE")
    else:
        atr = float(r["trailing_atr_15m"])
        price = float(r["decision_close_price"])
        ratio = float(r["trailing_atr_ratio_15m"])
        if atr <= 0.0 or price <= 0.0 or ratio <= 0.0:
            baseline_complete = False
            reasons.append("BASELINE_NON_POSITIVE_SCALE")
        elif not math.isclose(ratio, atr / price, rel_tol=1e-7, abs_tol=1e-12):
            baseline_complete = False
            reasons.append("ATR_RATIO_INCONSISTENT")

    if int(r.get("book_sample_count_15m") or 0) <= 0:
        reasons.append("BOOK_EVIDENCE_MISSING")
    if int(r.get("trade_count_15m") or 0) <= 0:
        reasons.append("TRADE_EVIDENCE_MISSING")

    try:
        slot = int(r["decision_close_ms"])
        timing_ok = (
            slot % H39_SLOT_MS == 0
            and int(r.get("feature_window_start_ms") or 0) == slot - H39_SLOT_MS
            and int(r.get("feature_window_end_ms") or 0) == slot
            and int(r.get("reference_time_ms") or 0) == slot + 60_000
            and int(r.get("target_60m_ms") or 0) == slot + 60 * 60_000
            and int(r.get("target_240m_ms") or 0) == slot + 240 * 60_000
        )
    except (KeyError, TypeError, ValueError):
        timing_ok = False
    if not timing_ok:
        reasons.append("TIMING_CONTRACT_INVALID")

    slot_utc = r.get("slot_utc")
    try:
        parsed = datetime.fromisoformat(str(slot_utc))
        utc_ok = (
            parsed.tzinfo is not None and int(parsed.astimezone(UTC).timestamp() * 1000) == slot
        )
    except (TypeError, ValueError, UnboundLocalError):
        utc_ok = False
    if not utc_ok:
        reasons.append("SLOT_UTC_INVALID")

    partitions = _json_object(r.get("source_partitions"), list)
    hashes = _json_object(r.get("source_partition_hashes"), dict)
    provenance_ok = bool(
        partitions
        and hashes
        and all(
            isinstance(name, str) and name and isinstance(hashes.get(name), str) and hashes[name]
            for name in partitions
        )
        and r.get("protocol_hash")
        and r.get("clarification_hash")
        and r.get("code_version_sha")
        and r.get("input_contract_version") == H39_INPUT_CONTRACT_VERSION
    )
    if not provenance_ok:
        reasons.append("PROVENANCE_OR_CONTRACT_IDENTITY_INVALID")

    return H39InputCheck(
        formal_test_ready=not reasons,
        baseline_complete=baseline_complete,
        reasons=tuple(dict.fromkeys(reasons)),
    )


def summarize_h39_required_inputs(rows: Sequence[Mapping[str, Any] | Any]) -> dict[str, Any]:
    checks = [check_h39_required_input(row) for row in rows]
    counter: Counter[str] = Counter(reason for check in checks for reason in check.reasons)
    micro_eligible = sum(bool(_mapping(row).get("eligible")) for row in rows)
    baseline_complete = sum(
        bool(_mapping(row).get("eligible")) and check.baseline_complete
        for row, check in zip(rows, checks, strict=True)
    )
    formal_ready = sum(check.formal_test_ready for check in checks)
    return {
        "input_contract_version": H39_INPUT_CONTRACT_VERSION,
        "raw_slots": len(rows),
        "microstructure_eligible_slots": micro_eligible,
        "baseline_complete_slots": baseline_complete,
        "formal_test_ready_slots": formal_ready,
        "excluded_by_reason": dict(sorted(counter.items())),
        "all_formal_test_ready": formal_ready == len(rows),
        "checks": [asdict(check) for check in checks],
    }
