from __future__ import annotations

import json
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path
from typing import Any

from ..domain import Candle
from ..research_contract.canonical import canonical_sha256
from .execution_model import ExecutionModel, ExecutionResult
from .fee_model import FeeModel
from .funding import FundingModel, FundingSettlement
from .metrics import ReturnMetricsContract, TerminalPolicy, summarize_ledger
from .policy import OrderType
from .portfolio import Portfolio
from .trade_event import TradeAction, TradeEvent

RUNTIME_MARKET_DATA_SCHEMA_VERSION = "1.0.0"
PASSIVE_BENCHMARK_PROVENANCE_SCHEMA_VERSION = "1.0.0"
_TOLERANCE = 1e-8


def canonical_runtime_market_data(candles: Sequence[Candle]) -> list[dict[str, Any]]:
    """Return the versioned economic candle payload consumed by formal P6."""
    return [
        {
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
        }
        for item in candles
    ]


def runtime_market_data_sha256(candles: Sequence[Candle]) -> str:
    return canonical_sha256(
        {
            "schema_version": RUNTIME_MARKET_DATA_SCHEMA_VERSION,
            "candles": canonical_runtime_market_data(candles),
        }
    )


def bind_runtime_market_data(
    accounting: Mapping[str, Any], candles: Sequence[Candle]
) -> dict[str, Any]:
    result = dict(accounting)
    result["formal_runtime_market_data_schema_version"] = RUNTIME_MARKET_DATA_SCHEMA_VERSION
    result["formal_runtime_market_data"] = canonical_runtime_market_data(candles)
    result["formal_runtime_market_data_sha256"] = runtime_market_data_sha256(candles)
    return result


def validate_runtime_dataset_binding(
    dataset_evidence: Any,
    candles: Sequence[Candle],
    expected_product: str,
) -> None:
    if not candles:
        raise ValueError("formal runtime market data is empty")
    if any(item.symbol != expected_product for item in candles):
        raise ValueError("runtime candle instrument differs from preregistered product")
    path = dataset_evidence.local_path()
    if path is None:
        raise ValueError("formal dataset evidence must be local and replayable")
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError(f"formal dataset evidence is not replayable: {exc}") from exc
    if not isinstance(raw, list):
        raise TypeError("formal dataset evidence must be a canonical candle array")
    required = tuple(canonical_runtime_market_data(candles)[0])
    normalized: list[dict[str, Any]] = []
    for index, value in enumerate(raw):
        if not isinstance(value, Mapping):
            raise TypeError(f"dataset candle {index} must be a JSON object")
        missing = [field for field in required if field not in value]
        if missing:
            raise ValueError(
                "formal dataset evidence lacks runtime economic fields: " + ",".join(missing)
            )
        normalized.append({field: value[field] for field in required})
    expected = canonical_runtime_market_data(candles)
    if canonical_sha256(normalized) != canonical_sha256(expected):
        raise ValueError("runtime candle payload differs from content-hashed dataset evidence")


_CRITICAL_IDENTITY_FIELDS: tuple[str, ...] = (
    "experiment_revision_id",
    "protocol_hash",
    "input_contract",
    "dataset_evidence_id",
    "dataset_content_sha256",
    "interval_start_ms",
    "interval_end_ms",
    "observation_count",
    "product_scope",
    "initial_capital",
    "economic_policy",
    "cost_model",
    "execution_model",
    "funding_model",
    "comparison_contract_id",
    "comparison_contract_hash",
    "terminal_policy",
    "metrics_contract_id",
    "metrics_contract_hash",
    "code_revision",
)


def validate_formal_run_identity_binding(
    candidate_identity: Mapping[str, Any],
    trial_identity: Mapping[str, Any],
) -> None:
    if not isinstance(trial_identity, Mapping):
        raise TypeError("formal run identity must be a JSON object")
    for field in _CRITICAL_IDENTITY_FIELDS:
        if field not in candidate_identity:
            raise ValueError(f"candidate identity missing critical field: {field}")
        if field not in trial_identity:
            raise ValueError(f"trial identity missing critical field: {field}")
        expected = candidate_identity[field]
        observed = trial_identity[field]
        if field == "product_scope":
            if tuple(observed) != tuple(expected):
                raise ValueError(
                    "random trial identity product_scope mismatch with candidate: "
                    f"expected {expected!r}, got {observed!r}"
                )
        elif field == "initial_capital":
            if not math.isclose(
                _finite(observed, "trial initial_capital"),
                _finite(expected, "candidate initial_capital"),
                rel_tol=0.0,
                abs_tol=_TOLERANCE,
            ):
                raise ValueError(
                    "random trial identity initial_capital mismatch with candidate: "
                    f"expected {expected!r}, got {observed!r}"
                )
        elif observed != expected:
            raise ValueError(
                f"random trial identity {field} mismatch with candidate: "
                f"expected {expected!r}, got {observed!r}"
            )
    if trial_identity.get("completeness") != "COMPLETE":
        raise ValueError("random trial run is not COMPLETE")
    if trial_identity.get("funding_event_set_sha256") != candidate_identity.get(
        "funding_event_set_sha256"
    ):
        raise ValueError("random trial funding event set mismatch with candidate")


def _require_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{label} must be a JSON object")
    return value


def _require_list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a JSON array")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{label} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} must be finite")
    return result


def _close(observed: Any, expected: Any, label: str) -> None:
    if isinstance(expected, float):
        if observed is None and expected is None:
            return
        if isinstance(observed, bool) or not isinstance(observed, (int, float)):
            raise TypeError(f"{label} must be numeric")
        if not math.isclose(float(observed), expected, rel_tol=0.0, abs_tol=_TOLERANCE):
            raise ValueError(f"{label} disagrees with independent replay")
        return
    if isinstance(expected, list):
        observed_list = _require_list(observed, label)
        if len(observed_list) != len(expected):
            raise ValueError(f"{label} length disagrees with independent replay")
        for index, (actual_item, expected_item) in enumerate(
            zip(observed_list, expected, strict=True)
        ):
            _close(actual_item, expected_item, f"{label}[{index}]")
        return
    if isinstance(expected, dict):
        observed_mapping = _require_mapping(observed, label)
        if set(observed_mapping) != set(expected):
            raise ValueError(f"{label} keys disagree with independent replay")
        for key, expected_item in expected.items():
            _close(observed_mapping[key], expected_item, f"{label}.{key}")
        return
    if observed != expected:
        raise ValueError(f"{label} disagrees with independent replay")


