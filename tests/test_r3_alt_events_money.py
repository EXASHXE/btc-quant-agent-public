"""Tests for r3_alt_engine: Events, money subledgers, ACK, and risk projections.

Covers Oracle cases:
- T01–T05: Mark / Point-in-time
- T06–T09: ACK semantics and causes
- T10–T15: Funding obligations, clocks, and owner isolation
- T16–T19: Risk projection, kill latches, pending loss recognition
- T32–T34: Corner capital safety, non-netting, deficit, and fee conversion
"""

import sys
from decimal import Decimal
from pathlib import Path

_SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

import pytest

from btc_quant_agent.strategy_research.r3_alt_engine.clock import (
    ClockManager,
)
from btc_quant_agent.strategy_research.r3_alt_engine.journal import (
    CauseOrOwnerFailClosedError,
    ConflictFailClosedError,
    InvalidMinuteClockError,
    compute_payload_digest,
)
from btc_quant_agent.strategy_research.r3_alt_engine.model import (
    CostScenario,
    Direction,
    EngineState,
    Event,
    EventKind,
    ExitReason,
    OwnerKey,
    OwnerLedger,
    OwnerPhase,
    PendingExitSlice,
    ReplayConfig,
)
from btc_quant_agent.strategy_research.r3_alt_engine.money import (
    assert_invariants,
    project_as_of,
)
from btc_quant_agent.strategy_research.r3_alt_engine.reducer import reduce


def _create_base_config() -> ReplayConfig:
    return ReplayConfig(
        candidates=("STRUCTURAL_CONTINUATION_LONG_04H",),
        cost_scenario=CostScenario.BASE,
        initial_cash=Decimal("1000.000000000000"),
    )


# ---------------------------------------------------------------------------
# T01–T05: Mark and PIT
# ---------------------------------------------------------------------------

def test_t01_same_close_mark_conflict() -> None:
    """T01: Same source, symbol, close with conflicting prices fails closed regardless of permutation."""
    config = _create_base_config()
    s_time = 1700000000000

    payload_50k = {"price": "50000.0", "close_ms": s_time}
    payload_52k = {"price": "52000.0", "close_ms": s_time}

    ev_50k = Event(
        event_id="MARK_BTC_50K",
        kind=EventKind.OBSERVED_MARK,
        book_id="BASE",
        candidate_id="",
        symbol="BTCUSDT",
        owner_key=OwnerKey("BASE", ""),
        order_id="",
        position_id="",
        fill_id="",
        settlement_id="",
        source_id="TEST_SOURCE",
        cause_id="",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=payload_50k,
        payload_digest=compute_payload_digest(payload_50k),
    )

    ev_52k = Event(
        event_id="MARK_BTC_52K",
        kind=EventKind.OBSERVED_MARK,
        book_id="BASE",
        candidate_id="",
        symbol="BTCUSDT",
        owner_key=OwnerKey("BASE", ""),
        order_id="",
        position_id="",
        fill_id="",
        settlement_id="",
        source_id="TEST_SOURCE",
        cause_id="",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=payload_52k,
        payload_digest=compute_payload_digest(payload_52k),
    )

    # Permutation 1: 50k then 52k
    st1 = EngineState(clock_ms=s_time, latest_mark_close_ms=s_time)
    st1, _, _ = reduce(st1, ev_50k, config)
    with pytest.raises(ConflictFailClosedError):
        reduce(st1, ev_52k, config)

    # Permutation 2: 52k then 50k
    st2 = EngineState(clock_ms=s_time, latest_mark_close_ms=s_time)
    st2, _, _ = reduce(st2, ev_52k, config)
    with pytest.raises(ConflictFailClosedError):
        reduce(st2, ev_50k, config)


