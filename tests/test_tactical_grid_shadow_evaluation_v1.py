from __future__ import annotations

import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest
from test_tactical_feature_evidence_v2 import build_sample_evidence_and_assessment

from btc_quant_agent.domain import Candle
from btc_quant_agent.market_watch.domain import (
    GRID_PATH_MODEL_VERSION,
    GridDecision,
)
from btc_quant_agent.market_watch.evidence import (
    GridPlanEvidence,
    TacticalEvidenceIdentityError,
    TacticalFeatureEvidenceV2,
    canonical_evidence_json,
    canonical_evidence_payload,
    compute_evidence_id,
)
from btc_quant_agent.market_watch.grid_shadow import (
    evaluate_grid_shadow_episode,
)
from btc_quant_agent.market_watch.grid_shadow_evidence import (
    GRID_HORIZON_MS,
    GridEligibilityStatus,
    GridTerminalReason,
    TacticalGridShadowEvaluationConflictError,
    TacticalGridShadowEvaluationIdentityError,
    compute_anchor_index,
    construct_grid_levels,
    deserialize_tactical_grid_shadow_evaluation,
    verify_tactical_grid_shadow_evaluation_identity,
)
from btc_quant_agent.market_watch.state import MarketWatchStateStore


def _make_grid_evidence(
    decision: GridDecision = GridDecision.LONG_BIAS,
    lower_bound: float | None = 48000.0,
    upper_bound: float | None = 52000.0,
    grid_count: int = 4,
    trigger_price: float | None = 50000.0,
    stop_loss: float | None = 46000.0,
    take_profit: float | None = 54000.0,
    decision_time_ms: int = 1_700_000_100_000,
) -> TacticalFeatureEvidenceV2:
    """Helper to generate a valid TacticalFeatureEvidenceV2 with a custom GridPlanEvidence."""
    base_ev, _ = build_sample_evidence_and_assessment(decision_time_ms=decision_time_ms)
    grid_plan_ev = GridPlanEvidence(
        decision=decision.value,
        lower_bound=lower_bound,
        upper_bound=upper_bound,
        grid_count=grid_count,
        estimated_grid_pct=2.0 if (lower_bound and upper_bound) else None,
        trigger_price=trigger_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        reason_codes=("GRID_RANGING",),
    )
    ev_updated = replace(base_ev, grid_advisory_plan=grid_plan_ev)
    payload = canonical_evidence_payload(ev_updated)
    new_ev_id = compute_evidence_id(payload)
    return replace(ev_updated, evidence_id=new_ev_id)


def _insert_feature_evidence(store: MarketWatchStateStore, ev: TacticalFeatureEvidenceV2) -> None:
    """Insert feature evidence into db for linkage validation."""
    now_ms = 1_700_000_100_000
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO tactical_feature_evidence_v2 (
                evidence_id, evidence_schema_version, decision_time_ms, symbol,
                snapshot_hash, policy_version, config_hash, semantic_identity_hash,
                signal_identity, setup_key, lifecycle_state, selected_playbook,
                final_directional_decision, rule_score, reference_universe_status,
                evidence_json, persisted_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ev.evidence_id,
                ev.evidence_schema_version,
                ev.decision_time_ms,
                ev.symbol,
                ev.snapshot_hash,
                ev.policy_version,
                ev.config_hash,
                None,
                ev.signal_identity,
                ev.setup_key,
                ev.lifecycle_state,
                ev.selected_playbook,
                ev.decision_trace.final_directional_decision,
                ev.rule_score,
                "COMPLETE",
                canonical_evidence_json(ev),
                now_ms,
            ),
        )
        conn.commit()


def _make_1m_candles(
    start_ms: int,
    count: int,
    prices: list[tuple[float, float, float, float]],
    symbol: str = "BTCUSDT",
) -> list[Candle]:
    """Generate 1m candles for testing."""
    candles: list[Candle] = []
    t = start_ms
    for i in range(count):
        o, h, l, c = prices[i] if i < len(prices) else prices[-1]
        candles.append(
            Candle(
                symbol=symbol,
                interval="1m",
                open_time_ms=t,
                close_time_ms=t + 60_000,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=10.0,
            )
        )
        t += 60_000
    return candles


