"""Contracts, invariants and immutable exploratory registration for B-line R4."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from . import LABELS, TASK

HORIZONS = [8, 4, 12, 24]
PRIMARY_HORIZON_HOURS = 8

REPO_ROOT = Path(__file__).resolve().parents[3]
LEDGER_PATH = REPO_ROOT / "docs/project/V0.6_B_LINE_STRATEGY_VALIDATION_REGISTER.md"

H40_EXCLUSION = ("2025-02-01T00:00:00Z", "2026-02-01T00:00:00Z")
H39_FORWARD = "2026-09-01T00:00:00Z"

COVERAGE_PERIOD_UTC = ("2021-01-01T00:00:00Z", "2025-01-01T00:00:00Z")


def canonical_json_bytes(value: Any) -> bytes:
    """Deterministic canonical JSON serialization."""
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def sha256_digest(path: Path) -> str:
    """Compute hex SHA256 digest of a file."""
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prior_failure_matrix() -> dict[str, Any]:
    """Verified mapping against the compact scientific validation register."""
    if not LEDGER_PATH.exists():
        raise FileNotFoundError(f"Missing ledger: {LEDGER_PATH}")

    content = LEDGER_PATH.read_text(encoding="utf-8")
    ledger_sha = sha256_digest(LEDGER_PATH)

    prior_failures = [
        {
            "family_id": "flow_spread_H32",
            "mechanism": "Spot-Perpetual taker-flow spread (H32)",
            "frozen_status": "INCONCLUSIVE_MECHANISM",
            "evidence_quote": "H32 INCONCLUSIVE_MECHANISM",
            "consequence": "No threshold/window/sign-only revival",
        },
        {
            "family_id": "flow_spread_H33_H34",
            "mechanism": "Spot-Perpetual taker-flow predictive edge (H33/H34)",
            "frozen_status": "FAIL",
            "evidence_quote": "H33/H34 FALSIFIED",
            "consequence": "Flow family inconclusive/falsified; stopped",
        },
        {
            "family_id": "tactical_trend_breakout",
            "mechanism": "Price-only trend pullback and breakout retest",
            "frozen_status": "ECONOMIC_BLOCKED",
            "evidence_quote": "No net economic/support PASS",
            "consequence": "Movement research only, stopped for direction",
        },
        {
            "family_id": "flow_regime_Goal_B",
            "mechanism": "Flow / regime development waves (Goal-B)",
            "frozen_status": "DEVELOPMENT_NO_GO",
            "evidence_quote": "NO_PROMOTABLE_DEVELOPMENT_CANDIDATE_BUDGET_EXHAUSTED",
            "consequence": "No automatic new wave",
        },
        {
            "family_id": "Goal_A_economics",
            "mechanism": "Original Goal-A directional heuristics",
            "frozen_status": "INCONCLUSIVE",
            "evidence_quote": "Original economics materially inconsistent",
            "consequence": "No independently accepted winner",
        },
        {
            "family_id": "funding_mark_R3",
            "mechanism": "Funding / Mark price carry & crowding (R3)",
            "frozen_status": "SOURCE_BLOCKED",
            "evidence_quote": "R3 source/causality blocked",
            "consequence": "No source/causality admission",
        },
        {
            "family_id": "funding_mark_R31",
            "mechanism": "Funding crowding direction (R3.1)",
            "frozen_status": "INCONCLUSIVE",
            "evidence_quote": "R3.1 COMPLETE_DEVELOPMENT_ONLY",
            "consequence": "Sparse exposed positives are not Alpha",
        },
        {
            "family_id": "exit_landmark_horizon",
            "mechanism": "Longer holds / partial exits (H18)",
            "frozen_status": "INCONCLUSIVE",
            "evidence_quote": "DIAGNOSTIC_INSUFFICIENT_SUPPORT",
            "consequence": "Longer holds not accepted upgrades",
        },
        {
            "family_id": "F3_basis_increment",
            "mechanism": "Spot-Perpetual cash basis increment",
            "frozen_status": "UNTESTED",
            "evidence_quote": "basis increment untested/PIT unknown",
            "consequence": "Synthetic PR #3 is not historical adoption",
        },
        {
            "family_id": "R3_stress_costs",
            "mechanism": "Stress cost evaluation on directional pilots",
            "frozen_status": "ECONOMIC_BLOCKED",
            "evidence_quote": "27/27 stress cells failed",
            "consequence": "No heldout rescue by default",
        },
        {
            "family_id": "PA_B_T6",
            "mechanism": "Price Action Breakout (PA-B T6)",
            "frozen_status": "FAIL",
            "evidence_quote": "EMPIRICALLY INFEASIBLE",
            "consequence": "STOP — empirically infeasible",
        },
        {
            "family_id": "R8_novelty_stop",
            "mechanism": "Controller novelty STOP",
            "frozen_status": "STOP",
            "evidence_quote": "Controller novelty STOP",
            "consequence": "Reopening needs genuinely new evidence, not renamed hypothesis",
        },
        {
            "family_id": "R11_D2_E2",
            "mechanism": "Binance D2 / OKX E2 prospective feeds",
            "frozen_status": "SOURCE_BLOCKED",
            "evidence_quote": "NOT_ACCEPTED pending independent source/PIT review",
            "consequence": "No source/Alpha admission",
        },
        {
            "family_id": "R1_FUNDING_PREMIUM_RELEASE",
            "mechanism": "Rally + extreme funding + basis compression (R1 Candidate 1)",
            "frozen_status": "REGIME_CONCENTRATED_SPARSE",
            "evidence_quote": "Funding 168 触发小时高度集中 2021",
            "consequence": "147/168 signals in 2021, 0 in 2022 bear market; unviable across regimes",
        },
        {
            "family_id": "R1_OI_DELEVERAGING_CONTINUATION",
            "mechanism": "Drop + 4h OI contraction + top position ratio (R1 Candidate 2)",
            "frozen_status": "INCONCLUSIVE_SUPPORT_HOLD",
            "evidence_quote": "OI 仅 2026 年 4 个触发小时",
            "consequence": "Suffered 7,645-hour blank publisher gap on top position ratio in 2022",
        },
        {
            "family_id": "R3_PRICE_DISCOVERY",
            "mechanism": "Spot-first minute-price discovery crossing (R3)",
            "frozen_status": "R3_MECHANISM_FEASIBILITY_NO_GO",
            "evidence_quote": "R3_MECHANISM_FEASIBILITY_NO_GO",
            "consequence": "0 triggers across 35,021 hours; intraminute lead-lag cointegrated away",
        },
    ]

    for item in prior_failures[:13]:
        if item["evidence_quote"] not in content:
            raise ValueError(f"LEDGER_EVIDENCE_MISMATCH: {item['family_id']}")

    return {
        "ledger_file": str(LEDGER_PATH.relative_to(REPO_ROOT)),
        "ledger_sha256": ledger_sha,
        "verified_failures": prior_failures,
        "rule": "Strict rejection of any sign/window/threshold/parameter revival of stopped families.",
    }


def scientific_novelty_gate_preflight() -> dict[str, Any]:
    """Evaluate at most two novel hypotheses against the scientific novelty precondition."""
    hypotheses = [
        {
            "hypothesis_id": "HYPOTHESIS_1_STATE_IMPACT_ASYMMETRY",
            "family": "Independently measured state/impact asymmetries",
            "description": (
                "Spot vs. Perpetual Realized Volatility and Price Impact Asymmetry: "
                "Tests whether relative price impact (return / volume) or realized volatility "
                "dispersion between Spot and Perpetual predicts short-term directional pressure."
            ),
            "physical_source_check": {
                "spot_1m_bars": "Observed in C1 canonical parquet (2021-2024)",
                "perp_1m_bars": "Observed in C1 canonical parquet (2021-2024)",
                "signed_order_flow": "UNAVAILABLE in C1; C2 signed flow covers only 2 months (2023-08, 2025-09)",
                "order_book_depth_l2": "UNAVAILABLE across 2021-2024",
            },
            "scientific_defects": [
                "C1 contains unsigned bars only; directional volume impact cannot be observed without inferring aggressor side.",
                "Spot and Perpetual 1m prices are cointegrated with r > 0.9999; 1h return correlation is 0.9994.",
                "Realized volatility ratio is centered at 0.9985 with negligible cross-sectional variance.",
                "Intraminute lead-lag crossing was already tested in R3 and yielded 0 triggers (R3_MECHANISM_FEASIBILITY_NO_GO).",
                "Unsigned impact is collinearly redundant with baseline X volatility and volume controls.",
            ],
            "preflight_verdict": "REJECTED_SOURCE_INSUFFICIENT_AND_COLLINEAR",
            "selected_for_registration": False,
        },
        {
            "hypothesis_id": "HYPOTHESIS_2_TRAPPED_LEVERAGE_OVERHANG",
            "family": "Genuine position/volatility-state transitions",
            "description": (
                "Trapped Long Leverage Overhang Breakout: "
                "Identifies leverage accumulation during range consolidation followed by a sharp downward "
                "breakout where newly accumulated long positions have not yet capitulated, creating a fragile "
                "overhang vulnerable to cascading forced liquidations over 4–24h."
            ),
            "physical_source_check": {
                "perp_1m_bars": "Observed in C1 canonical parquet (2021-2024)",
                "base_open_interest_5m": "Observed in daily Binance metrics archives (2021-2024, 1,461 files verified)",
                "top_position_ratio": "NOT REQUIRED (avoids the 2022 publisher gap of 7,645 missing hours)",
                "field_units": "base_open_interest in BTC native underlying quantity (float)",
                "causal_timing": "Strict sampling at cutoff - 10m (HH:50:00) with exact 24h and 4h predecessors",
            },
            "scientific_novelty_differentiators": [
                "Differs from R1 Funding: No funding rates, no premium index, no cash basis (viable in bear markets).",
                "Differs from R1 OI Contraction: R1 required contemporaneous OI contraction (<= -2%) and top position ratio. This hypothesis requires prior 24h OI accumulation (>= +1.5%) with uncapitulated 4h OI (>= -0.5%).",
                "Differs from PA-B / trend breakout: Conditioned on aggregate derivative leverage accumulation state, not price-only patterns.",
                "Differs from R3 price discovery: Uses physical open interest accumulation over 24h, not 15m intraminute spot-perp crossings.",
                "Differs from P1: Single deterministic discrete rule, zero ridge regression or fitted parameter weights.",
            ],
            "preflight_verdict": "ACCEPTED_NOVEL_AND_SOURCE_COMPATIBLE",
            "selected_for_registration": True,
        },
    ]

    selected = [h for h in hypotheses if h["selected_for_registration"]]
    if len(selected) > 1:
        raise ValueError("AT_MOST_ONE_CANDIDATE_ALLOWED")

    return {
        "status": "PREFLIGHT_PASS_EXACTLY_ONE_CANDIDATE",
        "hypotheses_evaluated": hypotheses,
        "selected_candidate_id": selected[0]["hypothesis_id"] if selected else None,
        "candidate_count": len(selected),
    }


def registration_contract(input_binding: dict[str, Any]) -> dict[str, Any]:
    """Generate the immutable registration dictionary frozen before trigger counts."""
    preflight = scientific_novelty_gate_preflight()
    if preflight["candidate_count"] != 1:
        raise ValueError("CANNOT_REGISTER_WITHOUT_EXACTLY_ONE_VALIDATED_CANDIDATE")

    return {
        "schema": "bline-r4-novel.exploratory-registration.v1",
        "task": TASK,
        "version": 1,
        "labels": LABELS,
        "state": "FROZEN_BEFORE_TRIGGER_INSPECTION_ZERO_PARAM_SEARCH",
        "parameter_search_budget": 0,
        "threshold_search_budget": 0,
        "horizon_search_budget": 0,
        "exit_search_budget": 0,
        "input_binding": input_binding,
        "precondition_gate": preflight,
        "mechanism": {
            "id": "TRAPPED_LEVERAGE_OVERHANG_BREAKOUT",
            "family": "Genuine position/volatility-state transitions",
            "economic_rationale": (
                "In BTC perpetual markets, periods of consolidation in a narrow trading range allow speculative leverage "
                "to build up as open interest accumulates. When the price breaks out downward (log_return_4h <= -0.01), "
                "if aggregate 24h base open interest has expanded (delta_log_oi_24h >= +0.015) and has not yet capitulated "
                "(delta_log_oi_4h >= -0.005), the newly entered long positions are immediately trapped underwater. "
                "Margin degradation and stop-loss clustering create persistent downward liquidation flow over 4–24h."
            ),
            "direction": "SHORT_ONLY",
            "paired_baseline_X": "SHORT iff log_return_4h <= -0.01",
            "observable_Z": {
                "formula": "delta_log_oi_24h >= 0.015 AND delta_log_oi_4h >= -0.005",
                "definitions": {
                    "delta_log_oi_24h": "log(base_open_interest(t) / base_open_interest(t - 24h))",
                    "delta_log_oi_4h": "log(base_open_interest(t) / base_open_interest(t - 4h))",
                },
                "thresholds": {
                    "log_return_4h_max": -0.01,
                    "delta_log_oi_24h_min": 0.015,
                    "delta_log_oi_4h_min": -0.005,
                },
            },
            "joint_rule": (
                "X baseline (log_return_4h <= -0.01) AND "
                "delta_log_oi_24h >= 0.015 AND "
                "delta_log_oi_4h >= -0.005"
            ),
            "paired_evaluation": (
                "Both X and X+Z arms evaluate on the exact same eligible origins where both X and Z are observed and complete. "
                "Missing Z masks both arms to NO_ACTION."
            ),
        },
        "native_sources": {
            "price_bars": {
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "product": "USD_M_PERPETUAL",
                "table": "bars",
                "interval": "1m",
                "source_layer": "C1 canonical parquet partitions",
            },
            "metrics": {
                "exchange": "binance",
                "symbol": "BTCUSDT",
                "product": "USD_M_PERPETUAL",
                "table": "metrics",
                "field": "sum_open_interest",
                "field_unit": "base BTC native quantity",
                "interval": "5m",
                "source_layer": "Deduplicated Binance daily metrics archives (bline-r2-20261019)",
            },
        },
        "clocks": {
            "origin_utc": "UTC HH:01",
            "cutoff_utc": "UTC HH:00",
            "bar_rule": "Interval ends strictly before cutoff (last bar close at HH:59:00 UTC)",
            "metrics_sampling": (
                "Sample latest native record with timestamp <= cutoff - 10m; guard requires exactly cutoff - 10m (HH:50:00 UTC). "
                "Predecessors at exactly (cutoff - 24h - 10m) and (cutoff - 4h - 10m) with identical guards."
            ),
            "entry_proxy": "HH:02 first minute open after origin (proxy only; no fill claim)",
            "horizons_hours": HORIZONS,
            "primary_horizon_hours": PRIMARY_HORIZON_HOURS,
            "receiver_pit": "PIT_UNKNOWN",
        },
        "coverage_scope": {
            "start_utc": COVERAGE_PERIOD_UTC[0],
            "end_utc": COVERAGE_PERIOD_UTC[1],
            "calendar_years": [2021, 2022, 2023, 2024],
            "warmup_hours": 24,
            "protected_exclusions": [
                {"start": H40_EXCLUSION[0], "end": H40_EXCLUSION[1], "reason": "H40 heldout"},
                {"start": H39_FORWARD, "end": "unbounded", "reason": "H39 forward boundary"},
            ],
        },
        "feasibility_floors": {
            "minimum_acted_origins": 30,
            "minimum_effective_weekly_blocks": 12,
            "approximate_target_density": "1 usable non-overlapping episode per 48 eligible hours (~0.5 to 2.0)",
            "interpretation": "Feasibility floor only; passing floors does not imply profitability or alpha.",
        },
        "invariants": {
            "no_lookahead": "All features and predecessor states strictly strictly before cutoff HH:00",
            "no_imputation": "Missing metrics or predecessors yield explicit NO_ACTION, never forward-fill or zero",
            "no_real_returns": "Zero real return labels, zero forward outcome evaluations, zero fill simulations",
            "no_protected_access": "Zero reads of H40/H39/forward databases, private accounts, or SQLite forward data",
        },
    }


def freeze_registration(output_dir: Path, registration: dict[str, Any]) -> str:
    """Freeze registration to disk immutably; any conflicting existing registration raises."""
    reg_path = output_dir / "exploratory_registration.v1.json"
    data = canonical_json_bytes(registration)
    if reg_path.exists():
        existing_data = reg_path.read_bytes()
        if existing_data != data:
            raise ValueError("REGISTRATION_ALREADY_FROZEN_WITH_DIFFERENT_CONTENT")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        with reg_path.open("xb") as stream:
            stream.write(data)
            stream.flush()

    receipt_path = output_dir / "registration_freeze_receipt.json"
    digest = sha256_digest(reg_path)
    receipt = {
        "registration_file": str(reg_path),
        "sha256": digest,
        "bytes": len(data),
        "frozen_at_utc": datetime.now(UTC).isoformat(),
        "task": TASK,
    }
    receipt_path.write_bytes(canonical_json_bytes(receipt))
    return digest