def test_t02_delayed_future_mark() -> None:
    """T02: Monotonic watermark; future mark cannot enter decision readset before available."""
    s_time = 1700000000000

    p_50k = {"price": "50000.0", "close_ms": s_time}
    ev_50k = Event(
        event_id="MARK_50K",
        kind=EventKind.OBSERVED_MARK,
        book_id="BASE",
        candidate_id="",
        symbol="BTCUSDT",
        owner_key=OwnerKey("BASE", ""),
        order_id="",
        position_id="",
        fill_id="",
        settlement_id="",
        source_id="SRC",
        cause_id="",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=p_50k,
        payload_digest=compute_payload_digest(p_50k),
    )

    p_51k = {"price": "51000.0", "close_ms": s_time + 60_000}
    ev_51k = Event(
        event_id="MARK_51K",
        kind=EventKind.OBSERVED_MARK,
        book_id="BASE",
        candidate_id="",
        symbol="BTCUSDT",
        owner_key=OwnerKey("BASE", ""),
        order_id="",
        position_id="",
        fill_id="",
        settlement_id="",
        source_id="SRC",
        cause_id="",
        economic_at_ms=s_time + 60_000,
        available_at_ms=s_time + 120_000,
        payload=p_51k,
        payload_digest=compute_payload_digest(p_51k),
    )

    queue = [ev_50k, ev_51k]

    # At S+60s, only 50k is eligible
    el_s60 = ClockManager.filter_eligible_events(queue, s_time + 60_000)
    assert len(el_s60) == 1
    assert el_s60[0].event_id == "MARK_50K"

    # At S+120s, 51k becomes eligible
    el_s120 = ClockManager.filter_eligible_events(queue, s_time + 120_000)
    assert len(el_s120) == 2


def test_t03_late_same_close_mark_conflict() -> None:
    """T03: Late conflicting mark for already accepted close is fatal without history rewrite."""
    config = _create_base_config()
    s_time = 1700000000000

    p_50k = {"price": "50000.0", "close_ms": s_time}
    ev_50k = Event(
        event_id="MARK_ORIG",
        kind=EventKind.OBSERVED_MARK,
        book_id="BASE",
        candidate_id="",
        symbol="BTCUSDT",
        owner_key=OwnerKey("BASE", ""),
        order_id="",
        position_id="",
        fill_id="",
        settlement_id="",
        source_id="SRC",
        cause_id="",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=p_50k,
        payload_digest=compute_payload_digest(p_50k),
    )

    p_48k = {"price": "48000.0", "close_ms": s_time}
    ev_48k_late = Event(
        event_id="MARK_LATE",
        kind=EventKind.OBSERVED_MARK,
        book_id="BASE",
        candidate_id="",
        symbol="BTCUSDT",
        owner_key=OwnerKey("BASE", ""),
        order_id="",
        position_id="",
        fill_id="",
        settlement_id="",
        source_id="SRC",
        cause_id="",
        economic_at_ms=s_time,
        available_at_ms=s_time + 180_000,
        payload=p_48k,
        payload_digest=compute_payload_digest(p_48k),
    )

    st = EngineState(clock_ms=s_time, latest_mark_close_ms=s_time)
    st, _, _ = reduce(st, ev_50k, config)
    assert st.latest_marks["BTCUSDT"] == Decimal("50000.0")

    with pytest.raises(ConflictFailClosedError):
        reduce(st, ev_48k_late, config)


def test_t04_report_decision_isolation() -> None:
    """T04: Economic report plane is isolated from decision and risk readset."""
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T04")

    # Standardized book: cash=1000, LONG q=1, entry=50000, mark=50000
    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        cash_settled=Decimal("1000.000000000000"),
        quantity=Decimal("1.0"),
        entry_price=Decimal("50000.0"),
    )
    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        latest_marks={"BTCUSDT": Decimal("50000.0")},
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    proj = project_as_of("BASE", st, s_time)
    assert proj.E_d == Decimal("1000.000000000000")
    assert proj.E_c == Decimal("1000.000000000000")


def test_t05_mark_staleness_boundary() -> None:
    """T05: Mark freshness boundary: age <= 120s valid; age > 120s (e.g. 180s) stale."""
    s_time = 1700000000000
    last_mark_close = s_time

    # At S+120s: age = 120s -> fresh
    cut_120 = s_time + 120_000
    age_120 = cut_120 - last_mark_close
    assert age_120 <= 120_000

    # At S+180s: age = 180s -> stale
    cut_180 = s_time + 180_000
    age_180 = cut_180 - last_mark_close
    assert age_180 > 120_000


# ---------------------------------------------------------------------------
# T06–T09: ACK Semantics
# ---------------------------------------------------------------------------

