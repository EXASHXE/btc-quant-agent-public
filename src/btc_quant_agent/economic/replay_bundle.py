from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from ..domain import Candle
from ..research_contract.canonical import (
    canonical_sha256,
    thaw_json,
)
from ..research_contract.models import EvidenceReference, ExperimentMetadata
from .signal import InformationSignal
from .signal_producer import SignalProducerRegistry, _runtime_candle_payload

FORMAL_REPLAY_INPUT_BUNDLE_SCHEMA_VERSION = "1.0.0"
VERIFIED_BY_REPLAY_SCOPE = "VERIFIED_BY_REPLAY"


@dataclass(frozen=True)
class InputReference:
    """Exact content-bound reference to a canonical input row."""

    source_type: str
    dataset_evidence_id: str
    open_time_ms: int
    close_time_ms: int
    available_at_ms: int
    row_content_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "dataset_evidence_id": self.dataset_evidence_id,
            "open_time_ms": self.open_time_ms,
            "close_time_ms": self.close_time_ms,
            "available_at_ms": self.available_at_ms,
            "row_content_sha256": self.row_content_sha256,
        }


@dataclass(frozen=True)
class DecisionInputEntry:
    """Per-signal proven input preimage and generation contract."""

    signal_id: str
    signal_timestamp_ms: int
    signal_payload: dict[str, Any]
    signal_payload_sha256: str
    producer_identity: str
    producer_version: str
    input_references: tuple[dict[str, Any], ...]
    input_set_sha256: str
    generation_contract: dict[str, Any]
    verified_scope: str = VERIFIED_BY_REPLAY_SCOPE

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": self.signal_id,
            "signal_timestamp_ms": self.signal_timestamp_ms,
            "signal_payload": dict(self.signal_payload),
            "signal_payload_sha256": self.signal_payload_sha256,
            "producer_identity": self.producer_identity,
            "producer_version": self.producer_version,
            "input_references": list(self.input_references),
            "input_set_sha256": self.input_set_sha256,
            "generation_contract": dict(self.generation_contract),
            "verified_scope": self.verified_scope,
        }


@dataclass(frozen=True)
class ReplayInputBundle:
    """Canonical versioned replay-input contract (FORMAL_REPLAY_INPUT_BUNDLE_V1)."""

    schema_version: str
    experiment_revision_id: str
    protocol_hash: str
    dataset_evidence_id: str
    dataset_content_sha256: str
    input_contract_identity: dict[str, Any]
    signal_set_sha256: str
    decision_inputs: tuple[dict[str, Any], ...]
    causal_execution_inputs: tuple[dict[str, Any], ...] = ()
    funding_input_identity: str | None = None
    bundle_sha256: str = ""

    def __post_init__(self) -> None:
        computed = canonical_sha256(self.semantic_payload())
        if not self.bundle_sha256:
            object.__setattr__(self, "bundle_sha256", computed)
        elif self.bundle_sha256 != computed:
            raise ValueError(
                f"bundle_sha256 mismatch: declared {self.bundle_sha256}, computed {computed}"
            )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "experiment_revision_id": self.experiment_revision_id,
            "protocol_hash": self.protocol_hash,
            "dataset_evidence_id": self.dataset_evidence_id,
            "dataset_content_sha256": self.dataset_content_sha256,
            "input_contract_identity": dict(self.input_contract_identity),
            "signal_set_sha256": self.signal_set_sha256,
            "decision_inputs": list(self.decision_inputs),
            "causal_execution_inputs": list(self.causal_execution_inputs),
            "funding_input_identity": self.funding_input_identity,
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["bundle_sha256"] = self.bundle_sha256
        return payload

    def legacy_decision_bindings(self) -> list[dict[str, Any]]:
        """Project the bundle into the absorbed legacy decision bindings compatibility view."""
        bindings: list[dict[str, Any]] = []
        for entry in self.decision_inputs:
            open_times = [ref["open_time_ms"] for ref in entry["input_references"]]
            legacy_hash = (
                entry.get("generation_contract", {}).get("expected_preimage_sha256")
                or entry["input_set_sha256"]
            )
            bindings.append(
                {
                    "schema_version": "1.0.0",
                    "dataset_evidence_id": self.dataset_evidence_id,
                    "dataset_content_sha256": self.dataset_content_sha256,
                    "input_contract": dict(self.input_contract_identity),
                    "material_input_scope": "EXACT_COMPLETE_SET",
                    "signal": dict(entry["signal_payload"]),
                    "decision_boundary_ms": entry["signal_timestamp_ms"],
                    "observation_open_times_ms": open_times,
                    "material_input_set_sha256": legacy_hash,
                }
            )
        return bindings