def _candles_from_accounting(
    accounting: Mapping[str, Any], expected_product: str
) -> tuple[Candle, ...]:
    if accounting.get("formal_runtime_market_data_schema_version") != (
        RUNTIME_MARKET_DATA_SCHEMA_VERSION
    ):
        raise ValueError("formal runtime market-data schema is missing or unsupported")
    values = _require_list(
        accounting.get("formal_runtime_market_data"), "formal_runtime_market_data"
    )
    candles: list[Candle] = []
    expected_keys = {
        "symbol",
        "interval",
        "open_time_ms",
        "close_time_ms",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "quote_volume",
    }
    for index, value in enumerate(values):
        item = _require_mapping(value, f"formal_runtime_market_data[{index}]")
        if set(item) != expected_keys:
            raise ValueError("formal runtime candle schema mismatch")
        candle = Candle(
            symbol=str(item["symbol"]),
            interval=str(item["interval"]),
            open_time_ms=int(item["open_time_ms"]),
            close_time_ms=int(item["close_time_ms"]),
            open=_finite(item["open"], "open"),
            high=_finite(item["high"], "high"),
            low=_finite(item["low"], "low"),
            close=_finite(item["close"], "close"),
            volume=_finite(item["volume"], "volume"),
            quote_volume=_finite(item["quote_volume"], "quote_volume"),
        )
        if candle.symbol != expected_product:
            raise ValueError("persisted runtime instrument differs from product scope")
        candles.append(candle)
    if not candles:
        raise ValueError("persisted runtime candle payload is empty")
    observed_hash = accounting.get("formal_runtime_market_data_sha256")
    expected_hash = runtime_market_data_sha256(candles)
    if observed_hash != expected_hash:
        raise ValueError("persisted runtime market-data hash mismatch")
    return tuple(candles)


def _events_from_accounting(accounting: Mapping[str, Any], product: str) -> tuple[TradeEvent, ...]:
    values = _require_list(accounting.get("trade_events"), "trade_events")
    events: list[TradeEvent] = []
    for index, value in enumerate(values):
        event = TradeEvent.from_dict(dict(_require_mapping(value, f"trade_events[{index}]")))
        if event.metadata.get("asset") != product:
            raise ValueError("trade event asset differs from formal product")
        events.append(event)
    return tuple(events)


def _curve_and_notional_from_ledger(
    *,
    initial_cash: float,
    events: Sequence[TradeEvent],
    candles: Sequence[Candle],
    observed_curve: Sequence[Any],
    product: str,
) -> tuple[tuple[tuple[int, float], ...], tuple[tuple[int, float], ...], tuple[float, float]]:
    if len(observed_curve) != len(candles):
        raise ValueError("equity curve length differs from runtime candle sequence")
    curve: list[tuple[int, float]] = []
    notional: list[tuple[int, float]] = []
    selected_count = 0
    peak = initial_cash
    max_dd = 0.0
    max_dd_pct = 0.0
    close_times = {item.close_time_ms for item in candles}

    def update_risk(value: float) -> None:
        nonlocal peak, max_dd, max_dd_pct
        peak = max(peak, value)
        drawdown = peak - value
        max_dd = max(max_dd, drawdown)
        max_dd_pct = max(max_dd_pct, drawdown / peak if peak > 0 else 0.0)

    for candle, raw_point in zip(candles, observed_curve, strict=True):
        point = _require_list(raw_point, "equity_curve point")
        if len(point) != 2 or point[0] != candle.close_time_ms:
            raise ValueError("equity curve timestamps differ from runtime candle closes")
        observed_equity = _finite(point[1], "equity_curve equity")
        minimum = sum(event.timestamp_ms < candle.close_time_ms for event in events)
        maximum = sum(event.timestamp_ms <= candle.close_time_ms for event in events)
        start = max(selected_count, minimum)
        matches: list[tuple[int, Portfolio, float]] = []
        for count in range(start, maximum + 1):
            portfolio = Portfolio.from_events(initial_cash, events[:count])
            equity = portfolio.total_equity({product: candle.close})
            if math.isclose(equity, observed_equity, rel_tol=0.0, abs_tol=_TOLERANCE):
                matches.append((count, portfolio, equity))
        if not matches:
            raise ValueError("equity curve cannot be reconstructed from ledger and market data")
        # Multiple same-timestamp prefixes can mark to the same equity (for example,
        # a zero-cost close filled at the candle close).  The simulator records its
        # close mark after all close-time ledger effects, so prefer the latest
        # reconstructable prefix rather than silently treating a completed exit as
        # still open.  Prefixes that include a next-bar event at the same timestamp
        # remain excluded when they change the observed close equity.
        count, portfolio, equity = matches[-1]
        for event_index in range(selected_count, count):
            event = events[event_index]
            if event.action is TradeAction.FUNDING_SETTLEMENT and event.timestamp_ms in close_times:
                continue
            state = Portfolio.from_events(initial_cash, events[: event_index + 1])
            update_risk(state.total_equity({product: event.price}))
        selected_count = count
        update_risk(equity)
        curve.append((candle.close_time_ms, equity))
        notional.append(
            (
                candle.close_time_ms,
                abs(portfolio.get_position_quantity(product)) * candle.close,
            )
        )
    if selected_count != len(events):
        raise ValueError("ledger contains events after the declared economic interval")
    return tuple(curve), tuple(notional), (max_dd, max_dd_pct)


def _metrics_contract(value: Mapping[str, Any]) -> ReturnMetricsContract:
    return ReturnMetricsContract(
        contract_name=str(value["contract_name"]),
        sampling_rule=str(value["sampling_rule"]),
        cadence_ms=int(value["cadence_ms"]),
        spacing_tolerance_ms=int(value["spacing_tolerance_ms"]),
        annualization_rule=str(value.get("annualization_rule", "CALENDAR_365D")),
        risk_free_rate_per_period=float(value.get("risk_free_rate_per_period", 0.0)),
        schema_version=str(value.get("schema_version", "1.0.0")),
    )


