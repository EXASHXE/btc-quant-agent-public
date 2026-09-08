from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..domain import Candle
from .execution_model import ExecutionModel
from .fee_model import FeeModel
from .funding import FundingModel, FundingSettlement
from .policy import TradePolicy
from .portfolio import Portfolio
from .signal import InformationSignal
from .trade_event import TradeAction, TradeEvent


@dataclass(frozen=True)
class SimulationSummary:
    """Comprehensive performance report resulting from economic simulation replay."""

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
    profit_factor: float
    sharpe_ratio: float
    trade_events: list[TradeEvent] = field(default_factory=list)
    equity_curve: list[tuple[int, float]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "initial_cash": self.initial_cash,
            "final_equity": self.final_equity,
            "gross_pnl_usdt": self.gross_pnl_usdt,
            "total_fees_usdt": self.total_fees_usdt,
            "total_funding_usdt": self.total_funding_usdt,
            "net_pnl_usdt": self.net_pnl_usdt,
            "net_return_pct": self.net_return_pct,
            "max_drawdown_usdt": self.max_drawdown_usdt,
            "max_drawdown_pct": self.max_drawdown_pct,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "profit_factor": self.profit_factor,
            "sharpe_ratio": self.sharpe_ratio,
            "trade_event_count": len(self.trade_events),
        }


