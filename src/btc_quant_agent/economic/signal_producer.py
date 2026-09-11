from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class SignalProducerContract:
    """Authoritative declaration of a deterministic signal producer contract."""

    contract_id: str
    version: str
    producer_identity: str
    producer_version: str
    rule: str
    parameters: dict[str, Any] = field(default_factory=dict)
    contract_hash: str = ""

    def __post_init__(self) -> None:
        computed = canonical_sha256(self.semantic_payload())
        if not self.contract_hash:
            object.__setattr__(self, "contract_hash", computed)
        elif self.contract_hash != computed:
            raise ValueError(
                f"contract_hash mismatch: declared {self.contract_hash}, computed {computed}"
            )

    def semantic_payload(self) -> dict[str, Any]:
        return {
            "contract_id": self.contract_id,
            "version": self.version,
            "producer_identity": self.producer_identity,
            "producer_version": self.producer_version,
            "rule": self.rule,
            "parameters": dict(self.parameters),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["contract_hash"] = self.contract_hash
        return payload


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
        authoritative_contract: SignalProducerContract | None = None,
    ) -> InformationSignal:
        """Deterministically replay a signal from exact, content-verified inputs."""
        ...


class SignalProducerRegistry:
    """Registry for verified deterministic signal producers and authoritative contracts."""

    _producers: ClassVar[dict[tuple[str, str], SignalProducer]] = {}
    _contracts: ClassVar[dict[str, SignalProducerContract]] = {}

    @classmethod
    def register_producer(cls, producer: SignalProducer) -> None:
        key = (producer.producer_identity, producer.producer_version)
        cls._producers[key] = producer

    register = register_producer

    @classmethod
    def get_producer(cls, identity: str, version: str) -> SignalProducer | None:
        return cls._producers.get((identity, version))

    get = get_producer

    @classmethod
    def register_contract(cls, contract: SignalProducerContract) -> None:
        cls._contracts[contract.contract_id] = contract

    @classmethod
    def get_contract(cls, contract_id: str) -> SignalProducerContract | None:
        return cls._contracts.get(contract_id)

    @classmethod
    def clear(cls) -> None:
        cls._producers.clear()
        cls._contracts.clear()
        cls._register_defaults()

    @classmethod
    def _register_defaults(cls) -> None:
        canonical_producer = CanonicalRuleSignalProducer()
        random_producer = RandomBenchmarkSignalProducer()
        synthetic_producer = SyntheticFixedSignalProducer()

        cls.register_producer(canonical_producer)
        cls.register_producer(random_producer)
        cls.register_producer(synthetic_producer)

        # Standard canonical contracts
        cls.register_contract(
            SignalProducerContract(
                contract_id="CANONICAL_RETURN_SIGN_V1",
                version="1.0.0",
                producer_identity=canonical_producer.producer_identity,
                producer_version=canonical_producer.producer_version,
                rule="RETURN_SIGN",
                parameters={},
            )
        )
        cls.register_contract(
            SignalProducerContract(
                contract_id="CANONICAL_MOMENTUM_THRESHOLD_V1",
                version="1.0.0",
                producer_identity=canonical_producer.producer_identity,
                producer_version=canonical_producer.producer_version,
                rule="MOMENTUM_THRESHOLD",
                parameters={},
            )
        )
        cls.register_contract(
            SignalProducerContract(
                contract_id="CANONICAL_PRICE_BREAKOUT_V1",
                version="1.0.0",
                producer_identity=canonical_producer.producer_identity,
                producer_version=canonical_producer.producer_version,
                rule="PRICE_BREAKOUT",
                parameters={},
            )
        )
        cls.register_contract(
            SignalProducerContract(
                contract_id="CANONICAL_RANDOM_BENCHMARK_V1",
                version="1.0.0",
                producer_identity=random_producer.producer_identity,
                producer_version=random_producer.producer_version,
                rule="RANDOM_MATCHED_OPPORTUNITY",
                parameters={},
            )
        )
        cls.register_contract(
            SignalProducerContract(
                contract_id="SYNTHETIC_FIXED_DIRECTION_V1",
                version="1.0.0",
                producer_identity=synthetic_producer.producer_identity,
                producer_version=synthetic_producer.producer_version,
                rule="FIXED_DIRECTION",
                parameters={},
            )
        )


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
        authoritative_contract: SignalProducerContract | None = None,
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

        rule = str(generation_contract.get("rule", ""))
        if rule == "FIXED_DIRECTION":
            raise ValueError(
                "FIXED_DIRECTION is forbidden in CanonicalRuleSignalProducer; "
                "market-derived candidate signals cannot use fixed direction. "
                "Use SyntheticFixedSignalProducer for synthetic testing only."
            )
        elif rule == "MOMENTUM_THRESHOLD":
            threshold = float(generation_contract.get("threshold_return_bps", 0.0)) / 10_000.0
            ret = (input_candles[-1].close - input_candles[0].open) / input_candles[0].open
            direction = 1 if ret > threshold else (-1 if ret < -threshold else 0)
        elif rule == "PRICE_BREAKOUT":
            breakout_level = float(generation_contract["breakout_level"])
            direction = (
                1
                if input_candles[-1].close > breakout_level
                else (-1 if input_candles[-1].close < breakout_level else 0)
            )
        elif rule == "RETURN_SIGN":
            direction = (
                1
                if input_candles[-1].close > input_candles[-1].open
                else (-1 if input_candles[-1].close < input_candles[-1].open else 0)
            )
        else:
            raise ValueError(f"unsupported rule in generation contract: {rule}")

        strength = float(generation_contract.get("strength", 1.0))
        horizon_ms = int(generation_contract.get("horizon_ms", 3_600_000))
        asset = str(generation_contract.get("asset", input_candles[-1].symbol))
        ci_raw = generation_contract.get("confidence_interval")
        confidence_interval = (
            tuple(ci_raw)
            if isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2
            else None
        )
        metadata = dict(generation_contract.get("metadata", {}))

        return InformationSignal(
            signal_id=signal_id,
            experiment_id=experiment_id,
            timestamp_ms=signal_timestamp_ms,
            asset=asset,
            direction=direction,
            strength=strength,
            confidence_interval=confidence_interval,
            horizon_ms=horizon_ms,
            metadata=metadata,
        )