def verify_formal_accounting(
    accounting: Mapping[str, Any],
    *,
    product: str,
    initial_cash: float,
    interval_start_ms: int,
    interval_end_ms: int,
    terminal_policy: str | TerminalPolicy,
    metrics_contract: Mapping[str, Any] | ReturnMetricsContract,
) -> None:
    candles = _candles_from_accounting(accounting, product)
    if candles[0].open_time_ms != interval_start_ms or candles[-1].close_time_ms != interval_end_ms:
        raise ValueError("persisted runtime market data differs from formal interval")
    if any(item.interval != candles[0].interval for item in candles):
        raise ValueError("formal runtime candle interval is not stable")
    events = _events_from_accounting(accounting, product)
    observed_curve = _require_list(accounting.get("equity_curve"), "equity_curve")
    curve, notional, drawdown = _curve_and_notional_from_ledger(
        initial_cash=initial_cash,
        events=events,
        candles=candles,
        observed_curve=observed_curve,
        product=product,
    )
    contract = (
        metrics_contract
        if isinstance(metrics_contract, ReturnMetricsContract)
        else _metrics_contract(metrics_contract)
    )
    pending = accounting.get("pending_order_count")
    if type(pending) is not int or pending != 0:
        raise ValueError("formal COMPLETE accounting requires zero pending orders")
    replay = summarize_ledger(
        initial_cash=initial_cash,
        events=events,
        equity_curve=curve,
        final_asset=product,
        final_mark_price=candles[-1].close,
        interval_start_ms=interval_start_ms,
        interval_end_ms=interval_end_ms,
        notional_curve=notional,
        terminal_policy=TerminalPolicy(terminal_policy),
        metrics_contract=contract,
        pending_order_count=pending,
        max_drawdown_override=drawdown,
    ).to_dict()
    for key, expected in replay.items():
        if key not in accounting:
            raise ValueError(f"formal accounting is missing replay field: {key}")
        _close(accounting[key], expected, f"accounting.{key}")


class PassiveBenchmarkReplayError(ValueError):
    """The preregistered passive policy cannot produce a complete replay."""

    def __init__(self, reason_code: str) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code)


def _execution_model_payload(model: ExecutionModel) -> dict[str, Any]:
    payload = {
        "decision_latency_ms": model.decision_latency_ms,
        "exchange_latency_ms": model.exchange_latency_ms,
        "limit_fill_prob_on_touch": model.limit_fill_prob_on_touch,
        "fee_model_sha256": canonical_sha256(asdict(model.fee_model)),
    }
    if model.order_submission_latency_ms != 0:
        payload["order_submission_latency_ms"] = model.order_submission_latency_ms
    return payload


def _passive_policy_payload(
    candles: Sequence[Candle], terminal_policy: TerminalPolicy, initial_cash: float
) -> dict[str, Any]:
    return {
        "schema_version": PASSIVE_BENCHMARK_PROVENANCE_SCHEMA_VERSION,
        "position_side": "LONG",
        "entry_order_type": OrderType.MARKET.value,
        "entry_signal_timestamp_ms": candles[0].open_time_ms,
        "entry_quantity_rule": "INITIAL_CAPITAL_DIVIDED_BY_FIRST_CANDLE_OPEN",
        "entry_max_fill_notional": initial_cash,
        "holding_rule": "HOLD_UNTIL_TERMINAL_POLICY",
        "funding_fill_tie_break": "FUNDING_BEFORE_FILL",
        "exit_order_type": (
            OrderType.MARKET.value if terminal_policy is TerminalPolicy.REQUIRE_FLAT else None
        ),
        "exit_signal_timestamp_ms": (
            candles[-2].close_time_ms
            if terminal_policy is TerminalPolicy.REQUIRE_FLAT and len(candles) >= 2
            else None
        ),
    }


def _execution_metadata(result: ExecutionResult) -> dict[str, Any]:
    return {**dict(result.metadata or {}), "slippage_usdt": result.slippage_usdt}


