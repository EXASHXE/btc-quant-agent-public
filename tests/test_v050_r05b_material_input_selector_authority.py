"""v0.5.0 R05B adversarial regression suite: material-input selector authority.

Permanent regression suite for the AG-02 HIGH repair.  The verifier (bundle
builder AND cold validator) independently reconstructs the required
material-input window from the full frozen candle dataset, the signal decision
timestamp, and the authoritative producer contract.  Caller-selected
``input_references`` / ``observation_open_times_ms`` /
``material_input_open_times_ms`` are assertions only: they must exactly equal
the independently reconstructed set.  A candidate can rehash every outer
artifact; the cold reconstruction still rejects a substituted, shortened,
extended, reordered, or non-latest window.

Test map (prompt v0.5.0_R05B):
- T1: exact Astra reproduction - lookback_bars=2, latest [c2,c3] accepted and
  cold-replayable; [c0,c3] and [c0,c1,c3] rejected; dataset values prove the
  economic consequence (latest window LONG, malicious window SHORT).
- T2: full rehash does not help - cold validation rejects after the attacker
  recomputes input_set_sha256 and bundle_sha256.
- T3: omitted latest row [c1,c2] rejected (not the latest window).
- T4: extra earlier row [c1,c2,c3] rejected.
- T5: row substitution [c1,c3] rejected.
- T6: ordering/duplicate selections [c3,c2], [c2,c2] rejected.
- T7: future/unavailable terminal row never enters the expected window and
  cannot be forced in by the caller.
- T8: cadence gap in the last-N window fails closed (no backward jump).
- T9: mixed symbol / interval window fails closed.
- T10: exact lookback semantics (min_lookback_bars alone is ambiguous).
- T11: RETURN_SIGN / PRICE_BREAKOUT exact-one; contradictory lookback fails.
- T12: auto-construction populates refs from reconstruction and cold-validates.
- T13: generation-contract forgery - builder overwrites canonical selector
  fields, cold validator rejects persisted forgeries.
- T14: the five built-in producer contract hashes are unchanged (R05A receipt).
- T15: RANDOM_BENCHMARK role keeps its own reconstruction; no candidate
  selector fields leak into benchmark-role semantics.
- T16: valid C-lite/R04 semantic path stays on the independently required
  latest window (intentional tightenings documented).

Platform note: the bundle layer (build + validate) is exercised directly
because it is the unit that owns selector authority; end-to-end execution
coverage is provided by the existing B04/R05A suites.
"""
from __future__ import annotations

import copy
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import test_v041_p6_metrics_benchmarks_qualification as p6
import test_v050_r05a_ag03_producer_contract_immutability as r05a

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic import (
    BenchmarkKind,
    InformationSignal,
    MATERIAL_INPUT_SELECTOR_TYPE,
    ReplayInputBundle,
    SignalProducerContract,
    SignalProducerRegistry,
    build_formal_replay_input_bundle,
    resolve_material_input_policy,
    select_required_material_candles,
    validate_formal_replay_input_bundle,
)
from btc_quant_agent.economic.signal_producer import _runtime_candle_payload
from btc_quant_agent.research_contract.canonical import canonical_sha256

START_MS = 1_800_000_000_000
CADENCE_MS = 900_000
# Decision timestamp: c4's open time.  c3 (close = START + 4*CADENCE - 1) is
# the latest eligible row; c4 is only available after the decision time.
DECISION_TS = START_MS + 4 * CADENCE_MS

MOMENTUM_PARAMS: dict[str, Any] = {
    "lookback_bars": 2,
    "threshold_return_bps": 150.0,
}
EXPECTED_WINDOW_MATCH = (
    "caller-selected material window for R05B-SIGNAL-1 does not equal"
)
COLD_RECONSTRUCTION_MATCH = (
    "persisted input references for R05B-SIGNAL-1 do not exactly equal"
)