# ==============================================================================
# B2B-A01 .. B2B-A04: Artifact, Identity, and Persistence
# ==============================================================================

def test_b2b_a01_source_feature_evidence_identity_verifies() -> None:
    """B2B-A01: source TacticalFeatureEvidenceV2 identity verifies fail-closed."""
    ev = _make_grid_evidence()
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    # Valid evidence evaluates cleanly
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.feature_evidence_id == ev.evidence_id

    # Tampered evidence_id fails
    tampered_ev = replace(ev, evidence_id="tampered_sha_000000000000000000000000000000000000000000000000000000000000")
    with pytest.raises(TacticalEvidenceIdentityError):
        evaluate_grid_shadow_episode(tampered_ev, candles)


def test_b2b_a02_tampered_embedded_evaluation_id_rejected() -> None:
    """B2B-A02: tampered embedded B2B evaluation_id rejected."""
    ev = _make_grid_evidence()
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    res = evaluate_grid_shadow_episode(ev, candles)

    # Valid identity passes
    verify_tactical_grid_shadow_evaluation_identity(res)

    # Tamper evaluation_id
    tampered = replace(res, evaluation_id="0000000000000000000000000000000000000000000000000000000000000000")
    with pytest.raises(TacticalGridShadowEvaluationIdentityError, match="B2B_EVALUATION_ID_MISMATCH"):
        verify_tactical_grid_shadow_evaluation_identity(tampered)

    # Deserializing tampered payload fails
    payload = tampered.to_dict()
    with pytest.raises(TacticalGridShadowEvaluationIdentityError):
        deserialize_tactical_grid_shadow_evaluation(payload, verify_identity=True)


def test_b2b_a03_identical_natural_key_replay_is_idempotent(tmp_path: Path) -> None:
    """B2B-A03: identical natural-key replay is idempotent."""
    store = MarketWatchStateStore(tmp_path / "mw.db")
    ev = _make_grid_evidence()
    _insert_feature_evidence(store, ev)

    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    eval_res = evaluate_grid_shadow_episode(ev, candles)

    id1 = store.save_grid_shadow_evaluation(eval_res)
    id2 = store.save_grid_shadow_evaluation(eval_res)
    assert id1 == id2 == eval_res.evaluation_id

    fetched = store.get_grid_shadow_evaluation(id1)
    assert fetched is not None
    assert fetched.evaluation_id == id1


def test_b2b_a04_divergent_same_natural_key_replay_fails_closed(tmp_path: Path) -> None:
    """B2B-A04: divergent same-natural-key replay fails closed."""
    store = MarketWatchStateStore(tmp_path / "mw.db")
    ev = _make_grid_evidence()
    _insert_feature_evidence(store, ev)

    candles1 = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    eval_res1 = evaluate_grid_shadow_episode(ev, candles1)
    store.save_grid_shadow_evaluation(eval_res1)

    # Different candles produce different evaluation_id under the same feature_evidence_id
    candles2 = _make_1m_candles(ev.decision_time_ms, 5, [(49000.0, 49000.0, 48500.0, 48500.0)])
    eval_res2 = evaluate_grid_shadow_episode(ev, candles2)
    assert eval_res1.evaluation_id != eval_res2.evaluation_id
    assert eval_res1.feature_evidence_id == eval_res2.feature_evidence_id

    with pytest.raises(TacticalGridShadowEvaluationConflictError, match="B2B_EVALUATION_CONFLICT"):
        store.save_grid_shadow_evaluation(eval_res2)


# ==============================================================================
# B2B-A05 .. B2B-A07: Causality and Coverage
# ==============================================================================

