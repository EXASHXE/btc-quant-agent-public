"""B03 regressions for the formal closed/PIT candle boundary and H4."""

from __future__ import annotations

import time
from dataclasses import replace

import pytest
from helpers_v042_semantic_goldens import case_by_id, load_goldens

from btc_quant_agent.domain import Candle
from btc_quant_agent.economic.acceptance_verifier import (
    LEGACY_RUNTIME_MARKET_DATA_SCHEMA_VERSION,
    RUNTIME_MARKET_DATA_SCHEMA_VERSION,
    bind_runtime_market_data,
    decode_runtime_market_data,
    runtime_market_data_sha256,
    validate_formal_candle_sequence,
)


def _from_golden(raw: dict[str, object]) -> Candle:
    return Candle(
        symbol=str(raw["symbol"]),
        interval=str(raw["interval"]),
        open_time_ms=int(raw["open_time_ms"]),
        close_time_ms=int(raw["close_time_ms"]),
        open=float(raw["open"]),
        high=float(raw["high"]),
        low=float(raw["low"]),
        close=float(raw["close"]),
        volume=float(raw["volume"]),
        quote_volume=float(raw["quote_volume"]),
        closed=raw["closed"],  # type: ignore[arg-type]
        available_at_ms=(
            int(raw["available_at_ms"]) if "available_at_ms" in raw else None
        ),
    )


def _valid() -> tuple[Candle, ...]:
    case = case_by_id(load_goldens(), "PIT-01-CLOSED-POSITIVE")
    return tuple(_from_golden(item) for item in case["inputs"]["candles"])


def test_pit_01_positive_round_trip_preserves_availability_and_identity() -> None:
    golden = case_by_id(load_goldens(), "PIT-01-CLOSED-POSITIVE")
    candles = _valid()
    validate_formal_candle_sequence(
        candles,
        expected_product="BTCUSDT",
        expected_interval="1m",
        decision_time_ms=int(golden["inputs"]["decision_time_ms"]),
    )
    accounting = bind_runtime_market_data({}, candles)
    decoded = decode_runtime_market_data(accounting, "BTCUSDT")
    assert decoded == candles
    assert accounting["formal_runtime_market_data_schema_version"] == (
        RUNTIME_MARKET_DATA_SCHEMA_VERSION
    )
    assert accounting["formal_runtime_market_data_sha256"] == runtime_market_data_sha256(
        decoded
    )
    assert accounting["formal_runtime_market_data"][0]["closed"] is True
    assert accounting["formal_runtime_market_data"][0]["available_at_ms"] == 61_000


def test_d_h4_closed_false_cannot_bind_as_formal_complete() -> None:
    case = case_by_id(load_goldens(), "D-H4-CLOSED-FALSE-NOT-COMPLETE")
    candle = _from_golden(case["inputs"]["candles"][0])
    assert candle.closed is False
    with pytest.raises(ValueError, match="not explicitly closed"):
        bind_runtime_market_data({"completeness": "COMPLETE"}, [candle])


def test_d_h4_legacy_schema_cannot_acquire_default_proof() -> None:
    case = case_by_id(load_goldens(), "D-H4-CLOSED-FALSE-NOT-COMPLETE")
    candle = dict(case["inputs"]["candles"][0])
    candle.pop("closed")
    accounting = {
        "formal_runtime_market_data_schema_version": (
            LEGACY_RUNTIME_MARKET_DATA_SCHEMA_VERSION
        ),
        "formal_runtime_market_data": [candle],
        "formal_runtime_market_data_sha256": "attacker-rehashed",
    }
    with pytest.raises(ValueError, match="legacy.*lacks formal availability proof"):
        decode_runtime_market_data(accounting, "BTCUSDT")


def test_pit_02_product_mismatch_rejected() -> None:
    case = case_by_id(load_goldens(), "PIT-02-PRODUCT-MISMATCH")
    candle = replace(_valid()[0], symbol=case["inputs"]["observed_product"])
    with pytest.raises(ValueError, match="instrument"):
        validate_formal_candle_sequence(
            [candle], expected_product=case["inputs"]["declared_product"]
        )


def test_pit_03_interval_mismatch_rejected() -> None:
    case = case_by_id(load_goldens(), "PIT-03-INTERVAL-MISMATCH")
    candle = replace(_valid()[0], interval=case["inputs"]["observed_interval"])
    with pytest.raises(ValueError, match="interval mismatch"):
        validate_formal_candle_sequence(
            [candle],
            expected_product="BTCUSDT",
            expected_interval=case["inputs"]["declared_interval"],
        )


def test_pit_04_overlap_rejected() -> None:
    case = case_by_id(load_goldens(), "PIT-04-OVERLAP")
    first = replace(
        _valid()[0],
        open_time_ms=case["inputs"]["first"]["open_time_ms"],
        close_time_ms=case["inputs"]["first"]["close_time_ms"],
        available_at_ms=case["inputs"]["first"]["close_time_ms"],
    )
    second = replace(
        _valid()[1],
        open_time_ms=case["inputs"]["second"]["open_time_ms"],
        close_time_ms=case["inputs"]["second"]["close_time_ms"],
        available_at_ms=case["inputs"]["second"]["close_time_ms"],
    )
    with pytest.raises(ValueError, match="overlap"):
        validate_formal_candle_sequence([first, second], expected_product="BTCUSDT")


def test_pit_05_required_gap_rejected() -> None:
    case = case_by_id(load_goldens(), "PIT-05-GAP")
    first, second = _valid()
    second = replace(
        second,
        open_time_ms=case["inputs"]["open_times_ms"][1],
        close_time_ms=case["inputs"]["open_times_ms"][1] + 59_999,
        available_at_ms=case["inputs"]["open_times_ms"][1] + 60_000,
    )
    with pytest.raises(ValueError, match="gap"):
        validate_formal_candle_sequence([first, second], expected_product="BTCUSDT")


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", float("nan")),
        ("high", float("inf")),
        ("low", float("-inf")),
        ("close", float("nan")),
        ("volume", float("inf")),
        ("quote_volume", float("nan")),
    ],
)
def test_pit_06_each_nonfinite_field_rejected(field: str, value: float) -> None:
    case = case_by_id(load_goldens(), "PIT-06-NONFINITE")
    assert len(case["inputs"]["invalid_fields"]) == 6
    with pytest.raises(ValueError, match="must be finite"):
        replace(_valid()[0], **{field: value})


def test_pit_07_not_yet_available_and_exact_boundary() -> None:
    case = case_by_id(load_goldens(), "PIT-07-NOT-YET-AVAILABLE")
    raw = case["inputs"]
    candle = replace(
        _valid()[0],
        open_time_ms=raw["event_time_ms"],
        close_time_ms=raw["close_time_ms"],
        available_at_ms=raw["available_at_ms"],
    )
    with pytest.raises(ValueError, match="not available by decision"):
        validate_formal_candle_sequence(
            [candle],
            expected_product="BTCUSDT",
            decision_time_ms=raw["decision_time_ms"],
        )
    validate_formal_candle_sequence(
        [replace(candle, available_at_ms=raw["decision_time_ms"])],
        expected_product="BTCUSDT",
        decision_time_ms=raw["decision_time_ms"],
    )


def test_historical_replay_never_consults_current_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    candles = _valid()
    monkeypatch.setattr(time, "time", lambda: (_ for _ in ()).throw(AssertionError("wall")))
    validate_formal_candle_sequence(
        candles,
        expected_product="BTCUSDT",
        decision_time_ms=candles[-1].available_at_ms,
    )
