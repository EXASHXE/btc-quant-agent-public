"""Consequence and coverage matrix generator for P2 metadata reconnaissance."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from scripts.strategy_research.p2_metadata_locator.config import (
    SELECTED_SAFE_MONTHS,
    CoverageStatus,
    SourceRole,
)
from scripts.strategy_research.p2_metadata_locator.scanner import ScanExecutionReceipt


@dataclass
class MatrixCell:
    symbol: str
    month: str
    role: SourceRole
    status: CoverageStatus
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "month": self.month,
            "role": self.role.value if isinstance(self.role, SourceRole) else str(self.role),
            "status": self.status.value if isinstance(self.status, CoverageStatus) else str(self.status),
            "reason": self.reason,
        }


@dataclass
class FeasibilityEvaluation:
    option_a_three_symbol_feasible: bool
    option_a_verdict: str
    option_a_rationale: str
    btc_only_amendment_feasible: bool
    btc_only_verdict: str
    btc_only_rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ConsequenceMatrix:
    task_id: str
    canonical_root_status: str
    symbols: list[str]
    safe_months: list[str]
    roles: list[str]
    grid: list[MatrixCell]
    protected_holdout_summary: dict[str, Any]
    feasibility: FeasibilityEvaluation

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "canonical_root_status": self.canonical_root_status,
            "symbols": self.symbols,
            "safe_months": self.safe_months,
            "roles": self.roles,
            "grid": [c.to_dict() for c in self.grid],
            "protected_holdout_summary": self.protected_holdout_summary,
            "feasibility": self.feasibility.to_dict(),
        }


def generate_coverage_matrix(receipt: ScanExecutionReceipt) -> ConsequenceMatrix:
    """Generate the full BTC/ETH/SOL x safe months x roles matrix based on scan receipt."""
    symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    roles = [
        SourceRole.KLINE_1M,
        SourceRole.TRUE_MARK_1M,
        SourceRole.FUNDING_RATES,
        SourceRole.SYMBOL_FILTERS_FEES,
        SourceRole.SPREAD_IMPACT_LICENCE,
    ]

    confirmed_root = receipt.confirmed_root
    grid: list[MatrixCell] = []

    # Map BTC probe results if any candidate was checked
    btc_probe_map = {}
    if receipt.evaluated_roots:
        # Check if any candidate found positive matches
        for ev in receipt.evaluated_roots:
            if ev.safe_partitions_checked:
                btc_probe_map = ev.safe_partitions_checked
                if ev.certainty.value == "ROOT_CONFIRMED_FOR_SELECTED_METADATA":
                    break

    for sym in symbols:
        for month in SELECTED_SAFE_MONTHS:
            for role in roles:
                if sym == "BTCUSDT":
                    # Check probe outcome
                    probe = btc_probe_map.get(month)
                    if confirmed_root and probe and probe.physical_exists:
                        if role == SourceRole.KLINE_1M:
                            status = CoverageStatus.PRESENT_METADATA_ONLY
                            reason = f"Verified physical presence under confirmed root {confirmed_root}"
                        elif role == SourceRole.TRUE_MARK_1M:
                            # True continuous 1m Mark price is distinct from Kline and daily repairs
                            status = CoverageStatus.UNKNOWN_UNPROBED
                            reason = "1m Kline present; continuous 1m Mark price source distinct and unverified"
                        elif role == SourceRole.FUNDING_RATES:
                            status = CoverageStatus.UNKNOWN_UNPROBED
                            reason = "Separate monthly funding rate archive unverified under root"
                        elif role == SourceRole.SYMBOL_FILTERS_FEES:
                            status = CoverageStatus.UNKNOWN_UNPROBED
                            reason = "Historical tick/lot/fee metadata unverified"
                        else:
                            status = CoverageStatus.UNKNOWN_UNPROBED
                            reason = "Noncommercial licence/rights unadmitted"
                    else:
                        status = CoverageStatus.UNKNOWN_UNPROBED
                        reason = "Canonical local root unknown in bounded project mounts; unprobed, not absent"
                elif sym in ("ETHUSDT", "SOLUSDT"):
                    # ETH and SOL have no approved source manifests or verified physical paths
                    status = CoverageStatus.UNKNOWN_UNPROBED
                    reason = f"No approved source manifest, schema, or verified physical path for {sym}"

                grid.append(
                    MatrixCell(
                        symbol=sym,
                        month=month,
                        role=role,
                        status=status,
                        reason=reason,
                    )
                )

    # Protected holdout summary
    protected_holdout_summary = {
        "holdout_window": "[2026-02-01, 2026-08-01)",
        "protected_months": ["2026-02", "2026-03", "2026-04", "2026-05", "2026-06", "2026-07"],
        "status": CoverageStatus.PROTECTED_EXCLUDED.value,
        "access_count": receipt.counters.protected_body_or_partition_accesses,
        "policy": "Strictly sealed; zero file open, zero lstat inside protected subtree.",
    }

    # Feasibility evaluation
    option_a_feasible = False
    option_a_verdict = "OPTION_A_NOT_FEASIBLE"
    option_a_rationale = (
        "Option A requires three symbols (BTC, ETH, SOL) across the selected folds. "
        "ETH and SOL sources, licenses, and local paths are completely unadmitted and unknown. "
        "Even for BTC, canonical local root is unconfirmed without owner path binding. "
        "Option A cannot be executed without admitted multi-asset sources and confirmed local root."
    )

    btc_only_feasible = False
    btc_only_verdict = "BTC_ONLY_AMENDMENT_BLOCKED_BY_PROTOCOL_GATE"
    btc_only_rationale = (
        "A prospective BTC-only diagnostic amendment would evaluate only 1 of 3 assets (33.3%). "
        "The frozen research protocol strictly enforces a >=60% positive-support screen across "
        "the asset universe. 1/3 = 33.3% < 60%, so BTC-only fails the support gate. "
        "This boundary cannot be quietly waived by workers; it requires explicit Controller amendment."
    )

    feasibility = FeasibilityEvaluation(
        option_a_three_symbol_feasible=option_a_feasible,
        option_a_verdict=option_a_verdict,
        option_a_rationale=option_a_rationale,
        btc_only_amendment_feasible=btc_only_feasible,
        btc_only_verdict=btc_only_verdict,
        btc_only_rationale=btc_only_rationale,
    )

    return ConsequenceMatrix(
        task_id=receipt.task_id,
        canonical_root_status="CONFIRMED" if confirmed_root else "UNKNOWN",
        symbols=symbols,
        safe_months=SELECTED_SAFE_MONTHS,
        roles=[r.value for r in roles],
        grid=grid,
        protected_holdout_summary=protected_holdout_summary,
        feasibility=feasibility,
    )