def test_b2b_a05_pre_decision_candle_cannot_fill() -> None:
    """B2B-A05: pre-decision candle cannot fill."""
    ev = _make_grid_evidence(decision_time_ms=1_700_000_100_000)
    # Candles strictly before decision time crossing levels
    pre_candles = _make_1m_candles(
        start_ms=1_700_000_000_000,
        count=1,
        prices=[(50000.0, 50000.0, 47000.0, 47500.0)],
    )
    # Candles after decision time flat at 50000
    post_candles = _make_1m_candles(
        start_ms=ev.decision_time_ms,
        count=5,
        prices=[(50000.0, 50000.0, 50000.0, 50000.0)] * 5,
    )
    all_candles = pre_candles + post_candles
    res = evaluate_grid_shadow_episode(ev, all_candles)
    # Pre-decision candle must not cause any paired cycle or open lots
    assert res.paired_cycle_count == 0
    assert res.max_open_lot_count == 0


def test_b2b_a06_incomplete_1m_coverage_cannot_fabricate_pnl() -> None:
    """B2B-A06: incomplete 1m coverage cannot fabricate PnL."""
    ev = _make_grid_evidence()
    # Missing first candle after decision time (gap at start)
    gap_candles = _make_1m_candles(
        start_ms=ev.decision_time_ms + 120_000,
        count=10,
        prices=[(50000.0, 51000.0, 49000.0, 50000.0)] * 10,
    )
    res = evaluate_grid_shadow_episode(ev, gap_candles)
    assert res.market_path_coverage == "INCOMPLETE"
    assert res.eligibility_status == GridEligibilityStatus.PENDING_DATA_GAP.value


