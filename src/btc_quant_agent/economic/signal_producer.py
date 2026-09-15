from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, ClassVar, Protocol, runtime_checkable

from ..domain import Candle
from ..research_contract.canonical import canonical_sha256, freeze_json, thaw_json
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
    parameters: Mapping[str, Any] = field(default_factory=dict)
    contract_hash: str = ""

    def __post_init__(self) -> None:
        frozen = freeze_json(self.parameters)
        if not isinstance(frozen, Mapping):
            raise TypeError("producer contract parameters must be a JSON object")
        object.__setattr__(self, "parameters", frozen)
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
            "parameters": thaw_json(self.parameters),
        }

    def to_dict(self) -> dict[str, Any]:
        payload = self.semantic_payload()
        payload["contract_hash"] = self.contract_hash
        return payload

    def to_versioned_identity(self) -> Any:
        from ..research_contract.models import VersionedIdentity

        return VersionedIdentity(
            logical_id=self.contract_id,
            version=self.version,
            content_sha256=self.contract_hash,
        )

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SignalProducerContract:
        return cls(
            contract_id=str(data["contract_id"]),
            version=str(data["version"]),
            producer_identity=str(data["producer_identity"]),
            producer_version=str(data["producer_version"]),
            rule=str(data["rule"]),
            parameters=dict(data.get("parameters", {})),
            contract_hash=str(data.get("contract_hash", "")),
        )


MATERIAL_INPUT_SELECTOR_TYPE = "LATEST_N_CONTIGUOUS_AVAILABLE_CLOSED"


@dataclass(frozen=True)
class MaterialInputSelectorPolicy:
    """Effective material-input selector resolved from an authoritative contract.

    The selector is the single owner of material-window authority: it is
    derived deterministically from the already-hashed rule/lookback semantics
    of the contract, never from caller-selected references or open times.
    """

    rule: str
    required_bars: int
    selector_type: str = MATERIAL_INPUT_SELECTOR_TYPE
    selector_sha256: str = ""

    def __post_init__(self) -> None:
        computed = canonical_sha256(
            {
                "rule": self.rule,
                "selector_type": self.selector_type,
                "required_bars": self.required_bars,
            }
        )
        if not self.selector_sha256:
            object.__setattr__(self, "selector_sha256", computed)
        elif self.selector_sha256 != computed:
            raise ValueError(
                f"selector_sha256 mismatch: declared {self.selector_sha256}, computed {computed}"
            )


def resolve_material_input_policy(
    contract: SignalProducerContract,
) -> MaterialInputSelectorPolicy:
    """Resolve the exact material-input selector from an authoritative contract.

    Fail-closed interpretation of the already-hashed rule/lookback semantics:

    - ``MOMENTUM_THRESHOLD`` uses exact ``lookback_bars`` when declared
      (``>= 1``); ``min_lookback_bars`` alone is an ambiguous floor and fails
      closed; when both are declared they must agree.
    - ``RETURN_SIGN`` / ``PRICE_BREAKOUT`` use exactly the latest 1 eligible
      candle; any declared lookback parameter must equal 1.
    - ``FIXED_DIRECTION`` stays a synthetic test-only positive control using
      exactly the latest 1 eligible candle.
    """
    rule = contract.rule
    params = contract.parameters
    lookback_raw = params.get("lookback_bars")
    min_lookback_raw = params.get("min_lookback_bars")

    def _int_parameter(name: str, raw: Any) -> int:
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                f"contract {contract.contract_id} parameter {name}={raw!r} is not an integer"
            ) from exc

    if rule == "MOMENTUM_THRESHOLD":
        if lookback_raw is not None:
            required_bars = _int_parameter("lookback_bars", lookback_raw)
            if (
                min_lookback_raw is not None
                and _int_parameter("min_lookback_bars", min_lookback_raw) != required_bars
            ):
                raise ValueError(
                    f"contract {contract.contract_id} lookback semantics disagree: "
                    f"lookback_bars={required_bars}, min_lookback_bars={min_lookback_raw}"
                )
        elif min_lookback_raw is not None:
            raise ValueError(
                f"ambiguous material-input selector for {contract.contract_id}: "
                "min_lookback_bars alone is a floor, not a complete selector; "
                "declare exact lookback_bars"
            )
        else:
            required_bars = 1
    elif rule in ("RETURN_SIGN", "PRICE_BREAKOUT", "FIXED_DIRECTION"):
        required_bars = 1
        for name, raw in (
            ("lookback_bars", lookback_raw),
            ("min_lookback_bars", min_lookback_raw),
        ):
            if raw is not None and _int_parameter(name, raw) != required_bars:
                raise ValueError(
                    f"contract {contract.contract_id} declares {name}={raw}; "
                    f"{rule} requires exactly {required_bars} latest eligible candle(s)"
                )
    else:
        raise ValueError(
            f"unsupported material-input selector rule for {contract.contract_id}: {rule}"
        )

    if required_bars < 1:
        raise ValueError(
            f"material-input selector for {contract.contract_id} requires at least 1 bar; "
            f"declared {required_bars}"
        )
    return MaterialInputSelectorPolicy(rule=rule, required_bars=required_bars)


