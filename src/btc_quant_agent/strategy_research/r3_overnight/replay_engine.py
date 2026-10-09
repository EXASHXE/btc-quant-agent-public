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
    Bar1h,
    Bar1m,
    Bar4h,
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
        # Per-candidate signal generators for complete state isolation
        self.signal_generators: dict[str, SignalGenerator] = {
            candidate.id: SignalGenerator() for candidate in self.registry.list_candidates()
        }
        self.signal_generator = SignalGenerator()  # Retained for backward compatibility

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

        # Collect and sort all marks causally by effective availability (B01)
        marks_by_sym: dict[str, list[MarkBar1m]] = {}
        for sym, m_list in marks_1m.items():
            sorted_m = sorted(m_list, key=lambda m: (max(m.close_ms, m.available_at_ms), m.close_ms))
            marks_by_sym[sym] = sorted_m

        mark_idx_by_sym: dict[str, int] = {sym: 0 for sym in marks_by_sym}
        last_seen_mark_by_sym: dict[str, MarkBar1m] = {}

        # Running lists of completed 1m bars for aggregation
        accumulated_1m: dict[str, list[Bar1m]] = {sym: [] for sym in bars_1m}

        # Step minute by minute
        for current_open_ms in sorted_minutes:
            current_bars = bars_by_minute.get(current_open_ms, {})

            # Causal mark stream: collect marks that became effectively available at or before current_open_ms
            # Invariant B01: newest completed close_ms wins among eligible marks; older arrivals cannot overwrite
            current_marks: dict[str, MarkBar1m] = {}
            for sym, m_list in marks_by_sym.items():
                idx = mark_idx_by_sym[sym]
                newly_eligible: list[MarkBar1m] = []
                while idx < len(m_list):
                    m = m_list[idx]
                    effective_avail = max(m.close_ms, m.available_at_ms)
                    if effective_avail <= current_open_ms:
                        newly_eligible.append(m)
                        idx += 1
                    else:
                        break
                mark_idx_by_sym[sym] = idx

                if newly_eligible:
                    # Select mark with highest completed close_ms, tiebreak with greatest available_at_ms
                    best_eligible = max(
                        newly_eligible,
                        key=lambda m: (m.close_ms, m.available_at_ms),
                    )
                    prev_seen = last_seen_mark_by_sym.get(sym)
                    if prev_seen is None or best_eligible.close_ms >= prev_seen.close_ms:
                        current_marks[sym] = best_eligible
                        last_seen_mark_by_sym[sym] = best_eligible

            # Append current bars to history
            for sym, bar in current_bars.items():
                accumulated_1m[sym].append(bar)

            # Check if this minute represents a decision availability point
            # Hourly decision occurs at hour end + 60s
            signals_by_candidate: dict[str, SignalEvent | None] = {}
            if current_open_ms % 3_600_000 == 60_000:
                # 60s after whole hour close: compute hourly signals
                # Bars available are strictly completed bars up to current_open_ms - 60_000
                decision_time = (current_open_ms // 3_600_000) * 3_600_000
                aggregated_by_sym: dict[str, tuple[list[Bar1h], list[Bar4h]]] = {}
                for sym, hist in accumulated_1m.items():
                    completed_1m = [b for b in hist if b.close_ms <= current_open_ms - 60_000]
                    bars_1h = aggregate_1m_to_1h(completed_1m)
                    bars_4h = aggregate_1m_to_4h(completed_1m)

                    # Prevent future leak: verify no bar in bars_1h has close > decision_time
                    for bh in bars_1h:
                        if bh.close_ms > decision_time:
                            raise FuturePriceLeakError(
                                f"Future price leak detected: 1h bar closed at {bh.close_ms} "
                                f"which is after decision time {decision_time}"
                            )
                    aggregated_by_sym[sym] = (bars_1h, bars_4h)

                for candidate in self.registry.list_candidates():
                    if candidate.id in self.ineligible_candidates:
                        continue

                    for sym in candidate.symbols:
                        if sym not in aggregated_by_sym:
                            continue
                        bars_1h, bars_4h = aggregated_by_sym[sym]
                        book = self.books[candidate.id]
                        gen = self.signal_generators[candidate.id]
                        sig = gen.evaluate_hourly_decision(
                            candidate=candidate,
                            symbol=sym,
                            bars_1h=bars_1h,
                            bars_4h=bars_4h,
                            last_exit_time_ms=book.last_economic_exit_time_ms.get(sym),
                            last_entry_4h_time_ms=book.last_entry_4h_time_ms.get(sym),
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