def build_passive_benchmark_accounting(
    *,
    candidate_identity: Mapping[str, Any],
    product: str,
    initial_cash: float,
    candles: Sequence[Candle],
    fee_model: FeeModel,
    execution_model: ExecutionModel,
    funding_model: FundingModel,
    funding_events: Sequence[FundingSettlement],
    interval_start_ms: int,
    interval_end_ms: int,
    terminal_policy: TerminalPolicy,
    metrics_contract: ReturnMetricsContract,
) -> dict[str, Any]:
    """Replay the one-position passive policy and persist every replay preimage."""
    terminal_policy = TerminalPolicy(terminal_policy)
    if not candles:
        raise PassiveBenchmarkReplayError("PASSIVE_RUNTIME_DATA_EMPTY")
    if any(item.symbol != product for item in candles):
        raise PassiveBenchmarkReplayError("PASSIVE_PRODUCT_SCOPE_MISMATCH")
    if any(
        item.timestamp_ms < interval_start_ms or item.timestamp_ms > interval_end_ms
        for item in funding_events
    ):
        raise PassiveBenchmarkReplayError("PASSIVE_FUNDING_EVENT_OUTSIDE_INTERVAL")
    if execution_model.fee_model != fee_model:
        raise PassiveBenchmarkReplayError("PASSIVE_EXECUTION_COST_MODEL_MISMATCH")

    passive_policy = _passive_policy_payload(candles, terminal_policy, initial_cash)
    desired_quantity = initial_cash / candles[0].open
    entry = execution_model.simulate_order(
        signal_timestamp_ms=candles[0].open_time_ms,
        side=1,
        desired_quantity=desired_quantity,
        order_type=OrderType.MARKET,
        future_candles=candles,
        max_fill_notional=initial_cash,
    )
    if not entry.is_filled:
        raise PassiveBenchmarkReplayError("PASSIVE_ENTRY_UNFILLED")

    exit_result: ExecutionResult | None = None
    if terminal_policy is TerminalPolicy.REQUIRE_FLAT:
        if len(candles) < 2:
            raise PassiveBenchmarkReplayError("NO_EXECUTABLE_TERMINAL_EXIT")
        exit_result = execution_model.simulate_order(
            signal_timestamp_ms=candles[-2].close_time_ms,
            side=-1,
            desired_quantity=entry.filled_quantity,
            order_type=OrderType.MARKET,
            future_candles=candles[-1:],
        )
        if not exit_result.is_filled or exit_result.fill_timestamp_ms > candles[-1].close_time_ms:
            raise PassiveBenchmarkReplayError("TERMINAL_EXIT_UNFILLED")

    portfolio = Portfolio(initial_cash)
    funding = sorted(funding_events, key=lambda item: item.timestamp_ms)
    funding_index = 0
    entry_applied = False
    exit_applied = False
    equity_curve: list[tuple[int, float]] = []
    notional_curve: list[tuple[int, float]] = []
    for bar in candles:
        scheduled: list[tuple[int, int, str, Any]] = []
        while (
            funding_index < len(funding)
            and funding[funding_index].timestamp_ms <= bar.close_time_ms
        ):
            settlement = funding[funding_index]
            funding_index += 1
            scheduled.append((settlement.timestamp_ms, 0, "funding", settlement))
        if not entry_applied and entry.fill_timestamp_ms <= bar.close_time_ms:
            scheduled.append((entry.fill_timestamp_ms, 1, "entry", entry))
        if (
            exit_result is not None
            and not exit_applied
            and exit_result.fill_timestamp_ms <= bar.close_time_ms
        ):
            scheduled.append((exit_result.fill_timestamp_ms, 1, "exit", exit_result))
        for _, _, kind, item in sorted(scheduled, key=lambda value: (value[0], value[1])):
            if kind == "funding":
                settlement = item
                quantity = portfolio.get_position_quantity(product)
                if quantity != 0.0:
                    cashflow = funding_model.calculate_cashflow(
                        quantity,
                        settlement.mark_price,
                        settlement.funding_rate,
                    )
                    portfolio.apply_funding(
                        settlement.timestamp_ms,
                        product,
                        cashflow,
                        settlement.mark_price,
                    )
            elif kind == "entry" and not entry_applied:
                portfolio.apply_trade(
                    entry.fill_timestamp_ms,
                    TradeAction.OPEN_LONG,
                    product,
                    entry.fill_price,
                    entry.filled_quantity,
                    entry.fee_usdt,
                    trade_id="PASSIVE_ENTRY",
                    observation_timestamp_ms=entry.observation_timestamp_ms,
                    decision_timestamp_ms=entry.decision_timestamp_ms,
                    order_timestamp_ms=entry.order_timestamp_ms,
                    settlement_timestamp_ms=entry.settlement_timestamp_ms,
                    metadata=_execution_metadata(entry),
                )
                entry_applied = True
            elif kind == "exit" and exit_result is not None and not exit_applied:
                portfolio.apply_trade(
                    exit_result.fill_timestamp_ms,
                    TradeAction.CLOSE_LONG,
                    product,
                    exit_result.fill_price,
                    exit_result.filled_quantity,
                    exit_result.fee_usdt,
                    trade_id="PASSIVE_EXIT",
                    observation_timestamp_ms=exit_result.observation_timestamp_ms,
                    decision_timestamp_ms=exit_result.decision_timestamp_ms,
                    order_timestamp_ms=exit_result.order_timestamp_ms,
                    settlement_timestamp_ms=exit_result.settlement_timestamp_ms,
                    metadata=_execution_metadata(exit_result),
                )
                exit_applied = True
        equity = portfolio.total_equity({product: bar.close})
        equity_curve.append((bar.close_time_ms, equity))
        notional_curve.append(
            (
                bar.close_time_ms,
                abs(portfolio.get_position_quantity(product)) * bar.close,
            )
        )

    summary = summarize_ledger(
        initial_cash=initial_cash,
        events=portfolio.trade_history,
        equity_curve=equity_curve,
        final_asset=product,
        final_mark_price=candles[-1].close,
        interval_start_ms=interval_start_ms,
        interval_end_ms=interval_end_ms,
        notional_curve=notional_curve,
        terminal_policy=terminal_policy,
        metrics_contract=metrics_contract,
    )
    if not summary.formal_complete:
        raise PassiveBenchmarkReplayError("PASSIVE_ACCOUNTING_INCOMPLETE")
    identity = dict(candidate_identity)
    identity["signal_set_sha256"] = canonical_sha256(passive_policy)
    identity["completeness"] = summary.completeness.value
    funding_payload = [asdict(item) for item in funding]
    provenance = {
        "schema_version": PASSIVE_BENCHMARK_PROVENANCE_SCHEMA_VERSION,
        "passive_policy": passive_policy,
        "cost_model": asdict(fee_model),
        "execution_model": _execution_model_payload(execution_model),
        "funding_model": asdict(funding_model),
        "funding_events": funding_payload,
        "terminal_policy": terminal_policy.value,
        "metrics_contract": metrics_contract.to_dict(),
    }
    accounting = bind_runtime_market_data(summary.to_dict(), candles)
    accounting["formal_run_identity"] = identity
    accounting["passive_provenance"] = provenance
    return accounting


def _content_hash(value: Any, label: str) -> str:
    identity = _require_mapping(value, label)
    if set(identity) != {"logical_id", "version", "content_sha256"}:
        raise ValueError(f"{label} schema mismatch")
    content_hash = identity.get("content_sha256")
    if not isinstance(content_hash, str):
        raise TypeError(f"{label} content_sha256 must be text")
    return content_hash


def _funding_events_from_provenance(value: Any) -> tuple[FundingSettlement, ...]:
    records = _require_list(value, "passive funding events")
    result: list[FundingSettlement] = []
    expected_keys = {"timestamp_ms", "funding_rate", "mark_price"}
    for index, raw in enumerate(records):
        item = _require_mapping(raw, f"passive funding event {index}")
        if set(item) != expected_keys:
            raise ValueError("passive funding-event schema mismatch")
        timestamp = item["timestamp_ms"]
        if type(timestamp) is not int:
            raise TypeError("passive funding timestamp must be an integer")
        rate = _finite(item["funding_rate"], "passive funding rate")
        mark = _finite(item["mark_price"], "passive funding mark")
        if timestamp <= 0 or mark <= 0:
            raise ValueError("passive funding timestamp and mark must be positive")
        result.append(FundingSettlement(timestamp, rate, mark))
    if any(
        result[index].timestamp_ms < result[index - 1].timestamp_ms
        for index in range(1, len(result))
    ):
        raise ValueError("passive funding events are not canonically ordered")
    return tuple(result)