def _binance_candles(specs: list[dict[str, Any]]) -> tuple[Candle, ...]:
    """Build closed candles under the Binance kline convention.

    Candle at position i: open_time_ms = START_MS + i * CADENCE_MS,
    close_time_ms = open_time + CADENCE_MS - 1 (so the next open equals the
    previous close + 1), and available_at_ms == close_time_ms.  A spec may
    override open_time_ms/symbol/interval/available_at_ms/closed.
    """
    candles: list[Candle] = []
    for index, spec in enumerate(specs):
        open_time = spec.get("open_time_ms", START_MS + index * CADENCE_MS)
        close_time = open_time + CADENCE_MS - 1
        candles.append(
            Candle(
                symbol=spec.get("symbol", "BTCUSDT"),
                interval=spec.get("interval", "15m"),
                open_time_ms=open_time,
                close_time_ms=close_time,
                open=spec["open"],
                high=spec.get("high", max(spec["open"], spec["close"]) + 0.5),
                low=spec.get("low", min(spec["open"], spec["close"]) - 0.5),
                close=spec["close"],
                volume=spec.get("volume", 10_000.0),
                quote_volume=spec.get("quote_volume", 1_000_000.0),
                available_at_ms=spec.get("available_at_ms", close_time),
                closed=spec.get("closed", True),
            )
        )
    return tuple(candles)


def _astra_candles() -> tuple[Candle, ...]:
    """Frozen contiguous dataset reproducing the Astra AG-02 window attack.

    Under the exact producer formula (last close - first open) / first open
    with a 150 bps threshold: the authoritative latest window [c2, c3] replays
    LONG (+2.0%); the malicious earlier window [c0, c3] replays SHORT
    (-1.92%).  c4 exists but is only available after the decision time.
    """
    return _binance_candles(
        [
            {"open": 104.0, "close": 105.0},
            {"open": 105.0, "close": 105.5},
            {"open": 100.0, "close": 101.5},
            {"open": 101.5, "close": 102.0},
            {"open": 102.0, "close": 103.0},
        ]
    )


def _momentum_contract() -> SignalProducerContract:
    return SignalProducerContract(
        contract_id="R05B_MOMENTUM_2BAR_V1",
        version="1.0.0",
        producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
        producer_version="1.0.0",
        rule="MOMENTUM_THRESHOLD",
        parameters=dict(MOMENTUM_PARAMS),
    )


def _register_contract(
    registry_ids: list[str],
    contract: SignalProducerContract,
) -> SignalProducerContract:
    SignalProducerRegistry.register_contract(contract)
    registry_ids.append(contract.contract_id)
    return contract


@pytest.fixture
def registry_ids() -> list[str]:
    """Track contract ids registered by a test; teardown removes only those."""
    added: list[str] = []
    yield added
    for contract_id in added:
        SignalProducerRegistry._contracts.pop(contract_id, None)


def _context(
    tmp_path: Path,
    contract: SignalProducerContract,
    candles: tuple[Candle, ...] | None = None,
) -> dict[str, Any]:
    """Formal context binding an authoritative contract over the frozen dataset."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    frozen = candles if candles is not None else _astra_candles()
    engine = p6._zero_cost_engine()
    dataset = p6._dataset_evidence(tmp_path, frozen)
    comparison = p6._comparison(
        dataset,
        frozen,
        engine,
        required=(BenchmarkKind.CASH,),
        descriptive=(),
    )
    protocol = replace(
        p6._protocol(comparison, engine),
        signal_producer_contract=contract,
    )
    signal = InformationSignal(
        signal_id="R05B-SIGNAL-1",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=DECISION_TS,
        direction=1,
        strength=1.0,
    )
    return {
        "candles": frozen,
        "engine": engine,
        "dataset": dataset,
        "comparison": comparison,
        "protocol": protocol,
        "signal": signal,
        "contract": contract,
    }


def _decision_entry(
    ctx: dict[str, Any],
    *,
    open_times: list[int] | None = None,
    generation_contract: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Hand-built decision input entry (caller assertion surface)."""
    signal = ctx["signal"]
    contract = ctx["contract"]
    gen = dict(generation_contract or {})
    gen.setdefault("rule", contract.rule)
    gen.setdefault("producer_contract_id", contract.contract_id)
    gen.setdefault("strength", 1.0)
    entry: dict[str, Any] = {
        "signal_id": signal.signal_id,
        "signal_timestamp_ms": signal.timestamp_ms,
        "signal_payload": signal.to_dict(),
        "producer_identity": contract.producer_identity,
        "producer_version": contract.producer_version,
        "producer_contract_id": contract.contract_id,
        "generation_contract": gen,
    }
    if open_times is not None:
        entry["observation_open_times_ms"] = list(open_times)
    return entry


