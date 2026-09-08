from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..domain import Candle
from .execution_model import ExecutionModel
from .fee_model import FeeModel
from .funding import FundingModel, FundingSettlement
from .policy import OrderType, TradePolicy
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

        # Sort input signals and funding strictly by timestamp
        sorted_signals = sorted(signals, key=lambda s: s.timestamp_ms)
        sig_idx = 0
        n_signals = len(sorted_signals)

        sorted_funding = sorted(funding_events, key=lambda f: f.timestamp_ms)
        fund_idx = 0
        n_funding = len(sorted_funding)

        peak_equity = self.initial_cash
        max_dd_usdt = 0.0
        max_dd_pct = 0.0
        drawdown_halt = False

        def _update_drawdown(current_equity: float) -> None:
            nonlocal peak_equity, max_dd_usdt, max_dd_pct, drawdown_halt
            peak_equity = max(peak_equity, current_equity)
            dd_usdt = peak_equity - current_equity
            dd_pct = dd_usdt / peak_equity if peak_equity > 0 else 0.0
            max_dd_usdt = max(max_dd_usdt, dd_usdt)
            max_dd_pct = max(max_dd_pct, dd_pct)
            if max_dd_pct >= self.policy.risk_budget.max_drawdown_stop_pct:
                drawdown_halt = True

        active_trade_entry_time: int | None = None
        active_trade_entry_price: float | None = None
        active_trade_peak_price: float | None = None
        active_trade_trough_price: float | None = None
        active_signal_id: str = ""

        trades_completed = 0
        winning_trades = 0
        losing_trades = 0
        gross_pnl_accum = 0.0

        # Pending fills queue: future fills that have not yet reached fill_timestamp_ms
        pending_fills: list[dict[str, Any]] = []

        def _apply_pending_fill(pf: dict[str, Any], sym: str) -> bool:
            """Apply pending fill if within risk constraints, returning True if applied."""
            nonlocal active_trade_entry_time, active_trade_entry_price
            nonlocal active_trade_peak_price, active_trade_trough_price
            nonlocal active_signal_id, trades_completed, winning_trades
            nonlocal losing_trades, gross_pnl_accum

            is_open = pf["action"] in (TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT)
            if is_open:
                if drawdown_halt:
                    return False
                active_qty = portfolio.get_position_quantity(sym)
                active_count = 1 if abs(active_qty) > 1e-12 else 0
                if active_count + 1 > self.policy.risk_budget.max_open_positions:
                    return False
                curr_gross = abs(active_qty) * pf["price"]
                if curr_gross + (pf["quantity"] * pf["price"]) > self.policy.risk_budget.max_gross_exposure_usdt:
                    return False

            ev = portfolio.apply_trade(
                timestamp_ms=pf["fill_timestamp_ms"],
                action=pf["action"],
                asset=sym,
                price=pf["price"],
                quantity=pf["quantity"],
                fee_usdt=pf["fee_usdt"],
                signal_id=pf["signal_id"],
                trade_id=pf["trade_id"],
                observation_timestamp_ms=pf["observation_timestamp_ms"],
                decision_timestamp_ms=pf["decision_timestamp_ms"],
                order_timestamp_ms=pf["order_timestamp_ms"],
                settlement_timestamp_ms=pf["settlement_timestamp_ms"],
            )
            if is_open:
                active_trade_entry_time = pf["fill_timestamp_ms"]
                active_trade_entry_price = pf["price"]
                active_trade_peak_price = pf["price"]
                active_trade_trough_price = pf["price"]
                active_signal_id = pf["signal_id"]
            else:
                trades_completed += 1
                gross_pnl_accum += ev.realized_pnl_usdt
                if ev.realized_pnl_usdt - ev.fee_usdt > 0:
                    winning_trades += 1
                else:
                    losing_trades += 1
                active_trade_entry_time = None
                active_trade_entry_price = None
                active_trade_peak_price = None
                active_trade_trough_price = None
                active_signal_id = ""

            _update_drawdown(portfolio.total_equity({sym: pf["price"]}))
            return True

        for i, bar in enumerate(candles):
            mark_price = bar.close

            # -------------------------------------------------------------
            # A. Open Time Processing: bar.open_time_ms
            # -------------------------------------------------------------
            # 1. Funding settlements at or before bar.open_time_ms
            # (Tie-break rule: Funding settles BEFORE any fill occurring at bar.open_time_ms)
            while fund_idx < n_funding and sorted_funding[fund_idx].timestamp_ms <= bar.open_time_ms:
                fevent = sorted_funding[fund_idx]
                fund_idx += 1
                pos_qty = portfolio.get_position_quantity(bar.symbol)
                if abs(pos_qty) > 1e-12:
                    cf = self.funding_model.calculate_cashflow(
                        position_quantity=pos_qty,
                        mark_price=fevent.mark_price,
                        funding_rate=fevent.funding_rate,
                    )
                    portfolio.apply_funding(
                        timestamp_ms=fevent.timestamp_ms,
                        asset=bar.symbol,
                        cashflow_usdt=cf,
                        mark_price=fevent.mark_price,
                    )
                    _update_drawdown(portfolio.total_equity({bar.symbol: fevent.mark_price}))

            # 2. Apply pending fills scheduled for <= bar.open_time_ms
            pending_fills.sort(key=lambda x: x["fill_timestamp_ms"])
            rem_fills = []
            for pf in pending_fills:
                if pf["fill_timestamp_ms"] <= bar.open_time_ms:
                    _apply_pending_fill(pf, bar.symbol)
                else:
                    rem_fills.append(pf)
            pending_fills = rem_fills

            # 3. Process new signals arriving at or before bar.open_time_ms
            while sig_idx < n_signals and sorted_signals[sig_idx].timestamp_ms <= bar.open_time_ms:
                sig = sorted_signals[sig_idx]
                sig_idx += 1

                # Asset validation
                if sig.asset != bar.symbol:
                    continue

                curr_pos_qty = portfolio.get_position_quantity(bar.symbol)
                has_active_pos = abs(curr_pos_qty) > 1e-12

                # Signal reversal exit
                if has_active_pos:
                    if self.policy.exit_rule.decay_exit_on_signal_reversal and (
                        (curr_pos_qty > 0 and sig.direction == -1) or (curr_pos_qty < 0 and sig.direction == 1)
                    ):
                        act = TradeAction.CLOSE_LONG if curr_pos_qty > 0 else TradeAction.CLOSE_SHORT
                        exit_fee = self.fee_model.calculate_fee(abs(curr_pos_qty) * bar.open, is_maker=False)
                        ev = portfolio.apply_trade(
                            timestamp_ms=bar.open_time_ms,
                            action=act,
                            asset=bar.symbol,
                            price=bar.open,
                            quantity=abs(curr_pos_qty),
                            fee_usdt=exit_fee,
                            signal_id=sig.signal_id,
                            observation_timestamp_ms=sig.timestamp_ms,
                            decision_timestamp_ms=sig.timestamp_ms,
                            order_timestamp_ms=sig.timestamp_ms,
                            settlement_timestamp_ms=bar.open_time_ms,
                        )
                        trades_completed += 1
                        gross_pnl_accum += ev.realized_pnl_usdt
                        if ev.realized_pnl_usdt - exit_fee > 0:
                            winning_trades += 1
                        else:
                            losing_trades += 1
                        active_trade_entry_time = None
                        active_trade_entry_price = None
                        active_trade_peak_price = None
                        active_trade_trough_price = None
                        active_signal_id = ""
                        _update_drawdown(portfolio.total_equity({bar.symbol: bar.open}))
                    continue

                # Sticky drawdown halt blocks all new entries
                if drawdown_halt:
                    continue

                # Risk budget: max open positions check (active + pending)
                active_open_count = 1 if abs(portfolio.get_position_quantity(bar.symbol)) > 1e-12 else 0
                pending_open_count = sum(
                    1 for pf in pending_fills if pf["action"] in (TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT)
                )
                if active_open_count + pending_open_count >= self.policy.risk_budget.max_open_positions:
                    continue

                # Market state inputs (strictly causal)
                spread_bps = float(sig.metadata.get("spread_bps", 0.0))
                if "volume_usdt" in sig.metadata:
                    vol_usdt = float(sig.metadata["volume_usdt"])
                elif bar.quote_volume > 0:
                    vol_usdt = float(bar.quote_volume)
                elif bar.volume > 0:
                    vol_usdt = float(bar.volume * bar.open)
                else:
                    vol_usdt = 0.0

                regime = sig.metadata.get("regime")
                regime_str = str(regime) if regime is not None else None

                if not self.policy.should_enter(
                    signal=sig,
                    current_spread_bps=spread_bps,
                    current_volume_usdt=vol_usdt,
                    current_regime=regime_str,
                ):
                    continue

                current_eq = portfolio.total_equity({bar.symbol: mark_price})
                atr_val = sig.metadata.get("atr")
                if atr_val is not None:
                    try:
                        atr_float = float(atr_val)
                    except (ValueError, TypeError):
                        continue
                else:
                    atr_float = None

                try:
                    qty = self.policy.calculate_quantity(
                        current_price=bar.open,
                        portfolio_equity=current_eq,
                        current_atr=atr_float,
                    )
                except ValueError:
                    # Sizing computation failed closed (missing ATR or stop loss)
                    continue

                if qty <= 0 or not math.isfinite(qty):
                    continue

                side = 1 if sig.direction == 1 else -1
                lim_price: float | None = None
                if self.policy.entry_rule.order_type == OrderType.LIMIT:
                    lim_price = self.policy.entry_rule.calculate_limit_price(
                        reference_price=bar.open, side=side
                    )

                # Pre-order Gross Exposure Check
                order_ref_price = lim_price if lim_price is not None else bar.open
                order_gross = qty * order_ref_price
                active_gross = abs(portfolio.get_position_quantity(bar.symbol)) * bar.open
                pending_gross = sum(
                    pf["quantity"] * pf["price"]
                    for pf in pending_fills
                    if pf["action"] in (TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT)
                )
                if active_gross + pending_gross + order_gross > self.policy.risk_budget.max_gross_exposure_usdt:
                    continue

                exec_res = self.execution_model.simulate_order(
                    signal_timestamp_ms=sig.timestamp_ms,
                    side=side,
                    desired_quantity=qty,
                    order_type=self.policy.entry_rule.order_type,
                    future_candles=candles[i:],
                    limit_price=lim_price,
                    time_in_force_ms=self.policy.entry_rule.time_in_force_ms,
                    observation_timestamp_ms=sig.timestamp_ms,
                )
                if exec_res.is_filled:
                    # Post-fill Exposure Check against actual fill price & quantity
                    fill_gross = exec_res.filled_quantity * exec_res.fill_price
                    if active_gross + pending_gross + fill_gross > self.policy.risk_budget.max_gross_exposure_usdt:
                        continue

                    act = TradeAction.OPEN_LONG if side == 1 else TradeAction.OPEN_SHORT
                    fill_info = {
                        "fill_timestamp_ms": exec_res.fill_timestamp_ms,
                        "action": act,
                        "asset": bar.symbol,
                        "price": exec_res.fill_price,
                        "quantity": exec_res.filled_quantity,
                        "fee_usdt": exec_res.fee_usdt,
                        "signal_id": sig.signal_id,
                        "trade_id": f"ORD_{sig.signal_id}",
                        "observation_timestamp_ms": exec_res.observation_timestamp_ms,
                        "decision_timestamp_ms": exec_res.decision_timestamp_ms,
                        "order_timestamp_ms": exec_res.order_timestamp_ms,
                        "settlement_timestamp_ms": exec_res.settlement_timestamp_ms,
                    }
                    if exec_res.fill_timestamp_ms <= bar.open_time_ms:
                        portfolio.apply_trade(
                            timestamp_ms=exec_res.fill_timestamp_ms,
                            action=act,
                            asset=bar.symbol,
                            price=exec_res.fill_price,
                            quantity=exec_res.filled_quantity,
                            fee_usdt=exec_res.fee_usdt,
                            signal_id=sig.signal_id,
                            observation_timestamp_ms=exec_res.observation_timestamp_ms,
                            decision_timestamp_ms=exec_res.decision_timestamp_ms,
                            order_timestamp_ms=exec_res.order_timestamp_ms,
                            settlement_timestamp_ms=exec_res.settlement_timestamp_ms,
                        )
                        active_trade_entry_time = exec_res.fill_timestamp_ms
                        active_trade_entry_price = exec_res.fill_price
                        active_trade_peak_price = exec_res.fill_price
                        active_trade_trough_price = exec_res.fill_price
                        active_signal_id = sig.signal_id
                        _update_drawdown(portfolio.total_equity({bar.symbol: exec_res.fill_price}))
                    else:
                        pending_fills.append(fill_info)

            # 4. Check gap exits at bar.open_time_ms for position open at start
            pos_qty = portfolio.get_position_quantity(bar.symbol)
            if abs(pos_qty) > 1e-12 and active_trade_entry_price is not None:
                is_long = pos_qty > 0
                gap_exit = False
                gap_price = bar.open
                if self.policy.exit_rule.stop_loss_pct is not None:
                    sl_pct = self.policy.exit_rule.stop_loss_pct
                    if is_long:
                        sl_level = active_trade_entry_price * (1.0 - sl_pct)
                        if bar.open <= sl_level:
                            gap_exit = True
                            gap_price = bar.open
                    else:
                        sl_level = active_trade_entry_price * (1.0 + sl_pct)
                        if bar.open >= sl_level:
                            gap_exit = True
                            gap_price = bar.open

                if gap_exit:
                    exit_act = TradeAction.CLOSE_LONG if is_long else TradeAction.CLOSE_SHORT
                    exit_fee = self.fee_model.calculate_fee(abs(pos_qty) * gap_price, is_maker=False)
                    ev = portfolio.apply_trade(
                        timestamp_ms=bar.open_time_ms,
                        action=exit_act,
                        asset=bar.symbol,
                        price=gap_price,
                        quantity=abs(pos_qty),
                        fee_usdt=exit_fee,
                        signal_id=active_signal_id,
                        observation_timestamp_ms=bar.open_time_ms,
                        decision_timestamp_ms=bar.open_time_ms,
                        order_timestamp_ms=bar.open_time_ms,
                        settlement_timestamp_ms=bar.open_time_ms,
                    )
                    trades_completed += 1
                    gross_pnl_accum += ev.realized_pnl_usdt
                    if ev.realized_pnl_usdt - exit_fee > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
                    active_trade_entry_time = None
                    active_trade_entry_price = None
                    active_trade_peak_price = None
                    active_trade_trough_price = None
                    active_signal_id = ""
                    _update_drawdown(portfolio.total_equity({bar.symbol: gap_price}))

            # -------------------------------------------------------------
            # B. Intra-bar Processing: between open and close
            # -------------------------------------------------------------
            # 1. Intra-bar funding settlements (< bar.close_time_ms)
            while fund_idx < n_funding and sorted_funding[fund_idx].timestamp_ms < bar.close_time_ms:
                fevent = sorted_funding[fund_idx]
                fund_idx += 1
                pos_qty = portfolio.get_position_quantity(bar.symbol)
                if abs(pos_qty) > 1e-12:
                    cf = self.funding_model.calculate_cashflow(
                        position_quantity=pos_qty,
                        mark_price=fevent.mark_price,
                        funding_rate=fevent.funding_rate,
                    )
                    portfolio.apply_funding(
                        timestamp_ms=fevent.timestamp_ms,
                        asset=bar.symbol,
                        cashflow_usdt=cf,
                        mark_price=fevent.mark_price,
                    )
                    _update_drawdown(portfolio.total_equity({bar.symbol: fevent.mark_price}))

            # 2. Intra-bar pending fills (< bar.close_time_ms)
            pending_fills.sort(key=lambda x: x["fill_timestamp_ms"])
            rem_fills = []
            for pf in pending_fills:
                if pf["fill_timestamp_ms"] < bar.close_time_ms:
                    _apply_pending_fill(pf, bar.symbol)
                else:
                    rem_fills.append(pf)
            pending_fills = rem_fills

            # -------------------------------------------------------------
            # C. Close Time Processing: bar.close_time_ms
            # -------------------------------------------------------------
            # 1. Funding settlements at bar.close_time_ms (before exit/fills at close)
            while fund_idx < n_funding and sorted_funding[fund_idx].timestamp_ms == bar.close_time_ms:
                fevent = sorted_funding[fund_idx]
                fund_idx += 1
                pos_qty = portfolio.get_position_quantity(bar.symbol)
                if abs(pos_qty) > 1e-12:
                    cf = self.funding_model.calculate_cashflow(
                        position_quantity=pos_qty,
                        mark_price=fevent.mark_price,
                        funding_rate=fevent.funding_rate,
                    )
                    portfolio.apply_funding(
                        timestamp_ms=fevent.timestamp_ms,
                        asset=bar.symbol,
                        cashflow_usdt=cf,
                        mark_price=fevent.mark_price,
                    )

            # 2. Check position exits during this bar (Stop Loss / Take Profit / Trailing / Expiry)
            pos_qty = portfolio.get_position_quantity(bar.symbol)
            if abs(pos_qty) > 1e-12 and active_trade_entry_price is not None and active_trade_entry_time is not None:
                is_long = pos_qty > 0
                holding_duration = bar.close_time_ms - active_trade_entry_time

                prior_peak = active_trade_peak_price if active_trade_peak_price is not None else active_trade_entry_price
                prior_trough = active_trade_trough_price if active_trade_trough_price is not None else active_trade_entry_price

                sl_triggered = False
                tp_triggered = False
                sl_price = 0.0
                tp_price = 0.0

                if self.policy.exit_rule.stop_loss_pct is not None:
                    sl_pct = self.policy.exit_rule.stop_loss_pct
                    if is_long:
                        sl_level = active_trade_entry_price * (1.0 - sl_pct)
                        if bar.low <= sl_level:
                            sl_triggered = True
                            sl_price = min(bar.open, sl_level)
                    else:
                        sl_level = active_trade_entry_price * (1.0 + sl_pct)
                        if bar.high >= sl_level:
                            sl_triggered = True
                            sl_price = max(bar.open, sl_level)

                if self.policy.exit_rule.take_profit_pct is not None:
                    tp_pct = self.policy.exit_rule.take_profit_pct
                    if is_long:
                        tp_level = active_trade_entry_price * (1.0 + tp_pct)
                        if bar.high >= tp_level:
                            tp_triggered = True
                            tp_price = max(bar.open, tp_level)
                    else:
                        tp_level = active_trade_entry_price * (1.0 - tp_pct)
                        if bar.low <= tp_level:
                            tp_triggered = True
                            tp_price = min(bar.open, tp_level)

                ts_triggered = False
                ts_price = 0.0
                if not sl_triggered and not tp_triggered and self.policy.exit_rule.trailing_stop_pct is not None:
                    ts_pct = self.policy.exit_rule.trailing_stop_pct
                    if is_long:
                        ts_level = prior_peak * (1.0 - ts_pct)
                        if bar.low <= ts_level:
                            ts_triggered = True
                            ts_price = min(bar.open, ts_level)
                    else:
                        ts_level = prior_trough * (1.0 + ts_pct)
                        if bar.high >= ts_level:
                            ts_triggered = True
                            ts_price = max(bar.open, ts_level)

                time_triggered = False
                if (
                    not sl_triggered
                    and not tp_triggered
                    and not ts_triggered
                    and holding_duration >= self.policy.exit_rule.max_holding_ms
                ):
                    time_triggered = True

                exit_triggered = False
                chosen_exit_price = mark_price

                # Conservative adverse collision handling:
                # If both SL and TP trigger in same candle, Stop Loss is evaluated first
                if sl_triggered:
                    exit_triggered = True
                    chosen_exit_price = sl_price
                elif tp_triggered:
                    exit_triggered = True
                    chosen_exit_price = tp_price
                elif ts_triggered:
                    exit_triggered = True
                    chosen_exit_price = ts_price
                elif time_triggered:
                    exit_triggered = True
                    chosen_exit_price = bar.close

                if not exit_triggered:
                    active_trade_peak_price = max(prior_peak, bar.high)
                    active_trade_trough_price = min(prior_trough, bar.low)
                else:
                    exit_action = TradeAction.CLOSE_LONG if is_long else TradeAction.CLOSE_SHORT
                    exit_fee = self.fee_model.calculate_fee(
                        notional=abs(pos_qty) * chosen_exit_price, is_maker=False
                    )
                    ev = portfolio.apply_trade(
                        timestamp_ms=bar.close_time_ms,
                        action=exit_action,
                        asset=bar.symbol,
                        price=chosen_exit_price,
                        quantity=abs(pos_qty),
                        fee_usdt=exit_fee,
                        signal_id=active_signal_id,
                        observation_timestamp_ms=bar.close_time_ms,
                        decision_timestamp_ms=bar.close_time_ms,
                        order_timestamp_ms=bar.close_time_ms,
                        settlement_timestamp_ms=bar.close_time_ms,
                    )
                    trades_completed += 1
                    gross_pnl_accum += ev.realized_pnl_usdt
                    if ev.realized_pnl_usdt - exit_fee > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1

                    active_trade_entry_time = None
                    active_trade_entry_price = None
                    active_trade_peak_price = None
                    active_trade_trough_price = None
                    active_signal_id = ""
                    _update_drawdown(portfolio.total_equity({bar.symbol: chosen_exit_price}))

            # 3. Pending fills at bar.close_time_ms
            pending_fills.sort(key=lambda x: x["fill_timestamp_ms"])
            rem_fills = []
            for pf in pending_fills:
                if pf["fill_timestamp_ms"] == bar.close_time_ms:
                    _apply_pending_fill(pf, bar.symbol)
                else:
                    rem_fills.append(pf)
            pending_fills = rem_fills

            # 4. Mark to Market at bar.close_time_ms
            curr_equity = portfolio.total_equity({bar.symbol: mark_price})
            _update_drawdown(curr_equity)
            equity_curve.append((bar.close_time_ms, curr_equity))

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
