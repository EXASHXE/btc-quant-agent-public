from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..research_contract.canonical import canonical_sha256
from .portfolio import Portfolio
from .trade_event import TradeAction, TradeEvent

ACCOUNTING_TOLERANCE = 1e-8
MILLISECONDS_PER_YEAR = 365 * 24 * 60 * 60 * 1000


class TerminalPolicy(StrEnum):
    MARK_TO_MARKET_OPEN = "MARK_TO_MARKET_OPEN"
    REQUIRE_FLAT = "REQUIRE_FLAT"


class ResultCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE_DATA = "INCOMPLETE_DATA"
    INCOMPLETE_PENDING_ORDERS = "INCOMPLETE_PENDING_ORDERS"
    UNSUPPORTED_TERMINAL_STATE = "UNSUPPORTED_TERMINAL_STATE"


class MetricStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    NOT_REQUESTED = "NOT_REQUESTED"
    INVALID_CADENCE = "INVALID_CADENCE"
    INSUFFICIENT_OBSERVATIONS = "INSUFFICIENT_OBSERVATIONS"
    ZERO_VARIANCE = "ZERO_VARIANCE"
    INVALID_EQUITY = "INVALID_EQUITY"


class ProfitFactorStatus(StrEnum):
    FINITE = "FINITE"
    INFINITE = "INFINITE"
    UNDEFINED = "UNDEFINED"


@dataclass(frozen=True)
class ReturnMetricsContract:
    """Predeclared time-return sampling and annualization semantics."""

    contract_name: str
    sampling_rule: str
    cadence_ms: int
    spacing_tolerance_ms: int
    annualization_rule: str = "CALENDAR_365D"
    risk_free_rate_per_period: float = 0.0
    schema_version: str = "1.0.0"

    def __post_init__(self) -> None:
        if not self.contract_name.strip() or not self.sampling_rule.strip():
            raise ValueError("metrics contract name and sampling_rule are required")
        if type(self.cadence_ms) is not int or self.cadence_ms <= 0:
            raise ValueError("cadence_ms must be a positive integer")
        if type(self.spacing_tolerance_ms) is not int or self.spacing_tolerance_ms < 0:
            raise ValueError("spacing_tolerance_ms must be a nonnegative integer")
        if self.spacing_tolerance_ms >= self.cadence_ms:
            raise ValueError("spacing tolerance must be smaller than cadence")
        if self.annualization_rule != "CALENDAR_365D":
            raise ValueError("unsupported annualization_rule")
        if not math.isfinite(self.risk_free_rate_per_period):
            raise ValueError("risk_free_rate_per_period must be finite")
        if self.schema_version != "1.0.0":
            raise ValueError("unsupported metrics contract schema")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "contract_name": self.contract_name,
            "sampling_rule": self.sampling_rule,
            "cadence_ms": self.cadence_ms,
            "spacing_tolerance_ms": self.spacing_tolerance_ms,
            "annualization_rule": self.annualization_rule,
            "risk_free_rate_per_period": self.risk_free_rate_per_period,
        }

    @property
    def contract_hash(self) -> str:
        return canonical_sha256(self.to_dict())

    @property
    def contract_id(self) -> str:
        return f"{self.contract_name}@{self.contract_hash}"

    def validate_timestamps(self, timestamps: Sequence[int]) -> bool:
        if len(timestamps) < 2:
            return False
        if any(type(ts) is not int or ts <= 0 for ts in timestamps):
            return False
        return all(
            timestamps[index] > timestamps[index - 1]
            and abs(
                (timestamps[index] - timestamps[index - 1]) - self.cadence_ms
            )
            <= self.spacing_tolerance_ms
            for index in range(1, len(timestamps))
        )

    def annualized_sharpe(
        self, equity_curve: Sequence[tuple[int, float]]
    ) -> tuple[float | None, MetricStatus]:
        if len(equity_curve) < 3:
            return None, MetricStatus.INSUFFICIENT_OBSERVATIONS
        timestamps = [point[0] for point in equity_curve]
        if not self.validate_timestamps(timestamps):
            return None, MetricStatus.INVALID_CADENCE
        values = [float(point[1]) for point in equity_curve]
        if any(not math.isfinite(value) or value <= 0 for value in values):
            return None, MetricStatus.INVALID_EQUITY
        returns = [
            (values[index] - values[index - 1]) / values[index - 1]
            for index in range(1, len(values))
        ]
        excess = [value - self.risk_free_rate_per_period for value in returns]
        mean_return = sum(excess) / len(excess)
        variance = sum((value - mean_return) ** 2 for value in excess) / len(excess)
        if variance <= 1e-24:
            return None, MetricStatus.ZERO_VARIANCE
        periods_per_year = MILLISECONDS_PER_YEAR / self.cadence_ms
        sharpe = mean_return / math.sqrt(variance) * math.sqrt(periods_per_year)
        if not math.isfinite(sharpe):
            return None, MetricStatus.INVALID_EQUITY
        return sharpe, MetricStatus.AVAILABLE


