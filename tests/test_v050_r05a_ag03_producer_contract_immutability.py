"""v0.5.0 R05A AG-03 regression tests: producer contract deep immutability.

Permanent regression suite for the AG-03 bounded repair (commit 2412e38), which
deep-froze ``SignalProducerContract.parameters`` through the canonical
``freeze_json`` machinery and hardened the ``SignalProducerRegistry`` hash
guards (registration mismatch/conflict checks, stale-preimage fail-closed
lookup) so a mutated contract can never survive a formally-authoritative run.

Test map:
- T1: Caller-supplied parameter mapping is detached at construction.
- T2: Direct top-level parameter mutation is rejected, state unchanged.
- T3: Mutation through a nested mapping is rejected.
- T4: Nested sequences are immutable (append/replacement impossible).
- T5: ``to_dict()`` / ``semantic_payload()`` views are detached copies.
- T6: Exact duplicate registration is an idempotent no-op.
- T7: Conflicting registration under an existing id is rejected atomically.
- T8: Stale internal preimage (``object.__setattr__`` bypass) fails closed in
  the registry and the formal replay resolution path.
- T9: Astra LONG -> NO_TRADE threshold attack is closed end to end.
- T10: Pre-edit default contract hash preservation receipt.
- T11: serialize/reconstruct round-trip stays immutable, plus a fresh-process
  registry smoke receipt over the five default hashes.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    CanonicalRuleSignalProducer,
    SignalProducerContract,
    SignalProducerRegistry,
)
from btc_quant_agent.economic.replay_bundle import _resolve_protocol_producer_contract
from btc_quant_agent.economic.signal_producer import _runtime_candle_payload
from btc_quant_agent.research_contract.canonical import (
    FrozenDict,
    canonical_sha256,
    freeze_json,
)

# Pre-edit baseline receipt captured at start SHA 0203e0f before the AG-03
# repair.  These are permanent expected values: the immutability-only repair
# must not change the semantic content (and therefore the hash) of any default
# contract.
BASELINE_CONTRACT_HASHES: dict[str, str] = {
    "CANONICAL_RETURN_SIGN_V1": (
        "0f67181ec8d4680bcb4addedb71e7f37390aa8e5ae6f395618a250f5152662a3"
    ),
    "CANONICAL_MOMENTUM_THRESHOLD_V1": (
        "791f97e7d65ba6bbc8ccac141cd0e58e6c3e39b89cd0d5c9d9ce0c0f658aa8d0"
    ),
    "CANONICAL_PRICE_BREAKOUT_V1": (
        "017f7ffba16b2c32c40b267cd8ddee64f96c029898c4e017527c2b637e585828"
    ),
    "CANONICAL_RANDOM_BENCHMARK_V1": (
        "4792c231a8832d2227a28e86735cf179729b2e7a85d5feefddca834c5a7cce95"
    ),
    "SYNTHETIC_FIXED_DIRECTION_V1": (
        "48241f266e19fa4c72cfe27da4aac00e0dfa3443545f79d270f84f8edc085d08"
    ),
}


def _make_contract(
    contract_id: str,
    *,
    rule: str = "MOMENTUM_THRESHOLD",
    params: dict[str, Any] | None = None,
    version: str = "1.0.0",
    identity: str = "CANONICAL_RULE_SIGNAL_PRODUCER",
    contract_hash: str = "",
) -> SignalProducerContract:
    """Construct a producer contract; an empty hash is auto-computed in __post_init__."""
    return SignalProducerContract(
        contract_id=contract_id,
        version=version,
        producer_identity=identity,
        producer_version="1.0.0",
        rule=rule,
        parameters=dict(params or {}),
        contract_hash=contract_hash,
    )


def _semantic_hash(contract: SignalProducerContract) -> str:
    return canonical_sha256(contract.semantic_payload())


@pytest.fixture
def registered_contract_ids() -> Iterator[list[str]]:
    """Track contract ids registered by a test so teardown removes only those.

    The registry is class-level global state; removing exactly the ids a test
    added keeps the suite hermetic without disturbing registrations made by
    other modules.
    """
    added: list[str] = []
    yield added
    for contract_id in added:
        SignalProducerRegistry._contracts.pop(contract_id, None)


def _long_trend_candles() -> tuple[Candle, ...]:
    """Two closed candles whose return is +1.5%: LONG under a 0.0 bps threshold."""
    return (
        Candle(
            symbol="BTCUSDT",
            interval="1m",
            open_time_ms=1_000,
            close_time_ms=59_999,
            open=100.0,
            high=101.5,
            low=99.5,
            close=101.0,
            volume=1.0,
            closed=True,
            available_at_ms=1_000,
        ),
        Candle(
            symbol="BTCUSDT",
            interval="1m",
            open_time_ms=60_000,
            close_time_ms=119_999,
            open=101.0,
            high=102.0,
            low=100.5,
            close=101.5,
            volume=1.0,
            closed=True,
            available_at_ms=60_000,
        ),
    )


# ==============================================================================
# T1 — Caller alias detachment
# ==============================================================================


def test_t1_caller_alias_detach_does_not_affect_contract() -> None:
    """T1: mutating the caller-owned mapping after construction cannot alter semantics/hash."""
    source: dict[str, Any] = {"threshold_return_bps": 0.0, "nested": {"values": [1, 2]}}
    pristine = copy.deepcopy(source)
    contract = _make_contract("R05A-T1-ALIAS-DETACH", params=source)

    source["threshold_return_bps"] = 9999
    source["nested"]["values"].append(3)

    assert contract.parameters["threshold_return_bps"] == 0.0
    assert contract.parameters["nested"]["values"] == (1, 2)
    assert contract.semantic_payload()["parameters"] == pristine
    expected_payload = {
        "contract_id": "R05A-T1-ALIAS-DETACH",
        "version": "1.0.0",
        "producer_identity": "CANONICAL_RULE_SIGNAL_PRODUCER",
        "producer_version": "1.0.0",
        "rule": "MOMENTUM_THRESHOLD",
        "parameters": pristine,
    }
    assert contract.contract_hash == canonical_sha256(expected_payload)
    assert _semantic_hash(contract) == contract.contract_hash


# ==============================================================================
# T2 — Direct top-level mutation rejected
# ==============================================================================


def test_t2_direct_toplevel_mutation_rejected() -> None:
    """T2: item assignment/deletion on the frozen parameters fails closed and changes nothing."""
    contract = _make_contract("R05A-T2-TOPLEVEL", params={"threshold_return_bps": 0.0})
    baseline_hash = contract.contract_hash
    baseline_payload = contract.semantic_payload()

    with pytest.raises(TypeError):
        contract.parameters["threshold_return_bps"] = 10000
    with pytest.raises(TypeError):
        del contract.parameters["threshold_return_bps"]
    with pytest.raises((TypeError, AttributeError)):
        contract.parameters.update({"threshold_return_bps": 10000})
    with pytest.raises((TypeError, AttributeError)):
        contract.parameters.pop("threshold_return_bps")

    # replace() carries the declared hash, which now disagrees with the changed
    # parameters: even the dataclass-level derivation avenue fails closed.
    with pytest.raises(ValueError, match="contract_hash mismatch"):
        dataclasses.replace(contract, parameters={"threshold_return_bps": 10000})

    assert contract.contract_hash == baseline_hash
    assert contract.semantic_payload() == baseline_payload
    assert _semantic_hash(contract) == baseline_hash


# ==============================================================================
# T3 — Nested mapping mutation rejected
# ==============================================================================


def test_t3_nested_mapping_mutation_rejected() -> None:
    """T3: mappings nested inside parameters are frozen; mutation through them must fail."""
    contract = _make_contract(
        "R05A-T3-NESTED-MAPPING",
        params={"outer": {"threshold_return_bps": 0.0, "inner": {"keep": 1}}},
    )
    baseline_hash = contract.contract_hash

    nested = contract.parameters["outer"]
    assert isinstance(nested, FrozenDict)
    with pytest.raises(TypeError):
        nested["threshold_return_bps"] = 10000
    with pytest.raises(TypeError):
        contract.parameters["outer"]["inner"]["keep"] = 2
    with pytest.raises(TypeError):
        contract.parameters["outer"]["brand_new"] = "injected"

    assert contract.parameters["outer"]["threshold_return_bps"] == 0.0
    assert contract.parameters["outer"]["inner"] == {"keep": 1}
    assert "brand_new" not in contract.parameters["outer"]
    assert _semantic_hash(contract) == baseline_hash


# ==============================================================================
# T4 — Nested sequence mutation impossible
# ==============================================================================


def test_t4_nested_sequence_mutation_impossible() -> None:
    """T4: sequences nested inside parameters are tuples; append/replacement cannot touch authority."""
    contract = _make_contract(
        "R05A-T4-NESTED-SEQUENCE",
        params={"values": [1, 2, 3], "matrix": [[1, 2], [3, 4]]},
    )
    baseline_hash = contract.contract_hash

    sequence = contract.parameters["values"]
    assert isinstance(sequence, tuple)
    with pytest.raises(AttributeError):
        sequence.append(4)
    with pytest.raises(TypeError):
        sequence[0] = 99
    with pytest.raises(TypeError):
        contract.parameters["values"][1] = 99

    matrix = contract.parameters["matrix"]
    assert matrix == ((1, 2), (3, 4))
    with pytest.raises(AttributeError):
        matrix[0].append(9)
    with pytest.raises(TypeError):
        matrix[1][0] = 0

    assert contract.parameters["values"] == (1, 2, 3)
    assert _semantic_hash(contract) == baseline_hash


# ==============================================================================
# T5 — Serialization is detached
# ==============================================================================


def test_t5_serialized_views_are_detached(registered_contract_ids: list[str]) -> None:
    """T5: mutating to_dict()/semantic_payload() output cannot affect the registered authority."""
    contract_id = "R05A-T5-DETACHED-VIEWS"
    contract = _make_contract(
        contract_id,
        params={"threshold_return_bps": 0.0, "nested": {"values": [1, 2]}},
    )
    SignalProducerRegistry.register_contract(contract)
    registered_contract_ids.append(contract_id)
    baseline_hash = contract.contract_hash

    payload = contract.to_dict()
    payload["parameters"]["threshold_return_bps"] = 10000
    payload["parameters"]["nested"]["values"].append(3)
    payload["contract_id"] = "TAMPERED"
    payload["contract_hash"] = "0" * 64

    resolved = SignalProducerRegistry.get_contract(contract_id)
    assert resolved is contract
    assert resolved.contract_id == contract_id
    assert resolved.contract_hash == baseline_hash
    assert _semantic_hash(resolved) == baseline_hash
    assert resolved.parameters["threshold_return_bps"] == 0.0
    assert resolved.parameters["nested"]["values"] == (1, 2)

    view = contract.semantic_payload()
    view["parameters"]["nested"]["values"].append(4)
    view["parameters"]["threshold_return_bps"] = 20000

    assert contract.parameters["nested"]["values"] == (1, 2)
    assert contract.parameters["threshold_return_bps"] == 0.0
    assert _semantic_hash(contract) == baseline_hash
    assert SignalProducerRegistry.get_contract(contract_id) is contract


# ==============================================================================
# T6 — Exact duplicate registration is idempotent
# ==============================================================================


def test_t6_exact_duplicate_registration_is_idempotent() -> None:
    """T6: re-registering an exact reconstruction no-ops and never replaces the stored authority."""
    original = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert original is not None

    replica = SignalProducerContract.from_dict(original.to_dict())
    assert replica == original
    SignalProducerRegistry.register_contract(replica)

    rebuilt = _make_contract("CANONICAL_RETURN_SIGN_V1", rule="RETURN_SIGN", params={})
    assert rebuilt == original
    SignalProducerRegistry.register_contract(rebuilt)

    stored = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert stored is original
    assert _semantic_hash(stored) == original.contract_hash
    assert stored.to_dict() == original.to_dict()


# ==============================================================================
# T7 — Conflicting registration rejected atomically
# ==============================================================================


@pytest.mark.parametrize(
    "conflict_kwargs",
    [
        {"version": "1.0.1"},
        {"rule": "PRICE_BREAKOUT"},
        {"params": {"threshold_return_bps": 10000.0, "limits": {"max_leverage": 10}}},
        {"params": {"threshold_return_bps": 0.0, "limits": {"max_leverage": 999}}},
    ],
    ids=["version", "rule", "top_level_parameter", "nested_parameter"],
)
def test_t7_conflicting_registration_rejected_atomically(
    conflict_kwargs: dict[str, Any],
    registered_contract_ids: list[str],
) -> None:
    """T7: any content change under an existing id is rejected; the authority is untouched."""
    contract_id = "R05A-T7-CONFLICT-TARGET"
    base_params: dict[str, Any] = {
        "threshold_return_bps": 0.0,
        "limits": {"max_leverage": 10},
    }
    authority = _make_contract(contract_id, params=dict(base_params))
    SignalProducerRegistry.register_contract(authority)
    registered_contract_ids.append(contract_id)
    authority_hash = authority.contract_hash
    authority_payload = authority.semantic_payload()

    kwargs: dict[str, Any] = {
        "rule": authority.rule,
        "params": dict(base_params),
        "version": authority.version,
        "identity": authority.producer_identity,
    }
    kwargs.update(conflict_kwargs)
    conflict = _make_contract(contract_id, **kwargs)

    with pytest.raises(ValueError, match="conflicting producer contract"):
        SignalProducerRegistry.register_contract(conflict)

    stored = SignalProducerRegistry.get_contract(contract_id)
    assert stored is authority
    assert stored.contract_hash == authority_hash
    assert stored.semantic_payload() == authority_payload
    assert _semantic_hash(stored) == authority_hash
    assert stored.to_dict() == authority.to_dict()


def test_t7b_forged_hash_registration_rejected() -> None:
    """T7b: a declared hash disagreeing with its content is rejected at construction."""
    original = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert original is not None

    with pytest.raises(ValueError, match="contract_hash mismatch"):
        _make_contract(
            "CANONICAL_RETURN_SIGN_V1",
            rule="RETURN_SIGN",
            params={},
            version="1.0.1",
            contract_hash=original.contract_hash,
        )

    stored = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert stored is original
    assert _semantic_hash(stored) == original.contract_hash


# ==============================================================================
# T8 — Stale internal preimage detected
# ==============================================================================


def test_t8_stale_internal_preimage_detected(registered_contract_ids: list[str]) -> None:
    """T8: an object.__setattr__ bypass with a stale contract_hash fails closed everywhere."""
    contract_id = "R05A-T8-STALE-PREIMAGE"
    contract = _make_contract(
        contract_id,
        params={"threshold_return_bps": 0.0, "nested": {"flags": [1]}},
    )
    SignalProducerRegistry.register_contract(contract)
    registered_contract_ids.append(contract_id)
    original_hash = contract.contract_hash
    assert SignalProducerRegistry.get_contract(contract_id) is contract

    # Adversarial, internal-only mechanism: swap parameters behind the frozen
    # facade while leaving contract_hash stale.
    hostile = freeze_json({"threshold_return_bps": 10000, "nested": {"flags": [1]}})
    object.__setattr__(contract, "parameters", hostile)
    assert canonical_sha256(contract.semantic_payload()) != original_hash

    with pytest.raises(ValueError, match="failing closed"):
        SignalProducerRegistry.get_contract(contract_id)
    with pytest.raises(ValueError, match="failing closed"):
        SignalProducerRegistry.get_contract(contract_id, original_hash)
    with pytest.raises(ValueError, match="producer contract hash mismatch"):
        SignalProducerRegistry.register_contract(contract)

    mapping_stub = {"contract_id": contract_id, "contract_hash": original_hash}
    with pytest.raises(ValueError, match="failing closed"):
        _resolve_protocol_producer_contract(
            SimpleNamespace(signal_producer_contract=mapping_stub)
        )

    identity_stub = SimpleNamespace(
        signal_producer_contract=SimpleNamespace(
            logical_id=contract_id, content_sha256=original_hash
        )
    )
    with pytest.raises(ValueError, match="failing closed"):
        _resolve_protocol_producer_contract(identity_stub)


# ==============================================================================
# T9 — Astra LONG -> NO_TRADE attack is closed
# ==============================================================================


def test_t9_astra_long_to_no_trade_attack_closed(
    registered_contract_ids: list[str],
) -> None:
    """T9: the threshold attack cannot reach a second formally-authoritative run with changed semantics."""
    producer = CanonicalRuleSignalProducer()
    contract_id = "R05A-T9-ASTRA-MOMENTUM"
    contract = _make_contract(contract_id, params={"threshold_return_bps": 0.0})
    SignalProducerRegistry.register_contract(contract)
    registered_contract_ids.append(contract_id)
    original_hash = contract.contract_hash
    # R05B: the canonical replay now enforces the exact required material
    # window (latest 1 eligible row for this N=1 momentum contract), so the
    # attack transcript replays with a single-candle window.
    candles = _long_trend_candles()[:1]

    def _replay(target: SignalProducerContract, label: str) -> Any:
        return producer.replay_signal(
            signal_id=label,
            signal_timestamp_ms=120_000,
            experiment_id="R05A-EXP",
            input_candles=candles,
            generation_contract={
                "expected_preimage_sha256": canonical_sha256(
                    [_runtime_candle_payload(candle) for candle in candles]
                )
            },
            authoritative_contract=target,
        )

    assert _replay(contract, "T9-ORIGINAL").direction == 1

    # Public mutation avenue: in-place change is impossible.
    with pytest.raises(TypeError):
        contract.parameters["threshold_return_bps"] = 10000

    # Derivation avenue: dataclasses.replace carries the stale declared hash and
    # fails closed; a freshly derived contract is a different identity and is
    # rejected under the existing id, leaving the stored authority unchanged.
    with pytest.raises(ValueError, match="contract_hash mismatch"):
        dataclasses.replace(contract, parameters={"threshold_return_bps": 10000})
    derivative = _make_contract(contract_id, params={"threshold_return_bps": 10000})
    assert derivative.contract_hash != original_hash
    with pytest.raises(ValueError, match="conflicting producer contract"):
        SignalProducerRegistry.register_contract(derivative)
    assert SignalProducerRegistry.get_contract(contract_id) is contract

    # Hostile bypass: prove the in-memory semantics flip exists so the boundary
    # rejection below is demonstrably load-bearing.
    object.__setattr__(contract, "parameters", freeze_json({"threshold_return_bps": 10000}))
    assert _replay(contract, "T9-BYPASS").direction == 0

    # The attack stops before any formally-authoritative resolution.
    with pytest.raises(ValueError, match="failing closed"):
        SignalProducerRegistry.get_contract(contract_id)
    with pytest.raises(ValueError, match="failing closed"):
        _resolve_protocol_producer_contract(
            SimpleNamespace(
                signal_producer_contract={
                    "contract_id": contract_id,
                    "contract_hash": original_hash,
                }
            )
        )
    with pytest.raises(ValueError, match="failing closed"):
        _resolve_protocol_producer_contract(
            SimpleNamespace(
                signal_producer_contract=SimpleNamespace(
                    logical_id=contract_id, content_sha256=original_hash
                )
            )
        )
    with pytest.raises(ValueError, match="producer contract hash mismatch"):
        SignalProducerRegistry.register_contract(contract)

    # Positive control: the default authority under the unchanged pre-edit
    # protocol identity still yields the ORIGINAL LONG semantics.
    default_contract = SignalProducerRegistry.get_contract(
        "CANONICAL_MOMENTUM_THRESHOLD_V1",
        BASELINE_CONTRACT_HASHES["CANONICAL_MOMENTUM_THRESHOLD_V1"],
    )
    assert default_contract is not None
    assert _replay(default_contract, "T9-ORIGINAL-IDENTITY").direction == 1


# ==============================================================================
# T10 — Default contract hash preservation
# ==============================================================================


def test_t10_default_contract_hash_preservation() -> None:
    """T10: all five default contracts keep their pre-edit baseline hashes."""
    for contract_id, baseline in BASELINE_CONTRACT_HASHES.items():
        contract = SignalProducerRegistry.get_contract(contract_id)
        assert contract is not None, contract_id
        assert contract.contract_hash == baseline, contract_id
        assert _semantic_hash(contract) == baseline, contract_id
        # The registry accepts the pre-edit hash as the expected identity.
        assert SignalProducerRegistry.get_contract(contract_id, baseline) is contract
        # A caller-supplied foreign expected hash yields None (existing behavior).
        assert SignalProducerRegistry.get_contract(contract_id, "ab" * 32) is None
        assert SignalProducerRegistry.get_contract("R05A-UNKNOWN-CONTRACT") is None
    assert set(BASELINE_CONTRACT_HASHES) == {
        "CANONICAL_RETURN_SIGN_V1",
        "CANONICAL_MOMENTUM_THRESHOLD_V1",
        "CANONICAL_PRICE_BREAKOUT_V1",
        "CANONICAL_RANDOM_BENCHMARK_V1",
        "SYNTHETIC_FIXED_DIRECTION_V1",
    }
    assert (
        SignalProducerRegistry.get_producer("CANONICAL_RULE_SIGNAL_PRODUCER", "1.0.0")
        is not None
    )


# ==============================================================================
# T11 — Serialize/reconstruct
# ==============================================================================


def test_t11_serialize_reconstruct_roundtrip_preserves_immutability() -> None:
    """T11: to_dict -> from_dict reproduces semantics/hash and stays deeply immutable."""
    candidates: list[SignalProducerContract | None] = [
        SignalProducerRegistry.get_contract(contract_id)
        for contract_id in BASELINE_CONTRACT_HASHES
    ]
    candidates.append(
        _make_contract(
            "R05A-T11-NESTED",
            params={"threshold_return_bps": 0.0, "nested": {"values": [1, 2]}},
        )
    )
    for contract in candidates:
        assert contract is not None
        payload = contract.to_dict()
        replica = SignalProducerContract.from_dict(payload)

        assert replica == contract
        assert replica.semantic_payload() == contract.semantic_payload()
        assert replica.contract_hash == contract.contract_hash
        assert _semantic_hash(replica) == replica.contract_hash
        assert replica.parameters == contract.parameters
        assert isinstance(replica.parameters, FrozenDict)
        with pytest.raises(TypeError):
            replica.parameters["injected"] = True

        # The versioned identity used by the formal replay resolution path
        # projects the same logical id, version, and content hash.
        identity = contract.to_versioned_identity()
        assert identity.logical_id == contract.contract_id
        assert identity.version == contract.version
        assert identity.content_sha256 == contract.contract_hash


SMOKE_SCRIPT = """\
import json