def validate_passive_benchmark_provenance(
    passive_value: Mapping[str, Any],
    *,
    comparison: Mapping[str, Any],
    candidate_identity: Mapping[str, Any],
    dataset_evidence: Any,
) -> Mapping[str, Any]:
    """Independently reconstruct and compare a persisted passive benchmark."""
    if passive_value.get("benchmark_kind") != "PASSIVE_PERPETUAL":
        raise ValueError("passive benchmark kind mismatch")
    if passive_value.get("vehicle") != comparison.get("benchmark_vehicle"):
        raise ValueError("passive benchmark vehicle mismatch")
    if passive_value.get("trial_id") is not None or passive_value.get("seed") is not None:
        raise ValueError("passive benchmark cannot carry random-trial identity")
    if passive_value.get("run_result_id") is not None:
        raise ValueError("passive benchmark cannot claim a candidate run result")

    scope = _require_list(comparison.get("product_scope"), "product_scope")
    if len(scope) != 1:
        raise ValueError("formal passive benchmark supports exactly one product")
    product = str(scope[0])
    accounting = _require_mapping(passive_value.get("accounting"), "passive accounting")
    identity = _require_mapping(
        accounting.get("formal_run_identity"), "passive formal run identity"
    )
    validate_formal_run_identity_binding(candidate_identity, identity)

    data_interval = _require_mapping(comparison.get("data_interval"), "data interval")
    expected_identity = {
        "dataset_evidence_id": data_interval.get("dataset_evidence_id"),
        "dataset_content_sha256": data_interval.get("dataset_content_sha256"),
        "interval_start_ms": data_interval.get("start_ms"),
        "interval_end_ms": data_interval.get("end_ms"),
        "observation_count": data_interval.get("observation_count"),
        "product_scope": scope,
        "initial_capital": comparison.get("initial_capital"),
        "economic_policy": comparison.get("candidate_policy"),
        "cost_model": comparison.get("cost_model"),
        "execution_model": comparison.get("execution_model"),
        "funding_model": comparison.get("funding_model"),
        "comparison_contract_id": candidate_identity.get("comparison_contract_id"),
        "comparison_contract_hash": candidate_identity.get("comparison_contract_hash"),
        "terminal_policy": comparison.get("terminal_policy"),
        "metrics_contract_id": candidate_identity.get("metrics_contract_id"),
        "metrics_contract_hash": candidate_identity.get("metrics_contract_hash"),
    }
    for field, expected in expected_identity.items():
        _close(identity.get(field), expected, f"passive identity.{field}")
    if getattr(dataset_evidence, "evidence_id", None) != identity.get(
        "dataset_evidence_id"
    ) or getattr(dataset_evidence, "content_sha256", None) != identity.get(
        "dataset_content_sha256"
    ):
        raise ValueError("passive dataset evidence identity/hash mismatch")
    if getattr(dataset_evidence, "evidence_id", None) != identity.get(
        "dataset_evidence_id"
    ) or getattr(dataset_evidence, "content_sha256", None) != identity.get(
        "dataset_content_sha256"
    ):
        raise ValueError("passive dataset evidence identity/hash mismatch")

    candles = _candles_from_accounting(accounting, product)
    if len(candles) != int(data_interval["observation_count"]):
        raise ValueError("passive runtime observation count mismatch")
    validate_runtime_dataset_binding(dataset_evidence, candles, product)

    provenance = _require_mapping(accounting.get("passive_provenance"), "passive provenance")
    expected_provenance_keys = {
        "schema_version",
        "passive_policy",
        "cost_model",
        "execution_model",
        "funding_model",
        "funding_events",
        "terminal_policy",
        "metrics_contract",
    }
    if set(provenance) != expected_provenance_keys:
        raise ValueError("passive provenance schema mismatch")
    if provenance.get("schema_version") != PASSIVE_BENCHMARK_PROVENANCE_SCHEMA_VERSION:
        raise ValueError("passive provenance schema version mismatch")

    cost_payload = dict(_require_mapping(provenance.get("cost_model"), "cost model"))
    cost_hash = canonical_sha256(cost_payload)
    if cost_hash != _content_hash(identity.get("cost_model"), "cost identity"):
        raise ValueError("passive cost model preimage does not match declared identity")
    fee_model = FeeModel(**cost_payload)

    execution_payload = dict(_require_mapping(provenance.get("execution_model"), "execution model"))
    expected_execution_keys = {
        "decision_latency_ms",
        "exchange_latency_ms",
        "limit_fill_prob_on_touch",
        "fee_model_sha256",
    }
    if "order_submission_latency_ms" in execution_payload:
        expected_execution_keys.add("order_submission_latency_ms")
    if set(execution_payload) != expected_execution_keys:
        raise ValueError("passive execution-model schema mismatch")
    if execution_payload.get("fee_model_sha256") != cost_hash:
        raise ValueError("passive execution model is not bound to the cost model")
    if canonical_sha256(execution_payload) != _content_hash(
        identity.get("execution_model"), "execution identity"
    ):
        raise ValueError("passive execution model preimage does not match declared identity")
    execution_model = ExecutionModel(
        fee_model=fee_model,
        decision_latency_ms=execution_payload["decision_latency_ms"],
        exchange_latency_ms=execution_payload["exchange_latency_ms"],
        limit_fill_prob_on_touch=execution_payload["limit_fill_prob_on_touch"],
        order_submission_latency_ms=execution_payload.get("order_submission_latency_ms", 0),
    )

    funding_payload = dict(_require_mapping(provenance.get("funding_model"), "funding model"))
    if canonical_sha256(funding_payload) != _content_hash(
        identity.get("funding_model"), "funding identity"
    ):
        raise ValueError("passive funding model preimage does not match declared identity")
    funding_model = FundingModel(**funding_payload)
    funding_events = _funding_events_from_provenance(provenance.get("funding_events"))
    funding_event_payload = [asdict(item) for item in funding_events]
    if canonical_sha256(funding_event_payload) != identity.get("funding_event_set_sha256"):
        raise ValueError("passive funding-event set differs from candidate run")

    terminal_policy = TerminalPolicy(str(provenance.get("terminal_policy")))
    if terminal_policy.value != comparison.get("terminal_policy"):
        raise ValueError("passive terminal policy differs from comparison contract")
    metrics_payload = dict(_require_mapping(provenance.get("metrics_contract"), "metrics contract"))
    _close(metrics_payload, comparison.get("metrics_contract"), "passive metrics contract")
    metrics_contract = _metrics_contract(metrics_payload)
    if metrics_contract.contract_hash != identity.get("metrics_contract_hash"):
        raise ValueError("passive metrics contract does not match declared identity")

    initial_cash = _finite(comparison.get("initial_capital"), "initial capital")
    expected_policy = _passive_policy_payload(candles, terminal_policy, initial_cash)
    _close(provenance.get("passive_policy"), expected_policy, "passive policy")
    if canonical_sha256(expected_policy) != identity.get("signal_set_sha256"):
        raise ValueError("passive policy identity mismatch")

    expected_accounting = build_passive_benchmark_accounting(
        candidate_identity=candidate_identity,
        product=product,
        initial_cash=initial_cash,
        candles=candles,
        fee_model=fee_model,
        execution_model=execution_model,
        funding_model=funding_model,
        funding_events=funding_events,
        interval_start_ms=int(data_interval["start_ms"]),
        interval_end_ms=int(data_interval["end_ms"]),
        terminal_policy=terminal_policy,
        metrics_contract=metrics_contract,
    )
    _close(accounting, expected_accounting, "passive accounting provenance")
    verify_formal_accounting(
        accounting,
        product=product,
        initial_cash=initial_cash,
        interval_start_ms=int(data_interval["start_ms"]),
        interval_end_ms=int(data_interval["end_ms"]),
        terminal_policy=terminal_policy,
        metrics_contract=metrics_contract,
    )

    expected_diagnostics = {
        "same_interval": True,
        "same_cost_model": True,
        "same_execution_model": True,
        "same_funding_model": True,
        "same_terminal_policy": True,
    }
    _close(
        passive_value.get("matching_diagnostics"),
        expected_diagnostics,
        "passive matching diagnostics",
    )
    if passive_value.get("comparable") is not True:
        raise ValueError("passive benchmark comparable flag disagrees with replay")
    return accounting