def _refs_for(ctx: dict[str, Any], open_times: list[int]) -> list[dict[str, Any]]:
    """Content-hashed InputReference dicts for genuine dataset rows."""
    by_open = {candle.open_time_ms: candle for candle in ctx["candles"]}
    return [
        {
            "source_type": "CANONICAL_CANDLE",
            "dataset_evidence_id": ctx["dataset"].evidence_id,
            "open_time_ms": candle.open_time_ms,
            "close_time_ms": candle.close_time_ms,
            "available_at_ms": candle.available_at_ms,
            "row_content_sha256": canonical_sha256(
                _runtime_candle_payload(candle)
            ),
        }
        for candle in (by_open[open_time] for open_time in open_times)
    ]


def _rehash_bundle(payload: dict[str, Any]) -> dict[str, Any]:
    """Attacker step: recompute the only candidate-owned bundle hash."""
    payload["bundle_sha256"] = canonical_sha256(
        {key: value for key, value in payload.items() if key != "bundle_sha256"}
    )
    return payload


def _tamper_refs(
    valid_payload: dict[str, Any],
    ctx: dict[str, Any],
    open_times: list[int],
) -> dict[str, Any]:
    """Replace persisted refs with a genuine-but-wrong window and rehash.

    This is exactly the Astra attack: every row is real, available and
    correctly hashed; the candidate recomputes input_set_sha256 and
    bundle_sha256.  Only the cold reconstruction can still reject it.
    """
    tampered = copy.deepcopy(valid_payload)
    refs = _refs_for(ctx, open_times)
    entry = tampered["decision_inputs"][0]
    entry["input_references"] = refs
    entry["input_set_sha256"] = canonical_sha256(refs)
    return _rehash_bundle(tampered)


def _build_bundle(
    ctx: dict[str, Any], entry: dict[str, Any]
) -> ReplayInputBundle:
    return build_formal_replay_input_bundle(
        protocol=ctx["protocol"],
        dataset_evidence=ctx["dataset"],
        candles=ctx["candles"],
        signals=(ctx["signal"],),
        decision_inputs=(entry,),
    )


def _cold_validate(ctx: dict[str, Any], payload: dict[str, Any]) -> None:
    validate_formal_replay_input_bundle(
        payload,
        candles=ctx["candles"],
        expected_protocol=ctx["protocol"],
        expected_dataset_evidence=ctx["dataset"],
        expected_signals=(ctx["signal"],),
    )


# ==============================================================================
# T1 - T7: Astra window-attack reproduction and rehash resistance
# ==============================================================================


