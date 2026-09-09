from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.research_contract.canonical import FrozenDict, canonical_sha256
from btc_quant_agent.research_contract.models import (
    P6_PENDING,
    DecisionStatus,
    EvidenceCompleteness,
    EvidenceReference,
    EvaluationMethod,
    ExperimentMetadata,
    FeatureDefinition,
    PredictionTarget,
    VersionedIdentity,
)
from btc_quant_agent.research_contract.registry import (
    EvidenceValidationError,
    InvalidTransitionError,
    RegistryCorruptionError,
    ResearchContractError,
    ResearchContractRegistry,
    StaleRegistryError,
)
from btc_quant_agent.research_registry import ResearchRegistry


FIXED_TIME = "2026-09-09T01:30:00+00:00"


def _identity(logical_id: str, value: Any, version: str = "v1") -> VersionedIdentity:
    return VersionedIdentity.from_payload(logical_id, version, value)


def _protocol(
    *,
    parameters: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    created_at_utc: str = FIXED_TIME,
) -> ExperimentMetadata:
    return ExperimentMetadata(
        experiment_id="EXP-P5-CAUSAL",
        name="Causal BTC policy evaluation",
        input_contract=_identity("BTC_CANONICAL_INPUT", {"bars": "1m", "funding": True}),
        feature_definition=FeatureDefinition(
            feature_id="F_MOMENTUM",
            name="Causal momentum",
            formula="close[t] / close[t-window] - 1",
            input_requirements=("closed_btcusdt_1m",),
            parameters=FrozenDict(parameters or {"window": 60, "winsor": [0.01, 0.99]}),
            bounds=(-1.0, 1.0),
        ),
        prediction_target=PredictionTarget(
            target_id="TARGET_RETURN_60M",
            name="Future 60m return",
            horizon_ms=3_600_000,
            horizon_description="first tradable open through 60m terminal mark",
        ),
        evaluation_method=EvaluationMethod(
            method_name="FWL_HAC",
            statistical_test="OLS_T_STATISTIC",
            parameters=FrozenDict({"hac_lag": 3, "controls": ["baseline"]}),
        ),
        economic_policy=_identity("POLICY_CAUSAL_MOMENTUM", {"entry_z": 2.0}),
        cost_model=_identity("COST_BINANCE_VIP0", {"taker_bps": 5.0}),
        execution_model=_identity(
            "EXECUTION_P4_C2", {"entry": "next_open", "intrabar": "standing_conditional"}
        ),
        benchmark=P6_PENDING,
        product_scope=("BTCUSDT-PERP",),
        code_revision="381e6f034698ba00fb971e151746336814d41a98",
        terminal_policy="FAIL_INCOMPLETE_FUNDING_AND_EXCLUDE_INCOMPLETE_HORIZONS",
        created_at_utc=created_at_utc,
        metadata=FrozenDict(metadata or {"comment": "P5 fixture"}),
    )


def _evidence(
    tmp_path: Path,
    protocol: ExperimentMetadata,
    *,
    name: str = "statistical-result",
    evidence_type: str = "STATISTICAL_RESULT",
) -> EvidenceReference:
    path = tmp_path / f"{name}.json"
    path.write_text(json.dumps({"name": name}, sort_keys=True) + "\n", encoding="utf-8")
    return EvidenceReference.from_file(
        path,
        evidence_type=evidence_type,
        logical_id=name,
        producing_revision_id=protocol.experiment_revision_id,
        producing_code_revision=protocol.code_revision,
        observed_at_utc=FIXED_TIME,
    )


def _transition_to_statistical(
    registry: ResearchContractRegistry,
    protocol: ExperimentMetadata,
    evidence: EvidenceReference,
) -> None:
    registry.update_decision_status(
        protocol.experiment_revision_id,
        DecisionStatus.STATISTICALLY_QUALIFIED,
        evidence_references=[evidence],
        reason="predefined statistical gate passed",
        actor="pytest",
        source="P5_TEST",
        decided_at_utc=FIXED_TIME,
        statistical_result_id=evidence.evidence_id,
    )