def _relative_error(observed: float, target: float) -> float | None:
    if target == 0.0:
        return 0.0 if observed == 0.0 else None
    return abs(observed - target) / abs(target)


def _mean_holding(accounting: Mapping[str, Any]) -> float:
    trips = _require_list(accounting.get("round_trips"), "round_trips")
    values = [
        _finite(_require_mapping(item, "round_trip")["holding_duration_ms"], "holding")
        for item in trips
    ]
    return sum(values) / len(values) if values else 0.0


def recompute_matching_diagnostics(
    candidate: Mapping[str, Any], trial: Mapping[str, Any], rules: Mapping[str, Any]
) -> tuple[dict[str, Any], bool]:
    def directions(accounting: Mapping[str, Any]) -> tuple[int, int, int]:
        events = _require_list(accounting.get("trade_events"), "trade_events")
        long_count = sum(
            _require_mapping(item, "event").get("action") == "OPEN_LONG" for item in events
        )
        short_count = sum(
            _require_mapping(item, "event").get("action") == "OPEN_SHORT" for item in events
        )
        return long_count + short_count, long_count, short_count

    candidate_count, candidate_long, candidate_short = directions(candidate)
    trial_count, trial_long, trial_short = directions(trial)
    count_pass = not bool(rules.get("match_entry_count")) or trial_count == candidate_count
    direction_pass = not bool(rules.get("match_direction_counts")) or (
        trial_long == candidate_long and trial_short == candidate_short
    )
    candidate_holding = _mean_holding(candidate)
    trial_holding = _mean_holding(trial)
    holding_error = _relative_error(trial_holding, candidate_holding)
    holding_limit = rules.get("maximum_mean_holding_error_fraction")
    holding_pass = holding_limit is None or (
        holding_error is not None and holding_error <= float(holding_limit)
    )
    exposure_error = abs(
        _finite(trial.get("time_exposure_fraction"), "trial exposure")
        - _finite(candidate.get("time_exposure_fraction"), "candidate exposure")
    )
    exposure_limit = rules.get("maximum_time_exposure_error_fraction")
    exposure_pass = exposure_limit is None or exposure_error <= float(exposure_limit)
    notional_error = _relative_error(
        _finite(trial.get("average_notional_exposure_usdt"), "trial notional"),
        _finite(candidate.get("average_notional_exposure_usdt"), "candidate notional"),
    )
    notional_limit = rules.get("maximum_average_notional_error_fraction")
    notional_pass = notional_limit is None or (
        notional_error is not None and notional_error <= float(notional_limit)
    )
    complete = trial.get("completeness") == "COMPLETE"
    candidate_id = candidate.get("formal_run_identity")
    trial_id = trial.get("formal_run_identity")
    if isinstance(candidate_id, Mapping) and isinstance(trial_id, Mapping):
        same_policy_cost_execution_funding = bool(
            candidate_id.get("economic_policy") == trial_id.get("economic_policy")
            and candidate_id.get("cost_model") == trial_id.get("cost_model")
            and candidate_id.get("execution_model") == trial_id.get("execution_model")
            and candidate_id.get("funding_model") == trial_id.get("funding_model")
        )
        same_interval = bool(
            candidate_id.get("interval_start_ms") == trial_id.get("interval_start_ms")
            and candidate_id.get("interval_end_ms") == trial_id.get("interval_end_ms")
            and candidate_id.get("observation_count") == trial_id.get("observation_count")
        )
        same_terminal_policy = bool(
            candidate_id.get("terminal_policy") == trial_id.get("terminal_policy")
        )
    else:
        same_policy_cost_execution_funding = False
        same_interval = False
        same_terminal_policy = False
    diagnostics = {
        "candidate_entry_count": candidate_count,
        "trial_entry_count": trial_count,
        "entry_count_match": count_pass,
        "candidate_long_count": candidate_long,
        "candidate_short_count": candidate_short,
        "trial_long_count": trial_long,
        "trial_short_count": trial_short,
        "direction_count_match": direction_pass,
        "candidate_mean_holding_ms": candidate_holding,
        "trial_mean_holding_ms": trial_holding,
        "mean_holding_error_fraction": holding_error,
        "mean_holding_match": holding_pass,
        "time_exposure_error_fraction": exposure_error,
        "time_exposure_match": exposure_pass,
        "average_notional_error_fraction": notional_error,
        "average_notional_match": notional_pass,
        "same_policy_cost_execution_funding": same_policy_cost_execution_funding,
        "same_interval": same_interval,
        "same_terminal_policy": same_terminal_policy,
        "trial_complete": complete,
    }
    return diagnostics, all(
        (
            count_pass,
            direction_pass,
            holding_pass,
            exposure_pass,
            notional_pass,
            same_policy_cost_execution_funding,
            same_interval,
            same_terminal_policy,
            complete,
        )
    )