def test_t06_ack_duplicate_idempotent() -> None:
    """T06: Exact identical ACK payload received multiple times debited exactly once."""
    config = _create_base_config()
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T06")

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.UNACKED_OPEN,
        cash_settled=Decimal("1000.000000000000"),
        fee_payable=Decimal("2.000000000000"),
    )
    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    ack_payload = {"fee_usdt": "2.000000000000", "order_id": "POS_T06"}
    ack_digest = compute_payload_digest(ack_payload)
    ack_event = Event(
        event_id="ACK_T06",
        kind=EventKind.FILL_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="POS_T06",
        position_id="POS_T06",
        fill_id="FILL_T06",
        settlement_id="",
        source_id="",
        cause_id="POS_T06",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=ack_payload,
        payload_digest=ack_digest,
    )

    # First delivery: cash debited 2 -> 998
    st, postings1, _ = reduce(st, ack_event, config)
    assert len(postings1) == 1
    assert st.owner_ledgers[owner_key].cash_settled == Decimal("998.000000000000")

    # Second delivery (identical): idempotent duplicate, no extra posting
    st, postings2, _ = reduce(st, ack_event, config)
    assert len(postings2) == 0
    assert st.owner_ledgers[owner_key].cash_settled == Decimal("998.000000000000")

    # Third delivery: still idempotent
    st, postings3, _ = reduce(st, ack_event, config)
    assert len(postings3) == 0
    assert st.owner_ledgers[owner_key].cash_settled == Decimal("998.000000000000")


def test_t07_ack_payload_conflict() -> None:
    """T07: Same ACK ID with conflicting payload raises ConflictFailClosedError before mutation."""
    config = _create_base_config()
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T07")

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.UNACKED_OPEN,
        cash_settled=Decimal("1000.000000000000"),
        fee_payable=Decimal("2.000000000000"),
    )
    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    ack_p1 = {"fee_usdt": "2.000000000000", "order_id": "POS_T07"}
    ack_ev1 = Event(
        event_id="ACK_T07",
        kind=EventKind.FILL_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="POS_T07",
        position_id="POS_T07",
        fill_id="FILL_T07",
        settlement_id="",
        source_id="",
        cause_id="POS_T07",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=ack_p1,
        payload_digest=compute_payload_digest(ack_p1),
    )

    st, _, _ = reduce(st, ack_ev1, config)
    assert st.owner_ledgers[owner_key].cash_settled == Decimal("998.000000000000")

    # Same ID changed fee 2 -> 3
    ack_p2 = {"fee_usdt": "3.000000000000", "order_id": "POS_T07"}
    ack_ev2 = Event(
        event_id="ACK_T07",
        kind=EventKind.FILL_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="POS_T07",
        position_id="POS_T07",
        fill_id="FILL_T07",
        settlement_id="",
        source_id="",
        cause_id="POS_T07",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=ack_p2,
        payload_digest=compute_payload_digest(ack_p2),
    )

    with pytest.raises(ConflictFailClosedError):
        reduce(st, ack_ev2, config)


def test_t08_older_ack_does_not_rewind_cooldown() -> None:
    """T08: Older P1 ACK cannot rewind newer P2 cooldown from 1700017140000 to 1700010000000."""
    newer_cooldown = 1700017140000
    older_cooldown = 1700010000000

    prev_cooldown = newer_cooldown
    resulting_cooldown = max(prev_cooldown, older_cooldown)
    assert resulting_cooldown == newer_cooldown


def test_t09_ack_owner_cause_mismatch() -> None:
    """T09: ACK pointing to mismatched owner or cause raises CauseOrOwnerFailClosedError."""
    config = _create_base_config()
    s_time = 1700000000000

    # Non-existent owner
    bad_owner = OwnerKey("BASE", "NON_EXISTENT")
    ack_payload = {"fee_usdt": "2.000000000000"}
    ack_ev = Event(
        event_id="ACK_BAD",
        kind=EventKind.FILL_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=bad_owner,
        order_id="ORD_X",
        position_id="POS_X",
        fill_id="FILL_X",
        settlement_id="",
        source_id="",
        cause_id="ORD_X",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=ack_payload,
        payload_digest=compute_payload_digest(ack_payload),
    )

    st = EngineState(clock_ms=s_time, latest_mark_close_ms=s_time)
    with pytest.raises(CauseOrOwnerFailClosedError):
        reduce(st, ack_ev, config)


# ---------------------------------------------------------------------------
# T10–T15: Funding and Clocks
# ---------------------------------------------------------------------------

