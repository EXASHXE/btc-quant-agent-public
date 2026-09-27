"""Synthetic-only closure checks for the production Discovery producer."""

from __future__ import annotations

import hashlib
import importlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from btc_quant_agent.h40.guards import H40GuardError
from btc_quant_agent.research_contract.canonical import canonical_json, canonical_sha256


def _synthetic_authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, seed: int = 31031) -> SimpleNamespace:
    """Real typed production path, with only canonical byte identity rebound to synthetic OHLC."""
    import pyarrow as pa
    import pyarrow.parquet as pq
    from test_v051_h40_p3_controller_authority_publication import (
        _exact_controller_authority,
        _exact_implementation_authority,
    )

    import btc_quant_agent.h40.source_manifest as source_module
    from btc_quant_agent.h40 import (
        H40DiscoveryAuthorizationReceipt,
        H40DiscoveryRunGrant,
        H40ProtocolIdentity,
        H40RunAuthority,
        H40RuntimeSnapshotSeal,
        H40SourceManifest,
        materialize_runtime_source_split_authority,
    )

    repo = tmp_path / "synthetic-repository"
    repo.mkdir()
    reference = H40SourceManifest.build_preregistered_reference(H40ProtocolIdentity.default().protocol_hash)
    eth = reference.get_source("ETHUSDT_USD_M_1H")
    path = repo / eth.locator
    path.parent.mkdir(parents=True)
    rng = np.random.Generator(np.random.PCG64(seed))
    rows: list[dict[str, float | int]] = []
    for start, count in ((datetime(2021, 1, 1, tzinfo=UTC), 96),
                         (datetime(2022, 10, 20, tzinfo=UTC), 288),
                         (datetime(2023, 1, 20, tzinfo=UTC), 288)):
        price = 100.0
        step = 0.0
        for hour in range(count):
            step = 0.35 * step + float(rng.normal(0, 0.002))
            close = price * float(np.exp(step))
            spread = float(rng.uniform(0.0005, 0.004))
            rows.append({"open_time_ms": int((start + timedelta(hours=hour)).timestamp() * 1000),
                         "open": price, "high": max(price, close) * (1 + spread),
                         "low": min(price, close) * (1 - spread), "close": close})
            price = close
    pq.write_table(pa.Table.from_pylist(rows), path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    original_spec = source_module.get_canonical_source_spec

    def synthetic_spec(protocol_hash: str, source_id: str):
        spec = original_spec(protocol_hash, source_id)
        return replace(spec, reference_file_sha256=digest) if source_id == eth.source_id else spec

    monkeypatch.setattr(source_module, "get_canonical_source_spec", synthetic_spec)
    reference = replace(reference, sources=tuple(
        replace(record, file_sha256=digest) if record.source_id == eth.source_id else record
        for record in reference.sources
    ))
    source = source_module.materialize_verified_manifest(repo, reference.protocol_identity_hash, reference)
    split, attestation = materialize_runtime_source_split_authority(source_manifest=source, repo_root=repo)
    seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=source, split_manifest=split, runtime_attestation=attestation, repo_root=repo,
    )
    implementation = _exact_implementation_authority()
    controller = _exact_controller_authority()
    run = H40RunAuthority.from_seal(seal, implementation.lifecycle_implementation_authority_hash)
    grant = H40DiscoveryRunGrant.from_controller_and_run(
        controller_authority=controller, run_authority=run, seal=seal,
        authorized_at_utc="2026-09-27T00:00:00Z",
    )
    receipt = H40DiscoveryAuthorizationReceipt(
        authorized_at_utc=grant.authorized_at_utc,
        controller_authority_hash=controller.controller_authority_hash,
        discovery_run_grant_hash=grant.discovery_run_grant_hash,
        discovery_selection_correction_contract_hash=controller.discovery_selection_correction_contract_hash,
        execution_disabled=True, not_testable_slot_count=150, registered_slot_count=18, total_slot_count=168,
        **{key: getattr(run, key) for key in (
            "lifecycle_governance_authority_hash", "lifecycle_implementation_authority_hash",
            "materialized_run_authority_hash", "protocol_authority_hash", "run_authority_id",
            "sealed_registered_roster_hash", "semantic_root_hash", "source_manifest_hash",
            "split_attestation_hash", "split_manifest_hash", "structural_ledger_hash",
        )},
    )
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()
    return SimpleNamespace(repo=repo, path=path, source=source, split=split, seal=seal,
                           implementation=implementation, controller=controller, run=run,
                           receipt=receipt, root=evidence_root)