def build_formal_replay_input_bundle(
    *,
    protocol: ExperimentMetadata,
    dataset_evidence: EvidenceReference,
    candles: Sequence[Candle],
    signals: Sequence[InformationSignal],
    decision_inputs: Sequence[Mapping[str, Any]],
    funding_events: Sequence[Any] = (),
    causal_execution_inputs: Sequence[Mapping[str, Any]] = (),
) -> ReplayInputBundle:
    """Construct and verify a canonical ReplayInputBundle from concrete inputs."""
    candles_by_open = {c.open_time_ms: c for c in candles}
    sorted_signals = sorted(signals, key=lambda s: (s.timestamp_ms, s.signal_id))
    signal_payloads = [s.to_dict() for s in sorted_signals]
    signal_set_sha256 = canonical_sha256(signal_payloads)

    normalized_entries: list[dict[str, Any]] = []
    seen_signal_ids: set[str] = set()

    for idx, raw in enumerate(decision_inputs):
        item = thaw_json(raw)
        if not isinstance(item, dict):
            raise TypeError(f"decision input entry {idx} must be a dictionary")
        if "signal" in item:
            signal_payload = dict(item["signal"])
            signal_id = str(signal_payload["signal_id"])
            signal_timestamp_ms = int(signal_payload["timestamp_ms"])
        else:
            signal_id = str(item["signal_id"])
            signal_timestamp_ms = int(item["signal_timestamp_ms"])
            signal_payload = dict(item["signal_payload"])

        if signal_id in seen_signal_ids:
            raise ValueError(f"duplicate decision input entry for signal {signal_id}")
        seen_signal_ids.add(signal_id)

        producer_identity = str(item.get("producer_identity", "CANONICAL_RULE_SIGNAL_PRODUCER"))
        producer_version = str(item.get("producer_version", "1.0.0"))
        generation_contract = dict(item.get("generation_contract", {}))

        # Build / normalize input references
        raw_refs = item.get("input_references")
        if raw_refs is None:
            open_times = item.get("observation_open_times_ms") or item.get("material_input_open_times_ms")
            if not open_times:
                raise ValueError(f"decision input entry for {signal_id} lacks input references")
            input_refs = []
            for ot in open_times:
                if ot not in candles_by_open:
                    raise ValueError(f"referenced candle open_time_ms {ot} not found in dataset")
                c = candles_by_open[ot]
                if c.available_at_ms is None or c.available_at_ms > signal_timestamp_ms:
                    raise ValueError(f"input candle at {ot} was not available by signal timestamp")
                row_hash = canonical_sha256(_runtime_candle_payload(c))
                ref = InputReference(
                    source_type="CANONICAL_CANDLE",
                    dataset_evidence_id=dataset_evidence.evidence_id,
                    open_time_ms=c.open_time_ms,
                    close_time_ms=c.close_time_ms,
                    available_at_ms=c.available_at_ms,
                    row_content_sha256=row_hash,
                )
                input_refs.append(ref.to_dict())
        else:
            input_refs = [dict(r) for r in raw_refs]

        input_set_sha256 = canonical_sha256(input_refs)
        signal_payload_sha256 = canonical_sha256(signal_payload)

        # Default generation contract if empty
        if not generation_contract:
            open_times = [r["open_time_ms"] for r in input_refs]
            ref_candles = [candles_by_open[r["open_time_ms"]] for r in input_refs]
            preimage_hash = canonical_sha256([_runtime_candle_payload(c) for c in ref_candles])
            generation_contract = {
                "rule": "FIXED_DIRECTION",
                "direction": int(signal_payload.get("direction", 1)),
                "strength": float(signal_payload.get("strength", 1.0)),
                "horizon_ms": int(signal_payload.get("horizon_ms", 3_600_000)),
                "asset": str(signal_payload.get("asset", "BTCUSDT")),
                "min_lookback_bars": len(open_times),
                "material_input_open_times_ms": open_times,
                "expected_preimage_sha256": preimage_hash,
            }

        entry = DecisionInputEntry(
            signal_id=signal_id,
            signal_timestamp_ms=signal_timestamp_ms,
            signal_payload=signal_payload,
            signal_payload_sha256=signal_payload_sha256,
            producer_identity=producer_identity,
            producer_version=producer_version,
            input_references=tuple(input_refs),
            input_set_sha256=input_set_sha256,
            generation_contract=generation_contract,
            verified_scope=VERIFIED_BY_REPLAY_SCOPE,
        )
        normalized_entries.append(entry.to_dict())

    normalized_entries.sort(key=lambda e: (int(e["signal_timestamp_ms"]), str(e["signal_id"])))

    funding_identity = (
        canonical_sha256([asdict(f) for f in sorted(funding_events, key=lambda f: f.timestamp_ms)])
        if funding_events
        else None
    )

    bundle = ReplayInputBundle(
        schema_version=FORMAL_REPLAY_INPUT_BUNDLE_SCHEMA_VERSION,
        experiment_revision_id=protocol.experiment_revision_id,
        protocol_hash=protocol.protocol_hash,
        dataset_evidence_id=dataset_evidence.evidence_id,
        dataset_content_sha256=dataset_evidence.content_sha256,
        input_contract_identity=protocol.input_contract.to_dict(),
        signal_set_sha256=signal_set_sha256,
        decision_inputs=tuple(normalized_entries),
        causal_execution_inputs=tuple(dict(c) for c in causal_execution_inputs),
        funding_input_identity=funding_identity,
    )

    # Perform formal verification before returning
    validate_formal_replay_input_bundle(
        bundle.to_dict(),
        candles=candles,
        expected_protocol=protocol,
        expected_dataset_evidence=dataset_evidence,
        expected_signals=signals,
    )
    return bundle


