"""Content-addressed, source-anchored H40 Discovery scientific verification.

This module does not run candidate features or authorize Discovery.  It verifies
the sealed decision/outcome evidence after an independently authorized producer
has materialized it.  All scientific decisions are recomputed from bound rows.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from bisect import bisect_right
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn, cast
from weakref import WeakKeyDictionary

import numpy as np

from ..research_contract.canonical import canonical_json, canonical_sha256
from .guards import H40GuardError, H40ProtectedSurfaceGuard, H40ReasonCode
from .lifecycle_authority import (
    DISCOVERY_PROVENANCE_CONTRACT_HASH,
    DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH,
    H40CandidateResultEntry,
    H40CandidateVerification,
    H40DiscoveryAuthorizationReceipt,
    H40DiscoveryResultEvidence,
    H40RuntimeSnapshotSeal,
    H40WFFoldResultEntry,
    H40WFValidationResultEvidence,
)
from .protocol_authority import compute_protocol_authority_hash
from .search_space import materialize_h40_search_space_production
from .source_manifest import H40SourceStatus
from .split_manifest import H40SplitManifest

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_L = 168
_M = 10_000
_FAMILIES = (
    "D1_TREND_CONTINUATION",
    "D2_BREAKOUT_CONTINUATION",
    "D3_FAILED_MOVE_REVERSAL",
    "D4_BTC_ETH_CONFIRM_DIVERGE",
    "D5_FUNDING_DIRECTION_INTERACTION",
    "PAIR_DEPTH_TWO",
)
_POLICIES = {
    "fit_invalid": (
        "H40_P3B_FIT_INVALID_CORRECTION_FAIL_CLOSED_V1",
        "7de7c7060c150518805562a473b154d3e91ba5fbc13b5488342ad358744d728a",
    ),
    "seed_identity": (
        "H40_P3B_BOOTSTRAP_SEED_IDENTITY_BINDING_V1",
        "7b2af0e0e7bde22ba10e81a7b356b6489614d42e6dc3a14a4b8d901423868d2c",
    ),
    "proxy_net_return": (
        "H40_P3B_PROXY_NET_RETURN_FORMULA_V1",
        "8a016bcff8e439090044e3003cb127bec3ed0e9c7f09fe8fd8307a2066ed76ba",
    ),
    "bootstrap_boundary": (
        "H40_P3B_BOOTSTRAP_BLOCK_BOUNDARY_SEMANTICS_V1",
        "0958dfa8bd61571983b2019b770edb29397da10e1df3f30c09b00362117320b6",
    ),
    "bootstrap_start_sampler": (
        "H40_P3B_BOOTSTRAP_START_SAMPLER_V1",
        "25d1af1277d45059d9cf474cacf0b59399b9f4af87ad3363a6dda570550ce8eb",
    ),
    "discovery_coverage_population": (
        "H40_P3B_DISCOVERY_COVERAGE_POPULATION_V1",
        "a9f4d5a0576f499fc4ee8433d170c33c13d80cbf2c0a179115f91172fa6e30c0",
    ),
}


def _fail(message: str, reason: H40ReasonCode = H40ReasonCode.CONFIG_IDENTITY_CONFLICT) -> NoReturn:
    raise H40GuardError(reason, message)


def _sha(value: object, name: str) -> str:
    if not isinstance(value, str) or _SHA.fullmatch(value) is None:
        _fail(f"{name} must be lowercase SHA-256")
    return value


def _keys(value: object, expected: set[str], name: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != expected:
        _fail(f"{name} has missing or extra schema keys")
    return cast(Mapping[str, Any], value)


def _integer(value: object, name: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        _fail(f"{name} must be integer >= {minimum}")
    return value


def _number(value: object, name: str, *, positive: bool = False) -> float:
    if not isinstance(value, str):
        _fail(f"{name} must be a decimal string")
    try:
        parsed = float(Decimal(value))
    except (ValueError, ArithmeticError):
        _fail(f"{name} is not a finite decimal")
    if not math.isfinite(parsed) or (positive and parsed <= 0):
        _fail(f"{name} is not a permitted finite decimal")
    return parsed


def _policies(value: object) -> None:
    payload = _keys(value, set(_POLICIES), "policy stack")
    for key, (policy_id, policy_hash) in _POLICIES.items():
        if payload[key] != {"policy_id": policy_id, "policy_hash": policy_hash}:
            _fail(f"{key} policy identity mismatch")


class H40DiscoveryEvidenceResolver:
    """Read a SHA-addressed canonical JSON object from one approved root."""

    __slots__ = ("_root",)

    def __setattr__(self, name: str, value: object) -> None:
        if name == "_root" and hasattr(self, "_root"):
            raise AttributeError("approved evidence root is write-once")
        object.__setattr__(self, name, value)

    def __init__(self, root: Path | str) -> None:
        path = Path(root)
        H40ProtectedSurfaceGuard.assert_path_allowed(path)
        if not path.is_dir() or path.is_symlink():
            _fail("approved evidence root must be a real directory")
        self._root = path.resolve(strict=True)

    def load(self, digest: str, schema_id: str, keys: set[str]) -> Mapping[str, Any]:
        _sha(digest, "evidence digest")
        object_path = self._root / digest[:2] / f"{digest}.json"
        if object_path.is_symlink() or object_path.parent.is_symlink():
            _fail("evidence symlink is forbidden")
        try:
            resolved = object_path.resolve(strict=True)
            if not resolved.is_relative_to(self._root) or not resolved.is_file():
                _fail("evidence path escaped approved root")
            raw = resolved.read_bytes()

            def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
                result: dict[str, Any] = {}
                for key, value in pairs:
                    if key in result:
                        _fail("duplicate JSON evidence key")
                    result[key] = value
                return result

            payload = json.loads(
                raw, parse_constant=lambda _: _fail("non-finite JSON number"),
                object_pairs_hook=unique_object,
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise H40GuardError(H40ReasonCode.CONFIG_IDENTITY_CONFLICT, "missing or malformed evidence") from exc
        result = _keys(payload, keys, schema_id)
        schema_field = (
            "evidence_schema_id" if schema_id == "H40_DISCOVERY_RESULT_EVIDENCE_V1"
            else "schema_id"
        )
        if (
            result.get(schema_field) != schema_id
            or canonical_sha256(result) != digest
            or raw != canonical_json(result).encode("utf-8")
        ):
            _fail("evidence schema or canonical content hash mismatch")
        return result


def _seal_context_binding(seal: H40RuntimeSnapshotSeal) -> tuple[Any, ...]:
    """Capture the mutable objects behind a runtime seal as well as its public hash."""
    contexts = (
        seal._source_manifest_context,
        seal._split_manifest_context,
        seal._runtime_attestation_context,
    )
    return (
        *(
            (id(context), canonical_sha256(context.to_dict()) if context is not None else None)
            for context in contexts
        ),
        seal._repo_root_context,
    )


def h40_proxy_net_return(action: str, p0: str, ch: str) -> tuple[float, float]:
    """BASE label log return and accepted R3 fractional proxy net return."""
    first = _number(p0, "P0", positive=True)
    last = _number(ch, "C_h", positive=True)
    if action not in ("LONG", "SHORT"):
        _fail("proxy return requires a directional action")
    r_h = math.log(last / first)
    sign = 1 if action == "LONG" else -1
    net = sign * math.expm1(r_h) - 0.0012
    if not math.isfinite(r_h) or not math.isfinite(net):
        _fail("proxy return is non-finite")
    return r_h, net


def h40_discovery_coverage(n_accept: int, n_base: int) -> bool:
    """R6 exact candidate-lock coverage hard gate."""
    audit = h40_discovery_coverage_audit(n_accept, n_base)
    return audit.lower_pass and audit.upper_pass


@dataclass(frozen=True)
class H40DiscoveryCoverageAudit:
    n_accept: int
    n_base: int
    lower_pass: bool
    upper_pass: bool

    def to_dict(self) -> dict[str, int | bool]:
        return {
            "N_accept": self.n_accept,
            "N_base": self.n_base,
            "lower_pass": self.lower_pass,
            "upper_pass": self.upper_pass,
        }


def h40_discovery_coverage_audit(n_accept: int, n_base: int) -> H40DiscoveryCoverageAudit:
    _integer(n_accept, "N_accept")
    _integer(n_base, "N_base")
    if n_base == 0:
        _fail("zero base-eligible Discovery denominator", H40ReasonCode.NOT_TESTABLE)
    if n_accept > n_base:
        _fail("accepted action outside base-eligible universe")
    return H40DiscoveryCoverageAudit(
        n_accept=n_accept,
        n_base=n_base,
        lower_pass=400 * n_accept >= n_base,
        upper_pass=10 * n_accept <= n_base,
    )


def h40_side_preserving_action(raw_score: float, p_up: float, threshold: float) -> str:
    """R3R4: calibration may suppress the direction owner, never flip it."""
    if not all(math.isfinite(value) for value in (raw_score, p_up, threshold)):
        _fail("non-finite direction confidence input")
    if threshold not in (0.55, 0.60, 0.65) or not 0 <= p_up <= 1:
        _fail("direction confidence threshold or probability mismatch")
    if raw_score > 0 and p_up >= threshold:
        return "LONG"
    if raw_score < 0 and p_up <= 1 - threshold:
        return "SHORT"
    return "NO_TRADE"


@dataclass(frozen=True)
class H40BootstrapSeedAudit:
    canonical_seed_preimage: str
    seed_digest_sha256: str
    raw_u64: int
    seed: int


def h40_bootstrap_seed(candidate_id: str, metric_id: str) -> H40BootstrapSeedAudit:
    _sha(candidate_id, "structural candidate ID")
    if metric_id not in ("PRECISION", "NET_EXPECTANCY"):
        _fail("Discovery metric ID mismatch")
    preimage = canonical_json([
        compute_protocol_authority_hash(), candidate_id, "WF1_CALIBRATION", metric_id,
    ])
    digest = hashlib.sha256(preimage.encode("utf-8")).digest()
    raw_u64 = int.from_bytes(digest[:8], byteorder="big", signed=False)
    return H40BootstrapSeedAudit(preimage, digest.hex(), raw_u64, raw_u64 % (2**63 - 1))


def h40_bootstrap_starts(seed: int, h: int) -> tuple[np.ndarray, str]:
    """Accepted R5 single-call PCG64 start matrix and canonical matrix hash."""
    _integer(seed, "seed")
    _integer(h, "H")
    if h < _L:
        _fail("Discovery interval shorter than bootstrap block", H40ReasonCode.NOT_TESTABLE)
    blocks = math.ceil(h / _L)
    rng = np.random.Generator(np.random.PCG64(seed))
    starts = rng.integers(
        low=0, high=h - _L + 1, size=(_M, blocks), dtype=np.int64, endpoint=False,
    )
    return starts, canonical_sha256(starts.tolist())


def h40_hac_effective_count(trades: Sequence[tuple[datetime, float, float]]) -> int:
    """R2 exact-hour HAC, occupied-day, and raw-count joint floor."""
    n = len(trades)
    if n == 0:
        return 0
    ordered = sorted(trades, key=lambda row: row[0])
    times = [row[0] for row in ordered]
    if any(t.tzinfo != UTC or t.minute or t.second or t.microsecond for t in times):
        _fail("HAC entries must be UTC-aligned hours")
    occupied_days = len({t.date() for t in times})
    by_time: dict[datetime, list[int]] = {}
    for index, timestamp in enumerate(times):
        by_time.setdefault(timestamp, []).append(index)

    def clipped(values: list[float]) -> float:
        mean = sum(values) / n
        deviations = [value - mean for value in values]
        gamma0 = sum(value * value for value in deviations) / n
        if gamma0 <= 0 or n < 2:
            return 1.0
        inflation = 1.0
        for lag in range(1, 25):
            pair_sum = 0.0
            offset = timedelta(hours=lag)
            for timestamp, left_indices in by_time.items():
                for i in left_indices:
                    for j in by_time.get(timestamp + offset, ()):
                        pair_sum += deviations[i] * deviations[j]
            rho = (pair_sum / n) / gamma0
            inflation += 2.0 * (1.0 - lag / 25.0) * rho
        if not math.isfinite(inflation) or inflation <= 0:
            return 1.0
        return min(float(n), max(1.0, n / inflation))

    correctness = [row[1] for row in ordered]
    net_returns = [row[2] for row in ordered]
    if any(not math.isfinite(value) for value in correctness + net_returns):
        _fail("HAC series contains non-finite value")
    return min(n, occupied_days, math.floor(min(clipped(correctness), clipped(net_returns))))


def h40_marginal_p(point: float, replicates: np.ndarray, null: float) -> float:
    if replicates.shape != (_M,) or not np.all(np.isfinite(replicates)):
        _fail("marginal p-value requires 10000 finite replicates")
    return (1 + int(np.count_nonzero(replicates - point >= point - null))) / (_M + 1)


def h40_holm_fixed_six(raw_p: Mapping[str, float]) -> dict[str, float]:
    if set(raw_p) != set(_FAMILIES):
        _fail("Holm family universe must contain exactly six fixed slots")
    for value in raw_p.values():
        if not math.isfinite(value) or value < 0 or value > 1:
            _fail("Holm p-value outside [0, 1]")
    sorted_items = sorted(raw_p.items(), key=lambda item: (item[1], item[0]))
    result: dict[str, float] = {}
    running = 0.0
    for rank, (family, p_value) in enumerate(sorted_items):
        running = max(running, (6 - rank) * p_value)
        result[family] = min(1.0, running)
    return result


def h40_family_adjusted_lcbs(
    points: Mapping[str, float], replicates: Mapping[str, np.ndarray],
) -> dict[str, float]:
    if not points or set(points) != set(replicates):
        _fail("family correction requires the complete registered candidate set")
    centered: list[np.ndarray] = []
    for candidate_id in sorted(points):
        vector = replicates[candidate_id]
        if vector.shape != (_M,) or not np.all(np.isfinite(vector)):
            _fail("family correction requires complete finite bootstrap vectors")
        centered.append(vector - points[candidate_id])
    family_max = np.maximum.reduce(centered)
    critical = float(np.sort(family_max)[9499])
    return {candidate_id: point - critical for candidate_id, point in points.items()}


def h40_bootstrap_metric(
    starts: np.ndarray,
    hourly_count: np.ndarray,
    hourly_correct: np.ndarray,
    hourly_net: np.ndarray,
    metric_id: str,
) -> np.ndarray:
    """R4 transport: source-hour aggregates move; original outcomes never change."""
    h = int(hourly_count.size)
    if h < _L or hourly_correct.shape != (h,) or hourly_net.shape != (h,):
        _fail("bootstrap source-hour arrays mismatch")
    blocks = math.ceil(h / _L)
    if starts.shape != (_M, blocks) or starts.dtype != np.int64:
        _fail("bootstrap start matrix shape or dtype mismatch")
    if metric_id not in ("PRECISION", "NET_EXPECTANCY"):
        _fail("bootstrap metric ID mismatch")
    if np.any(starts < 0) or np.any(starts > h - _L):
        _fail("bootstrap start outside non-circular universe")
    if (
        np.any(hourly_count < 0) or np.any(hourly_correct < 0)
        or np.any(hourly_correct > hourly_count)
        or np.any((hourly_count == 0) & (hourly_net != 0))
        or not all(np.all(np.isfinite(values)) for values in (
            hourly_count, hourly_correct, hourly_net,
        ))
    ):
        _fail("source-hour scientific aggregates are inconsistent")

    def sampled_sum(values: np.ndarray) -> np.ndarray:
        prefix = np.concatenate(([0.0], np.cumsum(values, dtype=np.float64)))
        full = prefix[starts + _L] - prefix[starts]
        tail_length = h - (blocks - 1) * _L
        full[:, -1] = prefix[starts[:, -1] + tail_length] - prefix[starts[:, -1]]
        return cast(np.ndarray, full.sum(axis=1))

    counts = sampled_sum(hourly_count)
    numerator = sampled_sum(hourly_correct if metric_id == "PRECISION" else hourly_net)
    return cast(np.ndarray, np.divide(
        numerator, counts, out=np.zeros(_M, dtype=np.float64), where=counts > 0,
    ))


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    forward = math.exp(value)
    return forward / (1.0 + forward)


def _platt_fit(scores: Sequence[float], labels: Sequence[int]) -> tuple[float, float]:
    """R3R2 Newton fit of R3R3 unique finite a>0 constrained MLE."""
    if len(scores) != len(labels) or not scores or len(set(scores)) < 2 or set(labels) != {0, 1}:
        _fail("Platt calibration population is degenerate", H40ReasonCode.NOT_TESTABLE)
    positive_scores = [score for score, label in zip(scores, labels, strict=True) if label == 1]
    negative_scores = [score for score, label in zip(scores, labels, strict=True) if label == 0]
    if min(positive_scores) >= max(negative_scores):
        _fail("Platt fit has complete or quasi separation", H40ReasonCode.NOT_TESTABLE)
    n = len(scores)
    base = sum(labels) / n
    a = 0.0
    b = math.log(base / (1.0 - base))

    def nll(slope: float, intercept: float) -> float:
        return sum(
            max(0.0, slope * x + intercept)
            + math.log1p(math.exp(-abs(slope * x + intercept)))
            - y * (slope * x + intercept)
            for x, y in zip(scores, labels, strict=True)
        )

    previous = nll(a, b)
    for _ in range(100):
        probability = [_sigmoid(a * x + b) for x in scores]
        weights = [p * (1 - p) for p in probability]
        g_a = sum((p - y) * x for p, y, x in zip(probability, labels, scores, strict=True))
        g_b = sum(p - y for p, y in zip(probability, labels, strict=True))
        h_aa = sum(w * x * x for w, x in zip(weights, scores, strict=True))
        h_ab = sum(w * x for w, x in zip(weights, scores, strict=True))
        h_bb = sum(weights)
        determinant = h_aa * h_bb - h_ab * h_ab
        if not math.isfinite(determinant) or determinant <= 0:
            _fail("Platt fit lacks unique finite optimum", H40ReasonCode.NOT_TESTABLE)
        delta_a = (h_bb * g_a - h_ab * g_b) / determinant
        delta_b = (-h_ab * g_a + h_aa * g_b) / determinant
        step = 1.0
        while step > 2**-52:
            candidate_a = a - step * delta_a
            candidate_b = b - step * delta_b
            if candidate_a > 0 and math.isfinite(candidate_b):
                current = nll(candidate_a, candidate_b)
                if current < previous:
                    break
            step *= 0.5
        else:
            _fail("Platt fit has no finite positive-slope improvement", H40ReasonCode.NOT_TESTABLE)
        a, b = candidate_a, candidate_b
        if abs(previous - current) / max(1.0, abs(previous)) < 1e-9:
            return a, b
        previous = current
    _fail("Platt fit did not converge within 100 Newton iterations", H40ReasonCode.NOT_TESTABLE)


def _isotonic_fit(scores: Sequence[float], labels: Sequence[int]) -> tuple[list[float], list[float]]:
    if len(scores) != len(labels) or len(scores) < 200 or min(sum(labels), len(labels) - sum(labels)) < 40:
        _fail("isotonic calibration population is ineligible", H40ReasonCode.NOT_TESTABLE)
    grouped: list[tuple[float, int, int]] = []
    for score, label in sorted(zip(scores, labels, strict=True), key=lambda item: item[0]):
        if grouped and grouped[-1][0] == score:
            x, successes, count = grouped[-1]
            grouped[-1] = (x, successes + label, count + 1)
        else:
            grouped.append((score, label, 1))
    blocks: list[tuple[int, int, int]] = []
    for index, (_, successes, count) in enumerate(grouped):
        blocks.append((index, successes, count))
        while len(blocks) >= 2:
            first = blocks[-2]
            second = blocks[-1]
            if first[1] * second[2] <= second[1] * first[2]:
                break
            blocks[-2:] = [(first[0], first[1] + second[1], first[2] + second[2])]
    support = [item[0] for item in grouped]
    values: list[float] = []
    for block_index, (start, successes, count) in enumerate(blocks):
        stop = blocks[block_index + 1][0] if block_index + 1 < len(blocks) else len(grouped)
        values.extend([successes / count] * (stop - start))
    return support, values


def h40_fit_calibrator(
    method: str, rows: Sequence[tuple[float, int]],
) -> tuple[str, tuple[float, float] | tuple[list[float], list[float]]]:
    scores = [item[0] for item in rows]
    labels = [item[1] for item in rows]
    if method == "CALIBRATION_ISOTONIC_IF_ELIGIBLE_V1" and len(rows) >= 200 and min(sum(labels), len(labels) - sum(labels)) >= 40:
        return "ISOTONIC", _isotonic_fit(scores, labels)
    if method not in ("CALIBRATION_ISOTONIC_IF_ELIGIBLE_V1", "CALIBRATION_PLATT_LOGISTIC_V1"):
        _fail("calibration contract identity mismatch")
    return "PLATT", _platt_fit(scores, labels)


def h40_predict_calibrated(
    fit: tuple[str, tuple[float, float] | tuple[list[float], list[float]]], score: float,
) -> float:
    method, parameters = fit
    if method == "PLATT":
        a, b = cast(tuple[float, float], parameters)
        return _sigmoid(a * score + b)
    support, values = cast(tuple[list[float], list[float]], parameters)
    index = max(0, bisect_right(support, score) - 1)
    return values[index]


def h40_calibration_gates(
    rows: Sequence[tuple[float, int, datetime, str]], base_rate: float,
) -> tuple[bool, float | None, float | None]:
    """R3R3 Brier skill and R3R4 deterministic adaptive ECE."""
    count = len(rows)
    if count < 20 or not 0 < base_rate < 1:
        return False, None, None
    ordered = sorted(rows, key=lambda row: (row[0], row[2], row[3]))
    if len({(row[2], row[3]) for row in ordered}) != count:
        _fail("calibration diagnostic row identity duplicated")
    bins = min(10, count // 20)
    ece = 0.0
    for bin_index in range(bins):
        subset = ordered[bin_index * count // bins:(bin_index + 1) * count // bins]
        confidence = sum(row[0] for row in subset) / len(subset)
        accuracy = sum(row[1] for row in subset) / len(subset)
        ece += len(subset) / count * abs(accuracy - confidence)
    brier = sum((p - y) ** 2 for p, y, _, _ in rows) / count
    baseline = sum((base_rate - y) ** 2 for _, y, _, _ in rows) / count
    if baseline <= 0:
        return False, ece, None
    skill = 1.0 - brier / baseline
    return ece <= 0.05 and skill > 0.0, ece, skill


_BAR_KEYS = {"timestamp", "product", "open", "high", "low", "close"}
_ROW_V1_KEYS = {
    "timestamp", "product", "regime_state", "opportunity_state", "raw_score",
    "secondary_filter_state", "p_up", "final_action", "r_h", "r_net",
}
_SOURCE_V1_KEYS = {
    "schema_id", "run_authority_id", "source_manifest_hash", "split_manifest_hash",
    "policies", "bars", "base_eligible_rows",
}
_DECISION_V1_KEYS = {
    "schema_id", "run_authority_id", "sealed_registered_roster_hash",
    "structural_configuration_hash", "source_manifest_hash", "split_manifest_hash",
    "source_evidence_hash", "partition_id", "policies", "rows",
}

_SOURCE_V2_KEYS = frozenset({
    "active_source_derivations",
    "base_eligible_membership",
    "policies",
    "provenance_contract_hash",
    "run_authority_id",
    "schema_id",
    "source_manifest_hash",
    "source_support",
    "split_attestation_hash",
    "split_manifest_hash",
})

_ACTIVE_SOURCE_DERIVATION_KEYS = frozenset({
    "cadence",
    "economic_row_count",
    "economic_rows_sha256",
    "locator",
    "product",
    "source_file_sha256",
    "source_id",
    "source_validation_receipt_sha256",
    "timestamp_field",
})

_DECISION_V2_KEYS = frozenset({
    "partition_id",
    "policies",
    "provenance_contract_hash",
    "rows",
    "run_authority_id",
    "schema_id",
    "sealed_registered_roster_hash",
    "source_evidence_hash",
    "source_manifest_hash",
    "split_manifest_hash",
    "structural_configuration_hash",
})

_ROW_V2_KEYS = frozenset({
    "final_action",
    "p_up",
    "product",
    "r_h",
    "r_net",
    "timestamp",
})

_FORBIDDEN_PREFIT_FIELDS = frozenset({
    "regime_state",
    "opportunity_state",
    "raw_score",
    "secondary_filter_state",
})

_SOURCE_KEYS = _SOURCE_V2_KEYS
_DECISION_KEYS = _DECISION_V2_KEYS
_ROW_KEYS = _ROW_V2_KEYS

SUPPORT_START_UTC = datetime(2021, 1, 1, tzinfo=UTC)
SUPPORT_END_UTC_EXCLUSIVE = datetime(2023, 2, 1, tzinfo=UTC)
LOOKBACK_RESERVE_END_UTC = datetime(2021, 1, 31, tzinfo=UTC)


def _timestamp(value: object, name: str) -> datetime:
    if not isinstance(value, str) or re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:00:00Z", value) is None:
        _fail(f"{name} must be an exact UTC decision hour")
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError:
        _fail(f"{name} is not calendar-valid")


def _partition_bounds(partition_id: str) -> tuple[datetime, datetime, datetime]:
    if partition_id == "WF1_TRAIN":
        return (
            datetime(2021, 1, 31, tzinfo=UTC),
            datetime(2022, 10, 31, tzinfo=UTC),
            datetime(2022, 11, 1, tzinfo=UTC),
        )
    if partition_id == "WF1_CALIBRATION":
        return (
            datetime(2022, 11, 1, tzinfo=UTC),
            datetime(2023, 1, 31, tzinfo=UTC),
            datetime(2023, 2, 1, tzinfo=UTC),
        )
    _fail("protected or non-Discovery partition is forbidden")


@dataclass(frozen=True)
class _Bar:
    timestamp: datetime
    product: str
    open: float
    high: float
    low: float
    close: float
    close_time: datetime | None = None

    @property
    def effective_close_time(self) -> datetime:
        if self.close_time is not None:
            return self.close_time
        return self.timestamp + timedelta(hours=1) - timedelta(milliseconds=1)


@dataclass(frozen=True)
class _Decision:
    timestamp: datetime
    product: str
    regime_state: str
    opportunity_state: str
    raw_score: float
    secondary_filter_state: str
    supplied_p_up: float | None
    supplied_action: str | None
    r_h: float
    supplied_r_net: float | None
    p0: float
    ch: float
    path: tuple[_Bar, ...]

    @property
    def prefit_eligible(self) -> bool:
        return (
            self.regime_state == "REGIME_VOL_MID"
            and self.opportunity_state == "O_ELIGIBLE"
            and self.raw_score != 0.0
            and self.secondary_filter_state == "PASS"
        )

    @property
    def proposed_action(self) -> str:
        return "LONG" if self.raw_score > 0 else "SHORT" if self.raw_score < 0 else "NO_TRADE"

    @property
    def label(self) -> str:
        if self.r_h > 0.0012:
            return "LONG_LABEL"
        if self.r_h < -0.0012:
            return "SHORT_LABEL"
        return "NEUTRAL_LABEL"

    def correct(self, action: str) -> float:
        return float(
            (action == "LONG" and self.label == "LONG_LABEL")
            or (action == "SHORT" and self.label == "SHORT_LABEL")
        )

    def net(self, action: str) -> float:
        return (1 if action == "LONG" else -1) * math.expm1(self.r_h) - 0.0012

    def excursions(self, action: str) -> tuple[float, float]:
        if action == "LONG":
            return (
                max(bar.high / self.p0 - 1 for bar in self.path),
                max(1 - bar.low / self.p0 for bar in self.path),
            )
        return (
            max(1 - bar.low / self.p0 for bar in self.path),
            max(bar.high / self.p0 - 1 for bar in self.path),
        )


def _extract_economic_rows(
    file_path: Path,
    raw_bytes: bytes,
    expected_product: str,
    expected_cadence: str,
    timestamp_field: str,
) -> tuple[list[_Bar], list[dict[str, str]]]:
    suffix = file_path.suffix.lower()
    if suffix not in (".parquet", ".json"):
        _fail("active source without accepted adapter", H40ReasonCode.NOT_TESTABLE)
    if expected_cadence != "1h":
        _fail("H40 economic adapter requires 1h cadence", H40ReasonCode.INTERVAL_MISMATCH)

    ts_vals: list[Any] = []
    open_vals: list[Any] = []
    high_vals: list[Any] = []
    low_vals: list[Any] = []
    close_vals: list[Any] = []

    if suffix == ".parquet":
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
        try:
            table = pq.read_table(file_path)
        except Exception as exc:
            raise H40GuardError(H40ReasonCode.NOT_TESTABLE, f"failed to read parquet: {exc}") from exc
        if timestamp_field not in table.column_names:
            _fail(f"timestamp field '{timestamp_field}' missing from parquet", H40ReasonCode.NOT_TESTABLE)
        for col in ("open", "high", "low", "close"):
            if col not in table.column_names:
                _fail(f"OHLC column '{col}' missing from parquet", H40ReasonCode.NOT_TESTABLE)
        ts_vals = table[timestamp_field].to_pylist()
        open_vals = table["open"].to_pylist()
        high_vals = table["high"].to_pylist()
        low_vals = table["low"].to_pylist()
        close_vals = table["close"].to_pylist()
    elif suffix == ".json":
        try:
            data = json.loads(raw_bytes.decode("utf-8"))
        except Exception as exc:
            raise H40GuardError(H40ReasonCode.NOT_TESTABLE, f"failed to parse json: {exc}") from exc
        if isinstance(data, dict):
            if "bars" in data and isinstance(data["bars"], list):
                for b in data["bars"]:
                    if not isinstance(b, dict):
                        _fail("json bar is not an object", H40ReasonCode.NOT_TESTABLE)
                    if timestamp_field not in b:
                        _fail(f"timestamp field '{timestamp_field}' not in json bar", H40ReasonCode.NOT_TESTABLE)
                    for col in ("open", "high", "low", "close"):
                        if col not in b:
                            _fail(f"OHLC column '{col}' missing from json bar", H40ReasonCode.NOT_TESTABLE)
                    ts_vals.append(b[timestamp_field])
                    open_vals.append(b["open"])
                    high_vals.append(b["high"])
                    low_vals.append(b["low"])
                    close_vals.append(b["close"])
            elif timestamp_field in data:
                ts_vals = data[timestamp_field]
                for col in ("open", "high", "low", "close"):
                    if col not in data:
                        _fail(f"OHLC column '{col}' missing from json", H40ReasonCode.NOT_TESTABLE)
                open_vals = data["open"]
                high_vals = data["high"]
                low_vals = data["low"]
                close_vals = data["close"]
            else:
                _fail("unsupported JSON structure", H40ReasonCode.NOT_TESTABLE)
        elif isinstance(data, list):
            for b in data:
                if not isinstance(b, dict):
                    _fail("json bar is not an object", H40ReasonCode.NOT_TESTABLE)
                if timestamp_field not in b:
                    _fail(f"timestamp field '{timestamp_field}' not in json bar", H40ReasonCode.NOT_TESTABLE)
                for col in ("open", "high", "low", "close"):
                    if col not in b:
                        _fail(f"OHLC column '{col}' missing from json bar", H40ReasonCode.NOT_TESTABLE)
                ts_vals.append(b[timestamp_field])
                open_vals.append(b["open"])
                high_vals.append(b["high"])
                low_vals.append(b["low"])
                close_vals.append(b["close"])
        else:
            _fail("unsupported JSON structure", H40ReasonCode.NOT_TESTABLE)

    n_rows = len(ts_vals)
    if not (len(open_vals) == len(high_vals) == len(low_vals) == len(close_vals) == n_rows):
        _fail("mismatched OHLC column lengths in source")

    extracted_bars: list[_Bar] = []
    canonical_rows: list[dict[str, str]] = []
    prev_dt: datetime | None = None

    for i in range(n_rows):
        raw_ts = ts_vals[i]
        if isinstance(raw_ts, bool):
            _fail("invalid boolean timestamp")
        elif isinstance(raw_ts, (int, float)):
            if raw_ts > 1e11:
                dt = datetime.fromtimestamp(raw_ts / 1000.0, tz=UTC)
            else:
                dt = datetime.fromtimestamp(raw_ts, tz=UTC)
        elif isinstance(raw_ts, str):
            dt = _timestamp(raw_ts, "source economic timestamp")
        else:
            _fail("invalid timestamp type")

        if not (SUPPORT_START_UTC <= dt < SUPPORT_END_UTC_EXCLUSIVE):
            continue

        if dt.tzinfo != UTC or dt.minute != 0 or dt.second != 0 or dt.microsecond != 0:
            _fail("timestamp is not UTC hourly aligned")

        if prev_dt is not None and dt <= prev_dt:
            _fail("source economic timestamps must be strictly sorted and unique")
        prev_dt = dt

        try:
            o = float(open_vals[i])
            h = float(high_vals[i])
            low_val = float(low_vals[i])
            c = float(close_vals[i])
        except (ValueError, TypeError):
            _fail("non-numeric OHLC in source")

        for name, val in (("open", o), ("high", h), ("low", low_val), ("close", c)):
            if not math.isfinite(val):
                _fail(f"non-finite source {name}")
            if val <= 0:
                _fail(f"non-positive source {name}")

        if low_val > min(o, c) or h < max(o, c) or low_val > h:
            _fail("source OHLC geometry is malformed")

        canonical_rows.append({
            "timestamp": dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "open": repr(o),
            "high": repr(h),
            "low": repr(low_val),
            "close": repr(c),
        })
        extracted_bars.append(_Bar(dt, expected_product, o, h, low_val, c))

    return extracted_bars, canonical_rows


def _compute_d1(bars: Mapping[tuple[datetime, str], _Bar], t: datetime, product: str, lookback_hours: int) -> float:
    b_last = bars.get((t - timedelta(hours=1), product))
    b_prev = bars.get((t - timedelta(hours=lookback_hours), product))
    if b_last is None or b_prev is None:
        return 0.0
    if b_last.effective_close_time >= t or b_prev.effective_close_time >= t:
        return 0.0
    return math.log(b_last.close / b_prev.close)


def _compute_d2(bars: Mapping[tuple[datetime, str], _Bar], t: datetime, product: str, range_hours: int) -> float:
    test_bar = bars.get((t - timedelta(hours=1), product))
    if test_bar is None or test_bar.effective_close_time >= t:
        return 0.0
    ref_bars: list[_Bar] = []
    # Normative R3R2 Section 2.2:
    # Reference bars: the set of complete hourly bars with close_time_ms < t and
    #                 open_time in (t - W, t). [the last closed signal bar is EXCLUDED]
    # For hourly aligned data, accepted reference set satisfies all of:
    #   open_time > t - W
    #   open_time < t
    #   close_time < t
    #   bar != last closed signal bar (test_bar at t - 1h)
    cutoff = t - timedelta(hours=range_hours)
    for k in range(2, range_hours):
        b = bars.get((t - timedelta(hours=k), product))
        if b is None or b.effective_close_time >= t:
            continue
        if b.timestamp > cutoff and b.timestamp < t and b.effective_close_time < t and b.timestamp != test_bar.timestamp:
            ref_bars.append(b)
    min_required = int((range_hours / 24) * 6)
    if len(ref_bars) < min_required or not ref_bars:
        return 0.0
    u = max(b.high for b in ref_bars)
    l_bound = min(b.low for b in ref_bars)
    if l_bound == u:
        return 0.0
    c = test_bar.close
    if c > u:
        return 1.0
    elif c < l_bound:
        return -1.0
    return 0.0


def _compute_d3(bars: Mapping[tuple[datetime, str], _Bar], t: datetime, product: str, range_hours: int) -> float:
    b2 = bars.get((t - timedelta(hours=1), product))
    b1 = bars.get((t - timedelta(hours=2), product))
    if b2 is None or b1 is None or b2.effective_close_time >= t or b1.effective_close_time >= t:
        return 0.0
    ref_bars: list[_Bar] = []
    # Normative R3R2 Section 2.3:
    # Prior range window W in {24h, 72h} of closed bars strictly before the break bar b1.
    # U(t) / L(t) as in Section 2.2 over that window.
    # Evaluated at b1 close time t_b1 = t - timedelta(hours=1):
    # Reference bars: complete hourly bars with close_time_ms < t_b1 and open_time in (t_b1 - W, t_b1).
    # b1 is the test bar and is excluded.
    # Therefore:
    #   open_time > t_b1 - W = t - 1h - W
    #   open_time < t_b1 = t - 1h
    #   close_time < t_b1
    #   bar != b1 (open_time != t - 2h)
    # For hourly aligned data, candidate open times are t - timedelta(hours=k) for k in range(3, range_hours + 1).
    t_b1 = t - timedelta(hours=1)
    cutoff = t_b1 - timedelta(hours=range_hours)
    for k in range(3, range_hours + 1):
        b = bars.get((t - timedelta(hours=k), product))
        if b is None or b.effective_close_time >= t_b1:
            continue
        if b.timestamp > cutoff and b.timestamp < t_b1 and b.effective_close_time < t_b1 and b.timestamp != b1.timestamp:
            ref_bars.append(b)
    min_required = int((range_hours / 24) * 6)
    if len(ref_bars) < min_required or not ref_bars:
        return 0.0
    u = max(b.high for b in ref_bars)
    l_bound = min(b.low for b in ref_bars)
    if l_bound == u:
        return 0.0
    c1 = b1.close
    c2 = b2.close
    if c1 > u and c2 < u:
        return -1.0
    elif c1 < l_bound and c2 > l_bound:
        return 1.0
    return 0.0


def _compute_r_vol_scalar(bars: Mapping[tuple[datetime, str], _Bar], t: datetime, product: str) -> float | None:
    closes: list[float] = []
    for k in range(24, 0, -1):
        b = bars.get((t - timedelta(hours=k), product))
        if b is None or b.effective_close_time >= t:
            return None
        closes.append(b.close)
    returns = [math.log(closes[i + 1] / closes[i]) for i in range(23)]
    mean_r = sum(returns) / 23.0
    var_r = sum((r - mean_r) ** 2 for r in returns) / 22.0
    if var_r < 0:
        return None
    rv = math.sqrt(var_r)
    return rv if math.isfinite(rv) else None


def _compute_o_range_scalar(bars: Mapping[tuple[datetime, str], _Bar], t: datetime, product: str) -> float | None:
    seq_bars: list[_Bar] = []
    for k in range(25, 0, -1):
        b = bars.get((t - timedelta(hours=k), product))
        if b is None or b.effective_close_time >= t:
            return None
        seq_bars.append(b)
    prior = bars.get((t - timedelta(hours=26), product))
    if prior is None or prior.effective_close_time >= t:
        return None
    prior_close = prior.close
    if not math.isfinite(prior_close) or prior_close <= 0:
        return None
    tr_values: list[float] = []
    for i in range(25):
        curr = seq_bars[i]
        prev_close = seq_bars[i - 1].close if i > 0 else prior_close
        tr = max(curr.high - curr.low, abs(curr.high - prev_close), abs(curr.low - prev_close))
        tr_values.append(tr)
    tr_ref = tr_values[:24]
    tr_last = tr_values[24]
    mean_tr = sum(tr_ref) / 24.0
    if mean_tr <= 0:
        return None
    ratio = tr_last / mean_tr
    return ratio if math.isfinite(ratio) else None


def _empirical_percentile(sample: Sequence[float], x: float) -> float:
    n = len(sample)
    if n == 0:
        return 0.0
    less_count = sum(1 for s in sample if s < x)
    has_equal = any(s == x for s in sample)
    rank = less_count / n
    tie = 0.5 / n if has_equal else 0.0
    return rank + tie


_PREFIT_CACHE: dict[tuple[str, str, str, str, str, str, str], tuple[float, str, str, str]] = {}
_TRAINING_REFS: dict[tuple[str, str], dict[str, list[tuple[datetime, float]]]] = {}


def clear_prefit_caches() -> None:
    _PREFIT_CACHE.clear()
    _TRAINING_REFS.clear()


def _get_training_refs(
    source_evidence_hash: str,
    product: str,
    bars: Mapping[tuple[datetime, str], _Bar],
) -> dict[str, list[tuple[datetime, float]]]:
    cache_key = (source_evidence_hash, product)
    if cache_key in _TRAINING_REFS:
        return _TRAINING_REFS[cache_key]

    rv_list: list[tuple[datetime, float]] = []
    exp_list: list[tuple[datetime, float]] = []
    product_times = sorted([t for t, p in bars if p == product])
    train_end = datetime(2022, 10, 31, tzinfo=UTC)

    for dt in product_times:
        if dt >= train_end:
            break
        rv = _compute_r_vol_scalar(bars, dt, product)
        if rv is not None and math.isfinite(rv):
            rv_list.append((dt, rv))
        exp = _compute_o_range_scalar(bars, dt, product)
        if exp is not None and math.isfinite(exp):
            exp_list.append((dt, exp))

    refs = {"R_VOL": rv_list, "O_RANGE": exp_list}
    _TRAINING_REFS[cache_key] = refs
    return refs


def _reconstruct_prefit_cached(
    *,
    candidate_id: str,
    slot: Any | None,
    partition_id: str,
    t: datetime,
    product: str,
    bars: Mapping[tuple[datetime, str], _Bar],
    source_evidence_hash: str,
) -> tuple[float, str, str, str]:
    cache_key = (
        compute_protocol_authority_hash(),
        DISCOVERY_PROVENANCE_CONTRACT_HASH,
        source_evidence_hash,
        candidate_id,
        partition_id,
        t.strftime("%Y-%m-%dT%H:%M:%SZ"),
        product,
    )
    if cache_key in _PREFIT_CACHE:
        return _PREFIT_CACHE[cache_key]

    dir_contract = str(getattr(slot, "direction_contract_id", None) or getattr(slot, "direction_variant", "D1_V1_RETURN_4H"))
    if "D1_V1" in dir_contract or dir_contract == "D1_V1_RETURN_4H":
        score = _compute_d1(bars, t, product, 4)
    elif "D1_V2" in dir_contract or dir_contract == "D1_V2_RETURN_12H":
        score = _compute_d1(bars, t, product, 12)
    elif "D2_V1" in dir_contract or dir_contract == "D2_V1_BREAKOUT_24H":
        score = _compute_d2(bars, t, product, 24)
    elif "D2_V2" in dir_contract or dir_contract == "D2_V2_BREAKOUT_72H":
        score = _compute_d2(bars, t, product, 72)
    elif "D3_V1" in dir_contract or dir_contract == "D3_V1_FAILED_BREAK_24H":
        score = _compute_d3(bars, t, product, 24)
    elif "D3_V2" in dir_contract or dir_contract == "D3_V2_FAILED_BREAK_72H":
        score = _compute_d3(bars, t, product, 72)
    else:
        _fail(f"unsupported direction contract '{dir_contract}'", H40ReasonCode.NOT_TESTABLE)

    training_refs = _get_training_refs(source_evidence_hash, product, bars)
    rv_series = training_refs["R_VOL"]
    exp_series = training_refs["O_RANGE"]

    if partition_id == "WF1_TRAIN":
        rv_sample = [v for dt, v in rv_series if dt < t]
        exp_sample = [v for dt, v in exp_series if dt < t]
    else:
        rv_sample = [v for _, v in rv_series]
        exp_sample = [v for _, v in exp_series]

    rv_val = _compute_r_vol_scalar(bars, t, product)
    if rv_val is None or len(rv_sample) < 60:
        regime_state = "REGIME_UNAVAILABLE"
    else:
        p_vol = _empirical_percentile(rv_sample, rv_val)
        if p_vol < 0.40:
            regime_state = "REGIME_VOL_LOW"
        elif p_vol < 0.60:
            regime_state = "REGIME_VOL_MID"
        else:
            regime_state = "REGIME_VOL_HIGH"

    exp_val = _compute_o_range_scalar(bars, t, product)
    if exp_val is None or len(exp_sample) < 60:
        opportunity_state = "O_NONE"
    else:
        p_opp = _empirical_percentile(exp_sample, exp_val)
        if p_opp < 0.60:
            opportunity_state = "O_NONE"
        elif p_opp < 0.80:
            opportunity_state = "O_WATCH"
        else:
            opportunity_state = "O_ELIGIBLE"

    sec_filter = str(getattr(slot, "secondary_filter_contract_id", "NONE") or "NONE")
    if sec_filter not in ("NONE", ""):
        _fail(f"unsupported secondary filter contract '{sec_filter}'", H40ReasonCode.NOT_TESTABLE)
    secondary_filter_state = "PASS"

    result = (score, regime_state, opportunity_state, secondary_filter_state)
    _PREFIT_CACHE[cache_key] = result
    return result


def _load_source_bars(
    resolver: H40DiscoveryEvidenceResolver,
    digest: str,
    *,
    run_authority_id: str,
    source_manifest_hash: str,
    split_manifest_hash: str,
    split_manifest: H40SplitManifest,
    split_attestation_hash: str | None = None,
    seal: H40RuntimeSnapshotSeal | None = None,
) -> tuple[dict[tuple[datetime, str], _Bar], dict[str, frozenset[tuple[datetime, str]]]]:
    payload = resolver.load(digest, "H40_P3B_SOURCE_DERIVATION_V2", set(_SOURCE_V2_KEYS))
    _policies(payload["policies"])
    if (
        payload["run_authority_id"] != run_authority_id
        or payload["source_manifest_hash"] != source_manifest_hash
        or payload["split_manifest_hash"] != split_manifest_hash
        or (split_attestation_hash is not None and payload["split_attestation_hash"] != split_attestation_hash)
        or payload["provenance_contract_hash"] != DISCOVERY_PROVENANCE_CONTRACT_HASH
    ):
        _fail("source derivation lineage mismatch")

    support = _keys(payload["source_support"], {"start_utc", "end_utc_exclusive"}, "source support")
    if (
        support["start_utc"] != "2021-01-01T00:00:00Z"
        or support["end_utc_exclusive"] != "2023-02-01T00:00:00Z"
    ):
        _fail("source support interval mismatch")

    active_derivations = payload["active_source_derivations"]
    if not isinstance(active_derivations, list) or not active_derivations:
        _fail("active_source_derivations must be a non-empty array")

    if seal is not None and not seal.synthetic_only:
        if seal._runtime_attestation_context is None or seal._source_manifest_context is None:
            _fail("production seal missing source/attestation context")
        active_ids = set(seal._runtime_attestation_context.active_required_source_ids)
        derivation_ids = {d.get("source_id") for d in active_derivations if isinstance(d, dict)}
        if derivation_ids != active_ids:
            _fail("active-source derivations do not cover sealed active required sources")

    bars: dict[tuple[datetime, str], _Bar] = {}

    for raw in active_derivations:
        entry = _keys(raw, set(_ACTIVE_SOURCE_DERIVATION_KEYS), "active source derivation")
        source_id = entry["source_id"]
        product = entry["product"]
        cadence = entry["cadence"]
        if cadence != "1h":
            _fail("non-1h cadence rejected for H40 economic adapter")
        locator = entry["locator"]

        suffix = Path(locator).suffix.lower()
        if suffix not in (".parquet", ".json"):
            _fail("active source without accepted adapter", H40ReasonCode.NOT_TESTABLE)

        if seal is not None and not seal.synthetic_only:
            repo_root = seal._repo_root_context
            assert repo_root is not None
            assert seal._source_manifest_context is not None
            assert seal._runtime_attestation_context is not None
            source_record = seal._source_manifest_context.get_source(source_id)
            evidence_entry = next(
                (e for e in seal._runtime_attestation_context.active_source_evidence if e.source_id == source_id),
                None,
            )
            if evidence_entry is None:
                _fail("source evidence entry missing from attestation")
            if source_record.receipt is None or source_record.receipt.status != H40SourceStatus.VERIFIED:
                _fail("source validation receipt missing or unverified")
            if canonical_sha256(source_record.to_dict()) != evidence_entry.source_record_hash:
                _fail("source record hash mismatch")
            if canonical_sha256(source_record.receipt.to_dict()) != evidence_entry.source_validation_receipt_hash:
                _fail("source validation receipt hash mismatch")
            if entry["source_validation_receipt_sha256"] != evidence_entry.source_validation_receipt_hash:
                _fail("source derivation receipt hash mismatch")
            if entry["source_file_sha256"] != source_record.file_sha256 or entry["source_file_sha256"] != evidence_entry.file_sha256:
                _fail("source file hash mismatch")
            if entry["locator"] != source_record.locator:
                _fail("source locator mismatch")
            if entry["product"] != source_record.product:
                _fail("source product mismatch")
            if entry["timestamp_field"] != source_record.receipt.timestamp_field:
                _fail("timestamp field mismatch")
            file_path = (repo_root / locator).resolve()
        else:
            repo_root = (getattr(seal, "_repo_root_context", None) if seal else None) or resolver._root
            file_path = (repo_root / locator)
            if not file_path.exists():
                file_path = resolver._root / locator

        H40ProtectedSurfaceGuard.assert_path_allowed(file_path, source_id=source_id)
        if not file_path.is_file():
            _fail("source file missing", H40ReasonCode.NOT_TESTABLE)

        raw_bytes = file_path.read_bytes()
        actual_hash = hashlib.sha256(raw_bytes).hexdigest()
        if actual_hash != entry["source_file_sha256"]:
            _fail("source file SHA-256 mismatch")

        extracted_bars, canonical_rows = _extract_economic_rows(
            file_path, raw_bytes, product, cadence, entry["timestamp_field"],
        )
        computed_count = len(canonical_rows)
        computed_digest = canonical_sha256(canonical_rows)
        if entry["economic_row_count"] != computed_count:
            _fail("economic row count mismatch")
        if entry["economic_rows_sha256"] != computed_digest:
            _fail("economic rows SHA-256 mismatch")

        for b in extracted_bars:
            bars[(b.timestamp, b.product)] = b

    raw_universe = _keys(
        payload["base_eligible_membership"], {"WF1_TRAIN", "WF1_CALIBRATION"},
        "source-bound base universe",
    )
    universes: dict[str, frozenset[tuple[datetime, str]]] = {}
    for partition_id in ("WF1_TRAIN", "WF1_CALIBRATION"):
        listed = raw_universe[partition_id]
        if not isinstance(listed, list):
            _fail("base universe must be an array")
        partition_start, partition_end, _ = _partition_bounds(partition_id)
        ordered_keys: list[tuple[datetime, str]] = []
        for raw_item in listed:
            item = _keys(raw_item, {"timestamp", "product"}, "base-universe row")
            timestamp = _timestamp(item["timestamp"], "base-universe timestamp")
            product = item["product"]
            if timestamp < LOOKBACK_RESERVE_END_UTC:
                _fail("lookback reserve hour cannot enter base-universe membership")
            if not (partition_start <= timestamp < partition_end) or product not in ("BTCUSDT", "ETHUSDT"):
                _fail("base-universe row outside accepted split/product")
            key = (timestamp, product)
            if ordered_keys and key <= ordered_keys[-1]:
                _fail("base-universe rows must be sorted and unique")
            if key not in bars:
                _fail("base-universe row has no source reference bar")
            ordered_keys.append(key)
        unique_timestamps = sorted({t.strftime("%Y-%m-%dT%H:%M:%SZ") for t, _ in ordered_keys})
        split = split_manifest.get_partition(partition_id)
        membership_hash = hashlib.sha256(",".join(unique_timestamps).encode("utf-8")).hexdigest()
        if split.count != len(unique_timestamps) or split.timestamps_sha256 != membership_hash:
            _fail("base universe does not match sealed split membership")
        expected_from_source = {
            (_timestamp(timestamp, "split membership"), product)
            for timestamp in unique_timestamps
            for product in ("BTCUSDT", "ETHUSDT")
            if (_timestamp(timestamp, "split membership"), product) in bars
        }
        if set(ordered_keys) != expected_from_source:
            _fail("base denominator omits source-eligible product row")
        universes[partition_id] = frozenset(ordered_keys)
    return bars, universes


def _load_decisions(
    resolver: H40DiscoveryEvidenceResolver,
    digest: str,
    *,
    run_authority_id: str,
    roster_hash: str,
    candidate_id: str,
    source_manifest_hash: str,
    split_manifest_hash: str,
    source_evidence_hash: str,
    partition_id: str,
    products: tuple[str, ...],
    horizon: int,
    bars: Mapping[tuple[datetime, str], _Bar],
    base_universe: frozenset[tuple[datetime, str]],
    slot: Any | None = None,
    seal: H40RuntimeSnapshotSeal | None = None,
) -> tuple[_Decision, ...]:
    payload = resolver.load(digest, "H40_P3B_RAW_DECISIONS_V2", set(_DECISION_V2_KEYS))
    _policies(payload["policies"])
    if (
        payload["run_authority_id"] != run_authority_id
        or payload["sealed_registered_roster_hash"] != roster_hash
        or payload["structural_configuration_hash"] != candidate_id
        or payload["source_manifest_hash"] != source_manifest_hash
        or payload["split_manifest_hash"] != split_manifest_hash
        or payload["source_evidence_hash"] != source_evidence_hash
        or payload["partition_id"] != partition_id
        or payload["provenance_contract_hash"] != DISCOVERY_PROVENANCE_CONTRACT_HASH
    ):
        _fail("decision population lineage mismatch")
    if slot is None:
        space = materialize_h40_search_space_production()
        slots_by_config = {s.structural_configuration_hash: s for s in space.slots}
        slot = slots_by_config.get(candidate_id)
    rows = payload["rows"]
    if not isinstance(rows, list):
        _fail("decision rows must be an array")
    start, end, support_end = _partition_bounds(partition_id)
    result: list[_Decision] = []
    previous: tuple[datetime, str] | None = None
    for raw in rows:
        if any(k in raw for k in _FORBIDDEN_PREFIT_FIELDS):
            _fail("forbidden transported prefit fields in V2 decision row")
        item = _keys(raw, set(_ROW_V2_KEYS), "source-bound decision")
        timestamp = _timestamp(item["timestamp"], "decision timestamp")
        product = item["product"]
        key = (timestamp, product)
        if (
            not start <= timestamp < end or product not in products
            or key not in base_universe or (previous is not None and key <= previous)
        ):
            _fail("decision is outside sorted active-scope partition")
        previous = key

        score, regime_state, opportunity_state, secondary_filter_state = _reconstruct_prefit_cached(
            candidate_id=candidate_id,
            slot=slot,
            partition_id=partition_id,
            t=timestamp,
            product=product,
            bars=bars,
            source_evidence_hash=source_evidence_hash,
        )

        first = bars.get(key)
        exit_time = timestamp + timedelta(hours=horizon - 1)
        if first is None or exit_time >= support_end:
            _fail("missing source-bound entry or unauthorized support endpoint", H40ReasonCode.NOT_TESTABLE)
        path = tuple(bars.get((timestamp + timedelta(hours=index), product)) for index in range(horizon))
        if any(bar is None for bar in path):
            _fail("missing source-local outcome-support hour", H40ReasonCode.NOT_TESTABLE)
        complete_path = tuple(cast(_Bar, bar) for bar in path)
        last = complete_path[-1]
        computed_r_h = math.log(last.close / first.open)
        supplied_r_h = _number(item["r_h"], "r_h")
        if supplied_r_h != computed_r_h:
            _fail("supplied log return does not match raw source prices")
        supplied_p_up = None if item["p_up"] is None else _number(item["p_up"], "p_up")
        if supplied_p_up is not None and not 0 <= supplied_p_up <= 1:
            _fail("probability outside [0, 1]")
        action = item["final_action"]
        if partition_id == "WF1_TRAIN":
            if action is not None or supplied_p_up is not None:
                _fail("training decision cannot apply future calibration")
        elif action not in ("LONG", "SHORT", "NO_TRADE"):
            _fail("calibration final action mismatch")
        supplied_net = None if item["r_net"] is None else _number(item["r_net"], "r_net")
        if action in ("LONG", "SHORT"):
            _, expected_net = h40_proxy_net_return(action, str(first.open), str(last.close))
            if supplied_net != expected_net:
                _fail("supplied proxy net return does not match raw source prices")
        elif supplied_net is not None:
            _fail("abstaining row cannot supply trade return")
        result.append(_Decision(
            timestamp, product, regime_state, opportunity_state,
            score, secondary_filter_state, supplied_p_up, action,
            computed_r_h, supplied_net, first.open, last.close, complete_path,
        ))
    expected_keys = frozenset(key for key in base_universe if key[1] in products)
    if frozenset((item.timestamp, item.product) for item in result) != expected_keys:
        _fail("decision rows do not cover complete active-scope base universe")
    return tuple(result)


_CORRECTION_KEYS = {
    "schema_id", "run_authority_id", "sealed_registered_roster_hash",
    "discovery_authorization_receipt_hash", "materialized_run_authority_hash",
    "source_manifest_hash", "split_manifest_hash", "discovery_partition",
    "discovery_selection_correction_contract_hash", "policies", "candidate_configuration_hashes",
    "metric_universes",
}
_RESULT_KEYS = {
    "schema_id", "run_authority_id", "sealed_registered_roster_hash",
    "structural_configuration_hash", "slot_hash", "slot_index", "source_manifest_hash",
    "split_manifest_hash", "source_evidence_hash", "training_evidence_hash",
    "calibration_evidence_hash", "fit_status", "fit_failure_reason", "policies",
    "hard_gate_input_evidence_hashes", "precision_input_evidence_hash",
    "net_expectancy_input_evidence_hash",
}
_GATE_KEYS = {
    "schema_id", "run_authority_id", "sealed_registered_roster_hash",
    "structural_configuration_hash", "gate_id", "source_evidence_hash",
    "training_evidence_hash", "calibration_evidence_hash", "policies", "audit",
}
_METRIC_KEYS = {
    "schema_id", "run_authority_id", "sealed_registered_roster_hash",
    "structural_configuration_hash", "metric_id", "correction_manifest_hash",
    "calibration_evidence_hash", "fit_status", "policies", "seed_identity_policy_id",
    "seed_identity_policy_hash", "protocol_id", "candidate_id", "partition_id",
    "canonical_seed_preimage", "seed_digest_sha256", "raw_u64", "seed",
    "numpy_version", "bit_generator", "bootstrap_start_sampler_policy_id",
    "bootstrap_start_sampler_policy_hash", "H", "L", "S", "B", "M",
    "start_matrix_hash",
}
_INVALID_METRIC_KEYS = {
    "schema_id", "run_authority_id", "sealed_registered_roster_hash",
    "structural_configuration_hash", "metric_id", "correction_manifest_hash",
    "fit_status", "fit_failure_reason", "policies",
}
_HARD_GATES = frozenset({
    "COVERAGE", "TRAINING_NEFF", "CALIBRATION_SAMPLE", "GEOMETRY",
    "CALIBRATION_DIAGNOSTICS", "CONFIDENCE",
})


@dataclass(frozen=True)
class _LoadedCandidate:
    entry: H40CandidateResultEntry
    slot: Any
    result: Mapping[str, Any]
    training: tuple[_Decision, ...]
    calibration: tuple[_Decision, ...]
    valid: bool
    coverage_audit: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _CandidateScience:
    hard_gates_passed: bool
    point_precision: float
    point_net_expectancy: float
    precision_replicates: np.ndarray
    net_replicates: np.ndarray
    p0: float
    coverage_audit: H40DiscoveryCoverageAudit


def _median(values: Sequence[float]) -> float:
    if not values:
        _fail("median requires a nonempty geometry cell")
    ordered = sorted(values)
    middle = len(ordered) // 2
    return ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2


def _geometry_rows(candidates: Mapping[str, _LoadedCandidate]) -> dict[
    str, dict[tuple[str, str, int, datetime, str, str], tuple[float, float]]
]:
    owners: dict[str, dict[tuple[str, str, int, datetime, str, str], tuple[float, float]]] = {}
    for candidate in candidates.values():
        slot = candidate.slot
        owner = str(slot.direction_contract_id)
        for row in candidate.training:
            if not row.prefit_eligible:
                continue
            side = row.proposed_action
            key = (
                owner, str(slot.scope), int(slot.primary_horizon.rstrip("h")),
                row.timestamp, row.product, side,
            )
            values = row.excursions(side)
            existing = owners.setdefault(owner, {}).get(key)
            if existing is not None and existing != values:
                _fail("geometry sibling fit rows disagree")
            owners[owner][key] = values
    return owners


def _geometry_pass(
    row: _Decision,
    slot: Any,
    owners: Mapping[str, Mapping[tuple[str, str, int, datetime, str, str], tuple[float, float]]],
) -> bool:
    owner = str(slot.direction_contract_id)
    scope = str(slot.scope)
    horizon = int(slot.primary_horizon.rstrip("h"))
    side = row.proposed_action
    records = owners.get(owner, {})
    for level in range(4):
        subset = [
            values for (_, record_scope, record_horizon, _, _, record_side), values in records.items()
            if (
                (level >= 3 or record_scope == scope)
                and (level >= 2 or record_horizon == horizon)
                and (level >= 1 or record_side == side)
            )
        ]
        if len(subset) >= 30:
            mfe = _median([item[0] for item in subset])
            mae = _median([item[1] for item in subset])
            return mfe >= 1.5 * 0.0012 and mfe / max(mae, 0.0012) >= 1.25
    return False


def _candidate_science(
    candidate: _LoadedCandidate,
    geometry: Mapping[str, Mapping[tuple[str, str, int, datetime, str, str], tuple[float, float]]],
    starts: Mapping[str, np.ndarray],
) -> _CandidateScience:
    training = candidate.training
    calibration = candidate.calibration
    fit_rows = [
        (row.raw_score, int(row.label == "LONG_LABEL"))
        for row in calibration if row.prefit_eligible and row.label != "NEUTRAL_LABEL"
    ]
    fit = h40_fit_calibrator(candidate.slot.calibration_contract_id, fit_rows)
    base_rate = sum(label for _, label in fit_rows) / len(fit_rows)

    training_trades = [
        (row.timestamp, row.correct(row.proposed_action), row.net(row.proposed_action))
        for row in training if row.prefit_eligible
    ]
    training_neff = h40_hac_effective_count(training_trades)
    diagnostic: list[tuple[float, int, datetime, str]] = []
    accepted: list[tuple[_Decision, str]] = []
    for row in calibration:
        action = "NO_TRADE"
        if row.prefit_eligible:
            predicted = h40_predict_calibrated(fit, row.raw_score)
            if row.supplied_p_up is None or row.supplied_p_up != predicted:
                _fail("candidate calibrated probability is not independently reproducible")
            if row.label != "NEUTRAL_LABEL":
                diagnostic.append((predicted, int(row.label == "LONG_LABEL"), row.timestamp, row.product))
            if _geometry_pass(row, candidate.slot, geometry):
                action = h40_side_preserving_action(
                    row.raw_score, predicted, candidate.slot.action_threshold,
                )
        elif row.supplied_p_up is not None:
            _fail("noneligible row cannot carry calibrated probability")
        if row.supplied_action != action:
            _fail("source-bound final action differs from accepted funnel")
        if action != "NO_TRADE":
            accepted.append((row, action))
    n_base = len(calibration)
    n_accept = len(accepted)
    coverage_audit = h40_discovery_coverage_audit(n_accept, n_base)
    coverage_pass = coverage_audit.lower_pass and coverage_audit.upper_pass
    calibration_neff = h40_hac_effective_count([
        (row.timestamp, row.correct(action), row.net(action)) for row, action in accepted
    ])
    side_counts = {
        side: sum(1 for _, action in accepted if action == side)
        for side in ("LONG", "SHORT")
    }
    side_floor_pass = all(count >= 15 for count in side_counts.values() if count > 0)
    diagnostics_pass, _, _ = h40_calibration_gates(diagnostic, base_rate)
    hard_pass = (
        coverage_pass and training_neff >= 120 and n_accept >= 40
        and calibration_neff >= 32 and side_floor_pass and diagnostics_pass
    )

    label_long = sum(row.label == "LONG_LABEL" for row in training)
    label_short = sum(row.label == "SHORT_LABEL" for row in training)
    if not training:
        _fail("training base label denominator is zero", H40ReasonCode.NOT_TESTABLE)
    p0 = 0.5
    if n_accept:
        p0 = max(
            0.5,
            side_counts["LONG"] / n_accept * label_long / len(training)
            + side_counts["SHORT"] / n_accept * label_short / len(training),
        )

    start, end, _ = _partition_bounds("WF1_CALIBRATION")
    h = int((end - start).total_seconds() // 3600)
    hourly_count = np.zeros(h, dtype=np.float64)
    hourly_correct = np.zeros(h, dtype=np.float64)
    hourly_net = np.zeros(h, dtype=np.float64)
    for row, action in accepted:
        hour = int((row.timestamp - start).total_seconds() // 3600)
        hourly_count[hour] += 1.0
        hourly_correct[hour] += row.correct(action)
        hourly_net[hour] += row.net(action)
    point_precision = float(hourly_correct.sum() / n_accept) if n_accept else 0.0
    point_net = float(hourly_net.sum() / n_accept) if n_accept else 0.0
    return _CandidateScience(
        hard_pass,
        point_precision,
        point_net,
        h40_bootstrap_metric(
            starts["PRECISION"], hourly_count, hourly_correct, hourly_net, "PRECISION",
        ),
        h40_bootstrap_metric(
            starts["NET_EXPECTANCY"], hourly_count, hourly_correct, hourly_net,
            "NET_EXPECTANCY",
        ),
        p0,
        coverage_audit,
    )


class H40ProductionDiscoveryEvidenceVerifier:
    """Production Discovery verifier behind the accepted lifecycle Protocol."""

    __slots__ = (
        "__weakref__",
        "_dependencies",
        "_entries_by_id",
        "_evidence_hash",
        "_manifest_hash",
        "_receipt",
        "_resolver",
        "_seal",
        "_split",
        "_verified",
    )

    synthetic_only = False

    def __setattr__(self, name: str, value: object) -> None:
        if name in {"_resolver", "_seal", "_receipt", "_split"} and hasattr(self, name):
            raise AttributeError(f"{name} is write-once production authority")
        object.__setattr__(self, name, value)

    def __init__(
        self,
        *,
        approved_evidence_root: Path | str,
        seal: H40RuntimeSnapshotSeal,
        authorization_receipt: H40DiscoveryAuthorizationReceipt,
        split_manifest: H40SplitManifest,
    ) -> None:
        if not isinstance(seal, H40RuntimeSnapshotSeal):
            raise TypeError("production verifier requires a typed runtime seal")
        if not isinstance(authorization_receipt, H40DiscoveryAuthorizationReceipt):
            raise TypeError("production verifier requires a typed Discovery receipt")
        if not isinstance(split_manifest, H40SplitManifest):
            raise TypeError("production verifier requires a typed split authority")
        if split_manifest.split_hash != seal.split_manifest_hash:
            _fail("split authority differs from runtime seal")
        self._resolver = H40DiscoveryEvidenceResolver(approved_evidence_root)
        self._seal = seal
        self._receipt = authorization_receipt
        self._split = split_manifest
        self._manifest_hash: str | None = None
        self._evidence_hash: str | None = None
        self._verified: dict[str, H40CandidateVerification] = {}
        self._dependencies: list[tuple[str, str, set[str]]] = []
        self._entries_by_id: dict[str, H40CandidateResultEntry] = {}
        _VERIFIER_BINDINGS[self] = (
            self._resolver, self._resolver._root, self._seal,
            self._seal.authority_context_hash, _seal_context_binding(self._seal),
            self._receipt,
            self._receipt.receipt_sha256, self._split,
            canonical_sha256(self._split.to_dict()),
        )

    def assert_runtime_integrity(
        self,
        *,
        seal: H40RuntimeSnapshotSeal | None = None,
        receipt: H40DiscoveryAuthorizationReceipt | None = None,
    ) -> None:
        binding = _VERIFIER_BINDINGS.get(self)
        if binding is None or type(self) is not H40ProductionDiscoveryEvidenceVerifier:
            _fail("production verifier constructor integrity failed")
        try:
            (
                resolver, root, bound_seal, seal_hash, seal_context,
                bound_receipt, receipt_hash, split, split_hash,
            ) = binding
            intact = (
                self._resolver is resolver
                and type(resolver) is H40DiscoveryEvidenceResolver
                and resolver._root == root
                and self._seal is bound_seal
                and self._seal.authority_context_hash == seal_hash
                and _seal_context_binding(self._seal) == seal_context
                and self._receipt is bound_receipt
                and self._receipt.receipt_sha256 == receipt_hash
                and self._split is split
                and canonical_sha256(self._split.to_dict()) == split_hash
                and self._split.split_hash == self._seal.split_manifest_hash
                and (seal is None or seal.authority_context_hash == seal_hash)
                and (receipt is None or receipt.receipt_sha256 == receipt_hash)
                and all(
                    getattr(H40ProductionDiscoveryEvidenceVerifier, name) is method
                    for name, method in _VERIFIER_METHODS.items()
                )
                and all(
                    getattr(H40DiscoveryEvidenceResolver, name) is method
                    for name, method in _RESOLVER_METHODS.items()
                )
            )
        except (AttributeError, TypeError, ValueError):
            intact = False
        if not intact:
            _fail("production verifier runtime authority or behavior changed")

    def _load(self, digest: str, schema_id: str, keys: set[str]) -> Mapping[str, Any]:
        self._dependencies.append((digest, schema_id, keys))
        return self._resolver.load(digest, schema_id, keys)

    def _result_binding(self) -> str:
        return canonical_sha256({
            "manifest_hash": self._manifest_hash,
            "evidence_hash": self._evidence_hash,
            "verified": {
                candidate_id: {
                    "hard_gates_passed": result.hard_gates_passed,
                    "adjusted_lcb_net_expectancy": (
                        None if result.adjusted_lcb_net_expectancy is None
                        else str(result.adjusted_lcb_net_expectancy)
                    ),
                    "adjusted_lcb_precision": (
                        None if result.adjusted_lcb_precision is None
                        else str(result.adjusted_lcb_precision)
                    ),
                    "scientific_unavailable": result.scientific_unavailable,
                }
                for candidate_id, result in self._verified.items()
            },
            "entries": {
                candidate_id: entry.to_dict()
                for candidate_id, entry in self._entries_by_id.items()
            },
            "dependencies": [
                [digest, schema_id, sorted(keys)]
                for digest, schema_id, keys in self._dependencies
            ],
        })

    def verify_discovery_manifest(
        self,
        evidence: H40DiscoveryResultEvidence,
        entries: Sequence[H40CandidateResultEntry],
    ) -> None:
        H40ProductionDiscoveryEvidenceVerifier.assert_runtime_integrity(self)
        _VERIFIER_RESULTS.pop(self, None)
        self._manifest_hash = None
        self._evidence_hash = None
        self._verified.clear()
        self._dependencies.clear()
        self._entries_by_id.clear()
        if not self._seal.synthetic_only:
            self._seal.verify_against_accepted_ledger()
        if len(entries) != 18 or tuple(entries) != evidence.candidate_result_entries:
            _fail("Discovery requires exact complete 18-entry result roster")
        expected = [
            (item.slot_index, item.slot_hash, item.structural_configuration_hash, item.family_id)
            for item in self._seal.roster
        ]
        actual = [
            (item.slot_index, item.slot_hash, item.structural_configuration_hash, item.family_id)
            for item in entries
        ]
        if actual != expected or len({entry.structural_configuration_hash for entry in entries}) != 18:
            _fail("Discovery entries differ from sealed REGISTERED roster")
        if (
            evidence.run_authority_id != self._receipt.run_authority_id
            or evidence.discovery_authorization_receipt_hash != self._receipt.receipt_sha256
            or evidence.sealed_registered_roster_hash != self._seal.sealed_registered_roster_hash
            or evidence.materialized_run_authority_hash != self._seal.materialized_run_authority_hash
            or evidence.discovery_selection_correction_contract_hash
            != DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
        ):
            _fail("Discovery result authority lineage mismatch")
        loaded_evidence = self._load(
            evidence.evidence_sha256, "H40_DISCOVERY_RESULT_EVIDENCE_V1",
            set(H40DiscoveryResultEvidence._KEYS),
        )
        if loaded_evidence != evidence.to_dict():
            _fail("Discovery result bytes differ from typed evidence")
        manifest_hash = evidence.correction_input_evidence_manifest_hash
        manifest = self._load(manifest_hash, "H40_P3B_DISCOVERY_CORRECTION_MANIFEST_V1", _CORRECTION_KEYS)
        _policies(manifest["policies"])
        if (
            manifest["run_authority_id"] != evidence.run_authority_id
            or manifest["sealed_registered_roster_hash"] != evidence.sealed_registered_roster_hash
            or manifest["discovery_authorization_receipt_hash"] != evidence.discovery_authorization_receipt_hash
            or manifest["materialized_run_authority_hash"] != evidence.materialized_run_authority_hash
            or manifest["source_manifest_hash"] != self._seal.source_manifest_hash
            or manifest["split_manifest_hash"] != self._seal.split_manifest_hash
            or manifest["discovery_partition"] != "WF1_CALIBRATION"
            or manifest["discovery_selection_correction_contract_hash"]
            != DISCOVERY_SELECTION_CORRECTION_CONTRACT_HASH
        ):
            _fail("correction manifest lineage or contract mismatch")
        if manifest["candidate_configuration_hashes"] != [
            item.structural_configuration_hash for item in entries
        ]:
            _fail("correction manifest candidate universe mismatch")
        universes = _keys(
            manifest["metric_universes"], {"PRECISION", "NET_EXPECTANCY"},
            "metric-specific correction universes",
        )
        expected_groups: dict[str, list[str]] = {name: [] for name in _FAMILIES}
        for item in entries:
            group = "PAIR_DEPTH_TWO" if item.complexity == 2 else item.family_id
            if group not in expected_groups:
                _fail("candidate family is outside fixed six-slot universe")
            expected_groups[group].append(item.structural_configuration_hash)
        for metric_id in ("PRECISION", "NET_EXPECTANCY"):
            if universes[metric_id] != expected_groups:
                _fail("metric-specific correction universe is not sealed family-local roster")

        ledger = materialize_h40_search_space_production()
        slots = {slot.structural_configuration_hash: slot for slot in ledger.slots}
        source_digests: set[str] = set()
        candidates: dict[str, _LoadedCandidate] = {}
        for entry in entries:
            slot = slots.get(entry.structural_configuration_hash)
            if slot is None or slot.slot_hash != entry.slot_hash or slot.slot_index != entry.slot_index:
                _fail("candidate result does not match accepted structural ledger")
            result = self._load(
                entry.candidate_result_input_evidence_hash,
                "H40_P3B_CANDIDATE_RESULT_INPUT_V1", _RESULT_KEYS,
            )
            _policies(result["policies"])
            if (
                result["run_authority_id"] != evidence.run_authority_id
                or result["sealed_registered_roster_hash"] != evidence.sealed_registered_roster_hash
                or result["structural_configuration_hash"] != entry.structural_configuration_hash
                or result["slot_hash"] != entry.slot_hash
                or result["slot_index"] != entry.slot_index
                or result["source_manifest_hash"] != self._seal.source_manifest_hash
                or result["split_manifest_hash"] != self._seal.split_manifest_hash
                or result["hard_gate_input_evidence_hashes"] != dict(entry.hard_gate_input_evidence_hashes)
                or result["precision_input_evidence_hash"] != entry.precision_input_evidence_hash
                or result["net_expectancy_input_evidence_hash"] != entry.net_expectancy_input_evidence_hash
            ):
                _fail("candidate result input lineage mismatch")
            source_digest = _sha(result["source_evidence_hash"], "source evidence")
            training_digest = _sha(result["training_evidence_hash"], "training decisions")
            calibration_digest = _sha(result["calibration_evidence_hash"], "calibration decisions")
            source_digests.add(source_digest)
            bars, universes_by_partition = _load_source_bars(
                self._resolver, source_digest,
                run_authority_id=evidence.run_authority_id,
                source_manifest_hash=self._seal.source_manifest_hash,
                split_manifest_hash=self._seal.split_manifest_hash,
                split_manifest=self._split,
                split_attestation_hash=self._seal.split_attestation_hash,
                seal=self._seal,
            )
            active_slot = cast(Any, slot)
            products = tuple(active_slot.asset_scope)
            horizon = int(active_slot.primary_horizon.rstrip("h"))
            training = _load_decisions(
                self._resolver, training_digest,
                run_authority_id=evidence.run_authority_id,
                roster_hash=evidence.sealed_registered_roster_hash,
                candidate_id=entry.structural_configuration_hash,
                source_manifest_hash=self._seal.source_manifest_hash,
                split_manifest_hash=self._seal.split_manifest_hash,
                source_evidence_hash=source_digest,
                partition_id="WF1_TRAIN", products=products, horizon=horizon,
                bars=bars, base_universe=universes_by_partition["WF1_TRAIN"],
                slot=slot,
                seal=self._seal,
            )
            calibration = _load_decisions(
                self._resolver, calibration_digest,
                run_authority_id=evidence.run_authority_id,
                roster_hash=evidence.sealed_registered_roster_hash,
                candidate_id=entry.structural_configuration_hash,
                source_manifest_hash=self._seal.source_manifest_hash,
                split_manifest_hash=self._seal.split_manifest_hash,
                source_evidence_hash=source_digest,
                partition_id="WF1_CALIBRATION", products=products, horizon=horizon,
                bars=bars, base_universe=universes_by_partition["WF1_CALIBRATION"],
                slot=slot,
                seal=self._seal,
            )
            if set(entry.hard_gate_input_evidence_hashes) != _HARD_GATES:
                _fail("candidate hard-gate input universe mismatch")
            coverage_audit: Mapping[str, Any] | None = None
            for gate_id, gate_digest in entry.hard_gate_input_evidence_hashes.items():
                gate = self._load(gate_digest, "H40_P3B_HARD_GATE_INPUT_V1", _GATE_KEYS)
                _policies(gate["policies"])
                if (
                    gate["gate_id"] != gate_id
                    or gate["run_authority_id"] != evidence.run_authority_id
                    or gate["sealed_registered_roster_hash"] != evidence.sealed_registered_roster_hash
                    or gate["structural_configuration_hash"] != entry.structural_configuration_hash
                    or gate["source_evidence_hash"] != source_digest
                    or gate["training_evidence_hash"] != training_digest
                    or gate["calibration_evidence_hash"] != calibration_digest
                ):
                    _fail("hard-gate input lineage mismatch")
                if gate_id == "COVERAGE":
                    if gate["audit"] is not None and not isinstance(gate["audit"], dict):
                        _fail("coverage audit must be an exact object or null")
                    coverage_audit = gate["audit"]
                elif gate["audit"] is not None:
                    _fail("noncoverage hard gate cannot carry a coverage audit")
            if result["fit_status"] not in ("COMPLETE", "FIT_INVALID"):
                _fail("candidate fit status mismatch")
            if result["fit_status"] == "COMPLETE" and result["fit_failure_reason"] is not None:
                _fail("complete candidate carries fit-failure reason")
            if result["fit_status"] == "FIT_INVALID" and not isinstance(result["fit_failure_reason"], str):
                _fail("fit-invalid candidate lacks reason")
            candidates[entry.structural_configuration_hash] = _LoadedCandidate(
                entry, slot, result, training, calibration, result["fit_status"] == "COMPLETE",
                coverage_audit,
            )
            self._dependencies.extend([
                (source_digest, "H40_P3B_SOURCE_DERIVATION_V2", set(_SOURCE_V2_KEYS)),
                (training_digest, "H40_P3B_RAW_DECISIONS_V2", set(_DECISION_V2_KEYS)),
                (calibration_digest, "H40_P3B_RAW_DECISIONS_V2", set(_DECISION_V2_KEYS)),
            ])
        if len(source_digests) != 1:
            _fail("Discovery candidates must share one sealed source-hour evidence object")
        self._evaluate_candidates(candidates, manifest_hash)
        self._entries_by_id = {
            entry.structural_configuration_hash: entry for entry in entries
        }
        self._manifest_hash = manifest_hash
        self._evidence_hash = evidence.evidence_sha256
        _VERIFIER_RESULTS[self] = self._result_binding()

    def _metric_starts(
        self, candidate: _LoadedCandidate, metric_id: str, manifest_hash: str,
    ) -> np.ndarray | None:
        entry = candidate.entry
        digest = (
            entry.precision_input_evidence_hash if metric_id == "PRECISION"
            else entry.net_expectancy_input_evidence_hash
        )
        if not candidate.valid:
            payload = self._load(
                digest, "H40_P3B_INVALID_METRIC_INPUT_V1", _INVALID_METRIC_KEYS,
            )
            _policies(payload["policies"])
            if (
                payload["run_authority_id"] != self._receipt.run_authority_id
                or payload["sealed_registered_roster_hash"] != self._seal.sealed_registered_roster_hash
                or payload["structural_configuration_hash"] != entry.structural_configuration_hash
                or payload["metric_id"] != metric_id
                or payload["correction_manifest_hash"] != manifest_hash
                or payload["fit_status"] != "FIT_INVALID"
                or payload["fit_failure_reason"] != candidate.result["fit_failure_reason"]
            ):
                _fail("fit-invalid metric marker lineage mismatch")
            return None
        payload = self._load(digest, "H40_P3B_METRIC_BOOTSTRAP_V1", _METRIC_KEYS)
        _policies(payload["policies"])
        if (
            payload["run_authority_id"] != self._receipt.run_authority_id
            or payload["sealed_registered_roster_hash"] != self._seal.sealed_registered_roster_hash
            or payload["structural_configuration_hash"] != entry.structural_configuration_hash
            or payload["candidate_id"] != entry.structural_configuration_hash
            or payload["metric_id"] != metric_id
            or payload["correction_manifest_hash"] != manifest_hash
            or payload["calibration_evidence_hash"] != candidate.result["calibration_evidence_hash"]
            or payload["fit_status"] != "COMPLETE"
            or payload["seed_identity_policy_id"] != _POLICIES["seed_identity"][0]
            or payload["seed_identity_policy_hash"] != _POLICIES["seed_identity"][1]
            or payload["bootstrap_start_sampler_policy_id"] != _POLICIES["bootstrap_start_sampler"][0]
            or payload["bootstrap_start_sampler_policy_hash"] != _POLICIES["bootstrap_start_sampler"][1]
            or payload["protocol_id"] != compute_protocol_authority_hash()
            or payload["partition_id"] != "WF1_CALIBRATION"
            or payload["bit_generator"] != "PCG64"
        ):
            _fail("metric bootstrap policy or lineage mismatch")
        if payload["numpy_version"] != np.__version__:
            _fail("REPLAY_ENVIRONMENT_MISMATCH", H40ReasonCode.NOT_TESTABLE)
        audit = h40_bootstrap_seed(entry.structural_configuration_hash, metric_id)
        if (
            payload["canonical_seed_preimage"] != audit.canonical_seed_preimage
            or payload["seed_digest_sha256"] != audit.seed_digest_sha256
            or payload["raw_u64"] != audit.raw_u64
            or payload["seed"] != audit.seed
        ):
            _fail("bootstrap seed metadata differs from accepted derivation")
        low, high, _ = _partition_bounds("WF1_CALIBRATION")
        h = int((high - low).total_seconds() // 3600)
        blocks = math.ceil(h / _L)
        if (
            payload["H"] != h or payload["L"] != _L
            or payload["S"] != h - _L + 1 or payload["B"] != blocks
            or payload["M"] != _M
        ):
            _fail("bootstrap dimensional audit mismatch")
        starts, matrix_hash = h40_bootstrap_starts(audit.seed, h)
        if payload["start_matrix_hash"] != matrix_hash:
            _fail("bootstrap start-matrix replay hash mismatch")
        return starts

    def _evaluate_candidates(
        self, candidates: Mapping[str, _LoadedCandidate], manifest_hash: str,
    ) -> None:
        geometry = _geometry_rows(candidates)
        scientific: dict[str, _CandidateScience] = {}
        for candidate_id, candidate in candidates.items():
            matrices: dict[str, np.ndarray] = {}
            for metric_id in ("PRECISION", "NET_EXPECTANCY"):
                matrix = self._metric_starts(candidate, metric_id, manifest_hash)
                if matrix is not None:
                    matrices[metric_id] = matrix
            try:
                computed = _candidate_science(candidate, geometry, matrices)
            except H40GuardError as exc:
                if candidate.valid or exc.reason_code != H40ReasonCode.NOT_TESTABLE:
                    raise
                continue
            if not candidate.valid:
                _fail("candidate declared fit-invalid but scientific inputs are complete")
            if candidate.coverage_audit != computed.coverage_audit.to_dict():
                _fail("coverage audit differs from raw decision population")
            scientific[candidate_id] = computed

        by_family: dict[str, list[str]] = {name: [] for name in _FAMILIES}
        for candidate_id, candidate in candidates.items():
            family = "PAIR_DEPTH_TWO" if candidate.entry.complexity == 2 else candidate.entry.family_id
            by_family[family].append(candidate_id)
        unavailable = {
            family for family, members in by_family.items()
            if any(member not in scientific for member in members)
        }
        adjusted: dict[str, dict[str, dict[str, float]]] = {}
        p_values: dict[str, dict[str, dict[str, float]]] = {}
        for family, members in by_family.items():
            if family in unavailable or not members:
                for candidate_id in members:
                    self._verified[candidate_id] = H40CandidateVerification(
                        hard_gates_passed=False,
                        adjusted_lcb_net_expectancy=None,
                        adjusted_lcb_precision=None,
                        scientific_unavailable=True,
                    )
                continue
            adjusted[family] = {}
            p_values[family] = {}
            for metric_id in ("PRECISION", "NET_EXPECTANCY"):
                points = {
                    candidate_id: (
                        scientific[candidate_id].point_precision if metric_id == "PRECISION"
                        else scientific[candidate_id].point_net_expectancy
                    )
                    for candidate_id in members
                }
                vectors = {
                    candidate_id: (
                        scientific[candidate_id].precision_replicates if metric_id == "PRECISION"
                        else scientific[candidate_id].net_replicates
                    )
                    for candidate_id in members
                }
                lcbs = h40_family_adjusted_lcbs(points, vectors)
                for candidate_id in members:
                    adjusted[family].setdefault(candidate_id, {})[metric_id] = lcbs[candidate_id]
                    null = scientific[candidate_id].p0 if metric_id == "PRECISION" else 0.0
                    p_values[family].setdefault(candidate_id, {})[metric_id] = h40_marginal_p(
                        points[candidate_id], vectors[candidate_id], null,
                    )

        representatives: dict[str, str] = {}
        for family, members in by_family.items():
            if family in unavailable or not members:
                continue
            eligible = [candidate_id for candidate_id in members if scientific[candidate_id].hard_gates_passed]
            if eligible:
                eligible.sort(key=lambda candidate_id: (
                    -adjusted[family][candidate_id]["NET_EXPECTANCY"],
                    -adjusted[family][candidate_id]["PRECISION"],
                    candidates[candidate_id].entry.complexity,
                    candidate_id,
                ))
                representatives[family] = eligible[0]
        holm: dict[str, dict[str, float]] = {}
        for metric_id in ("PRECISION", "NET_EXPECTANCY"):
            raw = {
                family: p_values[family][representatives[family]][metric_id]
                if family in representatives else 1.0
                for family in _FAMILIES
            }
            holm[metric_id] = h40_holm_fixed_six(raw)
        for family, members in by_family.items():
            if family in unavailable or not members:
                continue
            representative = representatives.get(family)
            for candidate_id in members:
                lcbs = adjusted[family][candidate_id]
                passed = (
                    candidate_id == representative
                    and holm["PRECISION"][family] <= 0.05
                    and holm["NET_EXPECTANCY"][family] <= 0.05
                )
                self._verified[candidate_id] = H40CandidateVerification(
                    hard_gates_passed=passed,
                    adjusted_lcb_net_expectancy=Decimal(str(lcbs["NET_EXPECTANCY"])),
                    adjusted_lcb_precision=Decimal(str(lcbs["PRECISION"])),
                )

    def verify_candidate(
        self,
        entry: H40CandidateResultEntry,
        *,
        run_authority_id: str,
        correction_manifest_hash: str,
    ) -> H40CandidateVerification:
        H40ProductionDiscoveryEvidenceVerifier.assert_runtime_integrity(self)
        try:
            results_intact = _VERIFIER_RESULTS.get(self) == self._result_binding()
        except (AttributeError, TypeError, ValueError):
            results_intact = False
        if not results_intact:
            _fail("production verifier scientific results changed after verification")
        if (
            self._manifest_hash is None or self._evidence_hash is None
            or correction_manifest_hash != self._manifest_hash
            or run_authority_id != self._receipt.run_authority_id
            or self._entries_by_id.get(entry.structural_configuration_hash) != entry
            or entry.structural_configuration_hash not in self._verified
        ):
            _fail("candidate verification has no matching bound Discovery manifest")
        for digest, schema_id, keys in self._dependencies:
            self._resolver.load(digest, schema_id, keys)
        return self._verified[entry.structural_configuration_hash]

    def verify_wf_fold(
        self,
        entry: H40WFFoldResultEntry,
        *,
        evidence: H40WFValidationResultEvidence,
    ) -> bool:
        H40ProductionDiscoveryEvidenceVerifier.assert_runtime_integrity(self)
        _fail("production WF scientific verification is not authorized", H40ReasonCode.NOT_TESTABLE)


_VERIFIER_BINDINGS: WeakKeyDictionary[
    H40ProductionDiscoveryEvidenceVerifier, tuple[Any, ...]
] = WeakKeyDictionary()
_VERIFIER_RESULTS: WeakKeyDictionary[H40ProductionDiscoveryEvidenceVerifier, str] = (
    WeakKeyDictionary()
)
_VERIFIER_METHODS: Mapping[str, Any] = MappingProxyType({
    name: method
    for name, method in vars(H40ProductionDiscoveryEvidenceVerifier).items()
    if callable(method)
})
_RESOLVER_METHODS: Mapping[str, Any] = MappingProxyType({
    name: method
    for name, method in vars(H40DiscoveryEvidenceResolver).items()
    if callable(method)
})