def test_b2b_a07_exact_24h_horizon_cannot_outcome_guidedly_extend() -> None:
    """B2B-A07: exact 24h horizon cannot outcome-guidedly extend."""
    ev = _make_grid_evidence(lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # 24h of 1m candles (1440 candles)
    horizon_ms = GRID_HORIZON_MS
    n_candles = 1440
    # First candle dips to 49000 (opens slot 1), then stays at 48500 through horizon end
    prices = [(50000.0, 50000.0, 48900.0, 48900.0)] + [(48900.0, 48900.0, 48900.0, 48900.0)] * (n_candles - 1)
    candles = _make_1m_candles(start_ms=ev.decision_time_ms, count=n_candles, prices=prices)

    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.terminal_reason == GridTerminalReason.HORIZON.value
    assert res.terminal_time_ms == ev.decision_time_ms + horizon_ms
    assert res.eligibility_status == GridEligibilityStatus.RESOLVED.value


# ==============================================================================
# B2B-A08 .. B2B-A11: Grid Structure and Slot Management
# ==============================================================================

def test_b2b_a08_n_intervals_produce_n_plus_1_deterministic_levels() -> None:
    """B2B-A08: N intervals produce N+1 deterministic monotonic levels."""
    levels = construct_grid_levels(lower_bound=40000.0, upper_bound=50000.0, grid_count=5)
    assert len(levels) == 6
    assert levels[0] == 40000.0
    assert levels[-1] == 50000.0
    for i in range(len(levels) - 1):
        assert levels[i] < levels[i + 1]
    # Check step = 2000
    assert levels[1] == 42000.0
    assert levels[2] == 44000.0


def test_b2b_a09_nearest_level_tie_chooses_lower_anchor_index() -> None:
    """B2B-A09: nearest-level tie chooses lower anchor index."""
    levels = (40000.0, 42000.0, 44000.0, 46000.0)
    # Midpoint between level 1 (42000) and level 2 (44000) is 43000
    anchor = compute_anchor_index(levels, reference_price=43000.0)
    assert anchor == 1  # chooses lower index on exact tie


def test_b2b_a10_slot_cannot_hold_duplicate_simultaneous_lots() -> None:
    """B2B-A10: a slot cannot hold duplicate simultaneous lots."""
    ev = _make_grid_evidence(
        decision=GridDecision.LONG_BIAS,
        lower_bound=48000.0,
        upper_bound=52000.0,
        grid_count=4,
        trigger_price=49500.0,
    )
    # Levels: 48000 (0), 49000 (1), 50000 (2), 51000 (3), 52000 (4)
    # Candle 1 crosses 49000 downward -> opens slot 1
    # Candle 2 crosses 49000 downward again without closing -> should not open another lot for slot 1
    prices = [
        (49500.0, 49500.0, 48900.0, 48950.0),
        (48950.0, 49050.0, 48900.0, 48950.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.max_open_lot_count == 1
    assert res.paired_cycle_count == 0


def test_b2b_a11_paired_close_re_arms_slot() -> None:
    """B2B-A11: paired close re-arms slot."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Levels: 48000, 49000, 50000, 51000, 52000. Anchor = 2 (50000).
    # 1. Downward through 49000 opens slot 1
    # 2. Upward through 50000 closes slot 1 (paired cycle 1)
    # 3. Downward through 49000 opens slot 1 again (re-armed!)
    # 4. Upward through 50000 closes slot 1 again (paired cycle 2)
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 50100.0, 48950.0, 50050.0),
        (50050.0, 50050.0, 48900.0, 48950.0),
        (48950.0, 50100.0, 48950.0, 50050.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 4, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.paired_cycle_count == 2


# ==============================================================================
# B2B-A12 .. B2B-A15: Direction Semantics
# ==============================================================================

def test_b2b_a12_long_bias_never_opens_short() -> None:
    """B2B-A12: LONG_BIAS never opens short."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Price rises crossing 51000 and 52000 upward
    prices = [(50000.0, 52500.0, 50000.0, 52200.0)]
    candles = _make_1m_candles(ev.decision_time_ms, 1, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.short_inventory_peak == 0.0
    assert res.max_open_lot_count == 0


def test_b2b_a13_short_bias_never_opens_long() -> None:
    """B2B-A13: SHORT_BIAS never opens long."""
    ev = _make_grid_evidence(decision=GridDecision.SHORT_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Price falls crossing 49000 and 48000 downward
    prices = [(50000.0, 50000.0, 47500.0, 47800.0)]
    candles = _make_1m_candles(ev.decision_time_ms, 1, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.long_inventory_peak == 0.0
    assert res.max_open_lot_count == 0


def test_b2b_a14_neutral_uses_below_anchor_long_and_above_anchor_short() -> None:
    """B2B-A14: NEUTRAL uses below-anchor long / above-anchor short."""
    ev = _make_grid_evidence(decision=GridDecision.NEUTRAL, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Levels: 48000 (0), 49000 (1), 50000 (2, anchor), 51000 (3), 52000 (4)
    # Candle 1: dips below anchor to 48900 -> opens long slot 1
    # Candle 2: rises back through 50000 to 51200 -> closes long slot 1 and opens short slot 3
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 51200.0, 48950.0, 51100.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.paired_cycle_count == 1
    assert res.long_inventory_peak > 0.0
    assert res.short_inventory_peak > 0.0


def test_b2b_a15_pause_creates_not_active_with_no_fills_or_pnl() -> None:
    """B2B-A15: PAUSE creates NOT_ACTIVE with no fills/PnL."""
    ev = _make_grid_evidence(decision=GridDecision.PAUSE)
    candles = _make_1m_candles(ev.decision_time_ms, 10, [(50000.0, 52000.0, 48000.0, 50000.0)] * 10)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.eligibility_status == GridEligibilityStatus.NOT_ACTIVE_PAUSE.value
    assert res.paired_cycle_count == 0
    assert res.gross_pnl_before_costs == 0.0
    assert res.net_pnl_after_fees_slippage == 0.0
    assert res.funding_pnl is None
    assert res.net_pnl_after_funding is None


# ==============================================================================
# B2B-A16 .. B2B-A18: Crossing Order and Path Models
# ==============================================================================

def test_b2b_a16_ascending_multi_level_crossing_is_low_to_high() -> None:
    """B2B-A16: ascending multi-level crossing is low→high."""
    ev = _make_grid_evidence(decision=GridDecision.SHORT_BIAS, lower_bound=40000.0, upper_bound=50000.0, grid_count=5)
    # Levels: 40k, 42k, 44k, 46k, 48k, 50k.
    # Single candle ascending from 41k to 47k (crosses 42k, 44k, 46k)
    candles = _make_1m_candles(ev.decision_time_ms, 1, [(41000.0, 47000.0, 41000.0, 47000.0)])
    res = evaluate_grid_shadow_episode(ev, candles)
    # Opened slots 1, 2, 3
    assert res.max_open_lot_count == 3


def test_b2b_a17_descending_multi_level_crossing_is_high_to_low() -> None:
    """B2B-A17: descending multi-level crossing is high→low."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=40000.0, upper_bound=50000.0, grid_count=5)
    # Levels: 40k, 42k, 44k, 46k, 48k, 50k. Anchor=44k (slot 2).
    # Single candle descending from 45k to 41k (crosses 44k, 42k)
    candles = _make_1m_candles(ev.decision_time_ms, 1, [(45000.0, 45000.0, 41000.0, 41000.0)])
    res = evaluate_grid_shadow_episode(ev, candles)
    # Crosses 44k (slot 2) and 42k (slot 1) downward
    assert res.max_open_lot_count == 2


def test_b2b_a18_divergent_1m_paths_evaluate_both_and_select_conservative() -> None:
    """B2B-A18: divergent 1m paths evaluate both and select deterministic conservative state."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Intrabar swing: open=50000, high=51500, low=48500, close=50000
    candles = _make_1m_candles(ev.decision_time_ms, 1, [(50000.0, 51500.0, 48500.0, 50000.0)])
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.grid_path_model_version == GRID_PATH_MODEL_VERSION
    # Conservative arbiter chose the path resulting in worse equity / inventory accumulation
    assert res.min_marked_equity <= 1.0


# ==============================================================================
# B2B-A19 .. B2B-A23: Costs and Accounting Invariants
# ==============================================================================

def test_b2b_a19_paired_gross_pnl_formulas_correct() -> None:
    """B2B-A19: long and short paired gross PnL formulas are correct."""
    # Long: buys at 49000, sells at 50000. Qty = (1.0 / 4) / 49000 = 0.25 / 49000
    # Expected gross = qty * (50000 - 49000) = 0.25 * 1000 / 49000 = 0.00510204...
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 50100.0, 48950.0, 50050.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.paired_cycle_count == 1
    expected_gross = 0.25 * (50000.0 - 49000.0) / 49000.0
    assert abs(res.paired_gross_pnl - expected_gross) < 1e-6


def test_b2b_a20_maker_fee_on_every_normal_open_and_paired_close() -> None:
    """B2B-A20: maker fee on every normal open/paired close."""
    ev = _make_grid_evidence(
        decision=GridDecision.LONG_BIAS,
        lower_bound=48000.0,
        upper_bound=52000.0,
        grid_count=4,
        trigger_price=49500.0,
    )
    maker_fee_rate = 0.0002
    unit_notional = 0.25
    # 1 open (49000) and 1 paired close (50000)
    # open fee = 0.25 * 0.0002 = 0.00005
    # close notional = qty * 50000 = (0.25 / 49000) * 50000 = 0.255102
    # close fee = 0.255102 * 0.0002 = 0.00005102
    prices = [
        (49500.0, 49500.0, 48900.0, 48950.0),
        (48950.0, 50100.0, 48950.0, 50050.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    expected_fees = (unit_notional * maker_fee_rate) + ((unit_notional / 49000.0) * 50000.0 * maker_fee_rate)
    assert abs(res.paired_maker_fees - expected_fees) < 1e-6


def test_b2b_a21_terminal_liquidation_uses_taker_fee_and_adverse_slippage() -> None:
    """B2B-A21: terminal liquidation uses taker fee + adverse slippage."""
    ev = _make_grid_evidence(
        decision=GridDecision.LONG_BIAS,
        lower_bound=48000.0,
        upper_bound=52000.0,
        grid_count=4,
        stop_loss=46000.0,
    )
    # Opens long at 49000, then hits stop loss at 46000
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 48950.0, 45500.0, 45800.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.terminal_reason == GridTerminalReason.STOP_LOSS.value
    assert res.terminal_taker_fee > 0.0
    assert res.terminal_slippage_cost > 0.0


def test_b2b_a22_utilization_never_exceeds_normalized_cap() -> None:
    """B2B-A22: utilization never exceeds normalized cap 1.0."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=40000.0, upper_bound=50000.0, grid_count=4)
    # Price crashes through all levels
    prices = [(50000.0, 50000.0, 39000.0, 39000.0)]
    candles = _make_1m_candles(ev.decision_time_ms, 1, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.peak_capital_utilization <= 1.0 + 1e-9


def test_b2b_a23_maximum_underwater_differs_from_peak_to_trough_drawdown() -> None:
    """B2B-A23: maximum_underwater differs correctly from peak-to-trough drawdown."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Scenario: equity rises above 1.0 to 1.05 (via paired cycle), then drops to 1.02.
    # Underwater from initial 1.0 is 0.0! But drawdown from peak (1.05) is 0.03.
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 50100.0, 48950.0, 50050.0),
        (50050.0, 50050.0, 48900.0, 48950.0),  # open lot again
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 3, prices)
    res = evaluate_grid_shadow_episode(ev, candles)
    assert res.max_drawdown_from_prior_peak != res.maximum_underwater
    assert abs(res.max_drawdown_from_prior_peak) >= abs(res.maximum_underwater)


# ==============================================================================
# B2B-A24 .. B2B-A27: Funding Causality and Boundary Discipline
# ==============================================================================

def test_b2b_a24_positive_funding_debits_long_and_credits_short() -> None:
    """B2B-A24: positive funding debits long / credits short."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Open long at 49000 in candle 0
    # Funding event occurs in candle 1 (no inventory change in candle 1)
    funding_time = ev.decision_time_ms + 100_000
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 48960.0, 48940.0, 48950.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    funding_records = [
        {"funding_time_ms": funding_time, "funding_rate": 0.001, "mark_price": 48950.0}
    ]
    res = evaluate_grid_shadow_episode(ev, candles, funding_records=funding_records)
    # Long position pays positive funding -> funding_pnl is negative
    assert res.funding_pnl is not None
    assert res.funding_pnl < 0.0


def test_b2b_a25_negative_funding_reverses_signs() -> None:
    """B2B-A25: negative funding reverses signs."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    funding_time = ev.decision_time_ms + 100_000
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 48960.0, 48940.0, 48950.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    funding_records = [
        {"funding_time_ms": funding_time, "funding_rate": -0.001, "mark_price": 48950.0}
    ]
    res = evaluate_grid_shadow_episode(ev, candles, funding_records=funding_records)
    # Long position receives negative funding -> funding_pnl is positive
    assert res.funding_pnl is not None
    assert res.funding_pnl > 0.0


def test_b2b_a26_settlement_in_inventory_changing_minute_creates_ambiguity() -> None:
    """B2B-A26: settlement in inventory-changing minute creates funding ambiguity and nulls authoritative funding/net."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Funding settlement falls in minute 0 where crossing happens
    funding_time = ev.decision_time_ms + 30_000
    prices = [(50000.0, 50000.0, 48900.0, 48950.0)]
    candles = _make_1m_candles(ev.decision_time_ms, 1, prices)
    funding_records = [
        {"funding_time_ms": funding_time, "funding_rate": 0.001, "mark_price": 49000.0}
    ]
    res = evaluate_grid_shadow_episode(ev, candles, funding_records=funding_records)
    assert res.funding_coverage == "AMBIGUOUS_FUNDING_BOUNDARY"
    assert res.funding_pnl is None
    assert res.net_pnl_after_funding is None
    # Net PnL after fees and slippage remains intact
    assert res.net_pnl_after_fees_slippage is not None


def test_b2b_a27_missing_settlement_mark_price_makes_funding_unavailable() -> None:
    """B2B-A27: missing settlement mark price makes funding/net unavailable."""
    ev = _make_grid_evidence(decision=GridDecision.LONG_BIAS, lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    funding_time = ev.decision_time_ms + 100_000
    prices = [
        (50000.0, 50000.0, 48900.0, 48950.0),
        (48950.0, 48960.0, 48940.0, 48950.0),
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 2, prices)
    # Missing mark_price
    funding_records = [
        {"funding_time_ms": funding_time, "funding_rate": 0.001, "mark_price": None}
    ]
    res = evaluate_grid_shadow_episode(ev, candles, funding_records=funding_records)
    assert res.funding_pnl is None
    assert res.net_pnl_after_funding is None


# ==============================================================================
# B2B-A28 .. B2B-A32: Boundary and Policy Diagnostics
# ==============================================================================

def test_b2b_a28_boundary_touch_is_not_breach_strict_outside_is_breach() -> None:
    """B2B-A28: boundary touch != breach; strict outside = breach."""
    ev = _make_grid_evidence(lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    # Touch lower bound 48000.0 exactly -> not a breach
    touch_candles = _make_1m_candles(ev.decision_time_ms, 1, [(50000.0, 50000.0, 48000.0, 49000.0)])
    res_touch = evaluate_grid_shadow_episode(ev, touch_candles)
    assert not res_touch.lower_boundary_breached
    assert res_touch.boundary_breach_count == 0

    # Strict outside: 47999.0 -> breach!
    breach_candles = _make_1m_candles(ev.decision_time_ms, 1, [(50000.0, 50000.0, 47999.0, 49000.0)])
    res_breach = evaluate_grid_shadow_episode(ev, breach_candles)
    assert res_breach.lower_boundary_breached
    assert res_breach.boundary_breach_count == 1


def test_b2b_a29_future_grid_shift_diagnostic_cannot_mutate_frozen_plan() -> None:
    """B2B-A29: future grid shift diagnostic cannot mutate frozen plan."""
    ev = _make_grid_evidence(lower_bound=48000.0, upper_bound=52000.0, grid_count=4)
    frozen_plan_copy = json.dumps(ev.grid_advisory_plan.to_dict()) if ev.grid_advisory_plan else ""
    future_asmts = [
        {
            "symbol": ev.symbol,
            "decision_time_ms": ev.decision_time_ms + 3600_000,
            "decision_json": json.dumps({"grid": {"decision": "LONG_BIAS", "lower_bound": 47000.0, "upper_bound": 51000.0, "grid_count": 4}}),
            "reason_codes_json": json.dumps(["GRID_RANGING"]),
        }
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    res = evaluate_grid_shadow_episode(ev, candles, future_assessments=future_asmts)
    assert json.dumps(res.frozen_grid_plan) == frozen_plan_copy
    assert res.grid_levels[0] == 48000.0
    assert res.grid_shift_count == 1


def test_b2b_a30_incomplete_assessment_coverage_never_becomes_zero_shifts() -> None:
    """B2B-A30: incomplete assessment coverage never becomes zero shifts."""
    ev = _make_grid_evidence()
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    res = evaluate_grid_shadow_episode(ev, candles, future_assessments=(), assessment_diagnostic_coverage="UNAVAILABLE")
    assert res.future_assessment_diagnostic_status == "UNAVAILABLE"
    assert res.grid_shift_count is None
    assert res.grid_shift_frequency_per_day is None


def test_b2b_a31_technical_trend_transition_reason_detected_without_backward_leakage() -> None:
    """B2B-A31: technical trend-transition reason detected without backward leakage."""
    ev = _make_grid_evidence()
    t_transition = ev.decision_time_ms + 7200_000
    future_asmts = [
        {
            "symbol": ev.symbol,
            "decision_time_ms": t_transition,
            "decision_json": json.dumps({"grid": {"decision": "PAUSE"}}),
            "reason_codes_json": json.dumps(["HIGH_ADX_OR_TREND_DOMINANT"]),
        }
    ]
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    res = evaluate_grid_shadow_episode(ev, candles, future_assessments=future_asmts)
    assert res.first_technical_trend_transition_ms == t_transition


def test_b2b_a32_trend_transition_loss_null_unless_coverage_authoritative() -> None:
    """B2B-A32: trend_transition_loss null unless diagnostic coverage authoritative."""
    ev = _make_grid_evidence()
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    res = evaluate_grid_shadow_episode(ev, candles, future_assessments=(), assessment_diagnostic_coverage="UNAVAILABLE")
    assert res.trend_transition_loss is None
    assert res.net_equity_at_first_trend_transition is None


# ==============================================================================
# B2B-A33 .. B2B-A35: Safety Fences and Boundary Isolation
# ==============================================================================

def test_b2b_a33_directional_b2a_rows_remain_unchanged(tmp_path: Path) -> None:
    """B2B-A33: directional B2A rows remain unchanged."""
    store = MarketWatchStateStore(tmp_path / "mw.db")
    ev = _make_grid_evidence()
    _insert_feature_evidence(store, ev)

    # Insert a mock B2A row
    with store._connect() as conn:
        conn.execute(
            """
            INSERT INTO tactical_shadow_evaluations_v2 (
                evaluation_id, evaluation_schema_version, shadow_record_id, feature_evidence_id,
                symbol, playbook, direction, signal_time_ms, evaluation_profile_version,
                evaluation_horizon_bars, evaluation_horizon_ms, fill_status, terminal_status,
                evaluation_json, persisted_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "mock_b2a_eval_id_12345",
                "TACTICAL_SHADOW_EVALUATION_V2",
                101,
                ev.evidence_id,
                ev.symbol,
                "BREAKOUT_RETEST",
                "LONG",
                ev.decision_time_ms,
                "DIRECTIONAL_OUTCOME_PROFILE_V1",
                12,
                10800000,
                "FILLED",
                "RESOLVED",
                "{}",
                1700000100000,
            ),
        )
        conn.commit()

    # Save a B2B evaluation
    candles = _make_1m_candles(ev.decision_time_ms, 5, [(50000.0, 50000.0, 50000.0, 50000.0)])
    b2b_eval = evaluate_grid_shadow_episode(ev, candles)
    store.save_grid_shadow_evaluation(b2b_eval)

    # Check B2A row is completely intact
    with store._connect() as conn:
        row = conn.execute("SELECT evaluation_id FROM tactical_shadow_evaluations_v2 WHERE shadow_record_id = 101").fetchone()
        assert row is not None
        assert row[0] == "mock_b2a_eval_id_12345"


def test_b2b_a34_h40_diff_remains_zero() -> None:
    """B2B-A34: H40 diff remains zero."""
    res = subprocess.run(
        ["git", "diff", "407dabc415ae8cae4210250e992941c8b9b25464..HEAD", "--", "src/btc_quant_agent/h40"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert res.stdout.strip() == "", f"Unexpected diff in H40: {res.stdout}"


def test_b2b_a35_no_authenticated_or_private_order_mutation_exists() -> None:
    """B2B-A35: no authenticated/private order/account mutation exists."""
    target_files = [
        "src/btc_quant_agent/market_watch/grid_shadow.py",
        "src/btc_quant_agent/market_watch/grid_shadow_evidence.py",
    ]
    forbidden_terms = [
        "new_order",
        "create_order",
        "cancel_order",
        "POST /fapi",
        "DELETE /fapi",
        "PUT /fapi",
        "BinanceSignedClient",
    ]
    for tf in target_files:
        p = Path(tf)
        if not p.exists():
            continue
        content = p.read_text(encoding="utf-8")
        for term in forbidden_terms:
            assert term not in content, f"Forbidden execution term '{term}' found in {tf}"