def _compare(observed: float, operator: str, threshold: float) -> bool:
    if operator == ">":
        return observed > threshold
    if operator == ">=":
        return observed >= threshold
    if operator == "<":
        return observed < threshold
    if operator == "<=":
        return observed <= threshold
    raise ValueError("unsupported gate operator")


def _quantile(values: Sequence[float], probability: float) -> float | None:
    if not values or not 0.0 <= probability <= 1.0:
        return None
    ordered = sorted(values)
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1.0 - weight) + ordered[upper] * weight


def _gate_payload(
    hurdle: Mapping[str, Any],
    candidate: Mapping[str, Any],
    cash: Mapping[str, Any] | None,
    passive: Mapping[str, Any] | None,
    random_trials: Sequence[Mapping[str, Any]],
    random_comparable: bool,
) -> dict[str, Any]:
    metric = str(hurdle["metric"])
    candidate_return = _finite(candidate.get("net_return_pct"), "candidate return")
    observed: float | None
    if metric == "NET_RETURN_PCT":
        observed = candidate_return
    elif metric == "MAX_DRAWDOWN_PCT":
        observed = _finite(candidate.get("max_drawdown_pct"), "candidate drawdown")
    elif metric == "PROFIT_FACTOR":
        value = candidate.get("profit_factor")
        observed = _finite(value, "candidate profit factor") if value is not None else None
    elif metric == "SHARPE_RATIO":
        value = candidate.get("sharpe_ratio")
        observed = _finite(value, "candidate sharpe") if value is not None else None
    elif metric == "EXCESS_RETURN_VS_CASH":
        observed = (
            None
            if cash is None
            else candidate_return - _finite(cash.get("net_return_pct"), "cash return")
        )
    elif metric == "EXCESS_RETURN_VS_PASSIVE":
        observed = (
            None
            if passive is None
            else candidate_return - _finite(passive.get("net_return_pct"), "passive return")
        )
    elif metric == "EXCESS_RETURN_VS_RANDOM_QUANTILE":
        probability = hurdle.get("random_quantile")
        quantile = (
            _quantile(
                [_finite(item.get("net_return_pct"), "random return") for item in random_trials],
                float(probability),
            )
            if random_comparable and probability is not None
            else None
        )
        observed = candidate_return - quantile if quantile is not None else None
    else:
        raise ValueError(f"unsupported economic hurdle metric: {metric}")
    threshold = _finite(hurdle.get("threshold"), "hurdle threshold")
    if observed is None or not math.isfinite(observed):
        return {
            "gate_id": hurdle["gate_id"],
            "metric": metric,
            "observed_value": None,
            "operator": hurdle["operator"],
            "hurdle": threshold,
            "testable": False,
            "passed": None,
            "reason_code": "METRIC_UNAVAILABLE",
        }
    passed = _compare(observed, str(hurdle["operator"]), threshold)
    return {
        "gate_id": hurdle["gate_id"],
        "metric": metric,
        "observed_value": observed,
        "operator": hurdle["operator"],
        "hurdle": threshold,
        "testable": True,
        "passed": passed,
        "reason_code": "GATE_PASSED" if passed else "GATE_FAILED",
    }