@dataclass(frozen=True)
class RoundTripAttribution:
    entry_event_id: str
    exit_event_id: str
    entry_timestamp_ms: int
    exit_timestamp_ms: int
    side: str
    quantity: float
    entry_notional_usdt: float
    exit_notional_usdt: float
    gross_realized_pnl_usdt: float
    entry_fee_usdt: float
    exit_fee_usdt: float
    funding_usdt: float
    net_pnl_usdt: float
    holding_duration_ms: int
    mae_usdt: None = None
    mfe_usdt: None = None
    path_metrics_status: str = "UNAVAILABLE_WITHOUT_INTRABAR_PATH"

    def __post_init__(self) -> None:
        if not self.entry_event_id.strip() or not self.exit_event_id.strip():
            raise ValueError("round-trip event identities are required")
        if self.side not in {"LONG", "SHORT"}:
            raise ValueError("round-trip side must be LONG or SHORT")
        if (
            type(self.entry_timestamp_ms) is not int
            or type(self.exit_timestamp_ms) is not int
            or self.entry_timestamp_ms <= 0
            or self.exit_timestamp_ms < self.entry_timestamp_ms
            or self.holding_duration_ms
            != self.exit_timestamp_ms - self.entry_timestamp_ms
        ):
            raise ValueError("round-trip timestamps/holding duration do not reconcile")
        numeric = (
            self.quantity,
            self.entry_notional_usdt,
            self.exit_notional_usdt,
            self.gross_realized_pnl_usdt,
            self.entry_fee_usdt,
            self.exit_fee_usdt,
            self.funding_usdt,
            self.net_pnl_usdt,
        )
        if any(not math.isfinite(value) for value in numeric):
            raise ValueError("round-trip values must be finite")
        if (
            self.quantity <= 0
            or self.entry_notional_usdt <= 0
            or self.exit_notional_usdt <= 0
            or self.entry_fee_usdt < 0
            or self.exit_fee_usdt < 0
        ):
            raise ValueError("round-trip quantity/notionals/fees are invalid")
        expected_net = (
            self.gross_realized_pnl_usdt
            - self.entry_fee_usdt
            - self.exit_fee_usdt
            + self.funding_usdt
        )
        if not math.isclose(
            self.net_pnl_usdt,
            expected_net,
            rel_tol=0.0,
            abs_tol=ACCOUNTING_TOLERANCE,
        ):
            raise ValueError("round-trip net PnL does not reconcile")

    def to_dict(self) -> dict[str, Any]:
        return {
            "round_trip_id": self.round_trip_id,
            "entry_event_id": self.entry_event_id,
            "exit_event_id": self.exit_event_id,
            "entry_timestamp_ms": self.entry_timestamp_ms,
            "exit_timestamp_ms": self.exit_timestamp_ms,
            "side": self.side,
            "quantity": self.quantity,
            "entry_notional_usdt": self.entry_notional_usdt,
            "exit_notional_usdt": self.exit_notional_usdt,
            "gross_realized_pnl_usdt": self.gross_realized_pnl_usdt,
            "entry_fee_usdt": self.entry_fee_usdt,
            "exit_fee_usdt": self.exit_fee_usdt,
            "funding_usdt": self.funding_usdt,
            "net_pnl_usdt": self.net_pnl_usdt,
            "holding_duration_ms": self.holding_duration_ms,
            "mae_usdt": self.mae_usdt,
            "mfe_usdt": self.mfe_usdt,
            "path_metrics_status": self.path_metrics_status,
        }

    @property
    def round_trip_id(self) -> str:
        payload = {
            "entry_event_id": self.entry_event_id,
            "exit_event_id": self.exit_event_id,
            "quantity": self.quantity,
            "gross_realized_pnl_usdt": self.gross_realized_pnl_usdt,
            "entry_fee_usdt": self.entry_fee_usdt,
            "exit_fee_usdt": self.exit_fee_usdt,
            "funding_usdt": self.funding_usdt,
        }
        return f"round-trip@{canonical_sha256(payload)}"