def test_deep_immutability_copies_nested_sources_and_blocks_exposed_mutation() -> None:
    requirements = ["closed_btcusdt_1m"]
    parameters = {"window": 60, "nested": {"levels": [1, 2]}}
    metadata = {"owners": ["research"]}
    feature = FeatureDefinition(
        "F", "feature", "formula", input_requirements=requirements, parameters=parameters
    )
    protocol = replace(_protocol(metadata=metadata), feature_definition=feature)
    original_hash = protocol.protocol_hash

    requirements.append("future_label")
    parameters["window"] = 999
    parameters["nested"]["levels"].append(3)
    metadata["owners"].append("mutator")

    assert protocol.protocol_hash == original_hash
    assert protocol.feature_definition.input_requirements == ("closed_btcusdt_1m",)
    assert protocol.feature_definition.parameters["window"] == 60
    assert protocol.metadata["owners"] == ("research",)
    with pytest.raises(TypeError):
        protocol.feature_definition.parameters["window"] = 1  # type: ignore[index]
    nested = protocol.feature_definition.parameters["nested"]
    assert isinstance(nested, FrozenDict)
    with pytest.raises(TypeError):
        nested["levels"] = ()  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        protocol.code_revision = "mutated"  # type: ignore[misc]


def test_hash_determinism_equivalent_order_and_save_load(tmp_path: Path) -> None:
    first = _protocol(parameters={"window": 60, "limits": {"high": 2, "low": 1}})
    second = _protocol(parameters={"limits": {"low": 1, "high": 2}, "window": 60})
    assert first.canonical_semantic_json == second.canonical_semantic_json
    assert first.protocol_hash == second.protocol_hash
    assert first.experiment_revision_id == second.experiment_revision_id

    path = tmp_path / "registry.json"
    registry = ResearchContractRegistry(path)
    registry.register_experiment(first, registered_at_utc=FIXED_TIME)
    loaded = ResearchContractRegistry(path)
    restored = loaded.get_experiment(first.experiment_revision_id)
    assert restored.protocol_hash == first.protocol_hash
    assert restored.canonical_semantic_json == first.canonical_semantic_json


@pytest.mark.parametrize(
    "change",
    [
        lambda p: replace(
            p,
            feature_definition=replace(
                p.feature_definition, parameters=FrozenDict({"window": 61})
            ),
        ),
        lambda p: replace(p, prediction_target=replace(p.prediction_target, horizon_ms=7_200_000)),
        lambda p: replace(
            p, evaluation_method=replace(p.evaluation_method, method_name="BLOCK_BOOTSTRAP")
        ),
        lambda p: replace(p, economic_policy=_identity("POLICY_CAUSAL_MOMENTUM", {"entry_z": 2.1})),
        lambda p: replace(p, cost_model=_identity("COST_BINANCE_VIP0", {"taker_bps": 6.0})),
        lambda p: replace(p, execution_model=_identity("EXECUTION_P4_C2", {"entry": "vwap"})),
        lambda p: replace(p, input_contract=_identity("BTC_CANONICAL_INPUT", {"bars": "5m"})),
        lambda p: replace(p, terminal_policy="LIQUIDATE_AT_LAST_COMPLETE_MARK"),
    ],
    ids=[
        "feature",
        "target",
        "evaluation",
        "economic-policy",
        "cost-model",
        "execution-model",
        "input-contract",
        "terminal-policy",
    ],
)
def test_each_semantic_change_creates_new_identity(change: Any) -> None:
    original = _protocol()
    changed = change(original)
    assert changed.protocol_hash != original.protocol_hash
    assert changed.experiment_revision_id != original.experiment_revision_id


def test_nonsemantic_audit_changes_do_not_change_protocol_identity() -> None:
    first = _protocol(metadata={"comment": "first"}, created_at_utc=FIXED_TIME)
    second = _protocol(
        metadata={"comment": "second"}, created_at_utc="2026-09-09T02:30:00+00:00"
    )
    assert first.protocol_hash == second.protocol_hash
    assert first.experiment_revision_id == second.experiment_revision_id