class SyntheticFixedSignalProducer:
    """Synthetic fixed-direction signal producer for unit testing only.

    Prohibited for production or candidate market-derived signals.
    """

    producer_identity: str = "SYNTHETIC_FIXED_SIGNAL_PRODUCER"
    producer_version: str = "1.0.0"

    def replay_signal(
        self,
        *,
        signal_id: str,
        signal_timestamp_ms: int,
        experiment_id: str,
        input_candles: Sequence[Candle],
        generation_contract: Mapping[str, Any],
        authoritative_contract: SignalProducerContract | None = None,
    ) -> InformationSignal:
        if not input_candles:
            raise ValueError("synthetic signal replay requires non-empty material inputs")
        min_lookback = int(generation_contract.get("min_lookback_bars", 1))
        if len(input_candles) < min_lookback:
            raise ValueError(
                f"insufficient lookback for signal replay: required {min_lookback}, got {len(input_candles)}"
            )
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
        ci_raw = generation_contract.get("confidence_interval")
        confidence_interval = (
            tuple(ci_raw)
            if isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2
            else None
        )
        metadata = dict(generation_contract.get("metadata", {}))

        return InformationSignal(
            signal_id=signal_id,
            experiment_id=experiment_id,
            timestamp_ms=signal_timestamp_ms,
            asset=asset,
            direction=direction,
            strength=strength,
            confidence_interval=confidence_interval,
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
        authoritative_contract: SignalProducerContract | None = None,
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
        ci_raw = generation_contract.get("confidence_interval")
        confidence_interval = (
            tuple(ci_raw)
            if isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2
            else None
        )
        metadata = dict(generation_contract.get("metadata", {}))

        return InformationSignal(
            signal_id=signal_id,
            experiment_id=experiment_id,
            timestamp_ms=signal_timestamp_ms,
            asset=asset,
            direction=direction,
            strength=strength,
            confidence_interval=confidence_interval,
            horizon_ms=horizon_ms,
            metadata=metadata,
        )


# Register default canonical producers and contracts
SignalProducerRegistry._register_defaults()
