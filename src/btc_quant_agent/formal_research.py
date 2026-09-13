"""Explicit application workflow over the accepted P5/P6 economic kernel.

No strategy discovery, economic arithmetic, implicit data fetch or execution
transport lives here. Submitted signals are reconstructed by the registered
producer through the existing bundle validator, never trusted as trade truth.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .domain import Candle
from .economic.acceptance_verifier import validate_persisted_qualification_semantics
from .economic.execution_model import ExecutionModel
from .economic.fee_model import FeeModel
from .economic.funding import FundingModel, FundingSettlement
from .economic.policy import (
    EntryRule,
    ExitRule,
    MarketStateFilter,
    PositionSizing,
    RiskBudget,
    TradePolicy,
)
from .economic.qualification import (
    ComparisonContract,
    EconomicQualificationResult,
    EconomicRunResult,
    EligibleOpportunity,
    FormalBenchmarkSuite,
    build_formal_benchmark_suite,
    evaluate_formal_economic_qualification,
    execute_bound_run,
    make_artifact_evidence,
)
from .economic.replay_bundle import build_formal_replay_input_bundle
from .economic.signal import InformationSignal
from .economic.simulator import EconomicSimulationEngine
from .publication import PublicationConflict, publication_lock, publish_bytes
from .research_contract.canonical import FrozenDict, canonical_json, canonical_sha256
from .research_contract.models import EvidenceReference, ExperimentMetadata
from .research_contract.registry import (
    P6_BENCHMARK_EVIDENCE_TYPE,
    P6_RESULT_EVIDENCE_TYPE,
    P6_RUN_EVIDENCE_TYPE,
    ResearchContractRegistry,
)

FORMAL_JOB_SCHEMA_VERSION = "1.0.0"


def _research_path(path: str | Path) -> Path:
    # realpath resolves symlinks without Path.resolve's final stat: sealed paths
    # must be refused before any read/stat of the protected target.
    resolved = Path(os.path.realpath(path))
    parts = [part.lower().replace("-", "_") for part in resolved.parts]
    if any(Path(part).stem == "final_holdout" for part in parts):
        raise ValueError("Final Holdout is sealed; formal jobs cannot access it")
    if "h39_validation" in parts or resolved.name == "h39_canonical_1m_candles.sqlite3":
        raise ValueError("formal jobs cannot access operational H39 stores")
    return resolved


def _reject_constant(value: str) -> None:
    raise ValueError(f"nonfinite JSON value: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON field: {key}")
        result[key] = value
    return result


def _load_object(path: Path) -> dict[str, Any]:
    raw = json.loads(
        _research_path(path).read_text(encoding="utf-8"),
        parse_constant=_reject_constant,
        object_pairs_hook=_unique_object,
    )
    if not isinstance(raw, dict):
        raise TypeError("formal JSON input must be an object")
    return raw


@dataclass(frozen=True)
class FormalResearchJobSpec:
    protocol: ExperimentMetadata
    comparison: ComparisonContract
    dataset_evidence: EvidenceReference
    engine: EconomicSimulationEngine
    candles: tuple[Candle, ...]
    signals: tuple[InformationSignal, ...]
    decision_inputs: tuple[Mapping[str, Any], ...]
    eligible_opportunities: tuple[EligibleOpportunity, ...]
    funding_events: tuple[FundingSettlement, ...]
    observed_at_utc: str

    def __post_init__(self) -> None:
        timestamp = datetime.fromisoformat(self.observed_at_utc)
        if timestamp.utcoffset() is None:
            raise ValueError("formal job observation time must include a UTC offset")
        for field in ("candles", "signals", "eligible_opportunities", "funding_events"):
            object.__setattr__(self, field, tuple(getattr(self, field)))
        object.__setattr__(self, "decision_inputs", tuple(FrozenDict(x) for x in self.decision_inputs))
        source = self.dataset_evidence.local_path()
        if source is None:
            raise ValueError("formal jobs require explicit local dataset evidence")
        _research_path(source)

    @classmethod
    def load(cls, path: str | Path) -> FormalResearchJobSpec:
        """Load explicit inputs; never substitute defaults for missing authority.

        protocol_path is resolved relative to the job file. Evidence paths retain
        their canonical meaning relative to the process cwd, as in P5/P6; they
        cannot be silently rebased without changing their evidence identity.
        """
        source = _research_path(path)
        raw = _load_object(source)
        if set(raw) != {
            "schema_version", "protocol_path", "comparison", "dataset_evidence", "engine",
            "candles", "signals", "decision_inputs", "eligible_opportunities",
            "funding_events", "observed_at_utc",
        } or raw["schema_version"] != FORMAL_JOB_SCHEMA_VERSION:
            raise ValueError("unsupported formal job schema; legacy inputs are diagnostic only")
        protocol = ExperimentMetadata.from_dict(_load_object(source.parent / raw["protocol_path"]))
        comparison = ComparisonContract.from_payload(raw["comparison"])
        config = raw["engine"]
        if set(config) != {"policy", "fee_model", "execution_model", "funding_model"}:
            raise ValueError("formal engine inputs must be explicit")
        policy = dict(config["policy"])
        for name, kind in (
            ("entry_rule", EntryRule), ("exit_rule", ExitRule), ("position_sizing", PositionSizing),
            ("risk_budget", RiskBudget), ("market_filter", MarketStateFilter),
        ):
            policy[name] = kind(**policy[name])
        execution = dict(config["execution_model"])
        execution["fee_model"] = FeeModel(**execution["fee_model"])
        engine = EconomicSimulationEngine(
            policy=TradePolicy(**policy), fee_model=FeeModel(**config["fee_model"]),
            execution_model=ExecutionModel(**execution),
            funding_model=FundingModel(**config["funding_model"]),
            initial_cash=comparison.initial_capital,
        )
        # A missing closed flag must not acquire Candle's compatibility default.
        if any("closed" not in row or "available_at_ms" not in row for row in raw["candles"]):
            raise ValueError("formal candles require explicit closed/availability proof")
        return cls(
            protocol=protocol, comparison=comparison,
            dataset_evidence=EvidenceReference.from_dict(raw["dataset_evidence"]), engine=engine,
            candles=tuple(Candle(**row) for row in raw["candles"]),
            signals=tuple(InformationSignal.from_dict(row) for row in raw["signals"]),
            decision_inputs=tuple(raw["decision_inputs"]),
            eligible_opportunities=tuple(EligibleOpportunity(**row) for row in raw["eligible_opportunities"]),
            funding_events=tuple(FundingSettlement(**row) for row in raw["funding_events"]),
            observed_at_utc=raw["observed_at_utc"],
        )


@dataclass(frozen=True)
class FormalResearchJobResult:
    run: EconomicRunResult
    benchmarks: FormalBenchmarkSuite
    qualification: EconomicQualificationResult
    evidence: tuple[EvidenceReference, ...]
    directory: Path
    registry_decision_recorded: bool

    def status(self) -> dict[str, Any]:
        return {
            "classification": "FORMAL_CURRENT", "execution": "DISABLED",
            "run_result_id": self.run.result_id, "benchmark_suite_id": self.benchmarks.suite_id,
            "qualification_result_id": self.qualification.result_id,
            "qualification_verdict": self.qualification.verdict.value,
            "registry_decision_recorded": self.registry_decision_recorded,
            "directory": str(self.directory),
            "evidence": [item.to_dict() for item in self.evidence],
        }


def verify_formal_qualification(
    artifact: Mapping[str, Any], *, protocol: ExperimentMetadata,
    dataset_evidence: EvidenceReference,
) -> None:
    """Cold acceptance of submitted artifacts, independent of consumer labels."""
    if (
        artifact.get("artifact_type") != P6_RESULT_EVIDENCE_TYPE
        or artifact.get("schema_version") != "1.1.0"
    ):
        raise ValueError("legacy/unsupported result is NOT_TESTABLE_FOR_NEW_PROMOTION")
    semantic = artifact.get("semantic_payload")
    if not isinstance(semantic, Mapping):
        raise TypeError("formal qualification semantic payload is required")
    if artifact.get("result_id") != f"economic-qualification@{canonical_sha256(semantic)}":
        raise ValueError("formal qualification identity mismatch")
    if (
        semantic.get("protocol_hash") != protocol.protocol_hash
        or semantic.get("experiment_revision_id") != protocol.experiment_revision_id
    ):
        raise ValueError("formal qualification differs from authoritative protocol")
    source = dataset_evidence.local_path()
    if source is None:
        raise ValueError("formal acceptance requires explicit local dataset evidence")
    _research_path(source)
    validate_persisted_qualification_semantics(semantic, dataset_evidence, protocol=protocol)


def _publish_immutable(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (canonical_json(payload) + "\n").encode("utf-8")
    path = _research_path(path)
    with publication_lock(path):
        if path.exists():
            if path.read_bytes() != encoded:
                raise PublicationConflict("formal artifact exists with different bytes")
            return
        publish_bytes(path, encoded, expected_sha256=None)


def run_formal_job(
    spec: FormalResearchJobSpec, *, output_directory: str | Path,
    registry: ResearchContractRegistry | None = None, record_decision: bool = False,
) -> FormalResearchJobResult:
    """Generate and independently verify current artifacts before optional P5 commit.

    Every call performs cold replay. No reusable acceptance cache is introduced.
    File publication is immutable/idempotent, not a multi-file transaction: a
    failed job may leave verified run/suite artifacts, never an implicit decision.
    """
    output = _research_path(output_directory)
    if record_decision and registry is None:
        raise ValueError("record_decision requires an existing authoritative P5 registry")
    if registry is not None:
        if registry.storage_path is not None:
            _research_path(registry.storage_path)
        authority = registry.get_experiment(spec.protocol.experiment_revision_id)
        if authority.protocol_hash != spec.protocol.protocol_hash:
            raise ValueError("job protocol differs from registry authority")
    bundle = build_formal_replay_input_bundle(
        protocol=spec.protocol, dataset_evidence=spec.dataset_evidence, candles=spec.candles,
        signals=spec.signals, decision_inputs=spec.decision_inputs, funding_events=spec.funding_events,
    ) if spec.signals or spec.decision_inputs else None
    run = execute_bound_run(
        protocol=spec.protocol, comparison=spec.comparison, dataset_evidence=spec.dataset_evidence,
        engine=spec.engine, candles=spec.candles, signals=spec.signals,
        replay_input_bundle=bundle, funding_events=spec.funding_events,
    )
    benchmarks = build_formal_benchmark_suite(
        protocol=spec.protocol, comparison=spec.comparison, dataset_evidence=spec.dataset_evidence,
        candidate_run=run, engine=spec.engine, candles=spec.candles,
        eligible_opportunities=spec.eligible_opportunities, funding_events=spec.funding_events,
    )
    directory = output / run.result_hash
    references = [spec.dataset_evidence]
    for name, artifact, kind in (
        ("candidate-run", run.to_dict(), P6_RUN_EVIDENCE_TYPE),
        ("benchmark-suite", benchmarks.to_dict(), P6_BENCHMARK_EVIDENCE_TYPE),
    ):
        path = directory / f"{name}.json"
        _publish_immutable(path, artifact)
        references.append(make_artifact_evidence(
            path, evidence_type=kind, logical_id=name, protocol=spec.protocol,
            observed_at_utc=spec.observed_at_utc,
        ))
    qualification = evaluate_formal_economic_qualification(
        protocol=spec.protocol, comparison=spec.comparison, candidate_run=run, benchmarks=benchmarks,
        required_evidence_ids=tuple(item.evidence_id for item in references),
        generated_at_utc=spec.observed_at_utc,
    )
    verify_formal_qualification(
        qualification.to_dict(), protocol=spec.protocol, dataset_evidence=spec.dataset_evidence,
    )
    path = directory / f"qualification-{qualification.result_hash}.json"
    _publish_immutable(path, qualification.to_dict())
    result_evidence = make_artifact_evidence(
        path, evidence_type=P6_RESULT_EVIDENCE_TYPE, logical_id="qualification",
        protocol=spec.protocol, observed_at_utc=spec.observed_at_utc,
    )
    references.append(result_evidence)
    decision_recorded = False
    if record_decision:
        assert registry is not None
        event = registry.record_economic_qualification(
            qualification.decision_attestation(result_evidence), evidence_references=tuple(references),
            reason="verified formal consumer workflow", actor="formal-research-job",
            decided_at_utc=spec.observed_at_utc,
        )
        decision_recorded = event is not None
    return FormalResearchJobResult(
        run, benchmarks, qualification, tuple(references), directory, decision_recorded,
    )


def run_formal_job_file(
    job_path: str | Path, *, output_directory: str | Path,
    registry_path: str | Path | None = None, record_decision: bool = False,
) -> FormalResearchJobResult:
    spec = FormalResearchJobSpec.load(job_path)
    registry = None
    if registry_path is not None:
        path = _research_path(registry_path)
        if not path.is_file():
            raise FileNotFoundError("formal job requires an existing P5 registry")
        registry = ResearchContractRegistry(path)
    return run_formal_job(
        spec, output_directory=output_directory, registry=registry, record_decision=record_decision,
    )
