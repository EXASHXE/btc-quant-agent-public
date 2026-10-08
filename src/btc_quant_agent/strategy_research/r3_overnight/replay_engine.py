"""Replay engine orchestrating point-in-time synthetic simulations across 8 candidate books."""

import hashlib
import json

from btc_quant_agent.strategy_research.r3_overnight.candidate_registry import (
    CandidateRegistry,
    get_default_registry,
)
from btc_quant_agent.strategy_research.r3_overnight.indicators import (
    aggregate_1m_to_1h,
    aggregate_1m_to_4h,
)
from btc_quant_agent.strategy_research.r3_overnight.ledger import VirtualBook
from btc_quant_agent.strategy_research.r3_overnight.signals import SignalGenerator
from btc_quant_agent.strategy_research.r3_overnight.types import (
    Bar1m,
    CompletedTrade,
    CostScenario,
    MarkBar1m,
    SignalEvent,
)


class FuturePriceLeakError(ValueError):
    """Raised when an attempt is made to access or leak future bars into a decision."""


class ReplayEngine:
    """
    Deterministic point-in-time replay engine.
    Instantiates isolated virtual books for each candidate under BASE and STRESS scenarios.
    """

    def __init__(
        self,
        cost_scenario: CostScenario = CostScenario.BASE,
        registry: CandidateRegistry | None = None,
    ) -> None:
        self.cost_scenario = cost_scenario
        self.registry = registry or get_default_registry()
        self.signal_generator = SignalGenerator()

        # Instantiate separate virtual books for each of the 8 candidates
        self.books: dict[str, VirtualBook] = {}
        for candidate in self.registry.list_candidates():
            self.books[candidate.id] = VirtualBook(
                candidate_id=candidate.id,
                cost_scenario=cost_scenario,
            )

        # Ineligible candidate IDs under this cost scenario
        self.ineligible_candidates: dict[str, str] = {}
        for candidate in self.registry.list_candidates():
            is_elig, reason = self.registry.check_geometry_eligibility(candidate.id, cost_scenario)
            if not is_elig and reason:
                self.ineligible_candidates[candidate.id] = reason

    def run_simulation(
        self,
        bars_1m: dict[str, list[Bar1m]],
        marks_1m: dict[str, list[MarkBar1m]],
    ) -> dict[str, list[CompletedTrade]]:
        """
        Execute simulation minute by minute across the provided synthetic dataset.
        Enforces strict Point-In-Time causality and clock boundaries.
        """
        # Determine simulation time range from available 1m bars
        all_timestamps = set()
        for sym, b_list in bars_1m.items():
            for b in b_list:
                all_timestamps.add(b.timestamp_ms)

        if not all_timestamps:
            return {cid: [] for cid in self.books}

        sorted_minutes = sorted(all_timestamps)

        # Map bars by minute for fast lookup
        bars_by_minute: dict[int, dict[str, Bar1m]] = {}
        for sym, b_list in bars_1m.items():
            for b in b_list:
                bars_by_minute.setdefault(b.timestamp_ms, {})[sym] = b

        marks_by_minute: dict[int, dict[str, MarkBar1m]] = {}
        for sym, m_list in marks_1m.items():
            for m in m_list:
                marks_by_minute.setdefault(m.timestamp_ms, {})[sym] = m

        # Running lists of completed 1m bars for aggregation
        accumulated_1m: dict[str, list[Bar1m]] = {sym: [] for sym in bars_1m}

        # Step minute by minute
        for current_open_ms in sorted_minutes:
            current_bars = bars_by_minute.get(current_open_ms, {})
            current_marks = marks_by_minute.get(current_open_ms, {})

            # Append current bars to history
            for sym, bar in current_bars.items():
                accumulated_1m[sym].append(bar)

            # Check if this minute represents a decision availability point
            # Hourly decision occurs at hour end + 60s
            signals_by_candidate: dict[str, SignalEvent | None] = {}
            if current_open_ms % 3_600_000 == 60_000:
                # 60s after whole hour close: compute hourly signals
                # Bars available are strictly completed bars up to current_open_ms - 60_000
                for candidate in self.registry.list_candidates():
                    if candidate.id in self.ineligible_candidates:
                        continue

                    # For simplicity, evaluate symbol BTCUSDT
                    for sym in candidate.symbols:
                        if sym not in accumulated_1m:
                            continue
                        completed_1m = [b for b in accumulated_1m[sym] if b.close_ms <= current_open_ms - 60_000]
                        bars_1h = aggregate_1m_to_1h(completed_1m)
                        bars_4h = aggregate_1m_to_4h(completed_1m)

                        # Prevent future leak: verify no bar in bars_1h has close > decision_time
                        decision_time = (current_open_ms // 3_600_000) * 3_600_000
                        for bh in bars_1h:
                            if bh.close_ms > decision_time:
                                raise FuturePriceLeakError(
                                    f"Future price leak detected: 1h bar closed at {bh.close_ms} "
                                    f"which is after decision time {decision_time}"
                                )

                        sig = self.signal_generator.evaluate_hourly_decision(
                            candidate=candidate,
                            symbol=sym,
                            bars_1h=bars_1h,
                            bars_4h=bars_4h,
                        )
                        if sig:
                            signals_by_candidate[candidate.id] = sig
                            break

            # Step each book through the 8 stages
            for cid, book in self.books.items():
                if cid in self.ineligible_candidates:
                    continue
                cand_def = self.registry.get_candidate(cid)
                hourly_sig = signals_by_candidate.get(cid)
                book.step_minute_open(
                    open_time_ms=current_open_ms,
                    bars_1m=current_bars,
                    marks_1m=current_marks,
                    candidate_max_hold_ms=cand_def.holding_ms,
                    hourly_signal=hourly_sig,
                )

        return {cid: book.completed_trades for cid, book in self.books.items()}

    def compute_deterministic_receipt_hash(self) -> str:
        """Compute SHA256 receipt hash of book states and trade logs."""
        hasher = hashlib.sha256()
        for cid in sorted(self.books.keys()):
            book = self.books[cid]
            record = {
                "candidate_id": cid,
                "cost_scenario": self.cost_scenario.value,
                "cash": str(book.cash),
                "decision_equity": str(book.decision_equity),
                "economic_equity": str(book.economic_equity),
                "high_water_equity": str(book.high_water_equity),
                "killed": book.killed,
                "kill_reason": book.kill_reason,
                "completed_trade_count": len(book.completed_trades),
                "funding_charge_count": len(book.funding_charges),
                "ineligible_status": self.ineligible_candidates.get(cid),
            }
            hasher.update(json.dumps(record, sort_keys=True).encode("utf-8"))
        return hasher.hexdigest()