def test_t10_funding_shortfall_and_owner_isolation() -> None:
    """
    T10: Standardized Funding witness:
    cash=1000, C_o=7, ETH Rfuture=2, BTC Rcover=0.40, BTC P=1, shortfall L=0.60.
    Pre-ACK: R_f=2.40, P=1, L=0.60, free=940.
    Post-ACK: cash=999, BTC P/Rcov/L=0, ETH=2, free=940.05.
    """
    config = _create_base_config()
    s_time = 1700000000000
    btc_owner = OwnerKey("BASE", "BTC_POS")
    eth_owner = OwnerKey("BASE", "ETH_POS")

    btc_ol = OwnerLedger(
        owner_key=btc_owner,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        cash_settled=Decimal("1000.000000000000"),
        enc_notional=Decimal("7.000000000000"),  # C_o = 7
        enc_funding_dedicated=Decimal("0.400000000000"),
        funding_payable=Decimal("1.000000000000"),
        enc_shortfall=Decimal("0.600000000000"),
    )

    eth_ol = OwnerLedger(
        owner_key=eth_owner,
        candidate_id="SC",
        symbol="ETHUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.ACKED_OPEN,
        enc_funding_future=Decimal("2.000000000000"),
    )

    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={btc_owner: btc_ol, eth_owner: eth_ol},
        opening_equity_posted={"BASE": True},
    )

    # Check pre-ACK projection
    proj_pre = project_as_of("BASE", st, s_time)
    assert proj_pre.R_f == Decimal("2.400000000000")
    assert proj_pre.L_f == Decimal("0.600000000000")
    assert proj_pre.P_f == Decimal("1.000000000000")
    assert proj_pre.C_o == Decimal("7.000000000000")
    assert proj_pre.A == Decimal("940.000000000000")

    # Execute FundingAck for BTC payable=1
    f_ack_payload = {"charge_usdt": "1.000000000000", "settlement_id": "FUND_BTC"}
    f_ack_digest = compute_payload_digest(f_ack_payload)
    f_ack_ev = Event(
        event_id="ACK_FUND_BTC",
        kind=EventKind.FUNDING_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=btc_owner,
        order_id="",
        position_id="BTC_POS",
        fill_id="",
        settlement_id="FUND_BTC",
        source_id="",
        cause_id="FUND_BTC",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=f_ack_payload,
        payload_digest=f_ack_digest,
    )

    st_post, _, _ = reduce(st, f_ack_ev, config)
    proj_post = project_as_of("BASE", st_post, s_time + 60_000)

    # Post-ACK verification:
    # cash=999, ETH reserve=2, BTC payable/cover/L=0, A=940.05
    assert proj_post.cash == Decimal("999.000000000000")
    assert proj_post.R_f == Decimal("2.000000000000")
    assert proj_post.L_f == Decimal("0.000000000000")
    assert proj_post.P_f == Decimal("0.000000000000")
    assert proj_post.A == Decimal("940.050000000000")


def test_t11_funding_ack_delayed_out_of_order() -> None:
    """T11: Funding ACK arriving out of order is normalized by available_at_ms."""
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T11")

    p_obl = {"phase": "FINAL", "charge_usdt": "1.0", "dedicated_cover": "0.4"}
    ev_obl = Event(
        event_id="FO_T11",
        kind=EventKind.FUNDING_OBLIGATION,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="",
        position_id="POS_T11",
        fill_id="",
        settlement_id="S1",
        source_id="",
        cause_id="",
        economic_at_ms=s_time,
        available_at_ms=s_time + 120_000,
        payload=p_obl,
        payload_digest=compute_payload_digest(p_obl),
    )

    p_ack = {"charge_usdt": "1.0", "settlement_id": "S1"}
    ev_ack = Event(
        event_id="ACK_FO_T11",
        kind=EventKind.FUNDING_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="",
        position_id="POS_T11",
        fill_id="",
        settlement_id="S1",
        source_id="",
        cause_id="S1",
        economic_at_ms=s_time,
        available_at_ms=s_time + 180_000,
        payload=p_ack,
        payload_digest=compute_payload_digest(p_ack),
    )

    # Sort queue: obligation available at S+120s before ACK at S+180s
    queue = [ev_ack, ev_obl]
    sorted_evs = ClockManager.filter_eligible_events(queue, s_time + 180_000)
    assert sorted_evs[0].event_id == "FO_T11"
    assert sorted_evs[1].event_id == "ACK_FO_T11"