def validate_persisted_qualification_semantics(
    semantic: Mapping[str, Any], dataset_evidence: Any
) -> None:
    comparison = _require_mapping(semantic.get("comparison_contract"), "comparison contract")
    scope = _require_list(comparison.get("product_scope"), "product_scope")
    if len(scope) != 1:
        raise ValueError("formal P6 supports exactly one product")
    product = str(scope[0])
    if comparison.get("benchmark_vehicle") != f"{product}_LINEAR_PERPETUAL":
        raise ValueError("benchmark vehicle is incompatible with product scope")
    data_interval = _require_mapping(comparison.get("data_interval"), "data interval")
    metrics = _require_mapping(comparison.get("metrics_contract"), "metrics contract")
    run_artifact = _require_mapping(semantic.get("run_result"), "run_result")
    run_semantic = _require_mapping(run_artifact.get("semantic_payload"), "run semantic")
    run_identity = _require_mapping(run_semantic.get("run_identity"), "run identity")
    candidate = _require_mapping(run_semantic.get("accounting"), "candidate accounting")
    if candidate.get("formal_run_identity") != run_identity:
        raise ValueError("candidate accounting/run identity binding mismatch")
    candles = _candles_from_accounting(candidate, product)
    validate_runtime_dataset_binding(dataset_evidence, candles, product)
    verify_formal_accounting(
        candidate,
        product=product,
        initial_cash=_finite(comparison.get("initial_capital"), "initial capital"),
        interval_start_ms=int(data_interval["start_ms"]),
        interval_end_ms=int(data_interval["end_ms"]),
        terminal_policy=str(comparison["terminal_policy"]),
        metrics_contract=metrics,
    )
    expected_run_id = "economic-run-result@" + canonical_sha256(
        {"run_identity": dict(run_identity), "accounting": dict(candidate)}
    )
    if run_artifact.get("result_id") != expected_run_id:
        raise ValueError("candidate run result id is not replayable")

    suite = _require_mapping(semantic.get("benchmark_suite"), "benchmark suite")
    rules = _require_mapping(comparison.get("matching_rules"), "matching rules")
    initial = _finite(comparison.get("initial_capital"), "initial capital")
    start = int(data_interval["start_ms"])
    end = int(data_interval["end_ms"])
    terminal = str(comparison["terminal_policy"])

    cash_accounting: Mapping[str, Any] | None = None
    cash_value = suite.get("cash")
    cash_comparable = False
    if cash_value is not None:
        cash = _require_mapping(cash_value, "cash benchmark")
        cash_accounting = _require_mapping(cash.get("accounting"), "cash accounting")
        verify_formal_accounting(
            cash_accounting,
            product=product,
            initial_cash=initial,
            interval_start_ms=start,
            interval_end_ms=end,
            terminal_policy=terminal,
            metrics_contract=metrics,
        )
        cash_candles = _candles_from_accounting(cash_accounting, product)
        validate_runtime_dataset_binding(dataset_evidence, cash_candles, product)
        cash_comparable = (
            cash.get("vehicle") == "USDT_CASH_NO_TRADE" and cash.get("comparable") is True
        )
        if not cash_comparable:
            raise ValueError("cash benchmark comparability is invalid")

    passive_accounting: Mapping[str, Any] | None = None
    passive_value = suite.get("passive")
    passive_comparable = False
    if passive_value is not None:
        passive = _require_mapping(passive_value, "passive benchmark")
        passive_accounting = validate_passive_benchmark_provenance(
            passive,
            comparison=comparison,
            candidate_identity=run_identity,
            dataset_evidence=dataset_evidence,
        )
        verify_formal_accounting(
            passive_accounting,
            product=product,
            initial_cash=initial,
            interval_start_ms=start,
            interval_end_ms=end,
            terminal_policy=terminal,
            metrics_contract=metrics,
        )
        passive_comparable = True

    random_value = suite.get("random")
    random_accounts: list[Mapping[str, Any]] = []
    random_comparable = False
    if random_value is not None:
        distribution = _require_mapping(random_value, "random distribution")
        trials = _require_list(distribution.get("trials"), "random trials")
        expected_count = int(comparison.get("random_trials", 0))
        if (
            distribution.get("seed") != comparison.get("random_seed")
            or len(trials) != expected_count
            or distribution.get("trial_count") != expected_count
        ):
            raise ValueError("random benchmark seed/trial count mismatch")
        master = random.Random(int(comparison["random_seed"]))
        all_comparable = True
        for index, raw_trial in enumerate(trials):
            trial = _require_mapping(raw_trial, f"random trial {index}")
            if trial.get("trial_id") != index or trial.get("seed") != master.randrange(0, 2**63):
                raise ValueError("random trial identity/seed is not deterministic")
            if trial.get("benchmark_kind") != "RANDOM_MATCHED" or trial.get(
                "vehicle"
            ) != comparison.get("benchmark_vehicle"):
                raise ValueError("random trial vehicle/kind mismatch")
            accounting = _require_mapping(trial.get("accounting"), "random accounting")
            identity = _require_mapping(
                accounting.get("formal_run_identity"), "random run identity"
            )
            trial_candles = _candles_from_accounting(accounting, product)
            validate_runtime_dataset_binding(dataset_evidence, trial_candles, product)
            validate_formal_run_identity_binding(run_identity, identity)
            verify_formal_accounting(
                accounting,
                product=product,
                initial_cash=initial,
                interval_start_ms=start,
                interval_end_ms=end,
                terminal_policy=terminal,
                metrics_contract=metrics,
            )
            expected_trial_run_id = "economic-run-result@" + canonical_sha256(
                {"run_identity": dict(identity), "accounting": dict(accounting)}
            )
            if trial.get("run_result_id") != expected_trial_run_id:
                raise ValueError("random trial run result identity mismatch")
            diagnostics, comparable = recompute_matching_diagnostics(candidate, accounting, rules)
            _close(
                trial.get("matching_diagnostics"),
                diagnostics,
                f"random trial {index} matching diagnostics",
            )
            if trial.get("comparable") is not comparable:
                raise ValueError("random trial comparable flag disagrees with recomputation")
            all_comparable = all_comparable and comparable
            random_accounts.append(accounting)
        random_comparable = bool(trials) and all_comparable
        if distribution.get("comparable") is not random_comparable:
            raise ValueError("random distribution comparable flag disagrees with trials")
        returns = [_finite(item.get("net_return_pct"), "random return") for item in random_accounts]
        expected_aggregate = {
            "mean_net_return_pct": sum(returns) / len(returns) if returns else None,
            "minimum_net_return_pct": min(returns) if returns else None,
            "maximum_net_return_pct": max(returns) if returns else None,
        }
        _close(distribution.get("aggregate"), expected_aggregate, "random aggregate")

    required = _require_list(comparison.get("required_benchmarks"), "required benchmarks")
    availability = {
        "CASH": cash_accounting is not None,
        "PASSIVE_PERPETUAL": passive_accounting is not None,
        "RANDOM_MATCHED": random_value is not None,
    }
    comparability = {
        "CASH": cash_comparable,
        "PASSIVE_PERPETUAL": passive_comparable,
        "RANDOM_MATCHED": random_comparable,
    }
    reasons: list[str] = []
    if run_identity.get("completeness") != "COMPLETE":
        reasons.append("CANDIDATE_RUN_INCOMPLETE")
    for kind in required:
        name = str(kind)
        if not availability.get(name, False):
            reasons.append(f"REQUIRED_BENCHMARK_MISSING:{name}")
        elif not comparability.get(name, False):
            reasons.append(f"REQUIRED_BENCHMARK_INCOMPARABLE:{name}")

    hurdles = _require_list(comparison.get("hurdles"), "hurdles")
    recomputed_gates = [
        _gate_payload(
            _require_mapping(item, "hurdle"),
            candidate,
            cash_accounting if cash_comparable else None,
            passive_accounting if passive_comparable else None,
            random_accounts,
            random_comparable,
        )
        for item in hurdles
    ]
    gates = _require_list(semantic.get("gates"), "gates")
    _close(gates, recomputed_gates, "qualification gates")
    if any(not bool(item["testable"]) for item in recomputed_gates):
        reasons.append("ECONOMIC_GATE_NOT_TESTABLE")
    if reasons:
        verdict = "NOT_TESTABLE"
    elif all(item["passed"] is True for item in recomputed_gates):
        verdict = "QUALIFIED"
        reasons.append("ALL_PREREGISTERED_HURDLES_PASSED")
    else:
        verdict = "REJECTED"
        reasons.append("PREREGISTERED_HURDLE_FAILED")
    if semantic.get("verdict") != verdict:
        raise ValueError("qualification verdict disagrees with independent recomputation")
    if semantic.get("reason_codes") != reasons:
        raise ValueError("qualification reason codes disagree with independent recomputation")
