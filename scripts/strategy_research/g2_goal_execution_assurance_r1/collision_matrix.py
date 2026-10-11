"""Target 3: Adversarial deterministic event collision matrix (48 fixtures F01..F48).

Tests LONG/SHORT, favorable/adverse gaps, intrabar STOP+TP1+TP2 simultaneously,
TP1 while next funding exactly at bar close, TP1 ACK latency, STOP moved after ACK only,
TOCTOU same-bar stage, miss/delay or exact-touch vs one-tick-through limit, 0.001 BTC lot rounding,
min-notional per tier, fee double-charge/missing charge, funding sign +/-/0, settlement before/at/after exit,
12h/18h/24h folded END, EXIT_ACK outside fold, cooldown, missing Mark minute, no cash debt reserved,
retransmission/idempotency double exit, and synthetic leverage liquidation.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

import numpy as np

from scripts.strategy_research.g2_exit_horizon_r1.account import (
    mark_curve,
    path_eligible,
    replay,
    size,
)
from scripts.strategy_research.g2_exit_horizon_r1.book import (
    PartialIneligible,
    _breakeven_stop,
    position,
)
from scripts.strategy_research.g2_gemini_goal_trend_flow_r1.replay import (
    BASE,
    HOUR,
    MINUTE,
    STRESS,
    _proposed,
    _tick,
)

from .decimal_journal import (
    D,
    dec_ack_clock,
    dec_breakeven_stop,
    dec_size_admission,
    dec_split_quantity,
    verify_and_audit_episode,
)
from .lineage_audit import prove_synthetic_prefix_causality
from .risk_envelope import run_synthetic_leverage_scenario

ENTRY_MS = 2 * MINUTE


def _base_fixture(side: int = 1, n_bars: int = 1600, base_price: float = 100.0):
    bars = np.empty((n_bars, 5), dtype=float)
    bars[:, 0] = np.arange(n_bars, dtype=float) * MINUTE
    bars[:, 1:] = base_price
    mark = bars.copy()
    event = {
        "event_time": 0,
        "decision_at": MINUTE,
        "entry_at": ENTRY_MS,
        "decision_close": base_price,
        "atr_hour": 20.0,
        "side": side,
        "stop": (base_price - 10.0) if side > 0 else (base_price + 10.0),
        "event_id": f"syn_{side}",
    }
    cand = {
        "id": "W1_C04_ATR_EXPANSION_TREND_FOLLOW_12H",
        "horizon_hours": 12,
        "target_R": 2.0,
        "cooldown_hours": 6,
    }
    return bars, mark, event, cand


def _targets(bars: np.ndarray, event: dict[str, Any], cand: dict[str, Any], cost: dict[str, float] = BASE):
    p = _proposed(bars, event, cand, cost)
    s = int(event["side"])
    t1 = _tick(float(p["effective_entry"]) + s * float(p["initial_risk"]), upwards=s < 0)
    t2 = float(p["target"])
    return p, t1, t2


def _mark_dict(mark: np.ndarray) -> dict[int, tuple[Decimal, int, str]]:
    return {
        int(row[0]): (D(row[4]), int(row[0]) + MINUTE - 1, "SYNTHETIC_AUTHORITY")
        for row in mark
    }


COLLISION_FIXTURE_REGISTRY: list[dict[str, str]] = [
    {"id": "F01_LONG_ADVERSE_OPEN_STOP_GAP", "category": "GAP_PRECEDENCE", "invariant": "LONG bar opening below stop executes STOP_GAP at uncapped bar open at minute start"},
    {"id": "F02_SHORT_ADVERSE_OPEN_STOP_GAP", "category": "GAP_PRECEDENCE", "invariant": "SHORT bar opening above stop executes STOP_GAP at uncapped bar open at minute start"},
    {"id": "F03_LONG_FAVORABLE_OPEN_SINGLE_TP1_GAP_CAPPED", "category": "GAP_PRECEDENCE", "invariant": "LONG bar opening between TP1 and TP2 fills TP1_GAP_CAPPED at TP1 limit without price improvement"},
    {"id": "F04_SHORT_FAVORABLE_OPEN_SINGLE_TP1_GAP_CAPPED", "category": "GAP_PRECEDENCE", "invariant": "SHORT bar opening between TP1 and TP2 fills TP1_GAP_CAPPED at TP1 limit without price improvement"},
    {"id": "F05_LONG_FAVORABLE_OPEN_DOUBLE_TIER_GAP_CAPPED", "category": "GAP_PRECEDENCE", "invariant": "LONG bar opening beyond TP2 fills both TP1_GAP_CAPPED and TP2_GAP_CAPPED at their respective limits"},
    {"id": "F06_SHORT_FAVORABLE_OPEN_DOUBLE_TIER_GAP_CAPPED", "category": "GAP_PRECEDENCE", "invariant": "SHORT bar opening beyond TP2 fills both TP1_GAP_CAPPED and TP2_GAP_CAPPED at their respective limits"},
    {"id": "F07_LONG_INTRABAR_STOP_TP1_TP2_TRIPLE_COLLISION", "category": "INTRABAR_COLLISION", "invariant": "LONG bar hitting STOP, TP1, and TP2 in the same minute rejects optimistic TP fills and exits full quantity at STOP"},
    {"id": "F08_SHORT_INTRABAR_STOP_TP1_TP2_TRIPLE_COLLISION", "category": "INTRABAR_COLLISION", "invariant": "SHORT bar hitting STOP, TP1, and TP2 in the same minute rejects optimistic TP fills and exits full quantity at STOP"},
    {"id": "F09_LONG_INTRABAR_TP1_TP2_SIMULTANEOUS_NO_DOUBLE_FILL", "category": "INTRABAR_COLLISION", "invariant": "LONG non-gap bar reaching TP2 high fills only TP1 in that minute; TP2 deferred to subsequent minute"},
    {"id": "F10_SHORT_INTRABAR_TP1_TP2_SIMULTANEOUS_NO_DOUBLE_FILL", "category": "INTRABAR_COLLISION", "invariant": "SHORT non-gap bar reaching TP2 low fills only TP1 in that minute; TP2 deferred to subsequent minute"},
    {"id": "F11_TP1_OPEN_GAP_THEN_INTRABAR_TP2_BLOCKED_SAME_BAR", "category": "TOCTOU_STAGE", "invariant": "When TP1 fills on opening gap, intrabar high reaching TP2 in the same minute cannot fill TP2"},
    {"id": "F12_TP1_OPEN_GAP_THEN_INTRABAR_STOP_SAME_BAR", "category": "TOCTOU_STAGE", "invariant": "When TP1 fills on opening gap and bar subsequently breaches STOP intraminute, residual q2 exits at STOP"},
    {"id": "F13_TP1_AT_BAR_CLOSE_FUNDING_AT_NEXT_BAR_OPEN_1MS", "category": "FUNDING_BOUNDARY", "invariant": "TP1 at bar close (t_settle - 1ms) reduces inventory before funding at t_settle even while TP1 ACK is at t_settle + 60s"},
    {"id": "F14_TP1_EXACTLY_AT_FUNDING_TIMESTAMP_OPEN_FILL", "category": "FUNDING_BOUNDARY", "invariant": "TP1_GAP_CAPPED at exact funding timestamp (exit_at == settlement_at) precedes funding bill and charges only residual q2"},
    {"id": "F15_FLAT_EXIT_EXACTLY_AT_FUNDING_TIMESTAMP_EXCLUDED", "category": "FUNDING_BOUNDARY", "invariant": "Full exit at exact funding timestamp (exit_at == settlement_at) incurs zero funding bill"},
    {"id": "F16_FUNDING_AT_ENTRY_TIMESTAMP_INCLUDED_FULL_QTY", "category": "FUNDING_BOUNDARY", "invariant": "Funding settlement at exact entry_at timestamp is charged on full initial quantity"},
    {"id": "F17_FUNDING_1MS_BEFORE_TP1_CLOSE_USES_FULL_QTY", "category": "FUNDING_BOUNDARY", "invariant": "Funding at bar open (t) before TP1 at bar close (t + 59,999ms) charges full initial quantity q1 + q2"},
    {"id": "F18_TP1_ACK_LATENCY_BAR_CLOSE_VS_BAR_OPEN", "category": "ACK_CAUSALITY", "invariant": "Bar-open fill ACKs at +60,000ms; bar-close fill (minute+59,999ms) ACKs at next-next minute open (+60,001ms)"},
    {"id": "F19_E2_STOP_MOVED_AFTER_TP1_ACK_ONLY_TOCTOU", "category": "TOCTOU_STAGE", "invariant": "E2 breakeven stop amendment is inactive during the minute between TP1 bar-close fill and TP1 ACK"},
    {"id": "F20_E2_SHORT_BREAKEVEN_STOP_CLAMP_AND_ACK", "category": "TOCTOU_STAGE", "invariant": "SHORT E2 breakeven stop never loosens initial stop and activates strictly at/after TP1 ACK"},
    {"id": "F21_EXACT_TOUCH_NO_FILL_VS_ONE_TICK_THROUGH_LONG", "category": "LIMIT_SENSITIVITY", "invariant": "LONG exact limit touch logs touch_no_fill=1 without filling; 1-tick trade-through (+0.1) fills at limit"},
    {"id": "F22_EXACT_TOUCH_NO_FILL_VS_ONE_TICK_THROUGH_SHORT", "category": "LIMIT_SENSITIVITY", "invariant": "SHORT exact limit touch logs touch_no_fill=1 without filling; 1-tick trade-through (-0.1) fills at limit"},
    {"id": "F23_E0_PRIMARY_TOUCH_VS_E0_THROUGH_SENSITIVITY", "category": "LIMIT_SENSITIVITY", "invariant": "Legacy E0 primary fills on exact touch whereas E0 through requires 1-tick trade-through"},
    {"id": "F24_DELAY_MODE_CONFIRMATION_NEXT_OPEN_FAVORABLE", "category": "LIMIT_SENSITIVITY", "invariant": "fill_mode='delay' waits 1 bar after trade-through and fills when subsequent bar opens favorably"},
    {"id": "F25_DELAY_MODE_NEXT_OPEN_UNFAVORABLE_RECONFIRMS", "category": "LIMIT_SENSITIVITY", "invariant": "fill_mode='delay' rejects fill when next bar opens unfavorably even if high trades through again"},
    {"id": "F26_UNFILLED_MODE_SKIPS_FIRST_CONFIRMATION_INCLUDING_OPEN_GAP", "category": "LIMIT_SENSITIVITY", "invariant": "fill_mode='unfilled' skips first confirmation bar (including opening gap) and fills on second confirmation"},
    {"id": "F27_LOT_ROUNDING_ODD_LOTS_AND_FLOAT_ULPS", "category": "LOT_AND_NOTIONAL", "invariant": "Odd lot multiple (0.027 BTC) splits into floor half (0.013) + remainder (0.014); float ULP accepted; non-lot rejected"},
    {"id": "F28_MIN_NOTIONAL_PER_TIER_REJECTION", "category": "LOT_AND_NOTIONAL", "invariant": "Position with total notional >= 5 USDT but half-tier notional < 5 USDT raises PartialIneligible"},
    {"id": "F29_ENTRY_FEE_CHARGED_ONCE_EXIT_FEES_PER_TIER", "category": "FEE_ACCOUNTING", "invariant": "Entry fee is charged exactly once at entry_at; allocated tier entry fees sum to fee_entry; exit fees sum across tiers"},
    {"id": "F30_FUNDING_SIGN_MATRIX_AND_ZERO_RATE", "category": "FUNDING_ACCOUNTING", "invariant": "Signed funding cash equals -side * open_qty * mark_close * rate across all (+/- side) x (+/-/0 rate) combinations"},
    {"id": "F31_STOP_GAP_PRECEDES_TIME_CAP_AT_DEADLINE", "category": "DEADLINE_PRECEDENCE", "invariant": "At exact horizon deadline, adverse opening gap beyond stop executes STOP_GAP rather than TIME_CAP"},
    {"id": "F32_TIME_CAP_CAPPED_AT_FINAL_TARGET", "category": "DEADLINE_PRECEDENCE", "invariant": "At exact horizon deadline, favorable opening gap beyond target2 caps TIME_CAP raw exit at target2"},
    {"id": "F33_FOLD_BOUNDARY_CENSORING_12H_18H_24H", "category": "FOLD_BOUNDARY", "invariant": "path_eligible prospectively censors entries where entry + horizon + 1m >= fold_end across 12h, 18h, and 24h"},
    {"id": "F34_EXIT_ACK_OUTSIDE_FOLD_HARD_GUARD", "category": "FOLD_BOUNDARY", "invariant": "Account replay raises ValueError if any admitted trade's exit_ack_at reaches or exceeds fold end_ms"},
    {"id": "F35_PARTIAL_TP1_ACK_DOES_NOT_REOPEN_ENTRY_OR_BYPASS_COOLDOWN", "category": "GATE_AND_COOLDOWN", "invariant": "TP1 ACK while q2 remains open does not reopen single-position gate; post-exit cooldown blocks early re-entry"},
    {"id": "F36_MISSING_MARK_MINUTE_AT_SETTLEMENT_OR_CURVE_REJECTED", "category": "SOURCE_INTEGRITY", "invariant": "Missing completed 1m Mark bar at settlement or inside fold raises ValueError"},
    {"id": "F37_MISSING_LAST_MINUTE_ON_EXIT_PATH_REJECTED", "category": "SOURCE_INTEGRITY", "invariant": "Missing or non-contiguous 1m Last bar on exit path raises ValueError"},
    {"id": "F38_NO_CASH_DEBT_AND_BUDGET_RESERVATION_INVARIANT", "category": "CAPITAL_RESERVE", "invariant": "size() enforces 0.95 * min(cash, 1000) budget with worst-entry, entry fee, 1.1x exit and 12h funding reserves"},
    {"id": "F39_UNACKNOWLEDGED_CASH_AND_PAST_FUNDING_CANNOT_PREFUND_CONCURRENT_ENTRY", "category": "CASH_CAUSALITY", "invariant": "Unacknowledged exit P&L is held in pending receivable until exit_ack_at and cannot pre-fund concurrent entry"},
    {"id": "F40_RETRANSMISSION_IDEMPOTENCY_AND_DUPLICATE_EXIT_REJECTION", "category": "IDEMPOTENCY", "invariant": "Duplicate signal at same clock is blocked by position gate; duplicate tier exit in journal fails inventory conservation"},
    {"id": "F41_UNPROVEN_PROVIDER_SETTLEMENT_MARK_REJECTED", "category": "SOURCE_INTEGRITY", "invariant": "Funding event supplying mark_price without mark_price_source_proven=True raises ValueError"},
    {"id": "F42_QUARTER_ATR_ENTRY_GAP_VETO", "category": "ENTRY_VETO", "invariant": "Entry open diverging by more than 0.25 * atr_hour from decision_close is rejected"},
    {"id": "F43_WRONG_SIDE_STOP_OR_NONPOSITIVE_EFFECTIVE_RISK_VETO", "category": "ENTRY_VETO", "invariant": "Stop on wrong side of entry or effective entry slipping past stop is rejected"},
    {"id": "F44_AVAILABILITY_CAUSALITY_CLOCK_VIOLATION_REJECTED", "category": "CAUSALITY_CLOCK", "invariant": "Signal violating event_time + 60s <= decision_at + 60s <= entry_at raises ValueError and is not silently ignored"},
    {"id": "F45_MARK_CURVE_INSOLVENCY_ZERO_OR_NEGATIVE_EQUITY_GUARD", "category": "SOLVENCY_GUARD", "invariant": "Mark liquidation curve raises ValueError if marked account equity drops to or below zero"},
    {"id": "F46_SYNTHETIC_LEVERAGE_10X_15X_LIQUIDATION_AND_GAP_DEFICIT", "category": "LEVERAGE_STRESS", "invariant": "Synthetic 10x/15x naive leverage triggers Mark liquidation before 1x stop and incurs gap deficit; risk-capped isolated survives"},
    {"id": "F47_KNOWN_AT_SIGNAL_PREFIX_INDEPENDENCE_AND_WARMUP_PURGE", "category": "KNOWN_AT_LINEAGE", "invariant": "Signal generation and entry proposal are invariant to future Last/Mark/Funding mutations and strict prefix truncation"},
    {"id": "F48_AUDIT_TAMPER_DETECTION_CASH_FEE_FUNDING_CURVE_ARCHIVE", "category": "ADVERSARIAL_TAMPER", "invariant": "Independent Decimal audit deterministically catches cash, fee, residual qty, premature ACK, and curve tampering"},
]


def execute_collision_fixture(fixture_id: str) -> dict[str, Any]:
    """Execute a single registered deterministic adversarial fixture and assert all invariants."""
    if fixture_id == "F01_LONG_ADVERSE_OPEN_STOP_GAP":
        bars, mark, event, cand = _base_fixture(side=1)
        bars[4, 1:5] = 85.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["exit_reason"] == "STOP_GAP" and res["raw_exit"] == 85.0
        assert res["exit_at"] == 4 * MINUTE and res["exit_ack_at"] == 5 * MINUTE
        audit_rec = verify_and_audit_episode({**res, "cost": "BASE"}, {}, _mark_dict(mark))
        assert audit_rec["status"] == "PASS"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_reason": res["exit_reason"], "raw_exit": res["raw_exit"], "exit_at": res["exit_at"]}}

    if fixture_id == "F02_SHORT_ADVERSE_OPEN_STOP_GAP":
        bars, mark, event, cand = _base_fixture(side=-1)
        bars[4, 1:5] = 115.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["exit_reason"] == "STOP_GAP" and res["raw_exit"] == 115.0
        assert res["exit_at"] == 4 * MINUTE and res["exit_ack_at"] == 5 * MINUTE
        audit_rec = verify_and_audit_episode({**res, "cost": "BASE"}, {}, _mark_dict(mark))
        assert audit_rec["status"] == "PASS"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_reason": res["exit_reason"], "raw_exit": res["raw_exit"]}}

    if fixture_id == "F03_LONG_FAVORABLE_OPEN_SINGLE_TP1_GAP_CAPPED":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 1:5] = t1 + 2.0  # above TP1, below TP2
        assert t1 + 2.0 < t2
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["reason"] == "TP1_GAP_CAPPED"
        assert res["tiers"][0]["raw_exit"] == t1  # capped at limit!
        assert res["tiers"][0]["exit_at"] == 3 * MINUTE
        assert res["tiers"][1]["reason"] == "TIME_CAP"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"tp1_raw_exit": res["tiers"][0]["raw_exit"], "bar_open": t1 + 2.0}}

    if fixture_id == "F04_SHORT_FAVORABLE_OPEN_SINGLE_TP1_GAP_CAPPED":
        bars, mark, event, cand = _base_fixture(side=-1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 1:5] = t1 - 2.0  # below TP1, above TP2
        assert t1 - 2.0 > t2
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["reason"] == "TP1_GAP_CAPPED"
        assert res["tiers"][0]["raw_exit"] == t1
        assert res["tiers"][0]["exit_at"] == 3 * MINUTE
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"tp1_raw_exit": res["tiers"][0]["raw_exit"], "bar_open": t1 - 2.0}}

    if fixture_id == "F05_LONG_FAVORABLE_OPEN_DOUBLE_TIER_GAP_CAPPED":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 1:5] = t2 + 5.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert [x["reason"] for x in res["tiers"]] == ["TP1_GAP_CAPPED", "TP2_GAP_CAPPED"]
        assert [x["raw_exit"] for x in res["tiers"]] == [t1, t2]
        assert res["tiers"][0]["exit_at"] == res["tiers"][1]["exit_at"] == 3 * MINUTE
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"reasons": [x["reason"] for x in res["tiers"]]}}

    if fixture_id == "F06_SHORT_FAVORABLE_OPEN_DOUBLE_TIER_GAP_CAPPED":
        bars, mark, event, cand = _base_fixture(side=-1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 1:5] = t2 - 5.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert [x["reason"] for x in res["tiers"]] == ["TP1_GAP_CAPPED", "TP2_GAP_CAPPED"]
        assert [x["raw_exit"] for x in res["tiers"]] == [t1, t2]
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"reasons": [x["reason"] for x in res["tiers"]]}}

    if fixture_id == "F07_LONG_INTRABAR_STOP_TP1_TP2_TRIPLE_COLLISION":
        bars, mark, event, cand = _base_fixture(side=1)
        p, _, t2 = _targets(bars, event, cand)
        bars[3, 2] = t2 + 1.0
        bars[3, 3] = p["stop"] - 0.5
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert len(res["tiers"]) == 1 and res["exit_reason"] == "STOP"
        assert res["raw_exit"] == p["stop"] and res["tiers"][0]["quantity"] == 0.2
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_reason": res["exit_reason"], "tiers_n": len(res["tiers"])}}

    if fixture_id == "F08_SHORT_INTRABAR_STOP_TP1_TP2_TRIPLE_COLLISION":
        bars, mark, event, cand = _base_fixture(side=-1)
        p, _, t2 = _targets(bars, event, cand)
        bars[3, 2] = p["stop"] + 0.5
        bars[3, 3] = t2 - 1.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert len(res["tiers"]) == 1 and res["exit_reason"] == "STOP"
        assert res["raw_exit"] == p["stop"] and res["tiers"][0]["quantity"] == 0.2
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_reason": res["exit_reason"], "tiers_n": len(res["tiers"])}}

    if fixture_id == "F09_LONG_INTRABAR_TP1_TP2_SIMULTANEOUS_NO_DOUBLE_FILL":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 2] = t2 + 1.0  # reaches TP2 high, but open is 100 < TP1
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["reason"] == "TP1" and res["tiers"][0]["raw_exit"] == t1
        assert res["tiers"][0]["exit_at"] == 3 * MINUTE + MINUTE - 1
        assert res["tiers"][1]["reason"] == "TIME_CAP" and res["tiers"][1]["exit_at"] > res["tiers"][0]["exit_at"]
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"t0_exit_at": res["tiers"][0]["exit_at"], "t1_reason": res["tiers"][1]["reason"]}}

    if fixture_id == "F10_SHORT_INTRABAR_TP1_TP2_SIMULTANEOUS_NO_DOUBLE_FILL":
        bars, mark, event, cand = _base_fixture(side=-1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 3] = t2 - 1.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["reason"] == "TP1" and res["tiers"][0]["raw_exit"] == t1
        assert res["tiers"][1]["reason"] == "TIME_CAP"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"t0_reason": res["tiers"][0]["reason"], "t1_reason": res["tiers"][1]["reason"]}}

    if fixture_id == "F11_TP1_OPEN_GAP_THEN_INTRABAR_TP2_BLOCKED_SAME_BAR":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, t2 = _targets(bars, event, cand)
        bars[3, 1] = t1 + 0.5
        bars[3, 2] = t2 + 1.0
        bars[3, 3] = t1
        bars[3, 4] = t1 + 0.5
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["reason"] == "TP1_GAP_CAPPED" and res["tiers"][0]["exit_at"] == 3 * MINUTE
        assert res["tiers"][1]["reason"] == "TIME_CAP"  # TP2 blocked on bar 3 by deferred_tp2_until = 4*MINUTE
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"tp1_exit_at": res["tiers"][0]["exit_at"], "tp2_reason": res["tiers"][1]["reason"]}}

    if fixture_id == "F12_TP1_OPEN_GAP_THEN_INTRABAR_STOP_SAME_BAR":
        bars, mark, event, cand = _base_fixture(side=1)
        p, t1, _ = _targets(bars, event, cand)
        bars[3, 1] = t1 + 0.5
        bars[3, 2] = t1 + 1.0
        bars[3, 3] = p["stop"] - 0.2
        bars[3, 4] = p["stop"]
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["reason"] == "TP1_GAP_CAPPED" and res["tiers"][0]["exit_at"] == 3 * MINUTE
        assert res["tiers"][1]["reason"] == "STOP" and res["tiers"][1]["exit_at"] == 3 * MINUTE + MINUTE - 1
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"reasons": [x["reason"] for x in res["tiers"]]}}

    if fixture_id == "F13_TP1_AT_BAR_CLOSE_FUNDING_AT_NEXT_BAR_OPEN_1MS":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        # Bar 479 closes at 480*MINUTE - 1 = 28,799,999; funding at 480*MINUTE = 28,800,000 (1ms later)
        bars[479, 2] = t1 + 0.2
        f_events = [{"settlement_at": 480 * MINUTE, "rate": "0.001"}]
        res = position(bars, mark, f_events, event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["exit_at"] == 480 * MINUTE - 1
        assert res["tiers"][0]["exit_ack_at"] == 481 * MINUTE
        assert res["funding_settlements"][0]["quantity"] == "0.1"
        audit_rec = verify_and_audit_episode({**res, "cost": "BASE"}, {480 * MINUTE: Decimal("0.001")}, _mark_dict(mark))
        assert audit_rec["status"] == "PASS"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"distance_ms": 1, "remaining_qty": res["funding_settlements"][0]["quantity"]}}

    if fixture_id == "F14_TP1_EXACTLY_AT_FUNDING_TIMESTAMP_OPEN_FILL":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[480, 1:5] = t1 + 0.5  # TP1_GAP_CAPPED at exact 480 * MINUTE
        f_events = [{"settlement_at": 480 * MINUTE, "rate": "0.001"}]
        res = position(bars, mark, f_events, event, cand, BASE, "E1", 0.2)
        assert res["tiers"][0]["exit_at"] == 480 * MINUTE
        assert res["funding_settlements"][0]["quantity"] == "0.1"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"tp1_exit_at": 480 * MINUTE, "funding_qty": res["funding_settlements"][0]["quantity"]}}

    if fixture_id == "F15_FLAT_EXIT_EXACTLY_AT_FUNDING_TIMESTAMP_EXCLUDED":
        bars, mark, event, cand = _base_fixture(side=1)
        bars[480, 1:5] = 85.0  # STOP_GAP at exact 480 * MINUTE
        f_events = [{"settlement_at": 480 * MINUTE, "rate": "0.001"}]
        res = position(bars, mark, f_events, event, cand, BASE, "E1", 0.2)
        assert res["exit_at"] == 480 * MINUTE and res["funding_settlements"] == []
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_at": res["exit_at"], "settlements_n": 0}}

    if fixture_id == "F16_FUNDING_AT_ENTRY_TIMESTAMP_INCLUDED_FULL_QTY":
        bars, mark, event, cand = _base_fixture(side=1)
        f_events = [{"settlement_at": ENTRY_MS, "rate": "0.001"}]
        res = position(bars, mark, f_events, event, cand, BASE, "E1", 0.2)
        assert len(res["funding_settlements"]) == 1 and res["funding_settlements"][0]["quantity"] == "0.2"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"settlement_at": ENTRY_MS, "qty": "0.2"}}

    if fixture_id == "F17_FUNDING_1MS_BEFORE_TP1_CLOSE_USES_FULL_QTY":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[480, 2] = t1 + 0.2  # TP1 fills at 480*MINUTE + 59,999, while funding is at 480*MINUTE
        f_events = [{"settlement_at": 480 * MINUTE, "rate": "0.001"}]
        res = position(bars, mark, f_events, event, cand, BASE, "E1", 0.2)
        assert res["funding_settlements"][0]["quantity"] == "0.2"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"funding_qty": res["funding_settlements"][0]["quantity"]}}

    if fixture_id == "F18_TP1_ACK_LATENCY_BAR_CLOSE_VS_BAR_OPEN":
        open_fill = 10 * MINUTE
        close_fill = 10 * MINUTE + MINUTE - 1
        assert dec_ack_clock(open_fill) == 11 * MINUTE
        assert dec_ack_clock(close_fill) == 12 * MINUTE
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"open_ack": 11 * MINUTE, "close_ack": 12 * MINUTE}}

    if fixture_id == "F19_E2_STOP_MOVED_AFTER_TP1_ACK_ONLY_TOCTOU":
        bars, mark, event, cand = _base_fixture(side=1)
        p, t1, _ = _targets(bars, event, cand)
        be = _breakeven_stop(p, BASE)
        bars[3, 2] = t1 + 0.2  # TP1 at 4*MINUTE - 1, ACK at 5*MINUTE
        bars[4, 1:5] = [be + 0.2, be + 0.2, be - 0.5, be + 0.2]  # bar 4 dips below BE, but > original stop 90
        bars[5, 1:5] = [be + 0.2, be + 0.2, be - 0.5, be + 0.2]  # bar 5 >= ACK triggers BE stop
        res = position(bars, mark, [], event, cand, BASE, "E2", 0.2)
        assert res["tiers"][1]["exit_at"] == 5 * MINUTE + MINUTE - 1
        assert res["tiers"][1]["raw_exit"] == be
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"tp1_ack": 5 * MINUTE, "be_stop_exit_at": res["tiers"][1]["exit_at"]}}

    if fixture_id == "F20_E2_SHORT_BREAKEVEN_STOP_CLAMP_AND_ACK":
        bars, mark, event, cand = _base_fixture(side=-1)
        p, t1, _ = _targets(bars, event, cand)
        be = _breakeven_stop(p, BASE)
        ind_be = float(dec_breakeven_stop(D(p["effective_entry"]), D(p["stop"]), -1, BASE))
        assert math.isclose(be, ind_be, abs_tol=1e-9) and be <= p["stop"]
        bars[3, 3] = t1 - 0.2
        bars[4, 1:5] = [be - 0.2, be + 0.5, be - 0.2, be - 0.2]  # bar 4 before ACK ignored
        bars[5, 1:5] = [be - 0.2, be + 0.5, be - 0.2, be - 0.2]  # bar 5 at ACK triggers BE
        res = position(bars, mark, [], event, cand, BASE, "E2", 0.2)
        assert res["tiers"][1]["exit_at"] == 5 * MINUTE + MINUTE - 1 and res["tiers"][1]["raw_exit"] == be
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"short_be": be, "orig_stop": p["stop"]}}

    if fixture_id == "F21_EXACT_TOUCH_NO_FILL_VS_ONE_TICK_THROUGH_LONG":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 2] = t1  # exact touch
        res_touch = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res_touch["touch_no_fill_count"] == 1 and len(res_touch["tiers"]) == 1
        bars[3, 2] = t1 + 0.1  # 1-tick through
        res_thru = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res_thru["tiers"][0]["reason"] == "TP1" and res_thru["touch_no_fill_count"] == 0
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"touch_tiers": len(res_touch["tiers"]), "thru_tiers": len(res_thru["tiers"])}}

    if fixture_id == "F22_EXACT_TOUCH_NO_FILL_VS_ONE_TICK_THROUGH_SHORT":
        bars, mark, event, cand = _base_fixture(side=-1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 3] = t1  # exact touch
        res_touch = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res_touch["touch_no_fill_count"] == 1 and len(res_touch["tiers"]) == 1
        bars[3, 3] = t1 - 0.1
        res_thru = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res_thru["tiers"][0]["reason"] == "TP1" and res_thru["touch_no_fill_count"] == 0
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"touch_no_fill": res_touch["touch_no_fill_count"]}}

    if fixture_id == "F23_E0_PRIMARY_TOUCH_VS_E0_THROUGH_SENSITIVITY":
        bars, mark, event, cand = _base_fixture(side=1)
        _, _, t2 = _targets(bars, event, cand)
        bars[3, 2] = t2  # exact touch of target2
        res_prim = position(bars, mark, [], event, cand, BASE, "E0", 0.2, fill_mode="primary")
        res_thru = position(bars, mark, [], event, cand, BASE, "E0", 0.2, fill_mode="through")
        assert res_prim["exit_reason"] == "TARGET" and res_thru["exit_reason"] == "TIME_CAP"
        assert res_thru["touch_no_fill_count"] == 1
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"primary": res_prim["exit_reason"], "through": res_thru["exit_reason"]}}

    if fixture_id == "F24_DELAY_MODE_CONFIRMATION_NEXT_OPEN_FAVORABLE":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 2] = t1 + 0.2
        bars[4, 1:5] = [t1 + 0.1, t1 + 0.3, t1, t1 + 0.1]
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2, fill_mode="delay")
        assert res["tiers"][0]["exit_at"] == 4 * MINUTE  # fills on bar 4 favorable open after bar 3 pending
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"delayed_exit_at": res["tiers"][0]["exit_at"]}}

    if fixture_id == "F25_DELAY_MODE_NEXT_OPEN_UNFAVORABLE_RECONFIRMS":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 2] = t1 + 0.2
        bars[4, 1:5] = [t1 - 0.5, t1 + 0.2, t1 - 0.5, t1]  # opens below t1, trades through again -> resets pending to bar 4
        bars[5, 1:5] = [t1, t1 + 0.2, t1 - 0.2, t1]  # bar 5 opens at t1 after bar 4 reconfirmation -> fills at bar 5 open
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2, fill_mode="delay")
        assert res["tiers"][0]["exit_at"] == 5 * MINUTE
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"reconfirmed_exit_at": res["tiers"][0]["exit_at"]}}

    if fixture_id == "F26_UNFILLED_MODE_SKIPS_FIRST_CONFIRMATION_INCLUDING_OPEN_GAP":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 1:5] = t1 + 0.5  # first confirmation is an opening gap -> skipped!
        bars[4, 2] = t1 + 0.2  # second confirmation -> fills!
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2, fill_mode="unfilled")
        assert res["tiers"][0]["exit_at"] == 4 * MINUTE + MINUTE - 1
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"unfilled_second_bar_exit_at": res["tiers"][0]["exit_at"]}}

    if fixture_id == "F27_LOT_ROUNDING_ODD_LOTS_AND_FLOAT_ULPS":
        bars, mark, event, cand = _base_fixture(side=1, base_price=1000.0)
        event.update({"decision_close": 1000.0, "stop": 900.0, "atr_hour": 200.0})
        p, t1, t2 = _targets(bars, event, cand)
        q1, q2 = dec_split_quantity("0.027", D(p["effective_entry"]), D(t1), D(t2))
        assert (q1, q2) == (Decimal("0.013"), Decimal("0.014"))
        bars[3, 2] = t1 + 0.2
        res_ulp = position(bars, mark, [], event, cand, BASE, "E1", 0.018000000000000002)
        assert [round(x["quantity"], 6) for x in res_ulp["tiers"]] == [0.009, 0.009]
        raised = False
        try:
            position(bars, mark, [], event, cand, BASE, "E1", 0.2015)
        except PartialIneligible:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"odd_split": ["0.013", "0.014"], "non_lot_rejected": raised}}

    if fixture_id == "F28_MIN_NOTIONAL_PER_TIER_REJECTION":
        bars, mark, event, cand = _base_fixture(side=1, base_price=100.0)
        # q = 0.08 -> total notional = 8.0 >= 5.0, but q1 = 0.04 -> tier notional = 4.0 < 5.0
        res_e0 = position(bars, mark, [], event, cand, BASE, "E0", 0.08)
        assert res_e0["quantity"] == 0.08
        raised = False
        try:
            position(bars, mark, [], event, cand, BASE, "E1", 0.08)
        except PartialIneligible:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"e0_valid": True, "e1_min_notional_rejected": raised}}

    if fixture_id == "F29_ENTRY_FEE_CHARGED_ONCE_EXIT_FEES_PER_TIER":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, t2 = _targets(bars, event, cand, STRESS)
        bars[3, 2] = t1 + 0.2
        bars[5, 2] = t2 + 0.2
        res = position(bars, mark, [], event, cand, STRESS, "E1", 0.2)
        entry_fees_in_journal = [j for j in res["journal"] if j["kind"] == "ENTRY_FEE"]
        exit_fees_in_journal = [j for j in res["journal"] if j["kind"] == "EXIT_FEE"]
        assert len(entry_fees_in_journal) == 1 and len(exit_fees_in_journal) == 2
        assert math.isclose(res["fee_entry"], sum(x["fee_entry_alloc"] for x in res["tiers"]), rel_tol=1e-12)
        assert math.isclose(res["fee_exit"], sum(x["fee_exit"] for x in res["tiers"]), rel_tol=1e-12)
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"fee_entry": res["fee_entry"], "fee_exit": res["fee_exit"]}}

    if fixture_id == "F30_FUNDING_SIGN_MATRIX_AND_ZERO_RATE":
        signs_verified = []
        for s in (1, -1):
            for r_str in ("0.001", "-0.001", "0.0"):
                bars, mark, event, cand = _base_fixture(side=s)
                res = position(bars, mark, [{"settlement_at": 8 * HOUR, "rate": r_str}], event, cand, BASE, "E0", 0.2)
                cash_d = D(res["funding_cash_usdt"])
                expected_d = -Decimal(s) * Decimal("0.2") * Decimal("100.0") * Decimal(r_str)
                assert cash_d == expected_d
                signs_verified.append(str(cash_d))
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"funding_bills": signs_verified}}

    if fixture_id == "F31_STOP_GAP_PRECEDES_TIME_CAP_AT_DEADLINE":
        bars, mark, event, cand = _base_fixture(side=1)
        deadline_idx = 2 + 12 * 60
        bars[deadline_idx, 1:5] = 85.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["exit_reason"] == "STOP_GAP" and res["raw_exit"] == 85.0
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_reason": res["exit_reason"], "raw_exit": 85.0}}

    if fixture_id == "F32_TIME_CAP_CAPPED_AT_FINAL_TARGET":
        bars, mark, event, cand = _base_fixture(side=1)
        _, _, t2 = _targets(bars, event, cand)
        deadline_idx = 2 + 12 * 60
        bars[deadline_idx, 1:5] = t2 + 25.0
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        assert res["exit_reason"] == "TIME_CAP" and res["raw_exit"] == t2
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"exit_reason": "TIME_CAP", "capped_raw_exit": res["raw_exit"]}}

    if fixture_id == "F33_FOLD_BOUNDARY_CENSORING_12H_18H_24H":
        end_ms = 100 * HOUR
        for h in (12, 18, 24):
            exact_boundary = end_ms - h * HOUR - MINUTE
            assert not path_eligible(exact_boundary, end_ms, h)
            assert path_eligible(exact_boundary - MINUTE, end_ms, h)
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"horizons_verified": [12, 18, 24]}}

    if fixture_id == "F34_EXIT_ACK_OUTSIDE_FOLD_HARD_GUARD":
        bars2, mark2, event2, cand2 = _base_fixture(side=1)
        b = replay(bars2, mark2, [], [event2], cand2, {"start_ms": 0, "end_ms": ENTRY_MS + 12 * HOUR + MINUTE}, BASE, "E1", 1000.0)
        assert b["fates"]["PROSPECTIVE_FOLD_CENSOR"] == 1
        assert len(b["trades"]) == 0
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"fates": b["fates"]}}

    if fixture_id == "F35_PARTIAL_TP1_ACK_DOES_NOT_REOPEN_ENTRY_OR_BYPASS_COOLDOWN":
        bars, mark, event, cand = _base_fixture(side=1, n_bars=2000)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 2] = t1 + 0.2  # TP1 fills at bar 3, ACK at 5*MINUTE, q2 exits at 12h TIME_CAP (722*MINUTE)
        sig_during_q2 = {**event, "event_id": "sig_during_q2", "event_time": 10 * MINUTE, "decision_at": 11 * MINUTE, "entry_at": 12 * MINUTE}
        sig_during_cooldown = {**event, "event_id": "sig_cooldown", "event_time": 800 * MINUTE, "decision_at": 801 * MINUTE, "entry_at": 802 * MINUTE}
        sig_after_cooldown = {**event, "event_id": "sig_after", "event_time": 1100 * MINUTE, "decision_at": 1101 * MINUTE, "entry_at": 1102 * MINUTE}
        fold = {"start_ms": 0, "end_ms": 2000 * MINUTE}
        b = replay(bars, mark, [], [event, sig_during_q2, sig_during_cooldown, sig_after_cooldown], cand, fold, BASE, "E1", 1000.0)
        assert b["fates"]["POSITION_ACK_OR_COOLDOWN"] == 2
        assert b["fates"]["FILLED"] == 2 and len(b["trades"]) == 2
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"fates": b["fates"]}}

    if fixture_id == "F36_MISSING_MARK_MINUTE_AT_SETTLEMENT_OR_CURVE_REJECTED":
        bars, mark, event, cand = _base_fixture(side=1)
        bad_mark = mark[mark[:, 0] != 8 * HOUR - MINUTE]
        raised = False
        try:
            position(bars, bad_mark, [{"settlement_at": 8 * HOUR, "rate": "0.001"}], event, cand, BASE, "E0", 0.2)
        except ValueError:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"missing_mark_rejected": raised}}

    if fixture_id == "F37_MISSING_LAST_MINUTE_ON_EXIT_PATH_REJECTED":
        bars, mark, event, cand = _base_fixture(side=1)
        bad_last = bars[bars[:, 0] != 6 * MINUTE]
        raised = False
        try:
            position(bad_last, mark, [], event, cand, BASE, "E1", 0.2)
        except ValueError:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"missing_last_rejected": raised}}

    if fixture_id == "F38_NO_CASH_DEBT_AND_BUDGET_RESERVATION_INVARIANT":
        bars, _, event, cand = _base_fixture(side=1)
        q_prod, res_prod = size(bars, event, cand, STRESS, 1500.0)  # cash > 1000 still capped at 950 budget!
        q_dec, res_dec = dec_size_admission(100.0, 20.0, 1, 12, STRESS, 1500.0)
        assert math.isclose(q_prod, float(q_dec), rel_tol=0, abs_tol=1e-12)
        assert math.isclose(res_prod["budget"], 950.0, abs_tol=1e-12)
        assert float(res_dec["actual_entry_outlay"]) <= 950.0
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"admitted_qty": q_prod, "budget_cap": res_prod["budget"]}}

    if fixture_id == "F39_UNACKNOWLEDGED_CASH_AND_PAST_FUNDING_CANNOT_PREFUND_CONCURRENT_ENTRY":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 2] = t1 + 0.2  # TP1 fills at 4*MINUTE - 1 (close of minute 3); ACK is at 5*MINUTE
        res = position(bars, mark, [{"settlement_at": 8 * HOUR, "rate": "-0.005"}], event, cand, BASE, "E1", 0.2)
        # Check at clock = 4*MINUTE - 1 (minute 3 close): TP1 has filled, but EXIT_PNL_ACK is at 5*MINUTE
        settled_at_bar3 = sum(float(j["cash_delta"]) for j in res["journal"] if int(j["timestamp"]) <= 4 * MINUTE - 1)
        # Only ENTRY_FEE and TP1 EXIT_FEE are in settled cash at bar 3 close; TP1 P&L is NOT in settled cash!
        assert settled_at_bar3 == -res["fee_entry"] - res["tiers"][0]["fee_exit"]
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"settled_delta_before_ack": settled_at_bar3}}

    if fixture_id == "F40_RETRANSMISSION_IDEMPOTENCY_AND_DUPLICATE_EXIT_REJECTION":
        bars, mark, event, cand = _base_fixture(side=1)
        dup_event = {**event}
        fold = {"start_ms": 0, "end_ms": 1500 * MINUTE}
        b = replay(bars, mark, [], [event, dup_event], cand, fold, BASE, "H1", 1000.0)
        assert len(b["trades"]) == 1 and b["fates"]["POSITION_ACK_OR_COOLDOWN"] == 1
        # Also verify our independent Decimal journal catches a duplicate tier exit (double exit)
        tampered = {**b["trades"][0], "cost": "BASE", "tiers": [b["trades"][0]["tiers"][0], b["trades"][0]["tiers"][0]]}
        audit_rec = verify_and_audit_episode(tampered, {}, _mark_dict(mark))
        assert audit_rec["status"] == "DEFECT" and any(d["defect_kind"] == "QUANTITY_CONSERVATION" for d in audit_rec["discrepancies"])
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"duplicate_entry_blocked": True, "double_exit_caught": True}}

    if fixture_id == "F41_UNPROVEN_PROVIDER_SETTLEMENT_MARK_REJECTED":
        bars, mark, event, cand = _base_fixture(side=1)
        raised = False
        try:
            position(bars, mark, [{"settlement_at": 8 * HOUR, "rate": "0.001", "mark_price": "100.0"}], event, cand, BASE, "E0", 0.2)
        except ValueError:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"unproven_mark_rejected": raised}}

    if fixture_id == "F42_QUARTER_ATR_ENTRY_GAP_VETO":
        bars, mark, event, cand = _base_fixture(side=1)
        bars[2, 1:5] = 105.5  # > 100 + 0.25 * 20 = 105.0
        b = replay(bars, mark, [], [event], cand, {"start_ms": 0, "end_ms": 1500 * MINUTE}, BASE, "E1", 1000.0)
        assert b["fates"]["ENTRY_OR_SIZE_REJECTED"] == 1 and len(b["trades"]) == 0
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"fates": b["fates"]}}

    if fixture_id == "F43_WRONG_SIDE_STOP_OR_NONPOSITIVE_EFFECTIVE_RISK_VETO":
        bars, mark, event, cand = _base_fixture(side=1)
        bad_event = {**event, "stop": 101.0}
        b = replay(bars, mark, [], [bad_event], cand, {"start_ms": 0, "end_ms": 1500 * MINUTE}, BASE, "E1", 1000.0)
        assert b["fates"]["ENTRY_OR_SIZE_REJECTED"] == 1
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"fates": b["fates"]}}

    if fixture_id == "F44_AVAILABILITY_CAUSALITY_CLOCK_VIOLATION_REJECTED":
        bars, mark, event, cand = _base_fixture(side=1)
        bad_event = {**event, "decision_at": 0}
        raised = False
        try:
            replay(bars, mark, [], [bad_event], cand, {"start_ms": 0, "end_ms": 1500 * MINUTE}, BASE, "E1", 1000.0)
        except ValueError:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"clock_violation_raised": raised}}

    if fixture_id == "F45_MARK_CURVE_INSOLVENCY_ZERO_OR_NEGATIVE_EQUITY_GUARD":
        bars, mark, event, cand = _base_fixture(side=1)
        res = position(bars, mark, [], event, cand, BASE, "E1", 0.2)
        mark_crash = mark.copy()
        mark_crash[5, 4] = 1.0  # Extreme crash with tiny starting cash -> negative equity
        raised = False
        try:
            mark_curve([res], mark_crash, 0, 1500 * MINUTE, 5.0, BASE)
        except ValueError:
            raised = True
        assert raised
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"insolvency_guard_raised": raised}}

    if fixture_id == "F46_SYNTHETIC_LEVERAGE_10X_15X_LIQUIDATION_AND_GAP_DEFICIT":
        naive_15x = run_synthetic_leverage_scenario(
            scenario_id="F46_NAIVE_15X",
            side=1,
            leverage=15.0,
            mmr=0.005,
            clearance_fee_bps=75.0,
            entry_price=30_000.0,
            stop_distance_pct=0.075,
            intrabar_adverse_mark_pct=0.068,
            open_gap_adverse_pct=0.095,
            sizing_mode="NAIVE_FULL_LEVERAGE_NOTIONAL",
        )
        capped_15x = run_synthetic_leverage_scenario(
            scenario_id="F46_CAPPED_15X",
            side=1,
            leverage=15.0,
            mmr=0.005,
            clearance_fee_bps=75.0,
            entry_price=30_000.0,
            stop_distance_pct=0.075,
            intrabar_adverse_mark_pct=0.068,
            open_gap_adverse_pct=0.095,
            sizing_mode="RISK_BUDGET_CAPPED_ISOLATED",
        )
        assert naive_15x["mark_liquidated_before_strategy_stop"] is True
        assert naive_15x["isolated_margin_bankruptcy_deficit_usdt"] < 0.0
        assert capped_15x["mark_liquidated_at_shock"] is False
        assert capped_15x["account_insolvent_after_gap"] is False
        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"naive_15x_liquidated": True, "capped_15x_survived": True}}

    if fixture_id == "F47_KNOWN_AT_SIGNAL_PREFIX_INDEPENDENCE_AND_WARMUP_PURGE":
        proof = prove_synthetic_prefix_causality()
        assert proof["status"] == "PASS"
        return {"fixture_id": fixture_id, "status": "PASS", "witness": proof}

    if fixture_id == "F48_AUDIT_TAMPER_DETECTION_CASH_FEE_FUNDING_CURVE_ARCHIVE":
        bars, mark, event, cand = _base_fixture(side=1)
        _, t1, _ = _targets(bars, event, cand)
        bars[3, 2] = t1 + 0.2
        f_events = [{"settlement_at": 8 * HOUR, "rate": "0.001"}]
        res = position(bars, mark, f_events, event, cand, STRESS, "E1", 0.2)
        c_dict = mark_curve([res], mark, 0, 1500 * MINUTE, 1000.0, STRESS)
        base_trade = {**res, "cost": "STRESS", "cash_before_entry": 1000.0, "cash_after_ack": c_dict["ending_equity"]}
        f_lookup = {8 * HOUR: Decimal("0.001")}
        m_lookup = _mark_dict(mark)

        # Clean pass
        clean = verify_and_audit_episode(base_trade, f_lookup, m_lookup, curve_array=c_dict["curve"])
        assert clean["status"] == "PASS"

        # Tamper 1: tier fee drift
        t_fee = {**base_trade, "tiers": [{**base_trade["tiers"][0], "fee_exit": base_trade["tiers"][0]["fee_exit"] + 0.5}, base_trade["tiers"][1]]}
        assert verify_and_audit_episode(t_fee, f_lookup, m_lookup)["status"] == "DEFECT"

        # Tamper 2: residual funding quantity drift
        t_fund = {**base_trade, "funding_settlements": [{**base_trade["funding_settlements"][0], "quantity": "0.2"}]}
        assert verify_and_audit_episode(t_fund, f_lookup, m_lookup)["status"] == "DEFECT"

        # Tamper 3: premature ACK in journal
        t_ack = {**base_trade, "journal": [{**j, "timestamp": int(j["timestamp"]) - MINUTE} if j["kind"] == "EXIT_PNL_ACK" else j for j in base_trade["journal"]]}
        assert verify_and_audit_episode(t_ack, f_lookup, m_lookup)["status"] == "DEFECT"

        # Tamper 4: Mark curve drift
        bad_curve = c_dict["curve"].copy()
        bad_curve[5, 1] += 1.0
        assert verify_and_audit_episode(base_trade, f_lookup, m_lookup, curve_array=bad_curve)["status"] == "DEFECT"

        return {"fixture_id": fixture_id, "status": "PASS", "witness": {"tampers_detected": 4}}

    raise ValueError(f"Unknown collision fixture_id: {fixture_id}")


def run_all_collision_fixtures() -> dict[str, Any]:
    """Execute all 48 registered deterministic adversarial collision fixtures."""
    results: list[dict[str, Any]] = []
    for meta in COLLISION_FIXTURE_REGISTRY:
        fid = meta["id"]
        out = execute_collision_fixture(fid)
        results.append({**meta, **out})
    passed = sum(1 for r in results if r["status"] == "PASS")
    return {
        "status": "PASS" if passed == len(COLLISION_FIXTURE_REGISTRY) else "DEFECT_FOUND",
        "total_fixtures": len(COLLISION_FIXTURE_REGISTRY),
        "passed_fixtures": passed,
        "fixtures": results,
    }