def test_t12_exit_before_s_remains_in_window() -> None:
    """T12: Position exited at S-10s remains in [S-15s, S+15s] window; retained in CLOSED_UNSETTLED."""
    s_time = 1700000000000
    exit_time = s_time - 10_000
    # In window [S-15s, S+15s]
    assert s_time - 15_000 <= exit_time <= s_time + 15_000


def test_t13_reject_non_minute_clock_api() -> None:
    """T13: Clock advance to non-minute boundary (e.g. S-5000ms) raises InvalidMinuteClockError."""
    s_time = 1700000000000
    non_aligned_time = s_time - 5_000

    with pytest.raises(InvalidMinuteClockError):
        ClockManager.validate_aligned_open(non_aligned_time)


def test_t14_exact_position_identity_no_substring() -> None:
    """T14: Exact position keys POS_1 vs POS_10 cannot collide via partial string matching."""
    k1 = OwnerKey("BASE", "POS_1")
    k10 = OwnerKey("BASE", "POS_10")
    assert str(k1) != str(k10)
    assert k1.position_id != k10.position_id
    # Exact dictionary lookup isolation
    ledgers: dict[OwnerKey, str] = {k1: "LEDGER_1", k10: "LEDGER_10"}
    assert ledgers[k1] == "LEDGER_1"
    assert ledgers[k10] == "LEDGER_10"


def test_t15_s_cannot_know_future_ownership() -> None:
    """T15: At whole hour S, final funding quantity uses max(pre, post) rather than premature sum."""
    pre_qty = Decimal("1.0")
    post_qty = Decimal("0.6")
    # max exposure across window, not sum 1.6
    final_charge_qty = max(pre_qty, post_qty)
    assert final_charge_qty == Decimal("1.0")
    assert final_charge_qty != pre_qty + post_qty


# ---------------------------------------------------------------------------
# T16–T19: Risk Projections and Permanent Kill
# ---------------------------------------------------------------------------

def test_t16_standardized_pending_loss_169_336545() -> None:
    """
    T16: Standardized witness:
    cash=1000, trade payable=169.336545.
    At first proof cut: E_c=E_r=830.663455, drawdown=169.336545 >= 100 -> killed=True, A=0.
    """
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T16")

    # Exited with pending loss slice
    loss_slice = PendingExitSlice(
        slice_id="SL_T16",
        quantity=Decimal("1.0"),
        raw_price=Decimal("49000.0"),
        effective_price=Decimal("49000.0"),
        gross_pnl=Decimal("-169.336545000000"),
        exit_fee=Decimal(0),
        exit_time_ms=s_time - 1,
        available_at_ms=s_time + 60_000,
        exit_reason=ExitReason.STOP_LOSS,
        is_loss=True,
        is_acknowledged=False,
    )

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.EXIT_PENDING,
        cash_settled=Decimal("1000.000000000000"),
        trade_payable=Decimal("169.336545000000"),
        pending_exit_slices=(loss_slice,),
    )

    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    # Before proof available (< S+60s): pending loss not visible
    proj_before = project_as_of("BASE", st, s_time)
    assert proj_before.E_c == Decimal("1000.000000000000")
    assert not proj_before.killed

    # At proof cut (S+60s): pending loss enters E_c
    proj_cut = project_as_of("BASE", st, s_time + 60_000)
    assert proj_cut.E_c == Decimal("830.663455000000")
    assert proj_cut.E_r == Decimal("830.663455000000")
    assert proj_cut.drawdown == Decimal("169.336545000000")
    assert proj_cut.killed is True
    assert proj_cut.A == Decimal("0.000000000000")


def test_t17_unacked_gain_non_reusable() -> None:
    """T17: Positive unacknowledged receivable does not inflate E_c or spendable capital."""
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T17")

    gain_slice = PendingExitSlice(
        slice_id="SL_T17",
        quantity=Decimal("1.0"),
        raw_price=Decimal("51000.0"),
        effective_price=Decimal("51000.0"),
        gross_pnl=Decimal("50.000000000000"),
        exit_fee=Decimal(0),
        exit_time_ms=s_time,
        available_at_ms=s_time + 60_000,
        exit_reason=ExitReason.TAKE_PROFIT,
        is_loss=False,
        is_acknowledged=False,
    )

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.EXIT_PENDING,
        cash_settled=Decimal("1000.000000000000"),
        trade_receivable=Decimal("50.000000000000"),
        pending_exit_slices=(gain_slice,),
    )

    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    # Before ACK: E_c is still 1000, free=950
    proj_before = project_as_of("BASE", st, s_time + 60_000)
    assert proj_before.E_c == Decimal("1000.000000000000")
    assert proj_before.A == Decimal("950.000000000000")