def test_t1_exact_astra_reproduction_latest_window_only_is_authoritative(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T1: [2,3] accepted/replayable; [0,3] and [0,1,3] rejected; the dataset
    values prove the direction difference."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]

    # Economic consequence, proven with the exact producer formula:
    # (last close - first open) / first open vs the 150 bps threshold.
    threshold = float(MOMENTUM_PARAMS["threshold_return_bps"]) / 10_000.0
    authoritative_ret = (candles[3].close - candles[2].open) / candles[2].open
    malicious_ret = (candles[3].close - candles[0].open) / candles[0].open
    assert authoritative_ret > threshold  # latest window [c2, c3] -> LONG
    assert malicious_ret < -threshold  # malicious [c0, c3] -> SHORT

    expected_open_times = [candles[2].open_time_ms, candles[3].open_time_ms]
    assert [
        candle.open_time_ms
        for candle in select_required_material_candles(
            contract, candles, DECISION_TS
        )
    ] == expected_open_times

    # 1. Latest valid window [c2, c3] -> accepted and cold-replayable.
    bundle = _build_bundle(
        ctx, _decision_entry(ctx, open_times=expected_open_times)
    )
    payload = bundle.to_dict()
    _cold_validate(ctx, payload)
    assert payload["decision_inputs"][0]["generation_contract"][
        "material_input_open_times_ms"
    ] == expected_open_times

    # 2. Malicious earlier non-contiguous window [c0, c3] -> rejected.
    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(
            ctx,
            _decision_entry(
                ctx,
                open_times=[candles[0].open_time_ms, candles[3].open_time_ms],
            ),
        )

    # 3. Malicious three-row selection [c0, c1, c3] -> rejected.
    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(
            ctx,
            _decision_entry(
                ctx,
                open_times=[
                    candles[0].open_time_ms,
                    candles[1].open_time_ms,
                    candles[3].open_time_ms,
                ],
            ),
        )


def test_t2_full_rehash_does_not_help_cold_validate_rejects(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T2: recomputing input_set_sha256 and bundle_sha256 for each malicious
    selection cannot survive the cold reconstruction."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()

    malicious_selections = [
        [candles[0].open_time_ms, candles[3].open_time_ms],
        [
            candles[0].open_time_ms,
            candles[1].open_time_ms,
            candles[3].open_time_ms,
        ],
    ]
    for malicious in malicious_selections:
        tampered = _tamper_refs(valid, ctx, malicious)
        with pytest.raises(ValueError, match=COLD_RECONSTRUCTION_MATCH):
            _cold_validate(ctx, tampered)


def test_t3_omitted_latest_row_rejected(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T3: [c1,c2] - all rows genuine, contiguous, available and correctly
    hashed - is rejected because it is not the latest material window."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    stale = [candles[1].open_time_ms, candles[2].open_time_ms]

    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(ctx, _decision_entry(ctx, open_times=stale))

    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()
    with pytest.raises(ValueError, match=COLD_RECONSTRUCTION_MATCH):
        _cold_validate(ctx, _tamper_refs(valid, ctx, stale))


def test_t4_extra_earlier_row_rejected(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T4: [c1,c2,c3] contains the correct window but is rejected for the
    exact N=2 selector."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    extended = [
        candles[1].open_time_ms,
        candles[2].open_time_ms,
        candles[3].open_time_ms,
    ]

    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(ctx, _decision_entry(ctx, open_times=extended))

    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()
    with pytest.raises(ValueError, match=COLD_RECONSTRUCTION_MATCH):
        _cold_validate(ctx, _tamper_refs(valid, ctx, extended))


def test_t5_row_substitution_rejected(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T5: [c1,c3] with valid row hashes is rejected."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    substituted = [candles[1].open_time_ms, candles[3].open_time_ms]

    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(ctx, _decision_entry(ctx, open_times=substituted))

    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()
    with pytest.raises(ValueError, match=COLD_RECONSTRUCTION_MATCH):
        _cold_validate(ctx, _tamper_refs(valid, ctx, substituted))


def test_t6_ordering_and_duplicate_selections_rejected(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T6: [c3,c2] and [c2,c2] are rejected by the builder assertion and the
    cold strictly-increasing check."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]

    for bad in (
        [candles[3].open_time_ms, candles[2].open_time_ms],
        [candles[2].open_time_ms, candles[2].open_time_ms],
    ):
        with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
            _build_bundle(ctx, _decision_entry(ctx, open_times=bad))

    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()
    for bad in (
        [candles[3].open_time_ms, candles[2].open_time_ms],
        [candles[2].open_time_ms, candles[2].open_time_ms],
    ):
        tampered = _tamper_refs(valid, ctx, bad)
        with pytest.raises(
            ValueError, match="must be strictly increasing"
        ):
            _cold_validate(ctx, tampered)


def test_t7_future_terminal_row_never_enters_required_window(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T7: a dataset row after the decision time never enters the expected
    window and the caller cannot force it in."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    assert candles[4].available_at_ms > DECISION_TS
    expected = select_required_material_candles(contract, candles, DECISION_TS)
    assert [candle.open_time_ms for candle in expected] == [
        candles[2].open_time_ms,
        candles[3].open_time_ms,
    ]

    # Caller assertion path: the future row is rejected at availability.
    with pytest.raises(
        ValueError, match="was not available by signal timestamp"
    ):
        _build_bundle(
            ctx,
            _decision_entry(
                ctx,
                open_times=[
                    candles[3].open_time_ms,
                    candles[4].open_time_ms,
                ],
            ),
        )

    # Cold persisted path: same rejection before any replay runs.
    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()
    tampered = _tamper_refs(
        valid, ctx, [candles[2].open_time_ms, candles[4].open_time_ms]
    )
    with pytest.raises(
        ValueError, match="was not available by signal timestamp"
    ):
        _cold_validate(ctx, tampered)


# ==============================================================================
# T8 - T11: pure selector semantics (fail-closed completeness properties)
# ==============================================================================


def test_t8_gap_in_required_window_fails_closed_without_backward_jump() -> None:
    """T8: a cadence gap in the last-N window fails closed; the selector does
    not jump farther backward to manufacture N contiguous rows."""
    contract = _momentum_contract()
    ts = START_MS + 5 * CADENCE_MS
    # c0, c1, c2 contiguous; c3 missing; c4 arrives after the gap.
    candles = _binance_candles(
        [
            {"open": 100.0, "close": 100.5},
            {"open": 100.5, "close": 101.0},
            {"open": 101.0, "close": 101.5},
            {"open": 102.0, "close": 102.5, "open_time_ms": START_MS + 4 * CADENCE_MS},
        ]
    )
    with pytest.raises(ValueError, match="has a cadence gap before"):
        select_required_material_candles(contract, candles, ts)


def test_t9_mixed_symbol_and_interval_windows_fail_closed() -> None:
    """T9: a required window crossing symbol or interval boundaries fails
    closed."""
    contract = _momentum_contract()
    mixed_symbol = _binance_candles(
        [
            {"open": 104.0, "close": 105.0},
            {"open": 105.0, "close": 105.5},
            {"open": 100.0, "close": 101.5, "symbol": "ETHUSDT"},
            {"open": 101.5, "close": 102.0},
        ]
    )
    with pytest.raises(ValueError, match="crosses symbol boundaries"):
        select_required_material_candles(
            contract, mixed_symbol, DECISION_TS
        )

    mixed_interval = _binance_candles(
        [
            {"open": 104.0, "close": 105.0},
            {"open": 105.0, "close": 105.5},
            {"open": 100.0, "close": 101.5, "interval": "5m"},
            {"open": 101.5, "close": 102.0},
        ]
    )
    with pytest.raises(ValueError, match="crosses interval boundaries"):
        select_required_material_candles(
            contract, mixed_interval, DECISION_TS
        )


def test_t10_exact_lookback_semantics(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T10: exact lookback_bars drives the selector; min_lookback_bars alone
    is an ambiguous floor and fails closed; 0/negative and disagreeing
    declarations fail closed."""
    candles = _astra_candles()

    two_bar = _momentum_contract()
    policy = resolve_material_input_policy(two_bar)
    assert policy.required_bars == 2
    assert policy.selector_type == MATERIAL_INPUT_SELECTOR_TYPE
    assert policy.selector_sha256
    assert [
        candle.open_time_ms
        for candle in select_required_material_candles(
            two_bar, candles, DECISION_TS
        )
    ] == [candles[2].open_time_ms, candles[3].open_time_ms]

    # min_lookback_bars alone is NOT a complete selector (pure + builder).
    with pytest.raises(ValueError, match="ambiguous material-input selector"):
        resolve_material_input_policy(
            SignalProducerContract(
                contract_id="R05B_MOMENTUM_MIN_ONLY_V1",
                version="1.0.0",
                producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
                producer_version="1.0.0",
                rule="MOMENTUM_THRESHOLD",
                parameters={"min_lookback_bars": 2, "threshold_return_bps": 150.0},
            )
        )
    registered_ambiguous = _register_contract(
        registry_ids,
        SignalProducerContract(
            contract_id="R05B_MOMENTUM_AMBIG_V1",
            version="1.0.0",
            producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
            producer_version="1.0.0",
            rule="MOMENTUM_THRESHOLD",
            parameters={"min_lookback_bars": 2, "threshold_return_bps": 150.0},
        ),
    )
    ctx = _context(tmp_path, registered_ambiguous)
    with pytest.raises(ValueError, match="ambiguous material-input selector"):
        _build_bundle(ctx, _decision_entry(ctx))

    # lookback_bars=0 / negative fail closed.
    for bad in (0, -2):
        with pytest.raises(ValueError, match="requires at least 1 bar"):
            resolve_material_input_policy(
                SignalProducerContract(
                    contract_id=f"R05B_MOMENTUM_BAD_{bad}_V1",
                    version="1.0.0",
                    producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
                    producer_version="1.0.0",
                    rule="MOMENTUM_THRESHOLD",
                    parameters={"lookback_bars": bad, "threshold_return_bps": 150.0},
                )
            )

    # Disagreeing lookback/min declarations fail closed.
    with pytest.raises(ValueError, match="lookback semantics disagree"):
        resolve_material_input_policy(
            SignalProducerContract(
                contract_id="R05B_MOMENTUM_DISAGREE_V1",
                version="1.0.0",
                producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
                producer_version="1.0.0",
                rule="MOMENTUM_THRESHOLD",
                parameters={
                    "lookback_bars": 2,
                    "min_lookback_bars": 1,
                    "threshold_return_bps": 150.0,
                },
            )
        )


def test_t11_return_sign_and_price_breakout_exact_one_row(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T11: RETURN_SIGN and PRICE_BREAKOUT use exactly the latest 1 eligible
    row; an extra older input rejects and contradictory lookback fails."""
    candles = _astra_candles()
    latest = candles[3].open_time_ms
    older = [candles[2].open_time_ms, latest]

    # RETURN_SIGN (built-in contract, empty parameters).
    rs_contract = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert rs_contract is not None
    ctx = _context(tmp_path, rs_contract)
    bundle = _build_bundle(ctx, _decision_entry(ctx, open_times=[latest]))
    _cold_validate(ctx, bundle.to_dict())
    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(ctx, _decision_entry(ctx, open_times=older))

    # Contradictory lookback fails closed (pure + builder).
    lb2 = _register_contract(
        registry_ids,
        SignalProducerContract(
            contract_id="R05B_RETURN_SIGN_LB2_V1",
            version="1.0.0",
            producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
            producer_version="1.0.0",
            rule="RETURN_SIGN",
            parameters={"lookback_bars": 2},
        ),
    )
    with pytest.raises(ValueError, match="RETURN_SIGN requires exactly 1"):
        resolve_material_input_policy(lb2)
    lb2_ctx = _context(tmp_path / "lb2", lb2)
    with pytest.raises(ValueError, match="RETURN_SIGN requires exactly 1"):
        _build_bundle(lb2_ctx, _decision_entry(lb2_ctx))

    # PRICE_BREAKOUT: exactly the latest 1 eligible row.
    pb = _register_contract(
        registry_ids,
        SignalProducerContract(
            contract_id="R05B_PRICE_BREAKOUT_V1",
            version="1.0.0",
            producer_identity="CANONICAL_RULE_SIGNAL_PRODUCER",
            producer_version="1.0.0",
            rule="PRICE_BREAKOUT",
            parameters={"breakout_level": 101.75},
        ),
    )
    pb_ctx = _context(tmp_path / "pb", pb)
    pb_bundle = _build_bundle(pb_ctx, _decision_entry(pb_ctx, open_times=[latest]))
    _cold_validate(pb_ctx, pb_bundle.to_dict())
    with pytest.raises(ValueError, match=EXPECTED_WINDOW_MATCH):
        _build_bundle(pb_ctx, _decision_entry(pb_ctx, open_times=older))


# ==============================================================================
# T12 - T13: auto-construction and generation-contract forgery
# ==============================================================================


def test_t12_auto_construction_from_reconstructed_authority(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T12: when the caller omits refs/open-times entirely, the builder
    reconstructs the exact required refs and the bundle cold-validates."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]

    entry = _decision_entry(ctx)
    assert "observation_open_times_ms" not in entry
    bundle = _build_bundle(ctx, entry)
    payload = bundle.to_dict()
    _cold_validate(ctx, payload)

    reconstructed = [
        candle.open_time_ms
        for candle in select_required_material_candles(
            contract, candles, DECISION_TS
        )
    ]
    entry_payload = payload["decision_inputs"][0]
    refs = entry_payload["input_references"]
    assert [ref["open_time_ms"] for ref in refs] == reconstructed
    assert entry_payload["input_set_sha256"] == canonical_sha256(refs)
    assert entry_payload["generation_contract"][
        "material_input_open_times_ms"
    ] == reconstructed


def test_t13_builder_overwrites_forged_generation_contract_fields(
    tmp_path: Path, registry_ids: list[str]
) -> None:
    """T13: forged material-input generation-contract fields are overwritten
    with canonical values derived from the reconstructed set; no forged field
    becomes authority."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    policy = resolve_material_input_policy(contract)
    expected_open_times = [candles[2].open_time_ms, candles[3].open_time_ms]

    forged_gen = {
        "rule": contract.rule,
        "producer_contract_id": contract.contract_id,
        "strength": 1.0,
        "min_lookback_bars": 99,
        "material_input_open_times_ms": [
            candles[0].open_time_ms,
            candles[1].open_time_ms,
        ],
        "expected_preimage_sha256": "0" * 64,
        "material_input_selector_type": "CALLER_CHOICE",
        "material_input_required_bars": 7,
        "material_input_selector_sha256": "f" * 64,
    }
    bundle = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=expected_open_times, generation_contract=forged_gen
        ),
    )
    payload = bundle.to_dict()
    _cold_validate(ctx, payload)

    gen = payload["decision_inputs"][0]["generation_contract"]
    expected_preimage = canonical_sha256(
        [_runtime_candle_payload(candle) for candle in (candles[2], candles[3])]
    )
    assert gen["material_input_open_times_ms"] == expected_open_times
    assert gen["min_lookback_bars"] == 2
    assert gen["material_input_required_bars"] == 2
    assert gen["material_input_selector_type"] == MATERIAL_INPUT_SELECTOR_TYPE
    assert gen["material_input_selector_sha256"] == policy.selector_sha256
    assert gen["expected_preimage_sha256"] == expected_preimage


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        (
            "min_lookback_bars",
            3,
            "generation_contract min_lookback_bars for R05B-SIGNAL-1 must equal",
        ),
        (
            "material_input_required_bars",
            5,
            "generation_contract material_input_required_bars"
            " for R05B-SIGNAL-1 must equal",
        ),
        (
            "material_input_selector_type",
            "CALLER_CHOICE",
            "generation_contract material_input_selector_type"
            " for R05B-SIGNAL-1 must equal",
        ),
        (
            "material_input_selector_sha256",
            "f" * 64,
            "generation_contract material_input_selector_sha256"
            " for R05B-SIGNAL-1 does not equal",
        ),
        (
            "expected_preimage_sha256",
            "0" * 64,
            "generation_contract expected_preimage_sha256"
            " for R05B-SIGNAL-1 does not equal",
        ),
        (
            "material_input_open_times_ms",
            [START_MS, START_MS + CADENCE_MS],
            "generation_contract material_input_open_times_ms"
            " for R05B-SIGNAL-1 does not equal",
        ),
    ],
)
def test_t13_cold_persisted_generation_contract_forgery_rejected(
    tmp_path: Path,
    registry_ids: list[str],
    field: str,
    value: Any,
    match: str,
) -> None:
    """T13: a persisted forged selector field is rejected by the cold
    validator even after a full bundle rehash."""
    contract = _register_contract(registry_ids, _momentum_contract())
    ctx = _context(tmp_path, contract)
    candles = ctx["candles"]
    valid = _build_bundle(
        ctx,
        _decision_entry(
            ctx, open_times=[candles[2].open_time_ms, candles[3].open_time_ms]
        ),
    ).to_dict()

    tampered = copy.deepcopy(valid)
    tampered["decision_inputs"][0]["generation_contract"][field] = value
    _rehash_bundle(tampered)
    with pytest.raises(ValueError, match=match):
        _cold_validate(ctx, tampered)


# ==============================================================================
# T14 - T16: identity preservation, role isolation, valid semantic path
# ==============================================================================


def test_t14_builtin_producer_contract_hashes_unchanged() -> None:
    """T14: all five built-in producer contract hashes from R05A show no
    drift; the R05B verifier hardening did not mutate their semantics."""
    for contract_id, expected in r05a.BASELINE_CONTRACT_HASHES.items():
        contract = SignalProducerRegistry.get_contract(contract_id)
        assert contract is not None
        assert contract.contract_hash == expected


def test_t15_random_benchmark_role_keeps_independent_reconstruction(
    tmp_path: Path,
) -> None:
    """T15: the RANDOM_BENCHMARK role keeps its own reconstruction; caller
    open-times generate content-hashed refs and no candidate selector fields
    leak into benchmark-role semantics."""
    candles = p6._candles()
    engine = p6._zero_cost_engine()
    dataset = p6._dataset_evidence(tmp_path, candles)
    comparison = p6._comparison(
        dataset,
        candles,
        engine,
        required=(BenchmarkKind.CASH,),
        descriptive=(),
    )
    protocol = p6._protocol(comparison, engine)
    signal = InformationSignal(
        signal_id="R05B-RANDOM-1",
        experiment_id=protocol.experiment_revision_id,
        timestamp_ms=candles[1].open_time_ms,
        direction=1,
        strength=1.0,
    )
    entry = {
        "signal_id": signal.signal_id,
        "signal_timestamp_ms": signal.timestamp_ms,
        "signal_payload": signal.to_dict(),
        "observation_open_times_ms": [candles[0].open_time_ms],
    }
    bundle = build_formal_replay_input_bundle(
        protocol=protocol,
        dataset_evidence=dataset,
        candles=candles,
        signals=(signal,),
        decision_inputs=(entry,),
        authority_role="RANDOM_BENCHMARK",
    )
    payload = bundle.to_dict()
    gen = payload["decision_inputs"][0]["generation_contract"]
    assert gen["rule"] == "RANDOM_MATCHED_OPPORTUNITY"
    assert "material_input_selector_type" not in gen
    assert "material_input_required_bars" not in gen
    assert "material_input_selector_sha256" not in gen
    assert gen["material_input_open_times_ms"] == [candles[0].open_time_ms]
    validate_formal_replay_input_bundle(
        payload,
        candles=candles,
        expected_protocol=protocol,
        expected_dataset_evidence=dataset,
        expected_signals=(signal,),
        expected_role="RANDOM_BENCHMARK",
    )


def test_t16_c_lite_r04_valid_semantic_path_stays_on_required_window(
    tmp_path: Path,
) -> None:
    """T16: the valid C-lite/R04 semantic path - a canonical RETURN_SIGN
    fixture that already uses the independently required latest window - stays
    semantically identical and cold-validates.

    Intentional tightenings observed in the regression battery (documented,
    not weakened): bar_pit ar_t1's late-row dataset is now rejected earlier
    with "insufficient eligible material candles" because the selector runs
    before the row-level availability check; b04 T13/T14 caller-asserted
    incomplete windows now fail at build time with "caller-selected material
    window ... does not equal the authoritative required input window"; and
    local momentum fixtures must declare exact lookback_bars because
    min_lookback_bars alone is an ambiguous floor that fails closed.
    """
    candles = _astra_candles()
    rs = SignalProducerRegistry.get_contract("CANONICAL_RETURN_SIGN_V1")
    assert rs is not None
    ctx = _context(tmp_path, rs, candles=candles)
    latest = candles[3].open_time_ms

    bundle = _build_bundle(ctx, _decision_entry(ctx, open_times=[latest]))
    payload = bundle.to_dict()
    _cold_validate(ctx, payload)

    # The persisted semantic content is exactly the independently required
    # latest window - the window C-lite/R04 formal consumers consume.
    reconstructed = [
        candle.open_time_ms
        for candle in select_required_material_candles(rs, candles, DECISION_TS)
    ]
    assert reconstructed == [latest]
    entry = payload["decision_inputs"][0]
    assert [ref["open_time_ms"] for ref in entry["input_references"]] == [latest]
    assert entry["generation_contract"]["material_input_open_times_ms"] == [
        latest
    ]
    assert entry["generation_contract"]["expected_preimage_sha256"] == (
        canonical_sha256([_runtime_candle_payload(candles[3])])
    )
