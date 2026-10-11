"""Deterministic tests for 24 real Exit R1 ledger episodes, all 890 trades, 20-cell E0 exposure, and C R1 provenance.

Operates directly on committed repository files under `evidence/v0.6/b_line/g2_exit_horizon_r1/`
and `evidence/v0.6/b_line/g2_btc_two_lead_mark_gap_r31/` so all tests run deterministically both
locally and in GitHub Actions CI without requiring external `/tmp` caches.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pytest

from scripts.strategy_research.g2_goal_c_risk_assurance_r2 import (
    CANDIDATE_IDS,
    COST_NAMES,
    EXIT_R1_EVIDENCE_DIR,
    R31_EVIDENCE_DIR,
    SCHEMES,
)
from scripts.strategy_research.g2_goal_c_risk_assurance_r2.decimal_margin_engine import (
    BPS_DIVISOR,
    COST_MODELS_DEC,
    EPS_1E7,
    MINUTE_MS,
    D,
    dec_effective_price,
    dec_fee,
    dec_mark_liquidation_equity,
    dec_split_quantities,
)
from scripts.strategy_research.g2_goal_c_risk_assurance_r2.forensic_ledger_reaudit import (
    build_testnet_readiness_prerequisites_design_only,
    lookup_asof_completed_mark_close,
    verify_future_mark_perturbation_invariance,
)
from scripts.strategy_research.g2_goal_c_risk_assurance_r2.freeze_provenance_audit import (
    audit_c_r1_three_commit_chain_and_ast_diff,
)


def _load_24_stratified_real_r1_trades() -> list[tuple[str, dict]]:
    """Select 24 stratified real trades from committed Exit R1 order ledgers across all dimensions."""
    all_rows: list[tuple[str, str, dict]] = []
    for cid in CANDIDATE_IDS:
        for cost_name in COST_NAMES:
            for scheme in SCHEMES:
                p = EXIT_R1_EVIDENCE_DIR / f"{cid}_{cost_name}_{scheme}_orders.jsonl"
                for line in p.read_text(encoding="utf-8").splitlines():
                    t = json.loads(line)
                    t["_cost_name"] = cost_name
                    t["_year"] = datetime.fromtimestamp(int(t["entry_at"]) / 1000.0, tz=UTC).year
                    f_cash = D(t["funding_cash_usdt"])
                    t["_funding_sign"] = (
                        "POS" if f_cash > Decimal(0) else ("NEG" if f_cash < Decimal(0) else "ZERO")
                    )
                    q_init = D(t["quantity"])
                    t["_has_reduced_q_funding"] = any(
                        D(s["quantity"]) < q_init for s in t.get("funding_settlements", [])
                    )
                    tid = f"{cid[:6]}_{cost_name}_{scheme}_{t['event_id']}"
                    all_rows.append((tid, f"{cid}_{cost_name}_{scheme}", t))

    selected: list[tuple[str, dict]] = []
    seen: set[str] = set()

    def _pick(pred) -> None:
        for tid, _, t in all_rows:
            if len(selected) >= 24:
                return
            if tid not in seen and pred(t):
                seen.add(tid)
                selected.append((tid, t))
                return

    # 1. Include up to 8 real episodes where TP1 reduced open quantity before a funding settlement
    for tid, _, t in all_rows:
        if t["_has_reduced_q_funding"] and len(selected) < 8:
            seen.add(tid)
            selected.append((tid, t))

    # 2. Cover every candidate x cost x scheme
    for cid in CANDIDATE_IDS:
        for cost_name in ("STRESS", "BASE"):
            for scheme in SCHEMES:
                _pick(
                    lambda x, c=cid, co=cost_name, sc=scheme: (
                        x["candidate"] == c
                        and x["_cost_name"] == co
                        and x.get("scheme", "E0") == sc
                        and len(x["tiers"]) == 2
                    )
                )
                _pick(
                    lambda x, c=cid, co=cost_name, sc=scheme: (
                        x["candidate"] == c
                        and x["_cost_name"] == co
                        and x.get("scheme", "E0") == sc
                    )
                )

    # 3. Cover all years, sides, and funding signs
    for yr in (2021, 2022, 2023):
        for side in (1, -1):
            for fsign in ("POS", "NEG", "ZERO"):
                _pick(lambda x, y=yr, s=side, fs=fsign: x["_year"] == y and int(x["side"]) == s and x["_funding_sign"] == fs)

    assert len(selected) == 24
    return selected


_REAL_24_EPISODES = _load_24_stratified_real_r1_trades()


@pytest.mark.parametrize(
    "trade_id,trade",
    _REAL_24_EPISODES,
    ids=[tid for tid, _ in _REAL_24_EPISODES],
)
def test_24_real_r1_ledger_episodes_decimal_quantity_fee_funding_and_asof_mark(
    trade_id: str,
    trade: dict,
) -> None:
    """Independently verify Decimal quantity, entry/exit fees, as-of Mark close, and ACK cash on 24 real cases."""
    cost_name = trade["_cost_name"]
    cost = COST_MODELS_DEC[cost_name]
    side = int(trade["side"])
    raw_entry = D(trade["raw_entry"])
    eff_entry = dec_effective_price(raw_entry, side, cost, is_entry=True)
    assert abs(eff_entry - D(trade["effective_entry"])) <= EPS_1E7

    qty = D(trade["quantity"])
    fee_entry = dec_fee(eff_entry, qty, cost)
    assert abs(fee_entry - D(trade["fee_entry"])) <= EPS_1E7

    # 5% reserve gate check on real trade admission
    cash_before = D(trade["cash_before_entry"])
    budget = Decimal("0.95") * min(cash_before, Decimal(1000))
    assert qty * eff_entry + fee_entry <= budget + EPS_1E7

    tiers = trade["tiers"]
    if len(tiers) == 2:
        q1_exp, q2_exp = dec_split_quantities(qty)
        assert abs(D(tiers[0]["quantity"]) - q1_exp) <= Decimal("1e-9")
        assert abs(D(tiers[1]["quantity"]) - q2_exp) <= Decimal("1e-9")
    else:
        assert len(tiers) == 1
        assert abs(D(tiers[0]["quantity"]) - qty) <= Decimal("1e-9")

    gross_total = Decimal(0)
    drag_total = Decimal(0)
    fee_exit_total = Decimal(0)
    for t_row in tiers:
        tq = D(t_row["quantity"])
        t_raw_exit = D(t_row["raw_exit"])
        t_eff_exit = dec_effective_price(t_raw_exit, side, cost, is_entry=False)
        assert abs(t_eff_exit - D(t_row["effective_exit"])) <= EPS_1E7
        t_fee = dec_fee(t_eff_exit, tq, cost)
        assert abs(t_fee - D(t_row["fee_exit"])) <= EPS_1E7
        gross_total += Decimal(side) * (t_raw_exit - raw_entry) * tq
        drag_total += Decimal(side) * (eff_entry - raw_entry + t_raw_exit - t_eff_exit) * tq
        fee_exit_total += t_fee

    net_pre_funding = gross_total - drag_total - fee_entry - fee_exit_total
    assert abs(net_pre_funding - D(trade["net_usdt"])) <= EPS_1E7

    # Verify every funding settlement's as-of completed 1m Mark close, remaining quantity, and signed cash
    funding_sum = Decimal(0)
    entry_at = int(trade["entry_at"])
    exit_at = int(trade["exit_at"])
    for s in trade.get("funding_settlements", []):
        s_at = int(s["settlement_at"])
        assert entry_at <= s_at < exit_at
        m_close_at = int(s["mark_close_at"])
        assert m_close_at <= s_at
        assert (m_close_at + 1) % MINUTE_MS == 0

        closed_before = sum(
            (D(x["quantity"]) for x in tiers if int(x["exit_at"]) <= s_at),
            Decimal(0),
        )
        rem_q = qty - closed_before
        assert abs(rem_q - D(s["quantity"])) <= Decimal("1e-9")

        m_price = D(s["settlement_mark"])
        rate_dec = D(s["source_rate_fraction"])
        expected_cash = -Decimal(side) * rem_q * m_price * rate_dec
        assert abs(expected_cash - D(s["signed_cash_usdt"])) <= Decimal("1e-9")
        funding_sum += expected_cash

        # Construct a local 5-bar Mark array around `m_close_at` and prove future Mark perturbation invariance
        m_open = m_close_at - (MINUTE_MS - 1)
        local_mark = np.zeros((5, 5), dtype=float)
        for k in range(5):
            local_mark[k, 0] = m_open + (k - 2) * MINUTE_MS
            local_mark[k, 1:] = float(m_price)
        looked_up_price, looked_up_close_at, bar_idx = lookup_asof_completed_mark_close(local_mark, s_at)
        assert looked_up_price == m_price
        assert looked_up_close_at == m_close_at
        assert verify_future_mark_perturbation_invariance(local_mark, s_at, bar_idx, m_price) is True

    assert abs(funding_sum - D(trade["funding_cash_usdt"])) <= EPS_1E7
    net_after_funding = net_pre_funding + funding_sum
    assert abs(net_after_funding - D(trade["net_after_funding_usdt"])) <= EPS_1E7

    entry_notional = raw_entry * qty
    net_after_bps = BPS_DIVISOR * net_after_funding / entry_notional
    assert abs(net_after_bps - D(trade["net_after_funding_bps"])) <= Decimal("1e-5")

    cash_after = D(trade["cash_after_ack"])
    assert abs((cash_before + net_after_funding) - cash_after) <= EPS_1E7
    journal_sum = sum((D(j["cash_delta"]) for j in trade["journal"]), Decimal(0))
    assert abs(journal_sum - net_after_funding) <= EPS_1E7

    # Also verify positive initial Mark exposure ratio at entry price
    eq0, not0, ratio0 = dec_mark_liquidation_equity(
        cash_before - fee_entry,
        Decimal(0),
        side,
        eff_entry,
        qty,
        raw_entry,
        cost,
    )
    assert eq0 > Decimal(0)
    assert not0 > Decimal(0)
    assert Decimal("0.50") < ratio0 < Decimal("1.00")


def test_all_890_order_ledger_trades_conservation_and_all_20_cells_e0_positive_exposure() -> None:
    """Verify all 890 order-ledger trades conserve cash and all 4 E0 cells have positive exposure ~0.934-0.944."""
    r1_results = json.loads((EXIT_R1_EVIDENCE_DIR / "EXIT_R1_RESULTS.json").read_text(encoding="utf-8"))
    r31_results = json.loads((R31_EVIDENCE_DIR / "R31_ECONOMIC_RESULTS.json").read_text(encoding="utf-8"))

    total_trades = 0
    for cid in CANDIDATE_IDS:
        for cost_name in COST_NAMES:
            for scheme in SCHEMES:
                p = EXIT_R1_EVIDENCE_DIR / f"{cid}_{cost_name}_{scheme}_orders.jsonl"
                trades = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines()]
                assert len(trades) > 0
                total_trades += len(trades)
                for t in trades:
                    cb = D(t["cash_before_entry"])
                    ca = D(t["cash_after_ack"])
                    naf = D(t["net_after_funding_usdt"])
                    assert abs((cb + naf) - ca) <= EPS_1E7

                acc = r1_results["candidates"][cid][cost_name]["account"][scheme]
                monthly = acc["monthly"]
                if scheme == "E0":
                    # Prove E0 monthly peak exposure is stored under `marked_exposure_ratio` and is ~0.934-0.944
                    peak_exp = max(float(m["marked_exposure_ratio"]) for m in monthly)
                    r31_monthly = r31_results["candidates"][cid]["costs"][cost_name]["monthly"]
                    r31_peak = max(float(m["marked_exposure_ratio"]) for m in r31_monthly)
                    assert peak_exp == pytest.approx(r31_peak, abs=1e-12)
                    assert 0.930 <= peak_exp <= 0.955
                else:
                    peak_exp = max(float(m["peak_exposure_ratio"]) for m in monthly)
                    breach_mins = sum(int(m["exposure_above_1x_minutes"]) for m in monthly)
                    assert breach_mins == 0
                    assert 0.930 <= peak_exp <= 0.955

    assert total_trades == 890


def test_c_r1_three_commit_chain_and_ast_diff_provenance() -> None:
    """Verify C R1's 3-commit chain (`8db2e3f -> 4c0bac0 -> f381dd7`) and untouched economic modules."""
    prov = audit_c_r1_three_commit_chain_and_ast_diff()
    assert prov["c_r1_procedural_freeze_status"] == "POST_FREEZE_REPAIR_NOT_PREACCEPTED"
    assert prov["two_commit_rule_violated_in_c_r1"] is True
    assert prov["c_r1_commit_count_since_exit_r1"] == 3
    assert prov["untouched_modules_count"] == 8
    assert prov["modified_modules_count"] == 2
    assert prov["ci_run_38162845456_truth_disclosure"]["change_filter_mode"] == "docs-only"
    assert prov["ci_run_38162845456_truth_disclosure"]["pytest_executed_in_final_ci"] is False


def test_testnet_readiness_prerequisites_design_only() -> None:
    """Verify future TESTNET readiness prerequisites are strictly design-only with 6 concrete gates."""
    prereqs = build_testnet_readiness_prerequisites_design_only()
    assert prereqs["testnet_connected"] is False
    assert prereqs["live_exchange_connected"] is False
    assert len(prereqs["prerequisites"]) == 6