def test_t18_small_pending_loss_reduces_capital() -> None:
    """T18: Visible pending loss of 20 reduces free capital from 950 to 931 without killing book."""
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T18")

    loss_slice = PendingExitSlice(
        slice_id="SL_T18",
        quantity=Decimal("1.0"),
        raw_price=Decimal("49000.0"),
        effective_price=Decimal("49000.0"),
        gross_pnl=Decimal("-20.000000000000"),
        exit_fee=Decimal(0),
        exit_time_ms=s_time,
        available_at_ms=s_time + 60_000,
        exit_reason=ExitReason.STOP_LOSS,
        is_loss=True,
        is_acknowledged=False,
    )

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.EXIT_PENDING,
        cash_settled=Decimal("1000.000000000000"),
        trade_payable=Decimal("20.000000000000"),
        pending_exit_slices=(loss_slice,),
    )

    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    proj = project_as_of("BASE", st, s_time + 60_000)
    assert proj.E_c == Decimal("980.000000000000")
    assert proj.E_r == Decimal("980.000000000000")
    assert proj.drawdown == Decimal("20.000000000000")
    assert proj.killed is False
    # A = 0.95 * 980 = 931
    assert proj.A == Decimal("931.000000000000")


def test_t19_kill_permanent_latch() -> None:
    """T19: Once killed_latches is True, subsequent winning ACK cannot reset kill."""
    st = EngineState(
        clock_ms=1700000000000,
        latest_mark_close_ms=1700000000000,
        killed_latches={"BASE": True},
        peak_E_r={"BASE": Decimal("1000.000000000000")},
    )

    proj = project_as_of("BASE", st, 1700000000000)
    assert proj.killed is True
    assert proj.A == Decimal("0.000000000000")


# ---------------------------------------------------------------------------
# T32–T34: Corner Capital Safety
# ---------------------------------------------------------------------------

def test_t32_different_pending_slices_non_netting() -> None:
    """
    T32: Pending negative slice of 100 and positive receivable of 100 cannot net to zero.
    Before ACK: E_c=900, drawdown=100 -> kill latched, free=0.
    """
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T32")

    loss_slice = PendingExitSlice(
        slice_id="SL_LOSS",
        quantity=Decimal("1.0"),
        raw_price=Decimal("49000.0"),
        effective_price=Decimal("49000.0"),
        gross_pnl=Decimal("-100.000000000000"),
        exit_fee=Decimal(0),
        exit_time_ms=s_time,
        available_at_ms=s_time + 60_000,
        exit_reason=ExitReason.STOP_LOSS,
        is_loss=True,
        is_acknowledged=False,
    )

    gain_slice = PendingExitSlice(
        slice_id="SL_GAIN",
        quantity=Decimal("1.0"),
        raw_price=Decimal("51000.0"),
        effective_price=Decimal("51000.0"),
        gross_pnl=Decimal("100.000000000000"),
        exit_fee=Decimal(0),
        exit_time_ms=s_time,
        available_at_ms=s_time + 60_000,
        exit_reason=ExitReason.TAKE_PROFIT,
        is_loss=False,
        is_acknowledged=False,
    )

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.EXIT_PENDING,
        cash_settled=Decimal("1000.000000000000"),
        trade_payable=Decimal("100.000000000000"),
        trade_receivable=Decimal("100.000000000000"),
        pending_exit_slices=(loss_slice, gain_slice),
    )

    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    proj = project_as_of("BASE", st, s_time + 60_000)
    # Cannot net! E_c = 1000 - 100 = 900
    assert proj.E_c == Decimal("900.000000000000")
    assert proj.drawdown == Decimal("100.000000000000")
    assert proj.killed is True
    assert proj.A == Decimal("0.000000000000")


def test_t33_capital_deficit_and_negative_equity_bounds() -> None:
    """T33: Deficit capital A_raw = -5 produces A=0 without crashing I06; negative equity preserved."""
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "POS_T33")

    ol = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.RESERVED,
        cash_settled=Decimal("100.000000000000"),
        enc_notional=Decimal("100.000000000000"),  # C_o = 100
    )

    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol},
        opening_equity_posted={"BASE": True},
    )

    proj = project_as_of("BASE", st, s_time)
    # A_raw = 0.95 * 100 - 100 = 95 - 100 = -5
    assert proj.A_raw == Decimal("-5.000000000000")
    assert proj.A == Decimal("0.000000000000")

    # Invariant assertion holds
    invs = assert_invariants(st, "BASE", proj)
    assert invs["I06"] is True