def test_no_semantic_overwrite_and_exact_duplicate_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    registry = ResearchContractRegistry(path)
    original = _protocol(metadata={"comment": "original"})
    registry.register_experiment(original, registered_at_utc=FIXED_TIME)
    generation = registry.generation

    duplicate = _protocol(
        metadata={"comment": "later audit comment"},
        created_at_utc="2026-09-09T02:30:00+00:00",
    )
    returned = registry.register_experiment(duplicate)
    assert returned is original
    assert registry.generation == generation
    assert len(registry.list_experiments()) == 1

    changed = replace(
        original,
        feature_definition=replace(
            original.feature_definition, parameters=FrozenDict({"window": 120})
        ),
    )
    registry.register_experiment(changed, registered_at_utc=FIXED_TIME)
    assert len(registry.list_revisions(original.experiment_family)) == 2
    assert registry.get_experiment(original.experiment_revision_id) == original
    with pytest.raises(ResearchContractError, match="allow_update"):
        registry.register_experiment(changed, allow_update=True)


def test_legal_transition_appends_once_and_invalid_jump_is_atomic(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    protocol = _protocol()
    registry = ResearchContractRegistry(path)
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    assert registry.get_status(protocol.experiment_revision_id) is DecisionStatus.REGISTERED
    assert len(registry.decision_events()) == 1

    before = path.read_bytes()
    generation = registry.generation
    with pytest.raises(InvalidTransitionError, match="illegal"):
        registry.update_decision_status(
            protocol.experiment_revision_id,
            DecisionStatus.ECONOMICALLY_QUALIFIED,
            evidence_references=[],
            reason="illegal jump",
            actor="pytest",
            source="P5_TEST",
        )
    assert path.read_bytes() == before
    assert registry.generation == generation
    assert len(registry.decision_events()) == 1

    evidence = _evidence(tmp_path, protocol)
    _transition_to_statistical(registry, protocol, evidence)
    assert registry.get_status(protocol.experiment_revision_id) is DecisionStatus.STATISTICALLY_QUALIFIED
    assert len(registry.decision_events()) == 2

    before = path.read_bytes()
    with pytest.raises(InvalidTransitionError, match="illegal"):
        registry.update_decision_status(
            protocol.experiment_revision_id,
            DecisionStatus.REGISTERED,
            evidence_references=[evidence],
            reason="backwards",
            actor="pytest",
            source="P5_TEST",
        )
    assert path.read_bytes() == before
    assert len(registry.decision_events()) == 2


def test_rejected_can_only_archive_and_frozen_never_thaws(tmp_path: Path) -> None:
    protocol = _protocol()
    registry = ResearchContractRegistry(tmp_path / "registry.json")
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    evidence = _evidence(tmp_path, protocol, name="rejection")
    registry.update_decision_status(
        protocol.experiment_revision_id,
        DecisionStatus.REJECTED,
        evidence_references=[evidence],
        reason="predefined gate failed",
        actor="pytest",
        source="P5_TEST",
        decided_at_utc=FIXED_TIME,
    )
    registry.update_decision_status(
        protocol.experiment_revision_id,
        DecisionStatus.FROZEN_ARCHIVE,
        evidence_references=[evidence],
        reason="archive terminal rejection",
        actor="pytest",
        source="P5_TEST",
        decided_at_utc=FIXED_TIME,
    )
    assert registry.get_status(protocol.experiment_revision_id) is DecisionStatus.FROZEN_ARCHIVE
    before = registry.storage_path.read_bytes() if registry.storage_path else b""
    with pytest.raises(InvalidTransitionError, match="illegal"):
        registry.update_decision_status(
            protocol.experiment_revision_id,
            DecisionStatus.REGISTERED,
            evidence_references=[evidence],
            reason="attempted thaw",
            actor="pytest",
            source="P5_TEST",
        )
    assert registry.storage_path is not None
    assert registry.storage_path.read_bytes() == before


def test_economic_qualification_remains_blocked_without_p6(tmp_path: Path) -> None:
    protocol = _protocol()
    registry = ResearchContractRegistry(tmp_path / "registry.json")
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    statistical = _evidence(tmp_path, protocol)
    _transition_to_statistical(registry, protocol, statistical)
    economic = _evidence(tmp_path, protocol, name="economic-result", evidence_type="ECONOMIC_RESULT")
    before = registry.storage_path.read_bytes() if registry.storage_path else b""

    with pytest.raises(InvalidTransitionError, match="P6 evidence contract"):
        registry.update_decision_status(
            protocol.experiment_revision_id,
            DecisionStatus.ECONOMICALLY_QUALIFIED,
            evidence_references=[economic],
            reason="P5 must not qualify economics",
            actor="pytest",
            source="P5_TEST",
            economic_result_id=economic.evidence_id,
        )
    assert registry.get_status(protocol.experiment_revision_id) is DecisionStatus.STATISTICALLY_QUALIFIED
    assert registry.storage_path is not None
    assert registry.storage_path.read_bytes() == before


def test_evidence_hash_binding_rejects_mismatch_and_later_tamper(tmp_path: Path) -> None:
    protocol = _protocol()
    path = tmp_path / "registry.json"
    registry = ResearchContractRegistry(path)
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    evidence = _evidence(tmp_path, protocol)
    registry.register_evidence(evidence)
    persisted_id = evidence.evidence_id

    incorrect = replace(evidence, content_sha256="0" * 64)
    with pytest.raises(EvidenceValidationError, match="hash mismatch"):
        registry.register_evidence(incorrect)
    evidence_path = evidence.local_path()
    assert evidence_path is not None
    evidence_path.write_text("tampered\n", encoding="utf-8")
    before = path.read_bytes()
    with pytest.raises(EvidenceValidationError, match="hash mismatch"):
        _transition_to_statistical(registry, protocol, evidence)
    assert path.read_bytes() == before
    assert registry.get_evidence(persisted_id).content_sha256 == evidence.content_sha256


def test_prohibited_reference_can_be_stored_without_reading_content_but_not_used(
    tmp_path: Path,
) -> None:
    protocol = _protocol()
    registry = ResearchContractRegistry(tmp_path / "registry.json")
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    sealed = EvidenceReference(
        evidence_type="H39_SEALED_REFERENCE",
        logical_id="H39-labels-not-loaded",
        content_sha256="1" * 64,
        observed_at_utc=FIXED_TIME,
        producing_revision_id="H39_FROZEN_PROTOCOL",
        producing_code_revision="historical-v0.3",
        completeness=EvidenceCompleteness.PROHIBITED,
        path_or_uri=str(tmp_path / "deliberately-absent-h39-labels.parquet"),
    )
    registry.register_evidence(sealed)
    with pytest.raises(EvidenceValidationError, match="not complete"):
        registry.update_decision_status(
            protocol.experiment_revision_id,
            DecisionStatus.REJECTED,
            evidence_references=[sealed],
            reason="cannot use prohibited evidence",
            actor="pytest",
            source="P5_TEST",
        )


def test_atomic_failure_before_replace_preserves_previous_bytes_and_state(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    original = _protocol()
    ResearchContractRegistry(path).register_experiment(original, registered_at_utc=FIXED_TIME)
    previous_bytes = path.read_bytes()

    def fail_before_replace(_: Path) -> None:
        raise OSError("injected failure before replace")

    failing = ResearchContractRegistry(path, before_replace=fail_before_replace)
    old_generation = failing.generation
    changed = replace(
        original,
        evaluation_method=replace(original.evaluation_method, method_name="INJECTED_FAILURE"),
    )
    with pytest.raises(OSError, match="injected failure"):
        failing.register_experiment(changed, registered_at_utc=FIXED_TIME)

    assert path.read_bytes() == previous_bytes
    assert failing.generation == old_generation
    assert len(failing.list_experiments()) == 1
    reloaded = ResearchContractRegistry(path)
    assert reloaded.list_experiments() == [original]
    assert not list(tmp_path.glob(".registry.json.*.tmp"))


def test_generation_compare_and_swap_rejects_stale_writer(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    original = _protocol()
    ResearchContractRegistry(path).register_experiment(original, registered_at_utc=FIXED_TIME)
    writer_a = ResearchContractRegistry(path)
    writer_b = ResearchContractRegistry(path)
    assert writer_a.generation == writer_b.generation

    revision_a = replace(original, code_revision="writer-a")
    revision_b = replace(original, code_revision="writer-b")
    writer_a.register_experiment(revision_a, registered_at_utc=FIXED_TIME)
    committed = path.read_bytes()
    with pytest.raises(StaleRegistryError, match="stale registry generation"):
        writer_b.register_experiment(revision_b, registered_at_utc=FIXED_TIME)
    assert path.read_bytes() == committed
    loaded = ResearchContractRegistry(path)
    ids = {item.experiment_revision_id for item in loaded.list_experiments()}
    assert ids == {original.experiment_revision_id, revision_a.experiment_revision_id}
    assert revision_b.experiment_revision_id not in ids


def test_corrupt_registry_variants_fail_closed_never_fallback_empty(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    protocol = _protocol()
    ResearchContractRegistry(path).register_experiment(protocol, registered_at_utc=FIXED_TIME)
    valid = path.read_bytes()

    path.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(RegistryCorruptionError, match="unreadable"):
        ResearchContractRegistry(path)

    path.write_bytes(valid)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["schema_version"] = "999"
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryCorruptionError, match="unsupported registry schema"):
        ResearchContractRegistry(path)

    path.write_bytes(valid)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["protocols"][protocol.experiment_revision_id]["protocol_hash"] = "0" * 64
    core = {
        "schema_version": raw["schema_version"],
        "generation": raw["generation"],
        "payload": raw["payload"],
    }
    raw["content_hash"] = canonical_sha256(core)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryCorruptionError, match="protocol hash mismatch"):
        ResearchContractRegistry(path)

    path.write_bytes(valid)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["generation"] = 0
    core = {
        "schema_version": raw["schema_version"],
        "generation": raw["generation"],
        "payload": raw["payload"],
    }
    raw["content_hash"] = canonical_sha256(core)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(RegistryCorruptionError, match="generation"):
        ResearchContractRegistry(path)


def test_append_only_replay_reconstructs_status_after_save_load(tmp_path: Path) -> None:
    path = tmp_path / "registry.json"
    protocol = _protocol()
    registry = ResearchContractRegistry(path)
    registry.register_experiment(protocol, registered_at_utc=FIXED_TIME)
    evidence = _evidence(tmp_path, protocol)
    _transition_to_statistical(registry, protocol, evidence)
    registry.update_decision_status(
        protocol.experiment_revision_id,
        DecisionStatus.REJECTED,
        evidence_references=[evidence],
        reason="economic work remains not testable",
        actor="pytest",
        source="P5_TEST",
        decided_at_utc=FIXED_TIME,
    )
    registry.update_decision_status(
        protocol.experiment_revision_id,
        DecisionStatus.FROZEN_ARCHIVE,
        evidence_references=[evidence],
        reason="archive rejected revision",
        actor="pytest",
        source="P5_TEST",
        decided_at_utc=FIXED_TIME,
    )

    loaded = ResearchContractRegistry(path)
    assert loaded.reconstruct_statuses() == {
        protocol.experiment_revision_id: DecisionStatus.FROZEN_ARCHIVE
    }
    events = loaded.decision_events(protocol.experiment_revision_id)
    assert [event.sequence for event in events] == [1, 2, 3, 4]
    assert events[0].previous_event_hash is None
    assert all(events[index].previous_event_hash == events[index - 1].event_hash for index in range(1, 4))


def test_legacy_registry_and_final_holdout_remain_isolated_and_sealed() -> None:
    legacy = ResearchRegistry.load("configs/research_registry.json")
    legacy.validate(".")
    assert legacy.final_holdout == "SEALED"
    assert all(not component.final_holdout_accessed for component in legacy.components.values())
