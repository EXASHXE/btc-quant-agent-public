from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from ..domain import Candle
from .execution_model import (
    CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE,
    CAUSAL_LIQUIDITY_UNAVAILABLE,
    LIMIT_INTRABAR_TOUCH_AMBIGUOUS,
    ConditionalTriggerTime,
    ExecutionModel,
)
from .fee_model import FeeModel
from .funding import FundingModel, FundingSettlement
from .metrics import (
    ResultCompleteness,
    ReturnMetricsContract,
    SimulationSummary,
    TerminalPolicy,
    summarize_ledger,
)
from .policy import OrderType, TradePolicy
from .portfolio import Portfolio
from .signal import InformationSignal
from .trade_event import TradeAction


class AmbiguousExecutionRejectionError(RuntimeError):
    """Raised when OHLC data cannot resolve a material execution ordering."""


class AmbiguousEntryRejectionError(AmbiguousExecutionRejectionError):
    """Raised when an entry fill time is not identifiable from OHLC data."""


class AmbiguousExitRejectionError(AmbiguousExecutionRejectionError):
    """Raised when OHLC data cannot resolve a material intrabar exit ordering."""


class CausalLiquidityRejectionError(ValueError):
    """Raised when a fill lacks liquidity observable by its fill boundary."""


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
        *,
        metrics_contract: ReturnMetricsContract | None = None,
        terminal_policy: TerminalPolicy = TerminalPolicy.MARK_TO_MARKET_OPEN,
    ) -> SimulationSummary:
        terminal_policy = TerminalPolicy(terminal_policy)
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
                profit_factor=None,
                sharpe_ratio=None,
                completeness=ResultCompleteness.INCOMPLETE_DATA,
                terminal_policy=terminal_policy,
            )

        portfolio = Portfolio(initial_cash=self.initial_cash)
        equity_curve: list[tuple[int, float]] = []
        notional_curve: list[tuple[int, float]] = []

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
        active_trailing_armed_time: int | None = None
        active_signal_id: str = ""

        # Pending fills queue: future fills that have not yet reached fill_timestamp_ms
        pending_fills: list[dict[str, Any]] = []

        def _raise_on_causal_liquidity_rejection(result: Any) -> None:
            if result.rejection_reason in {
                CAUSAL_LIQUIDITY_UNAVAILABLE,
                CAUSAL_LIQUIDITY_NOT_YET_AVAILABLE,
            }:
                raise CausalLiquidityRejectionError(
                    "SPREAD_AND_IMPACT requires causal current_spread_bps and "
                    "timestamped liquidity available by fill, or a declared adverse scenario"
                )

        def _apply_fill(pf: dict[str, Any], sym: str) -> bool:
            """Apply confirmed fill to portfolio ledger unconditionally (AR4)."""
            nonlocal active_trade_entry_time, active_trade_entry_price
            nonlocal active_trade_peak_price, active_trade_trough_price
            nonlocal active_trailing_armed_time
            nonlocal active_signal_id

            is_open = pf["action"] in (TradeAction.OPEN_LONG, TradeAction.OPEN_SHORT)

            portfolio.apply_trade(
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
                metadata=pf.get("metadata"),
            )
            if is_open:
                active_trade_entry_time = pf["fill_timestamp_ms"]
                active_trade_entry_price = pf["price"]
                active_trade_peak_price = pf["price"]
                active_trade_trough_price = pf["price"]
                active_trailing_armed_time = pf["fill_timestamp_ms"]
                active_signal_id = pf["signal_id"]
            else:
                active_trade_entry_time = None
                active_trade_entry_price = None
                active_trade_peak_price = None
                active_trade_trough_price = None
                active_trailing_armed_time = None
                active_signal_id = ""

            _update_drawdown(portfolio.total_equity({sym: pf["price"]}))
            return True

        def _execute_exit(
            action: TradeAction,
            side: int,
            quantity: float,
            trigger_timestamp_ms: int,
            candle_index: int,
            trade_id: str,
            signal_id: str,
            current_spread_bps: float | None = None,
        ) -> bool:
            """Unified exit execution adapter routing every economic exit through ExecutionModel (AR6)."""
            exec_res = self.execution_model.simulate_order(
                signal_timestamp_ms=trigger_timestamp_ms,
                side=side,
                desired_quantity=quantity,
                order_type=OrderType.MARKET,
                future_candles=candles[candle_index:],
                current_spread_bps=current_spread_bps,
                observation_timestamp_ms=trigger_timestamp_ms,
            )
            _raise_on_causal_liquidity_rejection(exec_res)
            if not exec_res.is_filled:
                return False

            fill_info = {
                "fill_timestamp_ms": exec_res.fill_timestamp_ms,
                "action": action,
                "asset": candles[candle_index].symbol,
                "price": exec_res.fill_price,
                "quantity": exec_res.filled_quantity,
                "fee_usdt": exec_res.fee_usdt,
                "signal_id": signal_id,
                "trade_id": trade_id,
                "observation_timestamp_ms": exec_res.observation_timestamp_ms,
                "decision_timestamp_ms": exec_res.decision_timestamp_ms,
                "order_timestamp_ms": exec_res.order_timestamp_ms,
                "settlement_timestamp_ms": exec_res.settlement_timestamp_ms,
                "reservation_notional": 0.0,
                "metadata": dict(exec_res.metadata or {}),
            }
            if exec_res.fill_timestamp_ms <= trigger_timestamp_ms:
                _apply_fill(fill_info, candles[candle_index].symbol)
            else:
                pending_fills.append(fill_info)
            return True

        def _execute_conditional_exit(
            *,
            action: TradeAction,
            side: int,
            quantity: float,
            armed_timestamp_ms: int,
            trigger_observation_timestamp_ms: int,
            candle_index: int,
            reference_price: float,
            trigger_time: ConditionalTriggerTime,
            trade_id: str,
            signal_id: str,
            current_spread_bps: float | None = None,
        ) -> bool:
            """Route a pre-armed conditional through the unified execution model."""
            trigger_bar = candles[candle_index]
            exec_res = self.execution_model.simulate_conditional_market_fill(
                armed_timestamp_ms=armed_timestamp_ms,
                trigger_observation_timestamp_ms=trigger_observation_timestamp_ms,
                side=side,
                desired_quantity=quantity,
                reference_price=reference_price,
                trigger_bar=trigger_bar,
                trigger_time=trigger_time,
                current_spread_bps=current_spread_bps,
            )
            if not exec_res.is_filled:
                return False

            fill_info = {
                "fill_timestamp_ms": exec_res.fill_timestamp_ms,
                "action": action,
                "asset": trigger_bar.symbol,
                "price": exec_res.fill_price,
                "quantity": exec_res.filled_quantity,
                "fee_usdt": exec_res.fee_usdt,
                "signal_id": signal_id,
                "trade_id": trade_id,
                "observation_timestamp_ms": exec_res.observation_timestamp_ms,
                "decision_timestamp_ms": exec_res.decision_timestamp_ms,
                "order_timestamp_ms": exec_res.order_timestamp_ms,
                "settlement_timestamp_ms": exec_res.settlement_timestamp_ms,
                "reservation_notional": 0.0,
                "metadata": dict(exec_res.metadata or {}),
            }
            if exec_res.fill_timestamp_ms <= trigger_bar.open_time_ms:
                _apply_fill(fill_info, trigger_bar.symbol)
            else:
                pending_fills.append(fill_info)
            return True

        def _has_pending_exit(sym: str) -> bool:
            return any(
                pf["action"] in (TradeAction.CLOSE_LONG, TradeAction.CLOSE_SHORT) and pf["asset"] == sym
                for pf in pending_fills
            )

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
                    _apply_fill(pf, bar.symbol)
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

                # Signal reversal exit (AR6: route through _execute_exit)
                if has_active_pos and not _has_pending_exit(bar.symbol):
                    if self.policy.exit_rule.decay_exit_on_signal_reversal and (
                        (curr_pos_qty > 0 and sig.direction == -1) or (curr_pos_qty < 0 and sig.direction == 1)
                    ):
                        act = TradeAction.CLOSE_LONG if curr_pos_qty > 0 else TradeAction.CLOSE_SHORT
                        exit_side = -1 if curr_pos_qty > 0 else 1
                        rev_spread: float | None = None
                        if "spread_bps" in sig.metadata:
                            try:
                                rev_spread = float(sig.metadata["spread_bps"])
                            except (ValueError, TypeError):
                                rev_spread = float("nan")
                        _execute_exit(
                            action=act,
                            side=exit_side,
                            quantity=abs(curr_pos_qty),
                            trigger_timestamp_ms=bar.open_time_ms,
                            candle_index=i,
                            trade_id=f"EXIT_REV_{sig.signal_id}",
                            signal_id=sig.signal_id,
                            current_spread_bps=rev_spread,
                        )
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
                # AR1: Spread evidence must be explicit when max_spread_bps is binding; do not invent 0.0
                spread_bps: float | None = None
                if "spread_bps" in sig.metadata:
                    try:
                        spread_bps = float(sig.metadata["spread_bps"])
                    except (ValueError, TypeError):
                        spread_bps = float("nan")

                liquidity_volume_base: float | None = None
                liquidity_available_at_ms: int | None = None
                if "liquidity_volume_base" in sig.metadata:
                    try:
                        liquidity_volume_base = float(sig.metadata["liquidity_volume_base"])
                    except (ValueError, TypeError):
                        liquidity_volume_base = float("nan")
                if "liquidity_available_at_ms" in sig.metadata:
                    value = sig.metadata["liquidity_available_at_ms"]
                    if type(value) is int:
                        liquidity_available_at_ms = value

                # AR2: Causal volume sourcing at bar open; do not use current bar's future volume
                vol_usdt: float | None = None
                if "volume_usdt" in sig.metadata:
                    try:
                        vol_usdt = float(sig.metadata["volume_usdt"])
                    except (ValueError, TypeError):
                        vol_usdt = float("nan")
                elif i > 0 and candles[i - 1].close_time_ms <= bar.open_time_ms:
                    prev_bar = candles[i - 1]
                    if prev_bar.quote_volume > 0:
                        vol_usdt = float(prev_bar.quote_volume)
                    elif prev_bar.volume > 0:
                        vol_usdt = float(prev_bar.volume * prev_bar.close)
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
                    ex_ante_price: float | None = lim_price
                else:
                    ex_ante_price = self.execution_model.fee_model.worst_case_price_bound(
                        reference_price=bar.open,
                        side=side,
                        current_spread_bps=spread_bps,
                    )

                # AR3, AR4: If no finite deterministic ex-ante bound exists, fail closed before submission
                if ex_ante_price is None or not math.isfinite(ex_ante_price) or ex_ante_price <= 0:
                    continue

                # Pre-order Gross Exposure Check using ex-ante reservation notional
                order_gross = qty * ex_ante_price
                active_gross = abs(portfolio.get_position_quantity(bar.symbol)) * bar.open
                pending_gross = sum(
                    pf.get("reservation_notional", pf["quantity"] * pf["price"])
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
                    current_spread_bps=spread_bps,
                    observation_timestamp_ms=sig.timestamp_ms,
                    max_fill_notional=order_gross,
                    causal_liquidity_volume_base=liquidity_volume_base,
                    causal_liquidity_available_at_ms=liquidity_available_at_ms,
                )
                _raise_on_causal_liquidity_rejection(exec_res)
                if exec_res.rejection_reason == LIMIT_INTRABAR_TOUCH_AMBIGUOUS:
                    metadata = exec_res.metadata or {}
                    raise AmbiguousEntryRejectionError(
                        "Ambiguous LIMIT entry touch ordering for "
                        f"{bar.symbol} bar "
                        f"[{metadata.get('ambiguity_window_open_ms')}, "
                        f"{metadata.get('ambiguity_window_close_ms')}]; "
                        "OHLC extrema cannot timestamp the fill"
                    )
                if exec_res.is_filled:
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
                        "reservation_notional": order_gross,
                        "metadata": {
                            **dict(exec_res.metadata or {}),
                            "reservation_notional": order_gross,
                        },
                    }
                    if exec_res.fill_timestamp_ms <= bar.open_time_ms:
                        _apply_fill(fill_info, bar.symbol)
                    else:
                        pending_fills.append(fill_info)

            # 4. Gap conditionals use observable opening-price evidence. The
            # order was armed before the bar path, so post-signal latency does not apply.
            pos_qty = portfolio.get_position_quantity(bar.symbol)
            if (
                abs(pos_qty) > 1e-12
                and active_trade_entry_price is not None
                and active_trade_entry_time is not None
                and not _has_pending_exit(bar.symbol)
            ):
                is_long = pos_qty > 0
                gap_reason = ""
                gap_armed_time = active_trade_entry_time
                if self.policy.exit_rule.stop_loss_pct is not None:
                    sl_pct = self.policy.exit_rule.stop_loss_pct
                    if is_long:
                        sl_level = active_trade_entry_price * (1.0 - sl_pct)
                        if bar.open <= sl_level:
                            gap_reason = "STOP_LOSS"
                    else:
                        sl_level = active_trade_entry_price * (1.0 + sl_pct)
                        if bar.open >= sl_level:
                            gap_reason = "STOP_LOSS"

                if self.policy.exit_rule.trailing_stop_pct is not None:
                    prior_peak = active_trade_peak_price or active_trade_entry_price
                    prior_trough = active_trade_trough_price or active_trade_entry_price
                    ts_pct = self.policy.exit_rule.trailing_stop_pct
                    ts_level = (
                        prior_peak * (1.0 - ts_pct)
                        if is_long
                        else prior_trough * (1.0 + ts_pct)
                    )
                    trailing_gap = bar.open <= ts_level if is_long else bar.open >= ts_level
                    if trailing_gap and not gap_reason:
                        gap_reason = "TRAILING_STOP"
                        gap_armed_time = active_trailing_armed_time or active_trade_entry_time

                if not gap_reason and self.policy.exit_rule.take_profit_pct is not None:
                    tp_pct = self.policy.exit_rule.take_profit_pct
                    tp_level = (
                        active_trade_entry_price * (1.0 + tp_pct)
                        if is_long
                        else active_trade_entry_price * (1.0 - tp_pct)
                    )
                    target_gap = bar.open >= tp_level if is_long else bar.open <= tp_level
                    if target_gap:
                        gap_reason = "TAKE_PROFIT"

                if gap_reason:
                    exit_act = TradeAction.CLOSE_LONG if is_long else TradeAction.CLOSE_SHORT
                    exit_side = -1 if is_long else 1
                    _execute_conditional_exit(
                        action=exit_act,
                        side=exit_side,
                        quantity=abs(pos_qty),
                        armed_timestamp_ms=gap_armed_time,
                        trigger_observation_timestamp_ms=bar.open_time_ms,
                        candle_index=i,
                        reference_price=bar.open,
                        trigger_time=ConditionalTriggerTime.BAR_OPEN_KNOWN,
                        trade_id=f"EXIT_GAP_{gap_reason}_{active_signal_id or bar.open_time_ms}",
                        signal_id=active_signal_id,
                    )

            # 5. Detect standing-order touches from the full OHLC bar. The
            # price reference is the pre-armed level, never the later close.
            standing_triggered = False
            pos_qty = portfolio.get_position_quantity(bar.symbol)
            if (
                abs(pos_qty) > 1e-12
                and active_trade_entry_price is not None
                and active_trade_entry_time is not None
                and active_trade_entry_time <= bar.open_time_ms
                and not _has_pending_exit(bar.symbol)
            ):
                is_long = pos_qty > 0
                adverse_triggers: list[tuple[str, float, int]] = []
                tp_trigger: tuple[str, float, int] | None = None

                if self.policy.exit_rule.stop_loss_pct is not None:
                    sl_pct = self.policy.exit_rule.stop_loss_pct
                    sl_level = (
                        active_trade_entry_price * (1.0 - sl_pct)
                        if is_long
                        else active_trade_entry_price * (1.0 + sl_pct)
                    )
                    if (is_long and bar.low <= sl_level) or (
                        not is_long and bar.high >= sl_level
                    ):
                        adverse_triggers.append(
                            ("STOP_LOSS", sl_level, active_trade_entry_time)
                        )

                if self.policy.exit_rule.trailing_stop_pct is not None:
                    prior_peak = active_trade_peak_price or active_trade_entry_price
                    prior_trough = active_trade_trough_price or active_trade_entry_price
                    ts_pct = self.policy.exit_rule.trailing_stop_pct
                    ts_level = (
                        prior_peak * (1.0 - ts_pct)
                        if is_long
                        else prior_trough * (1.0 + ts_pct)
                    )
                    if (is_long and bar.low <= ts_level) or (
                        not is_long and bar.high >= ts_level
                    ):
                        adverse_triggers.append(
                            (
                                "TRAILING_STOP",
                                ts_level,
                                active_trailing_armed_time or active_trade_entry_time,
                            )
                        )

                if self.policy.exit_rule.take_profit_pct is not None:
                    tp_pct = self.policy.exit_rule.take_profit_pct
                    tp_level = (
                        active_trade_entry_price * (1.0 + tp_pct)
                        if is_long
                        else active_trade_entry_price * (1.0 - tp_pct)
                    )
                    if (is_long and bar.high >= tp_level) or (
                        not is_long and bar.low <= tp_level
                    ):
                        tp_trigger = ("TAKE_PROFIT", tp_level, active_trade_entry_time)

                chosen_trigger: tuple[str, float, int] | None = None
                if adverse_triggers:
                    # If multiple adverse stops touched, select the worse price
                    # symmetrically: lowest for LONG, highest for SHORT.
                    chosen_trigger = (
                        min(adverse_triggers, key=lambda item: item[1])
                        if is_long
                        else max(adverse_triggers, key=lambda item: item[1])
                    )
                    if tp_trigger is not None:
                        if self.policy.exit_rule.ambiguous_exit_handling == "REJECT_AMBIGUOUS":
                            raise AmbiguousExitRejectionError(
                                f"Ambiguous exit collision at bar close_time_ms={bar.close_time_ms}: "
                                f"both an adverse stop and Take Profit triggered in the same "
                                f"candle for {bar.symbol}"
                            )
                        chosen_trigger = (
                            f"{chosen_trigger[0]}_COLLISION",
                            chosen_trigger[1],
                            chosen_trigger[2],
                        )
                elif tp_trigger is not None:
                    chosen_trigger = tp_trigger

                if chosen_trigger is not None:
                    standing_triggered = True
                    ambiguous_funding = next(
                        (
                            event
                            for event in sorted_funding[fund_idx:]
                            if bar.open_time_ms < event.timestamp_ms <= bar.close_time_ms
                            and self.funding_model.calculate_cashflow(
                                position_quantity=pos_qty,
                                mark_price=event.mark_price,
                                funding_rate=event.funding_rate,
                            )
                            != 0.0
                        ),
                        None,
                    )
                    if ambiguous_funding is not None:
                        raise AmbiguousExitRejectionError(
                            "Ambiguous trigger/funding ordering for standing exit in "
                            f"{bar.symbol} bar [{bar.open_time_ms}, {bar.close_time_ms}] "
                            f"with funding at {ambiguous_funding.timestamp_ms}"
                        )

                    exit_reason, reference_price, armed_time = chosen_trigger
                    exit_act = TradeAction.CLOSE_LONG if is_long else TradeAction.CLOSE_SHORT
                    exit_side = -1 if is_long else 1
                    _execute_conditional_exit(
                        action=exit_act,
                        side=exit_side,
                        quantity=abs(pos_qty),
                        armed_timestamp_ms=armed_time,
                        trigger_observation_timestamp_ms=bar.close_time_ms,
                        candle_index=i,
                        reference_price=reference_price,
                        trigger_time=ConditionalTriggerTime.INTRABAR_UNKNOWN,
                        trade_id=f"EXIT_{exit_reason}_{active_signal_id or bar.close_time_ms}",
                        signal_id=active_signal_id,
                    )

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
                    _apply_fill(pf, bar.symbol)
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

            # 2. Deterministic close-time expiry remains a discretionary market
            # exit. Conditional touches were already handled as standing orders.
            pos_qty = portfolio.get_position_quantity(bar.symbol)
            if (
                abs(pos_qty) > 1e-12
                and active_trade_entry_price is not None
                and active_trade_entry_time is not None
                and not _has_pending_exit(bar.symbol)
            ):
                is_long = pos_qty > 0
                holding_duration = bar.close_time_ms - active_trade_entry_time
                if holding_duration >= self.policy.exit_rule.max_holding_ms:
                    exit_action = TradeAction.CLOSE_LONG if is_long else TradeAction.CLOSE_SHORT
                    exit_side = -1 if is_long else 1
                    _execute_exit(
                        action=exit_action,
                        side=exit_side,
                        quantity=abs(pos_qty),
                        trigger_timestamp_ms=bar.close_time_ms,
                        candle_index=i,
                        trade_id=f"EXIT_MAX_HOLDING_{active_signal_id or bar.close_time_ms}",
                        signal_id=active_signal_id,
                    )

                if (
                    not standing_triggered
                    and active_trade_entry_time is not None
                    and active_trade_entry_price is not None
                    and abs(portfolio.get_position_quantity(bar.symbol)) > 1e-12
                    and active_trade_entry_time <= bar.open_time_ms
                    and not _has_pending_exit(bar.symbol)
                ):
                    prior_peak = active_trade_peak_price or active_trade_entry_price
                    prior_trough = active_trade_trough_price or active_trade_entry_price
                    active_trade_peak_price = max(prior_peak, bar.high)
                    active_trade_trough_price = min(prior_trough, bar.low)
                    active_trailing_armed_time = bar.close_time_ms

            # 3. Pending fills at bar.close_time_ms
            pending_fills.sort(key=lambda x: x["fill_timestamp_ms"])
            rem_fills = []
            for pf in pending_fills:
                if pf["fill_timestamp_ms"] == bar.close_time_ms:
                    _apply_fill(pf, bar.symbol)
                else:
                    rem_fills.append(pf)
            pending_fills = rem_fills

            # 4. Mark to Market at bar.close_time_ms
            curr_equity = portfolio.total_equity({bar.symbol: mark_price})
            _update_drawdown(curr_equity)
            equity_curve.append((bar.close_time_ms, curr_equity))
            notional_curve.append(
                (
                    bar.close_time_ms,
                    abs(portfolio.get_position_quantity(bar.symbol)) * mark_price,
                )
            )

        return summarize_ledger(
            initial_cash=self.initial_cash,
            events=portfolio.trade_history,
            equity_curve=equity_curve,
            final_asset=candles[-1].symbol,
            final_mark_price=candles[-1].close,
            interval_start_ms=candles[0].open_time_ms,
            interval_end_ms=candles[-1].close_time_ms,
            notional_curve=notional_curve,
            terminal_policy=terminal_policy,
            metrics_contract=metrics_contract,
            pending_order_count=len(pending_fills),
            max_drawdown_override=(max_dd_usdt, max_dd_pct),
        )