@pytest.fixture
def authority(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    return _synthetic_authority(tmp_path, monkeypatch)


def _producer(authority: SimpleNamespace, **overrides):
    module = importlib.import_module("btc_quant_agent.h40.discovery_producer")
    inputs = {"implementation_authority": authority.implementation, "controller_authority": authority.controller,
                  "authorization_receipt": authority.receipt, "run_authority": authority.run,
                  "seal": authority.seal, "split_manifest": authority.split,
                  "approved_evidence_root": authority.root, "repo_root": authority.repo}
    inputs.update(overrides)
    return module.H40ProductionDiscoveryEvidenceProducer(**inputs)


def test_p01_p19_complete_producer_verifier_roundtrip(authority: SimpleNamespace) -> None:
    from btc_quant_agent.h40 import H40ProductionDiscoveryEvidenceVerifier

    result = _producer(authority).produce()
    assert len(result.entries) == 18
    verifier = H40ProductionDiscoveryEvidenceVerifier(
        approved_evidence_root=result.approved_evidence_root, seal=authority.seal,
        authorization_receipt=authority.receipt, split_manifest=authority.split,
    )
    verifier.verify_discovery_manifest(result.evidence, result.entries)
    verified = [verifier.verify_candidate(entry, run_authority_id=result.evidence.run_authority_id,
                                              correction_manifest_hash=result.evidence.correction_input_evidence_manifest_hash) for entry in result.entries]
    verifier.verify_discovery_manifest(result.evidence, result.entries)
    assert verified == [verifier.verify_candidate(entry, run_authority_id=result.evidence.run_authority_id,
                                              correction_manifest_hash=result.evidence.correction_input_evidence_manifest_hash) for entry in result.entries]


def test_p02_p03_canonical_store_is_idempotent(tmp_path: Path) -> None:
    module = importlib.import_module("btc_quant_agent.h40.discovery_producer")
    writer = module.H40DiscoveryEvidenceWriter(tmp_path)
    payload = {"schema_id": "SYNTHETIC_TEST_V1", "value": "1"}
    digest = writer.write(payload)
    assert digest == canonical_sha256(payload)
    path = tmp_path / digest[:2] / f"{digest}.json"
    assert path.read_bytes() == canonical_json(payload).encode()
    assert writer.write(payload) == digest
    assert not list(tmp_path.rglob("*.tmp"))


def test_p04_conflicting_noncanonical_object_rejected(tmp_path: Path) -> None:
    module = importlib.import_module("btc_quant_agent.h40.discovery_producer")
    writer = module.H40DiscoveryEvidenceWriter(tmp_path)
    payload = {"schema_id": "SYNTHETIC_TEST_V1", "value": "1"}
    digest = writer.write(payload)
    path = tmp_path / digest[:2] / f"{digest}.json"
    path.write_bytes(b'{"value":"1", "schema_id":"SYNTHETIC_TEST_V1"}')
    with pytest.raises(H40GuardError):
        writer.write(payload)


def _read(root: Path, digest: str):
    import json
    return json.loads((root / digest[:2] / f"{digest}.json").read_bytes())


def _verifier(authority: SimpleNamespace):
    from btc_quant_agent.h40 import H40ProductionDiscoveryEvidenceVerifier
    return H40ProductionDiscoveryEvidenceVerifier(
        approved_evidence_root=authority.root, seal=authority.seal,
        authorization_receipt=authority.receipt, split_manifest=authority.split,
    )


@pytest.mark.parametrize("kind", ["root", "ancestor", "shard", "target", "escape", "protected", "confirmation"])
def test_p05_unsafe_store_paths(tmp_path: Path, kind: str) -> None:
    from btc_quant_agent.h40.discovery_producer import H40DiscoveryEvidenceWriter

    payload = {"value": "synthetic"}
    digest = canonical_sha256(payload)
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "root"
    root.mkdir()
    if kind == "root":
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        root = link
    elif kind == "ancestor":
        link = tmp_path / "link"
        link.symlink_to(tmp_path, target_is_directory=True)
        root = link / "root"
    elif kind == "shard":
        (root / digest[:2]).symlink_to(outside, target_is_directory=True)
    elif kind == "target":
        (root / digest[:2]).mkdir()
        (root / digest[:2] / f"{digest}.json").symlink_to(outside / "object")
    elif kind == "escape":
        root = root / ".." / "outside"
    elif kind in ("protected", "confirmation"):
        root = tmp_path / ("final_holdout" if kind == "protected" else "Confirmation")
    with pytest.raises(H40GuardError):
        H40DiscoveryEvidenceWriter(root).write(payload)
    assert not list(outside.iterdir())


def test_p04_store_replaced_directory_and_duplicate_json(tmp_path: Path) -> None:
    from btc_quant_agent.h40.discovery_producer import H40DiscoveryEvidenceWriter

    root = tmp_path / "root"
    root.mkdir()
    writer = H40DiscoveryEvidenceWriter(root)
    payload = {"value": "synthetic"}
    digest = writer.write(payload)
    path = root / digest[:2] / f"{digest}.json"
    path.write_bytes(b'{"value":"synthetic","value":"synthetic"}')
    with pytest.raises(H40GuardError):
        writer.write(payload)
    root.rename(tmp_path / "old")
    root.mkdir()
    with pytest.raises(H40GuardError):
        writer.write(payload)
    with pytest.raises(H40GuardError):
        writer._root = tmp_path


def test_p06_p07_authority_type_and_version_fences(authority: SimpleNamespace) -> None:
    from btc_quant_agent.h40 import H40DiscoveryAuthorizationReceiptV2

    for field in ("implementation_authority", "controller_authority", "authorization_receipt",
                  "run_authority", "seal", "split_manifest"):
        with pytest.raises(H40GuardError):
            _producer(authority, **{field: SimpleNamespace()})
    v2 = authority.receipt.to_dict()
    v2 = {key: value for key, value in v2.items() if key in H40DiscoveryAuthorizationReceiptV2._KEYS}
    v2["receipt_schema_id"] = "H40_RECEIPT_DISCOVERY_AUTH_V2"
    with pytest.raises(H40GuardError):
        _producer(authority, authorization_receipt=H40DiscoveryAuthorizationReceiptV2.from_dict(v2))
    synthetic = type(authority.seal).synthetic_for_tests(
        runtime_authority_snapshot_hash=authority.seal.runtime_authority_snapshot_hash,
        source_manifest_hash=authority.seal.source_manifest_hash,
        split_manifest_hash=authority.seal.split_manifest_hash,
        split_attestation_hash=authority.seal.split_attestation_hash,
        roster=authority.seal.roster, not_testable_slot_count=150,
    )
    with pytest.raises(H40GuardError):
        _producer(authority, seal=synthetic)
    class ForeignReceipt(type(authority.receipt)):
        pass
    with pytest.raises(H40GuardError):
        _producer(authority, authorization_receipt=ForeignReceipt(**authority.receipt.to_dict()))


def test_p08_all_receipt_run_bindings(authority: SimpleNamespace) -> None:
    from btc_quant_agent.h40 import H40RunAuthority

    for field in H40RunAuthority._KEYS - {"schema_id"}:
        with pytest.raises(H40GuardError):
            _producer(authority, authorization_receipt=replace(authority.receipt, **{field: "0" * 64}))
    for field in ("run_authority_id", "controller_authority_hash", "discovery_run_grant_hash"):
        with pytest.raises(H40GuardError):
            _producer(authority, authorization_receipt=replace(authority.receipt, **{field: "0" * 64}))
    with pytest.raises(H40GuardError):
        _producer(authority, run_authority=replace(authority.run, source_manifest_hash="0" * 64))
    with pytest.raises(H40GuardError):
        _producer(authority, split_manifest=replace(authority.split, source_manifest_hash="0" * 64))
    import copy
    for roster in (authority.seal.roster[:-1], (*authority.seal.roster, authority.seal.roster[0]),
                   (authority.seal.roster[0], *authority.seal.roster[:-1])):
        damaged = copy.copy(authority.seal)
        object.__setattr__(damaged, "roster", roster)
        with pytest.raises(H40GuardError):
            _producer(authority, seal=damaged)
    for field, value in (("family_id", "D2_BREAKOUT_CONTINUATION"), ("slot_hash", "0" * 64), ("slot_index", 167)):
        damaged = copy.copy(authority.seal)
        first = authority.seal.roster[0]
        if getattr(first, field) == value:
            value = "D1_TREND_CONTINUATION"
        object.__setattr__(damaged, "roster", (replace(first, **{field: value}), *authority.seal.roster[1:]))
        with pytest.raises(H40GuardError):
            _producer(authority, seal=damaged)
    assert not list(authority.root.iterdir())


def test_p09_through_p18_exact_scientific_graph(authority: SimpleNamespace) -> None:
    import math

    import pyarrow.parquet as pq

    from btc_quant_agent.h40 import discovery_evidence as science
    from btc_quant_agent.h40.search_space import materialize_h40_search_space_production

    result = _producer(authority).produce()
    objects = {digest: _read(authority.root, digest) for digest in result.dependency_digests}
    source = next(obj for obj in objects.values() if obj.get("schema_id") == "H40_P3B_SOURCE_DERIVATION_V2")
    assert set(source) == science._SOURCE_V2_KEYS
    assert source["source_support"] == {"start_utc": "2021-01-01T00:00:00Z", "end_utc_exclusive": "2023-02-01T00:00:00Z"}
    assert source["active_source_derivations"][0]["source_file_sha256"] == hashlib.sha256(authority.path.read_bytes()).hexdigest()
    bars = pq.read_table(authority.path).to_pylist()
    bars_by_time = {datetime.fromtimestamp(bar["open_time_ms"] / 1000, UTC): bar for bar in bars}
    slots = {slot.structural_configuration_hash: slot for slot in materialize_h40_search_space_production().slots}
    _, scientific_bars, _ = _producer(authority)._source()
    scientific_projection = []
    training_geometry_inputs = []
    status_counts: dict[str, int] = {}
    for entry in result.entries:
        candidate = objects[entry.candidate_result_input_evidence_hash]
        assert set(candidate) == science._RESULT_KEYS
        status = candidate["fit_status"]
        status_counts[status] = status_counts.get(status, 0) + 1
        assert candidate["slot_hash"] == entry.slot_hash
        assert candidate["slot_index"] == entry.slot_index
        assert candidate["source_manifest_hash"] == authority.seal.source_manifest_hash
        assert candidate["split_manifest_hash"] == authority.seal.split_manifest_hash
        for partition, field in (("WF1_TRAIN", "training_evidence_hash"), ("WF1_CALIBRATION", "calibration_evidence_hash")):
            decisions = objects[candidate[field]]
            assert set(decisions) == science._DECISION_V2_KEYS
            assert decisions["partition_id"] == partition
            rows = decisions["rows"]
            assert [{key: row[key] for key in ("timestamp", "product")} for row in rows] == source["base_eligible_membership"][partition]
            assert len(rows) == authority.split.get_partition(partition).count
            assert all(row["timestamp"] >= "2021-01-31T00:00:00Z" for row in rows)
            slot = slots[entry.structural_configuration_hash]
            horizon = int(slot.primary_horizon.rstrip("h"))
            reconstructed = [science._derive_source_decision(
                candidate_id=entry.structural_configuration_hash, slot=slot, partition_id=partition,
                timestamp=datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC),
                product=row["product"], horizon=horizon, bars=scientific_bars,
                source_evidence_hash=candidate["source_evidence_hash"],
            ) for row in rows]
            scientific_projection.append([entry.structural_configuration_hash, partition, [
                [r.timestamp.isoformat(), r.product, r.regime_state, r.opportunity_state, r.raw_score,
                 r.secondary_filter_state, r.r_h, r.p0, r.ch] for r in reconstructed
            ]])
            if partition == "WF1_TRAIN":
                training_geometry_inputs.append((slot, reconstructed))
            for row in rows:
                assert set(row) == science._ROW_V2_KEYS
                t = datetime.strptime(row["timestamp"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                expected = math.log(bars_by_time[t + timedelta(hours=horizon-1)]["close"] / bars_by_time[t]["open"])
                assert float(row["r_h"]) == expected
                if partition == "WF1_TRAIN":
                    assert row["p_up"] is row["final_action"] is row["r_net"] is None
        assert set(entry.hard_gate_input_evidence_hashes) == science._HARD_GATES
        for metric, digest in (("PRECISION", entry.precision_input_evidence_hash), ("NET_EXPECTANCY", entry.net_expectancy_input_evidence_hash)):
            obj = objects[digest]
            assert obj["metric_id"] == metric
            if status == "COMPLETE":
                assert set(obj) == science._METRIC_KEYS
                seed = science.h40_bootstrap_seed(entry.structural_configuration_hash, metric)
                assert obj["seed"] == seed.seed
                assert obj["start_matrix_hash"] == science.h40_bootstrap_starts(seed.seed, obj["H"])[1]
            else:
                assert set(obj) == science._INVALID_METRIC_KEYS
                assert obj["fit_failure_reason"] == candidate["fit_failure_reason"]
    # Goldens obtained by decoding these identical synthetic rows through
    # reviewed cccfddf's unextracted science (9504 exact rows, 42 geometry cells).
    assert canonical_sha256(scientific_projection) == "d5a962cd9c9556b573a890b6af8cbeb09d7201187511f477d727c8670bf0b2e0"
    geometry = science._geometry_training_rows(training_geometry_inputs)
    geometry_projection = [[owner, [
        [[*key[:3], key[3].isoformat(), *key[4:]], list(value)] for key, value in sorted(records.items())
    ]] for owner, records in sorted(geometry.items())]
    assert canonical_sha256(geometry_projection) == "27b23da5a3a6f59aecbd392c976793a138aff448395278b21746315de7fe6b92"
    assert status_counts.get("COMPLETE", 0) > 0, status_counts
    correction = objects[result.evidence.correction_input_evidence_manifest_hash]
    assert set(correction) == science._CORRECTION_KEYS
    assert correction["candidate_configuration_hashes"] == [item.structural_configuration_hash for item in result.entries]
    assert correction["metric_universes"]["PRECISION"] == correction["metric_universes"]["NET_EXPECTANCY"]
    assert set(correction["metric_universes"]["PRECISION"]) == set(science._FAMILIES)
    assert sum(map(len, correction["metric_universes"]["PRECISION"].values())) == 18
    for digest, obj in objects.items():
        assert canonical_sha256(obj) == digest


def test_p14_p20_fresh_roots_and_fresh_scientific_state_deterministic(authority: SimpleNamespace, tmp_path: Path) -> None:
    from btc_quant_agent.h40.discovery_evidence import clear_prefit_caches

    first = _producer(authority).produce()
    clear_prefit_caches()
    from btc_quant_agent.h40 import (
        H40RuntimeSnapshotSeal,
        H40RuntimeSourceSplitAttestation,
        H40SourceManifest,
        H40SourceRecord,
        H40SplitManifest,
    )
    second_root = tmp_path / "second-evidence"
    second_root.mkdir()
    # Identical typed lineage includes the canonical repository locator:
    # unverified inactive-source diagnostic receipts contain this location.
    # Keep that input fixed while reconstructing every mutable scientific state.
    fresh_source = H40SourceManifest(
        protocol_identity_hash=authority.source.protocol_identity_hash,
        sources=tuple(H40SourceRecord.from_dict(record.to_dict()) for record in authority.source.sources),
    )
    fresh_split = H40SplitManifest.from_dict(authority.split.to_dict())
    fresh_attestation = H40RuntimeSourceSplitAttestation.from_dict(
        authority.seal._runtime_attestation_context.to_dict(),
    )
    fresh_seal = H40RuntimeSnapshotSeal.from_verified_authority(
        source_manifest=fresh_source, split_manifest=fresh_split,
        runtime_attestation=fresh_attestation, repo_root=authority.repo,
    )
    fresh_authority = SimpleNamespace(**{**vars(authority), "source": fresh_source,
                                       "split": fresh_split, "seal": fresh_seal, "root": second_root,
                                       "run": type(authority.run).from_dict(authority.run.to_dict()),
                                       "receipt": type(authority.receipt).from_dict(authority.receipt.to_dict())})
    second = _producer(fresh_authority).produce()
    assert fresh_authority.seal is not authority.seal
    assert fresh_authority.run is not authority.run
    assert fresh_authority.receipt is not authority.receipt
    assert fresh_authority.source is not authority.source
    assert first.evidence == second.evidence
    assert first.entries == second.entries
    assert first.dependency_digests == second.dependency_digests
    assert all((first.approved_evidence_root / digest[:2] / f"{digest}.json").read_bytes() ==
               (second.approved_evidence_root / digest[:2] / f"{digest}.json").read_bytes()
               for digest in first.dependency_digests)
    assert first.approved_evidence_root != second.approved_evidence_root
    verifier = _verifier(fresh_authority)
    verifier.verify_discovery_manifest(second.evidence, second.entries)
    assert len([verifier.verify_candidate(
        entry, run_authority_id=second.evidence.run_authority_id,
        correction_manifest_hash=second.evidence.correction_input_evidence_manifest_hash,
    ) for entry in second.entries]) == 18


def test_p15_source_byte_mutation_fails_before_publication(authority: SimpleNamespace) -> None:
    producer = _producer(authority)
    authority.path.write_bytes(authority.path.read_bytes() + b"SYNTHETIC_TAMPER")
    with pytest.raises(H40GuardError):
        producer.produce()
    assert not list(authority.root.iterdir())


def test_missing_extra_duplicate_candidates_and_dependencies(authority: SimpleNamespace) -> None:
    result = _producer(authority).produce()
    verifier = _verifier(authority)
    for entries in (result.entries[:-1], tuple(sorted((*result.entries, result.entries[0]), key=lambda item: item.structural_configuration_hash)),
                    (result.entries[0], *result.entries[:-1])):
        with pytest.raises(H40GuardError):
            verifier.verify_discovery_manifest(result.evidence, entries)
    foreign = replace(result.entries[0], structural_configuration_hash="0" * 64)
    foreign_entries = tuple(sorted((foreign, *result.entries[1:]), key=lambda item: item.structural_configuration_hash))
    with pytest.raises(H40GuardError):
        verifier.verify_discovery_manifest(result.evidence, foreign_entries)
    first = result.entries[0]
    dependency = authority.root / first.precision_input_evidence_hash[:2] / f"{first.precision_input_evidence_hash}.json"
    saved = dependency.read_bytes()
    dependency.unlink()
    with pytest.raises(H40GuardError):
        verifier.verify_discovery_manifest(result.evidence, result.entries)
    dependency.write_bytes(saved)
    candidate = _read(authority.root, first.candidate_result_input_evidence_hash)
    decisions_hash = candidate["calibration_evidence_hash"]
    decisions_path = authority.root / decisions_hash[:2] / f"{decisions_hash}.json"
    saved = decisions_path.read_bytes()
    _read(authority.root, decisions_hash)
    for mutate in (lambda value: value["rows"].pop(),
                   lambda value: value["rows"].append(value["rows"][0]),
                   lambda value: value.update(extra_dependency="0" * 64)):
        import json
        changed = json.loads(saved)
        mutate(changed)
        decisions_path.write_bytes(canonical_json(changed).encode())
        with pytest.raises(H40GuardError):
            verifier.verify_discovery_manifest(result.evidence, result.entries)
    decisions_path.write_bytes(saved)


def test_p22_no_lifecycle_or_execution_side_effect(authority: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    from btc_quant_agent.execution.environment import (
        ACCEPTED_EXECUTION_WRITE_AUTHORITY,
        CURRENT_EXECUTION_POLICY,
    )
    from btc_quant_agent.h40.lifecycle_authority import H40LifecycleAuthorityService

    def forbidden(*args, **kwargs):
        raise AssertionError("producer attempted lifecycle authorization")
    monkeypatch.setattr(H40LifecycleAuthorityService, "authorize_discovery", forbidden)
    monkeypatch.setattr(H40LifecycleAuthorityService, "authorize_candidate_lock", forbidden)
    result = _producer(authority).produce()
    assert CURRENT_EXECUTION_POLICY == "RESEARCH_DISABLED_V1"
    assert ACCEPTED_EXECUTION_WRITE_AUTHORITY is None
    assert not any("RECEIPT" in str(_read(authority.root, digest).get("schema_id", "")) for digest in result.dependency_digests)
    assert not any("CANDIDATE_LOCK" in path.name for path in authority.root.rglob("*"))


def test_p12_p13_future_bars_cannot_change_causal_prefit(authority: SimpleNamespace) -> None:
    from btc_quant_agent.h40 import discovery_evidence as science
    from btc_quant_agent.h40.search_space import materialize_h40_search_space_production

    payload, bars, universes = _producer(authority)._source()
    source_hash = canonical_sha256(payload)
    for slot in materialize_h40_search_space_production().slots:
        if slot.status != "REGISTERED":
            continue
        for partition in ("WF1_TRAIN", "WF1_CALIBRATION"):
            t, product = universes[partition][-30]
            arguments = {"candidate_id": slot.structural_configuration_hash, "slot": slot,
                             "partition_id": partition, "timestamp": t, "product": product,
                             "horizon": int(slot.primary_horizon.rstrip("h"))}
            original = science._derive_source_decision(**arguments, bars=bars, source_evidence_hash=source_hash)
            changed_bars = {key: replace(bar, open=bar.open*1.01, high=bar.high*1.01,
                                         low=bar.low*1.01, close=bar.close*1.01)
                            if key[0] >= t else bar for key, bar in bars.items()}
            modified = science._derive_source_decision(
                **arguments, bars=changed_bars,
                source_evidence_hash=canonical_sha256([
                    [key[0].isoformat(), key[1], bar.open, bar.high, bar.low, bar.close]
                    for key, bar in sorted(changed_bars.items())
                ]),
            )
            assert (original.raw_score, original.regime_state, original.opportunity_state,
                    original.secondary_filter_state) == (
                modified.raw_score, modified.regime_state, modified.opportunity_state,
                modified.secondary_filter_state)
    science.clear_prefit_caches()


def test_p15_economic_digest_cannot_be_claimed(authority: SimpleNamespace) -> None:
    from btc_quant_agent.h40 import discovery_evidence as science
    from btc_quant_agent.h40.discovery_producer import H40DiscoveryEvidenceWriter

    payload, _, _ = _producer(authority)._source()
    payload["active_source_derivations"][0]["economic_rows_sha256"] = "0" * 64
    digest = H40DiscoveryEvidenceWriter(authority.root).write(payload)
    with pytest.raises(H40GuardError, match="economic rows SHA-256 mismatch"):
        science._load_source_bars(
            science.H40DiscoveryEvidenceResolver(authority.root), digest,
            run_authority_id=authority.run.run_authority_id,
            source_manifest_hash=authority.seal.source_manifest_hash,
            split_manifest_hash=authority.seal.split_manifest_hash, split_manifest=authority.split,
            split_attestation_hash=authority.seal.split_attestation_hash, seal=authority.seal,
        )


def test_p21_new_synthetic_source_changes_digest_graph(authority: SimpleNamespace, tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch) -> None:
    first = _producer(authority).produce()
    changed_root = tmp_path / "changed-fixture"
    changed_root.mkdir()
    changed_authority = _synthetic_authority(changed_root, monkeypatch, seed=31131)
    second = _producer(changed_authority).produce()
    assert first.evidence.evidence_sha256 != second.evidence.evidence_sha256
    assert first.evidence.correction_input_evidence_manifest_hash != second.evidence.correction_input_evidence_manifest_hash
    assert all(old.candidate_result_input_evidence_hash != new.candidate_result_input_evidence_hash
               for old, new in zip(first.entries, second.entries, strict=True))
    first_sources = [digest for digest in first.dependency_digests
                     if _read(first.approved_evidence_root, digest).get("schema_id") == "H40_P3B_SOURCE_DERIVATION_V2"]
    second_sources = [digest for digest in second.dependency_digests
                      if _read(second.approved_evidence_root, digest).get("schema_id") == "H40_P3B_SOURCE_DERIVATION_V2"]
    assert first_sources != second_sources
    _verifier(changed_authority).verify_discovery_manifest(second.evidence, second.entries)


def test_source_symlink_rejected_before_cold_read(authority: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    from btc_quant_agent.h40 import H40RuntimeSnapshotSeal

    real = authority.path.with_suffix(".safe")
    authority.path.rename(real)
    authority.path.symlink_to(real)
    def forbidden(*args, **kwargs):
        raise AssertionError("cold verification must follow producer locator guard")
    monkeypatch.setattr(H40RuntimeSnapshotSeal, "verify_against_accepted_ledger", forbidden)
    with pytest.raises(H40GuardError):
        _producer(authority)


def test_writer_rename_failure_cleans_unpublished_temp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import btc_quant_agent.h40.discovery_producer as module

    def failed(*args):
        raise OSError("synthetic rename failure")
    monkeypatch.setattr(module, "_rename_noreplace", failed)
    with pytest.raises(H40GuardError):
        module.H40DiscoveryEvidenceWriter(tmp_path).write({"synthetic": True})
    assert not list(tmp_path.rglob("*.tmp"))
    assert not list(tmp_path.rglob("*.json"))


def test_store_shard_namespace_change_cannot_publish_outside_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import btc_quant_agent.h40.discovery_producer as module

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "moved-shard"
    original_rename = module._rename_noreplace
    payload = {"value": "SYNTHETIC_RACE"}
    digest = canonical_sha256(payload)
    def move_shard(descriptor, source, target):
        (root / digest[:2]).rename(outside)
        (root / digest[:2]).mkdir()
        original_rename(descriptor, source, target)
    monkeypatch.setattr(module, "_rename_noreplace", move_shard)
    with pytest.raises(H40GuardError):
        module.H40DiscoveryEvidenceWriter(root).write(payload)
    assert not list(outside.iterdir())
    assert not list(root.rglob("*.json"))


def test_optimized_interpreter_publishes_final_evidence(tmp_path: Path) -> None:
    import os
    import subprocess
    import sys

    script = '''
import sys
from pathlib import Path
import pytest
from test_v051_h40_m3a_production_discovery_producer import _synthetic_authority, _producer, _verifier
with pytest.MonkeyPatch.context() as mp:
    authority = _synthetic_authority(Path(sys.argv[1]), mp)
    result = _producer(authority).produce()
    path = result.approved_evidence_root / result.evidence.evidence_sha256[:2] / (result.evidence.evidence_sha256 + '.json')
    if not path.is_file() or result.evidence.evidence_sha256 not in result.dependency_digests:
        raise RuntimeError('optimized producer omitted final evidence publication')
    verifier = _verifier(authority)
    verifier.verify_discovery_manifest(result.evidence, result.entries)
    print('optimized_interpreter_roundtrip_candidates:', len(result.entries))
'''
    repo = Path(__file__).resolve().parents[1]
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join((str(repo / "tests"), str(repo / "src")))}
    completed = subprocess.run([sys.executable, "-O", "-c", script, str(tmp_path)],
                               cwd=repo, env=environment, capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "optimized_interpreter_roundtrip_candidates: 18" in completed.stdout


def test_invalid_receipt_rejected_before_cold_source_read(authority: SimpleNamespace, monkeypatch: pytest.MonkeyPatch) -> None:
    from btc_quant_agent.h40 import H40RuntimeSnapshotSeal

    def forbidden(*args, **kwargs):
        raise AssertionError("unbound receipt must fail before cold source reads")
    monkeypatch.setattr(H40RuntimeSnapshotSeal, "verify_against_accepted_ledger", forbidden)
    with pytest.raises(H40GuardError):
        _producer(authority, authorization_receipt=replace(authority.receipt, run_authority_id="0" * 64))