class EconomicSimulationEngine:
    """Event-driven economic replay engine executing TradePolicy against market data."""

    def __init__(
        self,
        policy: TradePolicy,
        execution_model: ExecutionModel | None = None,
        fee_model: FeeModel | None = None,
        funding_model: FundingModel | None = None,
        initial_cash: float = 100_000.0,
    ) -> None:
        if not math.isfinite(initial_cash) or initial_cash <= 0:
            raise ValueError("initial_cash must be finite and positive")
        self.policy = policy
        self.fee_model = fee_model or FeeModel()
        self.execution_model = execution_model or ExecutionModel(fee_model=self.fee_model)
        self.funding_model = funding_model or FundingModel()
        self.initial_cash = initial_cash

    def simulate(
        self,
        candles: Sequence[Candle],
        signals: Sequence[InformationSignal] = (),
        funding_events: Sequence[FundingSettlement] = (),
    ) -> SimulationSummary:
        if not candles:
            return SimulationSummary(
                initial_cash=self.initial_cash,
                final_equity=self.initial_cash,
                gross_pnl_usdt=0.0,
                total_fees_usdt=0.0,
                total_funding_usdt=0.0,
                net_pnl_usdt=0.0,
                net_return_pct=0.0,
                max_drawdown_usdt=0.0,
                max_drawdown_pct=0.0,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                profit_factor=0.0,
                sharpe_ratio=0.0,
            )

        portfolio = Portfolio(initial_cash=self.initial_cash)
        equity_curve: list[tuple[int, float]] = []

        # Sort input signals and funding by timestamp
        sorted_signals = sorted(signals, key=lambda s: s.timestamp_ms)
        sig_idx = 0
        n_signals = len(sorted_signals)

        sorted_funding = sorted(funding_events, key=lambda f: f.timestamp_ms)
        fund_idx = 0
        n_funding = len(sorted_funding)

        peak_equity = self.initial_cash
        max_dd_usdt = 0.0
        max_dd_pct = 0.0

        active_trade_entry_time: int | None = None
        active_trade_entry_price: float | None = None
        active_trade_peak_price: float | None = None
        active_trade_trough_price: float | None = None

        trades_completed = 0
        winning_trades = 0
        losing_trades = 0
        gross_pnl_accum = 0.0

        for i, bar in enumerate(candles):
            mark_price = bar.close

            # 1. Process funding events that occur up to this bar's close
            while fund_idx < n_funding and sorted_funding[fund_idx].timestamp_ms <= bar.close_time_ms:
                fevent = sorted_funding[fund_idx]
                qty = portfolio.get_position_quantity()
                if abs(qty) > 1e-12:
                    cf = self.funding_model.calculate_cashflow(
                        position_quantity=qty,
                        mark_price=fevent.mark_price,
                        funding_rate=fevent.funding_rate,
                    )
                    portfolio.apply_funding(
                        timestamp_ms=fevent.timestamp_ms,
                        asset=bar.symbol,
                        cashflow_usdt=cf,
                        mark_price=fevent.mark_price,
                    )
                fund_idx += 1

            # 2. Check position exit conditions if position exists
            pos_qty = portfolio.get_position_quantity()
            if abs(pos_qty) > 1e-12 and active_trade_entry_price is not None and active_trade_entry_time is not None:
                is_long = pos_qty > 0
                holding_duration = bar.close_time_ms - active_trade_entry_time

                # Track peak and trough prices
                if active_trade_peak_price is None or bar.high > active_trade_peak_price:
                    active_trade_peak_price = bar.high
                if active_trade_trough_price is None or bar.low < active_trade_trough_price:
                    active_trade_trough_price = bar.low

                exit_triggered = False
                exit_price = mark_price
                action = TradeAction.CLOSE_LONG if is_long else TradeAction.CLOSE_SHORT

                # A. Stop Loss
                if self.policy.exit_rule.stop_loss_pct is not None:
                    sl_pct = self.policy.exit_rule.stop_loss_pct
                    if is_long and bar.low <= active_trade_entry_price * (1.0 - sl_pct):
                        exit_triggered = True
                        exit_price = active_trade_entry_price * (1.0 - sl_pct)
                    elif not is_long and bar.high >= active_trade_entry_price * (1.0 + sl_pct):
                        exit_triggered = True
                        exit_price = active_trade_entry_price * (1.0 + sl_pct)

                # B. Take Profit
                if not exit_triggered and self.policy.exit_rule.take_profit_pct is not None:
                    tp_pct = self.policy.exit_rule.take_profit_pct
                    if is_long and bar.high >= active_trade_entry_price * (1.0 + tp_pct):
                        exit_triggered = True
                        exit_price = active_trade_entry_price * (1.0 + tp_pct)
                    elif not is_long and bar.low <= active_trade_entry_price * (1.0 - tp_pct):
                        exit_triggered = True
                        exit_price = active_trade_entry_price * (1.0 - tp_pct)

                # C. Trailing Stop
                if not exit_triggered and self.policy.exit_rule.trailing_stop_pct is not None:
                    ts_pct = self.policy.exit_rule.trailing_stop_pct
                    if is_long and active_trade_peak_price is not None and bar.low <= active_trade_peak_price * (1.0 - ts_pct):
                        exit_triggered = True
                        exit_price = active_trade_peak_price * (1.0 - ts_pct)
                    elif not is_long and active_trade_trough_price is not None and bar.high >= active_trade_trough_price * (1.0 + ts_pct):
                        exit_triggered = True
                        exit_price = active_trade_trough_price * (1.0 + ts_pct)

                # D. Max Holding Period Time Exit
                if not exit_triggered and holding_duration >= self.policy.exit_rule.max_holding_ms:
                    exit_triggered = True
                    exit_price = bar.close

                # Execute Exit
                if exit_triggered:
                    side = -1 if is_long else 1
                    exit_res = self.execution_model.simulate_order(
                        signal_timestamp_ms=bar.close_time_ms,
                        side=side,
                        desired_quantity=abs(pos_qty),
                        order_type=self.policy.entry_rule.order_type,
                        future_candles=candles[i : min(len(candles), i + 3)],
                    )
                    actual_exit_price = exit_res.fill_price if exit_res.is_filled else exit_price
                    fee = exit_res.fee_usdt if exit_res.is_filled else self.fee_model.calculate_fee(abs(pos_qty) * actual_exit_price)
                    ev = portfolio.apply_trade(
                        timestamp_ms=bar.close_time_ms,
                        action=action,
                        asset=bar.symbol,
                        price=actual_exit_price,
                        quantity=abs(pos_qty),
                        fee_usdt=fee,
                    )
                    trades_completed += 1
                    trade_gross = ev.realized_pnl_usdt
                    gross_pnl_accum += trade_gross
                    if ev.realized_pnl_usdt - fee > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1

                    active_trade_entry_time = None
                    active_trade_entry_price = None
                    active_trade_peak_price = None
                    active_trade_trough_price = None

            # 3. Evaluate new signals at this bar
            while sig_idx < n_signals and sorted_signals[sig_idx].timestamp_ms <= bar.open_time_ms:
                sig = sorted_signals[sig_idx]
                sig_idx += 1

                # Check if portfolio already has max open positions
                curr_pos_qty = portfolio.get_position_quantity()
                if abs(curr_pos_qty) > 1e-12:
                    # Optional signal reversal exit
                    if self.policy.exit_rule.decay_exit_on_signal_reversal and (
                        (curr_pos_qty > 0 and sig.direction == -1) or (curr_pos_qty < 0 and sig.direction == 1)
                    ):
                            # Signal reversal triggers early close
                            act = TradeAction.CLOSE_LONG if curr_pos_qty > 0 else TradeAction.CLOSE_SHORT
                            exit_fee = self.fee_model.calculate_fee(abs(curr_pos_qty) * bar.open)
                            ev = portfolio.apply_trade(
                                timestamp_ms=bar.open_time_ms,
                                action=act,
                                asset=bar.symbol,
                                price=bar.open,
                                quantity=abs(curr_pos_qty),
                                fee_usdt=exit_fee,
                            )
                            trades_completed += 1
                            gross_pnl_accum += ev.realized_pnl_usdt
                            if ev.realized_pnl_usdt - exit_fee > 0:
                                winning_trades += 1
                            else:
                                losing_trades += 1
                            active_trade_entry_time = None
                            active_trade_entry_price = None
                    continue

                if self.policy.should_enter(sig):
                    current_eq = portfolio.total_equity({bar.symbol: mark_price})
                    qty = self.policy.calculate_quantity(current_price=bar.open, portfolio_equity=current_eq)
                    if qty > 0:
                        side = 1 if sig.direction == 1 else -1
                        exec_res = self.execution_model.simulate_order(
                            signal_timestamp_ms=sig.timestamp_ms,
                            side=side,
                            desired_quantity=qty,
                            order_type=self.policy.entry_rule.order_type,
                            future_candles=candles[i:],
                            limit_price=bar.open if self.policy.entry_rule.order_type.value == "LIMIT" else None,
                            time_in_force_ms=self.policy.entry_rule.time_in_force_ms,
                        )
                        if exec_res.is_filled:
                            act = TradeAction.OPEN_LONG if side == 1 else TradeAction.OPEN_SHORT
                            portfolio.apply_trade(
                                timestamp_ms=exec_res.fill_timestamp_ms,
                                action=act,
                                asset=bar.symbol,
                                price=exec_res.fill_price,
                                quantity=exec_res.filled_quantity,
                                fee_usdt=exec_res.fee_usdt,
                                signal_id=sig.signal_id,
                            )
                            active_trade_entry_time = exec_res.fill_timestamp_ms
                            active_trade_entry_price = exec_res.fill_price
                            active_trade_peak_price = exec_res.fill_price
                            active_trade_trough_price = exec_res.fill_price

            # 4. Record snapshot of portfolio equity
            curr_equity = portfolio.total_equity({bar.symbol: mark_price})
            equity_curve.append((bar.close_time_ms, curr_equity))

            peak_equity = max(peak_equity, curr_equity)
            dd_usdt = peak_equity - curr_equity
            dd_pct = dd_usdt / peak_equity if peak_equity > 0 else 0.0
            max_dd_usdt = max(max_dd_usdt, dd_usdt)
            max_dd_pct = max(max_dd_pct, dd_pct)

        final_eq = portfolio.total_equity({candles[-1].symbol: candles[-1].close})
        total_fees = sum(ev.fee_usdt for ev in portfolio.trade_history)
        total_funding = sum(ev.funding_usdt for ev in portfolio.trade_history)
        net_pnl = final_eq - self.initial_cash
        net_return_pct = net_pnl / self.initial_cash if self.initial_cash > 0 else 0.0

        # Sharpe calculation from equity curve returns
        sharpe = 0.0
        if len(equity_curve) > 2:
            eq_vals = [e[1] for e in equity_curve]
            pct_returns = [(eq_vals[k] - eq_vals[k - 1]) / eq_vals[k - 1] for k in range(1, len(eq_vals)) if eq_vals[k - 1] > 0]
            if pct_returns:
                mean_r = sum(pct_returns) / len(pct_returns)
                var_r = sum((r - mean_r) ** 2 for r in pct_returns) / len(pct_returns)
                std_r = math.sqrt(var_r) if var_r > 0 else 0.0
                if std_r > 1e-12:
                    # Annualize roughly assuming 15m cadence: 35040 intervals/year
                    sharpe = (mean_r / std_r) * math.sqrt(35040)

        win_rate = winning_trades / trades_completed if trades_completed > 0 else 0.0
        profit_factor = 0.0
        gross_wins = sum(ev.realized_pnl_usdt for ev in portfolio.trade_history if ev.realized_pnl_usdt > 0)
        gross_losses = abs(sum(ev.realized_pnl_usdt for ev in portfolio.trade_history if ev.realized_pnl_usdt < 0))
        if gross_losses > 0:
            profit_factor = gross_wins / gross_losses
        elif gross_wins > 0:
            profit_factor = float("inf")

        return SimulationSummary(
            initial_cash=self.initial_cash,
            final_equity=final_eq,
            gross_pnl_usdt=gross_pnl_accum,
            total_fees_usdt=total_fees,
            total_funding_usdt=total_funding,
            net_pnl_usdt=net_pnl,
            net_return_pct=net_return_pct,
            max_drawdown_usdt=max_dd_usdt,
            max_drawdown_pct=max_dd_pct,
            total_trades=trades_completed,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe,
            trade_events=portfolio.trade_history,
            equity_curve=equity_curve,
        )