@dataclass(frozen=True)
class SimulationSummary:
    """Diagnostic summary plus a complete reconstructable accounting contract.

    Legacy callers may still construct the leading fields for diagnostics. Formal
    qualification additionally requires ``formal_complete`` and validates the ledger.
    """

    initial_cash: float
    final_equity: float
    gross_pnl_usdt: float
    total_fees_usdt: float
    total_funding_usdt: float
    net_pnl_usdt: float
    net_return_pct: float
    max_drawdown_usdt: float
    max_drawdown_pct: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float | None
    sharpe_ratio: float | None
    trade_events: tuple[TradeEvent, ...] = field(default_factory=tuple)
    equity_curve: tuple[tuple[int, float], ...] = field(default_factory=tuple)
    final_cash: float | None = None
    realized_gross_pnl_usdt: float | None = None
    terminal_unrealized_pnl_usdt: float | None = None
    terminal_position_quantity: float | None = None
    terminal_mark_price: float | None = None
    terminal_position_notional_usdt: float | None = None
    fill_count: int | None = None
    completed_round_trips: int | None = None
    flat_trades: int | None = None
    gross_wins_usdt: float | None = None
    gross_losses_usdt: float | None = None
    net_wins_usdt: float | None = None
    net_losses_usdt: float | None = None
    profit_factor_status: ProfitFactorStatus = ProfitFactorStatus.UNDEFINED
    turnover_usdt: float | None = None
    time_exposure_ms: int | None = None
    time_exposure_fraction: float | None = None
    average_notional_exposure_usdt: float | None = None
    maximum_notional_exposure_usdt: float | None = None
    average_capital_exposure_fraction: float | None = None
    slippage_attribution_usdt: float | None = None
    terminal_policy: TerminalPolicy | None = None
    terminal_treatment: str | None = None
    completeness: ResultCompleteness = ResultCompleteness.INCOMPLETE_DATA
    pending_order_count: int | None = None
    ledger_event_ids: tuple[str, ...] = field(default_factory=tuple)
    round_trips: tuple[RoundTripAttribution, ...] = field(default_factory=tuple)
    metrics_contract_id: str | None = None
    sharpe_status: MetricStatus = MetricStatus.NOT_REQUESTED
    accounting_tolerance: float = ACCOUNTING_TOLERANCE

    def __post_init__(self) -> None:
        object.__setattr__(self, "trade_events", tuple(self.trade_events))
        object.__setattr__(self, "equity_curve", tuple(self.equity_curve))
        object.__setattr__(self, "ledger_event_ids", tuple(self.ledger_event_ids))
        object.__setattr__(self, "round_trips", tuple(self.round_trips))
        if self.terminal_policy is not None and not isinstance(
            self.terminal_policy, TerminalPolicy
        ):
            object.__setattr__(self, "terminal_policy", TerminalPolicy(self.terminal_policy))
        if not isinstance(self.completeness, ResultCompleteness):
            object.__setattr__(self, "completeness", ResultCompleteness(self.completeness))
        if not isinstance(self.profit_factor_status, ProfitFactorStatus):
            object.__setattr__(
                self, "profit_factor_status", ProfitFactorStatus(self.profit_factor_status)
            )
        if not isinstance(self.sharpe_status, MetricStatus):
            object.__setattr__(self, "sharpe_status", MetricStatus(self.sharpe_status))
        if self.profit_factor is not None and math.isinf(self.profit_factor):
            object.__setattr__(self, "profit_factor", None)
            object.__setattr__(self, "profit_factor_status", ProfitFactorStatus.INFINITE)
        elif self.profit_factor is not None and self.profit_factor_status is (
            ProfitFactorStatus.UNDEFINED
        ):
            object.__setattr__(self, "profit_factor_status", ProfitFactorStatus.FINITE)

        numeric_values = {
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "gross_pnl_usdt": self.gross_pnl_usdt,
            "total_fees_usdt": self.total_fees_usdt,
            "total_funding_usdt": self.total_funding_usdt,
            "net_pnl_usdt": self.net_pnl_usdt,
            "net_return_pct": self.net_return_pct,
            "max_drawdown_usdt": self.max_drawdown_usdt,
            "max_drawdown_pct": self.max_drawdown_pct,
            "win_rate": self.win_rate,
            "accounting_tolerance": self.accounting_tolerance,
        }
        optional_values = {
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "final_cash": self.final_cash,
            "realized_gross_pnl_usdt": self.realized_gross_pnl_usdt,
            "terminal_unrealized_pnl_usdt": self.terminal_unrealized_pnl_usdt,
            "terminal_position_quantity": self.terminal_position_quantity,
            "terminal_mark_price": self.terminal_mark_price,
            "terminal_position_notional_usdt": self.terminal_position_notional_usdt,
            "gross_wins_usdt": self.gross_wins_usdt,
            "gross_losses_usdt": self.gross_losses_usdt,
            "net_wins_usdt": self.net_wins_usdt,
            "net_losses_usdt": self.net_losses_usdt,
            "turnover_usdt": self.turnover_usdt,
            "time_exposure_fraction": self.time_exposure_fraction,
            "average_notional_exposure_usdt": self.average_notional_exposure_usdt,
            "maximum_notional_exposure_usdt": self.maximum_notional_exposure_usdt,
            "average_capital_exposure_fraction": self.average_capital_exposure_fraction,
            "slippage_attribution_usdt": self.slippage_attribution_usdt,
        }
        if any(not math.isfinite(value) for value in numeric_values.values()):
            raise ValueError("simulation summary numeric values must be finite")
        if any(
            value is not None and not math.isfinite(value)
            for value in optional_values.values()
        ):
            raise ValueError("simulation summary optional numeric values must be finite")
        if self.initial_cash <= 0 or self.accounting_tolerance <= 0:
            raise ValueError("initial cash and accounting tolerance must be positive")
        for name in (
            "total_trades",
            "winning_trades",
            "losing_trades",
            "fill_count",
            "completed_round_trips",
            "flat_trades",
            "time_exposure_ms",
            "pending_order_count",
        ):
            value = getattr(self, name)
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError(f"{name} must be a nonnegative integer")
        if any(
            self.equity_curve[index][0] <= self.equity_curve[index - 1][0]
            for index in range(1, len(self.equity_curve))
        ):
            raise ValueError("equity curve timestamps must be strictly increasing")
        if any(
            type(timestamp) is not int
            or timestamp <= 0
            or not math.isfinite(value)
            for timestamp, value in self.equity_curve
        ):
            raise ValueError("equity curve must contain positive timestamps and finite values")

    @property
    def formal_complete(self) -> bool:
        required = (
            self.final_cash,
            self.realized_gross_pnl_usdt,
            self.terminal_unrealized_pnl_usdt,
            self.terminal_position_quantity,
            self.terminal_mark_price,
            self.terminal_position_notional_usdt,
            self.fill_count,
            self.completed_round_trips,
            self.flat_trades,
            self.gross_wins_usdt,
            self.gross_losses_usdt,
            self.net_wins_usdt,
            self.net_losses_usdt,
            self.turnover_usdt,
            self.time_exposure_ms,
            self.time_exposure_fraction,
            self.average_notional_exposure_usdt,
            self.maximum_notional_exposure_usdt,
            self.average_capital_exposure_fraction,
            self.slippage_attribution_usdt,
            self.pending_order_count,
        )
        return self.completeness is ResultCompleteness.COMPLETE and all(
            value is not None for value in required
        )

    def validate_accounting(self) -> None:
        if not self.formal_complete:
            raise ValueError(f"simulation result is not formally complete: {self.completeness}")
        assert self.realized_gross_pnl_usdt is not None
        assert self.terminal_unrealized_pnl_usdt is not None
        expected = (
            self.realized_gross_pnl_usdt
            + self.terminal_unrealized_pnl_usdt
            - self.total_fees_usdt
            + self.total_funding_usdt
        )
        if not math.isclose(
            self.final_equity - self.initial_cash,
            expected,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("simulation accounting identity does not reconcile")
        if not self.equity_curve or not math.isclose(
            self.equity_curve[-1][1],
            self.final_equity,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("terminal equity curve point does not reconcile")
        if len(self.ledger_event_ids) != len(self.trade_events):
            raise ValueError("ledger event identities do not cover trade history")
        expected_event_ids = tuple(
            ledger_event_id(event, index)
            for index, event in enumerate(self.trade_events, start=1)
        )
        if self.ledger_event_ids != expected_event_ids:
            raise ValueError("ledger event identities disagree with trade history")
        assert self.final_cash is not None
        expected_cash = (
            self.initial_cash
            + self.realized_gross_pnl_usdt
            - self.total_fees_usdt
            + self.total_funding_usdt
        )
        if not math.isclose(
            self.final_cash,
            expected_cash,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("final cash does not reconcile to the ledger")
        if not math.isclose(
            self.net_pnl_usdt,
            self.final_equity - self.initial_cash,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("net PnL does not reconcile")
        if not math.isclose(
            self.net_return_pct,
            self.net_pnl_usdt / self.initial_cash,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("net return does not reconcile")
        if not math.isclose(
            self.gross_pnl_usdt,
            self.realized_gross_pnl_usdt,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("gross PnL aliases do not reconcile")
        assert self.terminal_position_quantity is not None
        assert self.terminal_mark_price is not None
        assert self.terminal_position_notional_usdt is not None
        expected_notional = abs(self.terminal_position_quantity) * self.terminal_mark_price
        if not math.isclose(
            self.terminal_position_notional_usdt,
            expected_notional,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("terminal position notional does not reconcile")
        assert self.fill_count is not None
        if self.fill_count != sum(
            event.action is not TradeAction.FUNDING_SETTLEMENT
            for event in self.trade_events
        ):
            raise ValueError("fill count disagrees with trade history")
        assert self.completed_round_trips is not None
        assert self.flat_trades is not None
        if self.completed_round_trips != len(self.round_trips):
            raise ValueError("completed round-trip count disagrees with attribution")
        if self.total_trades != self.completed_round_trips:
            raise ValueError("legacy total_trades must equal completed round trips")
        if (
            self.winning_trades + self.losing_trades + self.flat_trades
            != self.completed_round_trips
        ):
            raise ValueError("round-trip outcome counts do not reconcile")
        recomputed_round_trips = attribute_round_trips(self.trade_events)
        if self.round_trips != recomputed_round_trips:
            raise ValueError("round-trip attribution disagrees with trade history")
        wins = tuple(
            item
            for item in self.round_trips
            if item.net_pnl_usdt > self.accounting_tolerance
        )
        losses = tuple(
            item
            for item in self.round_trips
            if item.net_pnl_usdt < -self.accounting_tolerance
        )
        if self.winning_trades != len(wins) or self.losing_trades != len(losses):
            raise ValueError("round-trip win/loss counts disagree with net economics")
        assert self.gross_wins_usdt is not None
        assert self.gross_losses_usdt is not None
        assert self.net_wins_usdt is not None
        assert self.net_losses_usdt is not None
        expected_gross_wins = sum(
            max(item.gross_realized_pnl_usdt, 0.0) for item in self.round_trips
        )
        expected_gross_losses = sum(
            max(-item.gross_realized_pnl_usdt, 0.0) for item in self.round_trips
        )
        expected_net_wins = sum(item.net_pnl_usdt for item in wins)
        expected_net_losses = sum(-item.net_pnl_usdt for item in losses)
        for observed, expected_value, label in (
            (self.gross_wins_usdt, expected_gross_wins, "gross wins"),
            (self.gross_losses_usdt, expected_gross_losses, "gross losses"),
            (self.net_wins_usdt, expected_net_wins, "net wins"),
            (self.net_losses_usdt, expected_net_losses, "net losses"),
        ):
            if not math.isclose(
                observed,
                expected_value,
                rel_tol=0.0,
                abs_tol=self.accounting_tolerance,
            ):
                raise ValueError(f"{label} do not reconcile")
        expected_win_rate = (
            len(wins) / self.completed_round_trips
            if self.completed_round_trips
            else 0.0
        )
        if not math.isclose(
            self.win_rate,
            expected_win_rate,
            rel_tol=0.0,
            abs_tol=self.accounting_tolerance,
        ):
            raise ValueError("win rate does not reconcile")
        if expected_net_losses > self.accounting_tolerance:
            expected_profit_factor = expected_net_wins / expected_net_losses
            if (
                self.profit_factor_status is not ProfitFactorStatus.FINITE
                or self.profit_factor is None
                or not math.isclose(
                    self.profit_factor,
                    expected_profit_factor,
                    rel_tol=0.0,
                    abs_tol=self.accounting_tolerance,
                )
            ):
                raise ValueError("finite profit factor does not reconcile")
        elif expected_net_wins > self.accounting_tolerance:
            if (
                self.profit_factor is not None
                or self.profit_factor_status is not ProfitFactorStatus.INFINITE
            ):
                raise ValueError("infinite profit factor representation is invalid")
        elif (
            self.profit_factor is not None
            or self.profit_factor_status is not ProfitFactorStatus.UNDEFINED
        ):
            raise ValueError("undefined profit factor representation is invalid")
        assert self.time_exposure_fraction is not None
        if not 0.0 <= self.time_exposure_fraction <= 1.0:
            raise ValueError("time exposure fraction must be in [0, 1]")

    def to_dict(self) -> dict[str, Any]:
        def finite_or_none(value: float | None) -> float | None:
            return value if value is None or math.isfinite(value) else None

        return {
            "schema_version": "2.0.0",
            "initial_cash": self.initial_cash,
            "final_cash": self.final_cash,
            "final_equity": self.final_equity,
            "gross_pnl_usdt": self.gross_pnl_usdt,
            "realized_gross_pnl_usdt": self.realized_gross_pnl_usdt,
            "terminal_unrealized_pnl_usdt": self.terminal_unrealized_pnl_usdt,
            "total_fees_usdt": self.total_fees_usdt,
            "total_funding_usdt": self.total_funding_usdt,
            "slippage_attribution_usdt": self.slippage_attribution_usdt,
            "net_pnl_usdt": self.net_pnl_usdt,
            "net_return_pct": self.net_return_pct,
            "terminal_position_quantity": self.terminal_position_quantity,
            "terminal_mark_price": self.terminal_mark_price,
            "terminal_position_notional_usdt": self.terminal_position_notional_usdt,
            "fill_count": self.fill_count,
            "completed_round_trips": self.completed_round_trips,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "flat_trades": self.flat_trades,
            "gross_wins_usdt": self.gross_wins_usdt,
            "gross_losses_usdt": self.gross_losses_usdt,
            "net_wins_usdt": self.net_wins_usdt,
            "net_losses_usdt": self.net_losses_usdt,
            "win_rate": self.win_rate,
            "profit_factor": finite_or_none(self.profit_factor),
            "profit_factor_status": self.profit_factor_status.value,
            "max_drawdown_usdt": self.max_drawdown_usdt,
            "max_drawdown_pct": self.max_drawdown_pct,
            "turnover_usdt": self.turnover_usdt,
            "time_exposure_ms": self.time_exposure_ms,
            "time_exposure_fraction": self.time_exposure_fraction,
            "average_notional_exposure_usdt": self.average_notional_exposure_usdt,
            "maximum_notional_exposure_usdt": self.maximum_notional_exposure_usdt,
            "average_capital_exposure_fraction": self.average_capital_exposure_fraction,
            "sharpe_ratio": finite_or_none(self.sharpe_ratio),
            "sharpe_status": self.sharpe_status.value,
            "metrics_contract_id": self.metrics_contract_id,
            "terminal_policy": self.terminal_policy.value if self.terminal_policy else None,
            "terminal_treatment": self.terminal_treatment,
            "completeness": self.completeness.value,
            "pending_order_count": self.pending_order_count,
            "accounting_tolerance": self.accounting_tolerance,
            "ledger_event_ids": list(self.ledger_event_ids),
            "trade_events": [event.to_dict() for event in self.trade_events],
            "trade_event_count": len(self.trade_events),
            "round_trips": [item.to_dict() for item in self.round_trips],
            "equity_curve": [list(point) for point in self.equity_curve],
        }


@dataclass
class _OpenLot:
    event_id: str
    timestamp_ms: int
    side: int
    entry_price: float
    remaining_quantity: float
    remaining_entry_fee: float
    remaining_funding: float = 0.0


def ledger_event_id(event: TradeEvent, sequence: int) -> str:
    return f"ledger-event@{canonical_sha256({'sequence': sequence, 'event': event.to_dict()})}"


def attribute_round_trips(
    events: Sequence[TradeEvent], *, tolerance: float = ACCOUNTING_TOLERANCE
) -> tuple[RoundTripAttribution, ...]:
    lots_by_asset: dict[str, list[_OpenLot]] = {}
    result: list[RoundTripAttribution] = []
    ids = [ledger_event_id(event, index) for index, event in enumerate(events, start=1)]
    for index, event in enumerate(events):
        asset_raw = event.metadata.get("asset")
        if not isinstance(asset_raw, str) or not asset_raw.strip():
            raise ValueError("round-trip attribution requires event asset metadata")
        lots = lots_by_asset.setdefault(asset_raw, [])
        if event.action in (TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT):
            lots.append(
                _OpenLot(
                    event_id=ids[index],
                    timestamp_ms=event.timestamp_ms,
                    side=1 if event.action is TradeAction.OPEN_LONG else -1,
                    entry_price=event.price,
                    remaining_quantity=event.quantity,
                    remaining_entry_fee=event.fee_usdt,
                )
            )
            continue
        if event.action is TradeAction.FUNDING_SETTLEMENT:
            total_quantity = sum(lot.remaining_quantity for lot in lots)
            if total_quantity <= tolerance:
                if abs(event.funding_usdt) > tolerance:
                    raise ValueError("funding cannot be attributed without an open lot")
                continue
            for lot in lots:
                lot.remaining_funding += (
                    event.funding_usdt * lot.remaining_quantity / total_quantity
                )
            continue

        expected_side = 1 if event.action is TradeAction.CLOSE_LONG else -1
        remaining_close = event.quantity
        for lot in list(lots):
            if remaining_close <= tolerance:
                break
            if lot.side != expected_side:
                raise ValueError("close event side disagrees with open-lot attribution")
            quantity_before = lot.remaining_quantity
            matched = min(quantity_before, remaining_close)
            fraction = matched / quantity_before
            entry_fee = lot.remaining_entry_fee * fraction
            funding = lot.remaining_funding * fraction
            exit_fee = event.fee_usdt * matched / event.quantity
            gross = lot.side * matched * (event.price - lot.entry_price)
            net = gross - entry_fee - exit_fee + funding
            result.append(
                RoundTripAttribution(
                    entry_event_id=lot.event_id,
                    exit_event_id=ids[index],
                    entry_timestamp_ms=lot.timestamp_ms,
                    exit_timestamp_ms=event.timestamp_ms,
                    side="LONG" if lot.side > 0 else "SHORT",
                    quantity=matched,
                    entry_notional_usdt=matched * lot.entry_price,
                    exit_notional_usdt=matched * event.price,
                    gross_realized_pnl_usdt=gross,
                    entry_fee_usdt=entry_fee,
                    exit_fee_usdt=exit_fee,
                    funding_usdt=funding,
                    net_pnl_usdt=net,
                    holding_duration_ms=event.timestamp_ms - lot.timestamp_ms,
                )
            )
            lot.remaining_quantity -= matched
            lot.remaining_entry_fee -= entry_fee
            lot.remaining_funding -= funding
            remaining_close -= matched
            if lot.remaining_quantity <= tolerance:
                lots.remove(lot)
        if remaining_close > tolerance:
            raise ValueError("close quantity is not covered by open lots")
    return tuple(result)


def _time_exposure_ms(
    events: Sequence[TradeEvent], start_ms: int, end_ms: int
) -> int:
    position = 0.0
    cursor = start_ms
    exposed = 0
    for event in events:
        event_time = min(max(event.timestamp_ms, start_ms), end_ms)
        if position != 0.0 and event_time > cursor:
            exposed += event_time - cursor
        cursor = max(cursor, event_time)
        position = event.position_after
    if position != 0.0 and end_ms > cursor:
        exposed += end_ms - cursor
    return exposed


def _notional_exposure_stats(
    events: Sequence[TradeEvent],
    notional_curve: Sequence[tuple[int, float]],
    start_ms: int,
    end_ms: int,
) -> tuple[float, float]:
    """Time-weight notional using ledger marks plus declared curve marks.

    Candle-close snapshots alone miss positions opened and closed within one bar.
    Ledger events therefore update exposure at their causal event price, while
    supplied mark points refresh that exposure at each observable curve time.
    """
    points: list[tuple[int, int, float]] = [(start_ms, -1, 0.0)]
    for sequence, event in enumerate(events, start=1):
        if start_ms <= event.timestamp_ms <= end_ms:
            points.append(
                (
                    event.timestamp_ms,
                    sequence,
                    abs(event.position_after) * event.price,
                )
            )
    for timestamp_ms, notional in notional_curve:
        if type(timestamp_ms) is not int or not start_ms <= timestamp_ms <= end_ms:
            raise ValueError("notional curve timestamp lies outside the interval")
        if not math.isfinite(notional) or notional < 0:
            raise ValueError("notional curve values must be finite and nonnegative")
        # A candle close can share a timestamp with the next candle open.  The
        # close mark is observable before any new open-time ledger event, so it
        # sorts first; a same-time event then defines exposure going forward.
        points.append((timestamp_ms, 0, float(notional)))
    points.sort(key=lambda item: (item[0], item[1]))
    cursor = start_ms
    current = 0.0
    area = 0.0
    maximum = 0.0
    for timestamp_ms, _, notional in points:
        if timestamp_ms > cursor:
            area += current * (timestamp_ms - cursor)
            cursor = timestamp_ms
        current = notional
        maximum = max(maximum, current)
    if end_ms > cursor:
        area += current * (end_ms - cursor)
    return area / (end_ms - start_ms), maximum


def summarize_ledger(
    *,
    initial_cash: float,
    events: Sequence[TradeEvent],
    equity_curve: Sequence[tuple[int, float]],
    final_asset: str,
    final_mark_price: float,
    interval_start_ms: int,
    interval_end_ms: int,
    notional_curve: Sequence[tuple[int, float]],
    terminal_policy: TerminalPolicy,
    metrics_contract: ReturnMetricsContract | None = None,
    pending_order_count: int = 0,
    max_drawdown_override: tuple[float, float] | None = None,
) -> SimulationSummary:
    if interval_end_ms <= interval_start_ms:
        raise ValueError("economic interval must have positive duration")
    if not final_asset.strip():
        raise ValueError("final asset is required")
    if any(
        event.timestamp_ms < interval_start_ms
        or event.timestamp_ms > interval_end_ms
        or event.metadata.get("asset") != final_asset
        for event in events
    ):
        raise ValueError("formal ledger events must use one asset inside the interval")
    portfolio = Portfolio.from_events(initial_cash, events)
    final_quantity = portfolio.get_position_quantity(final_asset)
    position = portfolio.positions.get(final_asset)
    unrealized = position.unrealized_pnl(final_mark_price) if position else 0.0
    final_equity = portfolio.total_equity({final_asset: final_mark_price})
    curve = tuple((int(ts), float(value)) for ts, value in equity_curve)
    if (
        any(timestamp < interval_start_ms or timestamp > interval_end_ms for timestamp, _ in curve)
        or not curve
        or curve[-1][0] != interval_end_ms
    ):
        raise ValueError("equity curve must terminate at the economic interval end")
    notional_points = tuple((int(ts), float(value)) for ts, value in notional_curve)
    if tuple(timestamp for timestamp, _ in notional_points) != tuple(
        timestamp for timestamp, _ in curve
    ):
        raise ValueError("notional and equity curves must share exact timestamps")
    if not curve or not math.isclose(
        curve[-1][1], final_equity, rel_tol=0.0, abs_tol=ACCOUNTING_TOLERANCE
    ):
        raise ValueError("last equity-curve point must equal final equity")

    realized = sum(event.realized_pnl_usdt for event in events)
    fees = sum(event.fee_usdt for event in events)
    funding = sum(event.funding_usdt for event in events)
    expected_delta = realized + unrealized - fees + funding
    if not math.isclose(
        final_equity - initial_cash,
        expected_delta,
        rel_tol=0.0,
        abs_tol=ACCOUNTING_TOLERANCE,
    ):
        raise ValueError("ledger accounting identity does not reconcile")

    round_trips = attribute_round_trips(events)
    wins = tuple(item for item in round_trips if item.net_pnl_usdt > ACCOUNTING_TOLERANCE)
    losses = tuple(item for item in round_trips if item.net_pnl_usdt < -ACCOUNTING_TOLERANCE)
    flats = len(round_trips) - len(wins) - len(losses)
    gross_wins = sum(max(item.gross_realized_pnl_usdt, 0.0) for item in round_trips)
    gross_losses = sum(max(-item.gross_realized_pnl_usdt, 0.0) for item in round_trips)
    net_wins = sum(item.net_pnl_usdt for item in wins)
    net_losses = sum(-item.net_pnl_usdt for item in losses)
    if net_losses > ACCOUNTING_TOLERANCE:
        profit_factor = net_wins / net_losses
        profit_factor_status = ProfitFactorStatus.FINITE
    elif net_wins > ACCOUNTING_TOLERANCE:
        profit_factor = None
        profit_factor_status = ProfitFactorStatus.INFINITE
    else:
        profit_factor = None
        profit_factor_status = ProfitFactorStatus.UNDEFINED

    peak = initial_cash
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    for _, value in curve:
        peak = max(peak, value)
        drawdown = peak - value
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(
            max_drawdown_pct, drawdown / peak if peak > 0 else 0.0
        )
    if max_drawdown_override is not None:
        max_drawdown = max(max_drawdown, max_drawdown_override[0])
        max_drawdown_pct = max(max_drawdown_pct, max_drawdown_override[1])

    duration = interval_end_ms - interval_start_ms
    exposure_ms = _time_exposure_ms(events, interval_start_ms, interval_end_ms)
    average_notional, maximum_notional = _notional_exposure_stats(
        events,
        notional_points,
        interval_start_ms,
        interval_end_ms,
    )
    slippage = 0.0
    for event in events:
        if event.action is TradeAction.FUNDING_SETTLEMENT:
            continue
        reference = event.metadata.get("ref_price")
        if isinstance(reference, (int, float)) and math.isfinite(float(reference)):
            slippage += abs(event.price - float(reference)) * event.quantity

    if metrics_contract is None:
        sharpe, sharpe_status = None, MetricStatus.NOT_REQUESTED
        metrics_contract_id = None
    else:
        sharpe, sharpe_status = metrics_contract.annualized_sharpe(curve)
        metrics_contract_id = metrics_contract.contract_id

    if pending_order_count:
        completeness = ResultCompleteness.INCOMPLETE_PENDING_ORDERS
    elif terminal_policy is TerminalPolicy.REQUIRE_FLAT and abs(final_quantity) > 1e-12:
        completeness = ResultCompleteness.UNSUPPORTED_TERMINAL_STATE
    else:
        completeness = ResultCompleteness.COMPLETE
    treatment = "TERMINAL_FLAT" if abs(final_quantity) <= 1e-12 else "MARK_TO_MARKET_OPEN"
    net_pnl = final_equity - initial_cash
    event_ids = tuple(
        ledger_event_id(event, index) for index, event in enumerate(events, start=1)
    )
    summary = SimulationSummary(
        initial_cash=initial_cash,
        final_cash=portfolio.cash,
        final_equity=final_equity,
        gross_pnl_usdt=realized,
        realized_gross_pnl_usdt=realized,
        terminal_unrealized_pnl_usdt=unrealized,
        total_fees_usdt=fees,
        total_funding_usdt=funding,
        slippage_attribution_usdt=slippage,
        net_pnl_usdt=net_pnl,
        net_return_pct=net_pnl / initial_cash,
        terminal_position_quantity=final_quantity,
        terminal_mark_price=final_mark_price,
        terminal_position_notional_usdt=abs(final_quantity) * final_mark_price,
        fill_count=sum(event.action is not TradeAction.FUNDING_SETTLEMENT for event in events),
        completed_round_trips=len(round_trips),
        total_trades=len(round_trips),
        winning_trades=len(wins),
        losing_trades=len(losses),
        flat_trades=flats,
        gross_wins_usdt=gross_wins,
        gross_losses_usdt=gross_losses,
        net_wins_usdt=net_wins,
        net_losses_usdt=net_losses,
        win_rate=len(wins) / len(round_trips) if round_trips else 0.0,
        profit_factor=profit_factor,
        profit_factor_status=profit_factor_status,
        max_drawdown_usdt=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
        turnover_usdt=sum(
            event.price * event.quantity
            for event in events
            if event.action is not TradeAction.FUNDING_SETTLEMENT
        ),
        time_exposure_ms=exposure_ms,
        time_exposure_fraction=exposure_ms / duration,
        average_notional_exposure_usdt=average_notional,
        maximum_notional_exposure_usdt=maximum_notional,
        average_capital_exposure_fraction=average_notional / initial_cash,
        sharpe_ratio=sharpe,
        sharpe_status=sharpe_status,
        metrics_contract_id=metrics_contract_id,
        terminal_policy=terminal_policy,
        terminal_treatment=treatment,
        completeness=completeness,
        pending_order_count=pending_order_count,
        ledger_event_ids=event_ids,
        trade_events=tuple(events),
        round_trips=round_trips,
        equity_curve=curve,
    )
    if summary.formal_complete:
        summary.validate_accounting()
    return summary