def validate_formal_replay_input_bundle(
    bundle_dict: Mapping[str, Any],
    *,
    candles: Sequence[Candle],
    expected_protocol: ExperimentMetadata | None = None,
    expected_dataset_evidence: EvidenceReference | None = None,
    expected_signals: Sequence[InformationSignal] | None = None,
    expected_bundle_sha256: str | None = None,
) -> dict[str, Any]:
    """Strictly validate a ReplayInputBundle with deterministic signal replay."""
    bundle = thaw_json(bundle_dict)
    if not isinstance(bundle, dict):
        raise TypeError("formal replay input bundle must be a dictionary")

    required_keys = {
        "schema_version",
        "experiment_revision_id",
        "protocol_hash",
        "dataset_evidence_id",
        "dataset_content_sha256",
        "input_contract_identity",
        "signal_set_sha256",
        "decision_inputs",
        "causal_execution_inputs",
        "funding_input_identity",
        "bundle_sha256",
    }
    if set(bundle) != required_keys:
        raise ValueError("formal replay input bundle schema mismatch")

    if bundle["schema_version"] != FORMAL_REPLAY_INPUT_BUNDLE_SCHEMA_VERSION:
        raise ValueError(f"unsupported replay input bundle schema version: {bundle['schema_version']}")

    # Verify bundle hash integrity
    semantic_payload = {k: bundle[k] for k in required_keys if k != "bundle_sha256"}
    computed_bundle_hash = canonical_sha256(semantic_payload)
    if bundle["bundle_sha256"] != computed_bundle_hash:
        raise ValueError("replay input bundle sha256 checksum mismatch")
    if expected_bundle_sha256 is not None and bundle["bundle_sha256"] != expected_bundle_sha256:
        raise ValueError("replay input bundle sha256 differs from expected identity")

    # Verify protocol bindings
    if expected_protocol is not None:
        if bundle["experiment_revision_id"] != expected_protocol.experiment_revision_id:
            raise ValueError("replay input bundle experiment revision mismatch")
        if bundle["protocol_hash"] != expected_protocol.protocol_hash:
            raise ValueError("replay input bundle protocol hash mismatch")
        if bundle["input_contract_identity"] != expected_protocol.input_contract.to_dict():
            raise ValueError("replay input bundle input contract mismatch")

    # Verify dataset bindings
    if expected_dataset_evidence is not None:
        if bundle["dataset_evidence_id"] != expected_dataset_evidence.evidence_id:
            raise ValueError("replay input bundle dataset evidence id mismatch")
        if bundle["dataset_content_sha256"] != expected_dataset_evidence.content_sha256:
            raise ValueError("replay input bundle dataset content hash mismatch")

    candles_by_open = {c.open_time_ms: c for c in candles}
    seen_signal_ids: set[str] = set()
    verified_signals: list[InformationSignal] = []

    for idx, entry in enumerate(bundle["decision_inputs"]):
        if not isinstance(entry, dict):
            raise TypeError(f"decision input entry {idx} must be a dictionary")
        if entry.get("verified_scope") != VERIFIED_BY_REPLAY_SCOPE:
            raise ValueError(f"decision input entry {idx} is not verified by replay")

        signal_id = str(entry["signal_id"])
        if signal_id in seen_signal_ids:
            raise ValueError(f"duplicate signal {signal_id} in replay input bundle")
        seen_signal_ids.add(signal_id)

        signal_timestamp_ms = int(entry["signal_timestamp_ms"])
        signal_payload = entry["signal_payload"]
        if not isinstance(signal_payload, dict):
            raise TypeError(f"signal payload for {signal_id} must be a dictionary")

        if canonical_sha256(signal_payload) != entry["signal_payload_sha256"]:
            raise ValueError(f"signal payload sha256 mismatch for {signal_id}")

        formal_signal = InformationSignal.from_dict(signal_payload)
        if formal_signal.signal_id != signal_id:
            raise ValueError(f"signal id mismatch between entry and payload for {signal_id}")
        if formal_signal.timestamp_ms != signal_timestamp_ms:
            raise ValueError(f"timestamp mismatch between entry and payload for {signal_id}")

        input_refs = entry["input_references"]
        if not isinstance(input_refs, list) or not input_refs:
            raise ValueError(f"decision inputs for {signal_id} require non-empty input references")

        if canonical_sha256(input_refs) != entry["input_set_sha256"]:
            raise ValueError(f"input set sha256 mismatch for {signal_id}")

        ref_candles: list[Candle] = []
        last_open_time = -1
        for ref in input_refs:
            if not isinstance(ref, dict):
                raise TypeError(f"input reference for {signal_id} must be a dictionary")
            open_time = int(ref["open_time_ms"])
            if open_time <= last_open_time:
                raise ValueError(f"input references for {signal_id} must be strictly increasing")
            last_open_time = open_time

            if open_time not in candles_by_open:
                raise ValueError(f"referenced candle open_time_ms {open_time} not found in dataset")
            candle = candles_by_open[open_time]

            # Validate candle content and closed state
            if candle.closed is not True:
                raise ValueError(f"referenced candle at {open_time} is not closed")
            if candle.available_at_ms is None:
                raise ValueError(f"referenced candle at {open_time} lacks availability timestamp")
            if candle.available_at_ms > signal_timestamp_ms:
                raise ValueError(f"input candle at {open_time} was not available by signal timestamp")
            if int(ref["available_at_ms"]) != candle.available_at_ms:
                raise ValueError(f"asserted availability timestamp mismatch for candle at {open_time}")

            actual_row_hash = canonical_sha256(_runtime_candle_payload(candle))
            if ref["row_content_sha256"] != actual_row_hash:
                raise ValueError(f"candle row content sha256 mismatch at {open_time}")
            ref_candles.append(candle)

        # Producer lookup and deterministic replay verification
        producer_identity = str(entry["producer_identity"])
        producer_version = str(entry["producer_version"])
        producer = SignalProducerRegistry.get(producer_identity, producer_version)
        if producer is None:
            raise ValueError(
                f"unregistered or non-replayable signal producer: {producer_identity} {producer_version} (Mode B: NOT_TESTABLE)"
            )

        generation_contract = entry["generation_contract"]
        if not isinstance(generation_contract, dict):
            raise TypeError(f"generation contract for {signal_id} must be a dictionary")

        replayed_signal = producer.replay_signal(
            signal_id=signal_id,
            signal_timestamp_ms=signal_timestamp_ms,
            experiment_id=formal_signal.experiment_id,
            input_candles=ref_candles,
            generation_contract=generation_contract,
        )

        # Verify exact match between replayed signal and formal signal payload
        if replayed_signal.direction != formal_signal.direction:
            raise ValueError(
                f"replayed signal direction mismatch for {signal_id}: replayed {replayed_signal.direction} != formal {formal_signal.direction}"
            )
        if replayed_signal.strength != formal_signal.strength:
            raise ValueError(
                f"replayed signal strength mismatch for {signal_id}: replayed {replayed_signal.strength} != formal {formal_signal.strength}"
            )
        if replayed_signal.timestamp_ms != formal_signal.timestamp_ms:
            raise ValueError(
                f"replayed signal timestamp mismatch for {signal_id}: replayed {replayed_signal.timestamp_ms} != formal {formal_signal.timestamp_ms}"
            )
        if replayed_signal.asset != formal_signal.asset:
            raise ValueError(
                f"replayed signal asset mismatch for {signal_id}: replayed {replayed_signal.asset} != formal {formal_signal.asset}"
            )
        if replayed_signal.horizon_ms != formal_signal.horizon_ms:
            raise ValueError(
                f"replayed signal horizon mismatch for {signal_id}: replayed {replayed_signal.horizon_ms} != formal {formal_signal.horizon_ms}"
            )

        verified_signals.append(formal_signal)

    # If expected signals provided, verify 1:1 coverage and signal_set_sha256
    if expected_signals is not None:
        sorted_expected = sorted(expected_signals, key=lambda s: (s.timestamp_ms, s.signal_id))
        expected_payloads = [s.to_dict() for s in sorted_expected]
        expected_signal_set_hash = canonical_sha256(expected_payloads)
        if bundle["signal_set_sha256"] != expected_signal_set_hash:
            raise ValueError("replay input bundle signal_set_sha256 mismatch")

        bundle_signal_payloads = [e["signal_payload"] for e in bundle["decision_inputs"]]
        if bundle_signal_payloads != expected_payloads:
            raise ValueError("replay input bundle decision inputs do not exactly cover signals")

    return bundle