from btc_quant_agent.economic import SignalProducerRegistry
from btc_quant_agent.research_contract.canonical import canonical_sha256

ids = [
    "CANONICAL_RETURN_SIGN_V1",
    "CANONICAL_MOMENTUM_THRESHOLD_V1",
    "CANONICAL_PRICE_BREAKOUT_V1",
    "CANONICAL_RANDOM_BENCHMARK_V1",
    "SYNTHETIC_FIXED_DIRECTION_V1",
]
receipt = {}
for contract_id in ids:
    contract = SignalProducerRegistry.get_contract(contract_id)
    assert contract is not None, contract_id
    receipt[contract_id] = canonical_sha256(contract.semantic_payload())
print(json.dumps(receipt, sort_keys=True))
"""


def test_t11b_fresh_process_registry_smoke_matches_baseline() -> None:
    """T11 (fresh-process receipt): a clean interpreter registers the five defaults at baseline hashes."""
    import btc_quant_agent.economic.signal_producer as signal_producer_module

    package_root = Path(signal_producer_module.__file__).resolve().parents[2]
    env = dict(os.environ)
    entries = [entry for entry in env.get("PYTHONPATH", "").split(os.pathsep) if entry]
    if str(package_root) not in entries:
        entries.insert(0, str(package_root))
    env["PYTHONPATH"] = os.pathsep.join(entries)

    completed = subprocess.run(
        [sys.executable, "-c", SMOKE_SCRIPT],
        capture_output=True,
        text=True,
        timeout=180,
        env=env,
        cwd=str(package_root),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])
    assert receipt == BASELINE_CONTRACT_HASHES


# ==============================================================================
# T12 — Fail-closed construction of non-JSON / non-object parameters
# ==============================================================================


def test_t12a_non_mapping_parameters_rejected() -> None:
    """T12a: parameters that are not a JSON object fail closed at construction."""
    for bad_parameters in ([1, 2, 3], "threshold=0", 42):
        with pytest.raises(TypeError, match="parameters must be a JSON object"):
            SignalProducerContract(
                contract_id="R05A-T12A-NON-MAPPING",
                version="1.0.0",
                producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
                producer_version="1.0.0",
                rule="MOMENTUM_THRESHOLD",
                parameters=bad_parameters,
            )


def test_t12b_non_json_values_rejected() -> None:
    """T12b: sets and non-string keys inside parameters fail closed at construction."""
    with pytest.raises(TypeError, match="unsupported canonical JSON value: set"):
        _make_contract("R05A-T12B-SET", params={"tags": {"LONG", "SHORT"}})
    with pytest.raises(TypeError, match="canonical JSON object keys must be strings"):
        _make_contract("R05A-T12B-NONSTR-KEY", params={1: "one"})


def test_t12c_enum_parameters_normalized_to_strings() -> None:
    """T12c: enum parameter values are normalized to strings by the canonical machinery."""
    class Mode(Enum):
        LONG = "long"

    contract = _make_contract("R05A-T12C-ENUM", params={"mode": Mode.LONG})
    assert contract.parameters["mode"] == "long"
    assert len(contract.parameters) == 1
    assert list(contract.parameters) == ["mode"]
    assert contract.semantic_payload()["parameters"] == {"mode": "long"}
    assert _semantic_hash(contract) == contract.contract_hash