def select_required_material_candles(
    contract: SignalProducerContract,
    candles: Sequence[Candle],
    signal_timestamp_ms: int,
) -> tuple[Candle, ...]:
    """Reconstruct the authoritative required material window from the frozen dataset.

    A candle is eligible at ``signal_timestamp_ms`` only when it is explicitly
    closed, carries an availability timestamp, and both its availability and
    close times precede the decision timestamp. The required set is exactly the
    latest ``N`` eligible contiguous rows under the resolved selector policy;
    a cadence gap, duplicate open times, or symbol/interval mixing inside the
    window fails closed instead of stepping backward around missing rows.
    Rows after the decision timestamp are simply ineligible.
    """
    policy = resolve_material_input_policy(contract)
    eligible = sorted(
        (
            candle
            for candle in candles
            if candle.closed is True
            and candle.available_at_ms is not None
            and candle.available_at_ms <= signal_timestamp_ms
            and candle.close_time_ms <= signal_timestamp_ms
        ),
        key=lambda candle: candle.open_time_ms,
    )
    if len(eligible) < policy.required_bars:
        raise ValueError(
            f"insufficient eligible material candles for {contract.contract_id}: "
            f"required the latest {policy.required_bars} eligible rows, found {len(eligible)}"
        )
    window = tuple(eligible[-policy.required_bars :])
    previous: Candle | None = None
    for candle in window:
        if previous is not None:
            if candle.open_time_ms <= previous.open_time_ms:
                raise ValueError(
                    f"required material window for {contract.contract_id} contains duplicate "
                    f"or non-increasing open times at {candle.open_time_ms}"
                )
            if candle.open_time_ms != previous.close_time_ms + 1:
                raise ValueError(
                    f"required material window for {contract.contract_id} has a cadence gap "
                    f"before {candle.open_time_ms}; the selector must not step backward "
                    "around missing material rows"
                )
        previous = candle
    if len({candle.symbol for candle in window}) != 1:
        raise ValueError(
            f"required material window for {contract.contract_id} crosses symbol boundaries"
        )
    if len({candle.interval for candle in window}) != 1:
        raise ValueError(
            f"required material window for {contract.contract_id} crosses interval boundaries"
        )
    return window


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
        recomputed = canonical_sha256(contract.semantic_payload())
        if recomputed != contract.contract_hash:
            raise ValueError(
                f"producer contract hash mismatch for {contract.contract_id}: "
                f"declared {contract.contract_hash}, computed {recomputed}"
            )
        existing = cls._contracts.get(contract.contract_id)
        if existing is not None:
            if canonical_sha256(existing.semantic_payload()) != recomputed:
                raise ValueError(
                    f"conflicting producer contract for existing id {contract.contract_id}: "
                    "authority under an existing id is never replaced"
                )
            return
        cls._contracts[contract.contract_id] = contract

    @classmethod
    def get_contract(
        cls, contract_id: str, contract_hash: str | None = None
    ) -> SignalProducerContract | None:
        contract = cls._contracts.get(contract_id)
        if contract is None:
            return None
        recomputed = canonical_sha256(contract.semantic_payload())
        if recomputed != contract.contract_hash:
            raise ValueError(
                f"stored producer contract {contract_id} content does not match its "
                "cached contract_hash; failing closed"
            )
        if contract_hash is not None and contract.contract_hash != contract_hash:
            return None
        return contract

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
        rule = (
            authoritative_contract.rule
            if authoritative_contract is not None
            else str(generation_contract.get("rule", ""))
        )
        if rule == "FIXED_DIRECTION":
            raise ValueError(
                "FIXED_DIRECTION is forbidden in CanonicalRuleSignalProducer; "
                "canonical candidate signals must derive direction from market inputs. "
                "Use SyntheticFixedSignalProducer for synthetic testing only."
            )
        if authoritative_contract is None:
            raise ValueError(
                "authoritative_contract is strictly required for CanonicalRuleSignalProducer replay"
            )

        rule = authoritative_contract.rule
        params = authoritative_contract.parameters
        if "rule" in generation_contract and generation_contract["rule"] != rule:
            raise ValueError(
                f"generation_contract rule mismatch: contract specifies {rule}, entry declared {generation_contract['rule']}"
            )

        # Defense in depth: the producer cannot prove latestness (it does not
        # possess the full dataset), but every locally available completeness
        # property of the required material window is enforced here.
        policy = resolve_material_input_policy(authoritative_contract)
        declared_min_lookback = generation_contract.get("min_lookback_bars")
        if declared_min_lookback is not None and int(declared_min_lookback) != policy.required_bars:
            raise ValueError(
                f"generation_contract min_lookback_bars mismatch: selector requires "
                f"{policy.required_bars}, entry declared {declared_min_lookback}"
            )
        declared_selector_type = generation_contract.get("material_input_selector_type")
        if (
            declared_selector_type is not None
            and declared_selector_type != MATERIAL_INPUT_SELECTOR_TYPE
        ):
            raise ValueError(
                f"generation_contract material_input_selector_type mismatch: selector requires "
                f"{MATERIAL_INPUT_SELECTOR_TYPE}, entry declared {declared_selector_type}"
            )
        declared_required_bars = generation_contract.get("material_input_required_bars")
        if declared_required_bars is not None and int(declared_required_bars) != policy.required_bars:
            raise ValueError(
                f"generation_contract material_input_required_bars mismatch: selector requires "
                f"{policy.required_bars}, entry declared {declared_required_bars}"
            )
        declared_selector_sha256 = generation_contract.get("material_input_selector_sha256")
        if (
            declared_selector_sha256 is not None
            and declared_selector_sha256 != policy.selector_sha256
        ):
            raise ValueError(
                "generation_contract material_input_selector_sha256 mismatch: entry declared a "
                "selector policy that disagrees with the authoritative contract"
            )

        if not input_candles:
            raise ValueError("signal replay requires non-empty material inputs")
        if len(input_candles) != policy.required_bars:
            raise ValueError(
                f"signal replay requires the exact required material window: "
                f"required {policy.required_bars}, got {len(input_candles)}"
            )

        # Validate order and integrity of input candles
        open_times = [c.open_time_ms for c in input_candles]
        if open_times != sorted(set(open_times)):
            raise ValueError("input candles must be ordered and non-overlapping")
        if len({c.symbol for c in input_candles}) != 1 or len({c.interval for c in input_candles}) != 1:
            raise ValueError("input candles must share one symbol and one interval")
        if policy.required_bars > 1:
            for previous, candle in zip(input_candles, input_candles[1:]):
                if candle.open_time_ms != previous.close_time_ms + 1:
                    raise ValueError(
                        "input candles must be contiguous required material rows"
                    )

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

        if rule == "FIXED_DIRECTION":
            raise ValueError(
                "FIXED_DIRECTION is forbidden in CanonicalRuleSignalProducer; "
                "market-derived candidate signals cannot use fixed direction. "
                "Use SyntheticFixedSignalProducer for synthetic testing only."
            )
        elif rule == "MOMENTUM_THRESHOLD":
            threshold = float(params.get("threshold_return_bps", 0.0)) / 10_000.0
            ret = (input_candles[-1].close - input_candles[0].open) / input_candles[0].open
            direction = 1 if ret > threshold else (-1 if ret < -threshold else 0)
        elif rule == "PRICE_BREAKOUT":
            if "breakout_level" not in params:
                raise ValueError("PRICE_BREAKOUT requires breakout_level in authoritative contract parameters")
            breakout_level = float(params["breakout_level"])
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
            raise ValueError(f"unsupported rule in authoritative contract: {rule}")

        strength = float(params.get("strength", 1.0))
        horizon_ms = int(params.get("horizon_ms", 3_600_000))
        asset = str(params.get("asset", input_candles[-1].symbol))
        ci_raw = params.get("confidence_interval")
        confidence_interval = (
            tuple(ci_raw)
            if isinstance(ci_raw, (list, tuple)) and len(ci_raw) == 2
            else None
        )
        metadata = thaw_json(params.get("metadata", {}))

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
