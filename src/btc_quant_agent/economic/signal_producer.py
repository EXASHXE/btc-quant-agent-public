from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, Protocol, runtime_checkable

from ..domain import Candle
from ..research_contract.canonical import canonical_sha256
from .signal import InformationSignal


def _runtime_candle_payload(item: Candle) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "interval": item.interval,
        "open_time_ms": item.open_time_ms,
        "close_time_ms": item.close_time_ms,
        "open": item.open,
        "high": item.high,
        "low": item.low,
        "close": item.close,
        "volume": item.volume,
        "quote_volume": item.quote_volume,
        "closed": item.closed,
        "available_at_ms": item.available_at_ms,
    }


@runtime_checkable
class SignalProducer(Protocol):
    """Protocol for deterministic signal replay verification."""

    @property
    def producer_identity(self) -> str:
        ...

    @property
    def producer_version(self) -> str:
        ...

    def replay_signal(
        self,
        *,
        signal_id: str,
        signal_timestamp_ms: int,
        experiment_id: str,
        input_candles: Sequence[Candle],
        generation_contract: Mapping[str, Any],
    ) -> InformationSignal:
        """Deterministically replay a signal from exact, content-verified inputs."""
        ...


class SignalProducerRegistry:
    """Registry for verified deterministic signal producers."""

    _producers: ClassVar[dict[tuple[str, str], SignalProducer]] = {}

    @classmethod
    def register(cls, producer: SignalProducer) -> None:
        key = (producer.producer_identity, producer.producer_version)
        cls._producers[key] = producer

    @classmethod
    def get(cls, identity: str, version: str) -> SignalProducer | None:
        return cls._producers.get((identity, version))

    @classmethod
    def clear(cls) -> None:
        cls._producers.clear()


class CanonicalRuleSignalProducer:
    """Canonical rule-based signal producer with strict deterministic replay."""

    producer_identity: str = "CANONICAL_RULE_SIGNAL_PRODUCER"
    producer_version: str = "1.0.0"

    def replay_signal(
        self,
        *,
        signal_id: str,
        signal_timestamp_ms: int,
        experiment_id: str,
        input_candles: Sequence[Candle],
        generation_contract: Mapping[str, Any],
    ) -> InformationSignal:
        if not input_candles:
            raise ValueError("signal replay requires non-empty material inputs")
        min_lookback = int(generation_contract.get("min_lookback_bars", 1))
        if len(input_candles) < min_lookback:
            raise ValueError(
                f"insufficient lookback for signal replay: required {min_lookback}, got {len(input_candles)}"
            )

        # Validate order and integrity of input candles
        open_times = [c.open_time_ms for c in input_candles]
        if open_times != sorted(set(open_times)):
            raise ValueError("input candles must be ordered and non-overlapping")

        for candle in input_candles:
            if candle.closed is not True:
                raise ValueError("input candle is not explicitly closed")
            if candle.available_at_ms is None or candle.available_at_ms > signal_timestamp_ms:
                raise ValueError("input candle was not available by signal timestamp")

        expected_open_times = generation_contract.get("material_input_open_times_ms")
        if expected_open_times is not None and list(expected_open_times) != open_times:
            raise ValueError("input open times do not match generation contract")

        expected_preimage = generation_contract.get("expected_preimage_sha256")
        if expected_preimage is not None:
            actual_preimage = canonical_sha256(
                [_runtime_candle_payload(c) for c in input_candles]
            )
            if actual_preimage != expected_preimage:
                raise ValueError("input preimage hash mismatch during signal replay")

        rule = str(generation_contract.get("rule", "FIXED_DIRECTION"))
        if rule == "FIXED_DIRECTION":
            direction = int(generation_contract["direction"])
        elif rule == "MOMENTUM_THRESHOLD":
            threshold = float(generation_contract.get("threshold_return_bps", 0.0)) / 10_000.0
            ret = (input_candles[-1].close - input_candles[0].open) / input_candles[0].open
            direction = 1 if ret > threshold else (-1 if ret < -threshold else 0)
        elif rule == "PRICE_BREAKOUT":
            breakout_level = float(generation_contract["breakout_level"])
            direction = 1 if input_candles[-1].close > breakout_level else (-1 if input_candles[-1].close < breakout_level else 0)
        elif rule == "RETURN_SIGN":
            direction = 1 if input_candles[-1].close > input_candles[-1].open else (-1 if input_candles[-1].close < input_candles[-1].open else 0)
        else:
            raise ValueError(f"unsupported rule in generation contract: {rule}")

        strength = float(generation_contract.get("strength", 1.0))
        horizon_ms = int(generation_contract.get("horizon_ms", 3_600_000))
        asset = str(generation_contract.get("asset", input_candles[-1].symbol))
        metadata = dict(generation_contract.get("metadata", {}))

        return InformationSignal(
            signal_id=signal_id,
            experiment_id=experiment_id,
            timestamp_ms=signal_timestamp_ms,
            asset=asset,
            direction=direction,
            strength=strength,
            horizon_ms=horizon_ms,
            metadata=metadata,
        )


class RandomBenchmarkSignalProducer:
    """Deterministic signal producer for P6 random benchmark trials."""

    producer_identity: str = "RANDOM_BENCHMARK_PRODUCER"
    producer_version: str = "1.0.0"

    def replay_signal(
        self,
        *,
        signal_id: str,
        signal_timestamp_ms: int,
        experiment_id: str,
        input_candles: Sequence[Candle],
        generation_contract: Mapping[str, Any],
    ) -> InformationSignal:
        if not input_candles:
            raise ValueError("random benchmark signal replay requires non-empty material inputs")
        for candle in input_candles:
            if candle.closed is not True:
                raise ValueError("input candle is not explicitly closed")
            if candle.available_at_ms is None or candle.available_at_ms > signal_timestamp_ms:
                raise ValueError("input candle was not available by signal timestamp")

        expected_open_times = generation_contract.get("material_input_open_times_ms")
        if expected_open_times is not None:
            open_times = [c.open_time_ms for c in input_candles]
            if list(expected_open_times) != open_times:
                raise ValueError("input open times do not match generation contract")

        expected_preimage = generation_contract.get("expected_preimage_sha256")
        if expected_preimage is not None:
            actual_preimage = canonical_sha256(
                [_runtime_candle_payload(c) for c in input_candles]
            )
            if actual_preimage != expected_preimage:
                raise ValueError("input preimage hash mismatch during signal replay")

        direction = int(generation_contract["direction"])
        strength = float(generation_contract.get("strength", 1.0))
        horizon_ms = int(generation_contract.get("horizon_ms", 3_600_000))
        asset = str(generation_contract.get("asset", input_candles[-1].symbol))
        metadata = dict(generation_contract.get("metadata", {}))

        return InformationSignal(
            signal_id=signal_id,
            experiment_id=experiment_id,
            timestamp_ms=signal_timestamp_ms,
            asset=asset,
            direction=direction,
            strength=strength,
            horizon_ms=horizon_ms,
            metadata=metadata,
        )


# Register default canonical producers
SignalProducerRegistry.register(CanonicalRuleSignalProducer())
SignalProducerRegistry.register(RandomBenchmarkSignalProducer())