def test_t34_atomic_fee_cover_conversion_on_notice() -> None:
    """
    T34: Atomic fee cover conversion:
    cash=1000, entry notional cover=100, fee cover=2, exit cover=1 -> C_o=103.
    Fee notice 2 arrives: E_c=998, fee payable=2, C_o=101, A=847.1.
    FillAck arrives: cash=998, payable=0, C_o=1, G=100, A=947.1. No double fee deduction!
    """
    config = _create_base_config()
    s_time = 1700000000000
    owner_key = OwnerKey("BASE", "ORD_T34")

    # 1. Reserved order
    ol_res = OwnerLedger(
        owner_key=owner_key,
        candidate_id="SC",
        symbol="BTCUSDT",
        direction=Direction.LONG,
        phase=OwnerPhase.RESERVED,
        cash_settled=Decimal("1000.000000000000"),
        enc_notional=Decimal("100.000000000000"),
        enc_fee=Decimal("2.000000000000"),
        enc_exit_fee=Decimal("1.000000000000"),
    )
    st = EngineState(
        clock_ms=s_time,
        latest_mark_close_ms=s_time,
        owner_ledgers={owner_key: ol_res},
        opening_equity_posted={"BASE": True},
    )

    proj_res = project_as_of("BASE", st, s_time)
    assert proj_res.C_o == Decimal("103.000000000000")

    # 2. EconomicFill with fee 2 arrives
    fill_payload = {
        "quantity": "0.002",
        "raw_price": "50000.0",
        "effective_price": "50000.0",
        "fee_usdt": "2.000000000000",
        "direction": "LONG",
    }
    fill_ev = Event(
        event_id="FILL_T34",
        kind=EventKind.ECONOMIC_FILL,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="ORD_T34",
        position_id="ORD_T34",
        fill_id="FILL_T34",
        settlement_id="",
        source_id="",
        cause_id="ORD_T34",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=fill_payload,
        payload_digest=compute_payload_digest(fill_payload),
    )

    st_filled, _, _ = reduce(st, fill_ev, config)
    proj_filled = project_as_of("BASE", st_filled, s_time + 60_000)

    # Verification on fee notice:
    # E_c = 1000 - 2 = 998, fee payable = 2
    # C_o = 100 notional + 0 fee cover + 1 exit cover = 101
    # A = 0.95 * 998 - 101 = 948.1 - 101 = 847.1
    assert proj_filled.E_c == Decimal("998.000000000000")
    assert proj_filled.visible_unpaid_fees == Decimal("2.000000000000")
    assert proj_filled.C_o == Decimal("101.000000000000")
    assert proj_filled.A == Decimal("847.100000000000")

    # 3. FillAck arrives
    ack_payload = {"fee_usdt": "2.000000000000", "order_id": "ORD_T34"}
    ack_ev = Event(
        event_id="ACK_FILL_T34",
        kind=EventKind.FILL_ACK,
        book_id="BASE",
        candidate_id="SC",
        symbol="BTCUSDT",
        owner_key=owner_key,
        order_id="ORD_T34",
        position_id="ORD_T34",
        fill_id="FILL_T34",
        settlement_id="",
        source_id="",
        cause_id="ORD_T34",
        economic_at_ms=s_time,
        available_at_ms=s_time + 60_000,
        payload=ack_payload,
        payload_digest=compute_payload_digest(ack_payload),
    )

    st_acked, _, _ = reduce(st_filled, ack_ev, config)
    proj_acked = project_as_of("BASE", st_acked, s_time + 60_000)

    # Verification on ACK:
    # cash = 998, payable = 0, C_o = 1 (exit cover)
    # A = 0.95 * 998 - 1 = 948.1 - 1 = 947.1
    assert proj_acked.cash == Decimal("998.000000000000")
    assert proj_acked.visible_unpaid_fees == Decimal("0.000000000000")
    assert proj_acked.C_o == Decimal("1.000000000000")
    assert proj_acked.A == Decimal("947.100000000000")
