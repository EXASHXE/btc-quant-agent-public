"""Independent regression witnesses for review-discovered financial boundaries."""

from __future__ import annotations

from decimal import Decimal

import pytest

from scripts.g1_offline_preview_r1.model import SafetyViolation, digest
from scripts.g1_offline_preview_r1.reducer import transition
from tests.test_v06_g1_offline_preview_r1_core import ev, next_bar, open_position


def test_unrestricted_close_cannot_bypass_stop():
    s = next_bar(open_position(), last="100", high="101", low="94")
    before = digest(s)
    with pytest.raises(SafetyViolation, match="REQUIRED_EXIT_UNHANDLED"):
        transition(s, ev("CLOSE", s["last_at"] + 1, {"fill_id": "bad-close"}))
    assert digest(s) == before and s["remaining_qty"] == "0.02"


def test_same_settlement_clock_different_id_no_second_charge():
    s = open_position()
    at = s["last_at"] + 1
    a = {"settlement_id": "one", "settlement_at": at, "rate_fraction": "0.001"}
    s = transition(s, ev("FUNDING", at, a))
    before = digest(s)
    with pytest.raises(SafetyViolation, match="FUNDING_DUPLICATE"):
        transition(s, ev("FUNDING", at, {**a, "settlement_id": "different"}, label="different-id"))
    assert digest(s) == before and sum(x["kind"] == "FUNDING" for x in s["journal"]) == 1


@pytest.mark.parametrize("final_first", [False, True])
def test_stop_before_partial_ack_all_ack_orders_conserve(final_first):
    s = next_bar(open_position(), last="105", high="106", low="104")
    s = transition(s, ev("TP1", s["last_at"] + 1, {"fill_id": "half"}))
    s = next_bar(s, last="94", high="95", low="93")
    s = transition(s, ev("STOP", s["last_at"] + 1, {"fill_id": "flat"}))
    assert len(s["pending_cash"]) == 2 and Decimal(s["remaining_qty"]) == 0
    before = Decimal(s["cash"])
    net = sum((Decimal(x) for x in s["pending_cash"].values()), Decimal(0))
    s = next_bar(s, last="94", high="95", low="93")
    ids = ["flat", "half"] if final_first else ["half", "flat"]
    for i, fill in enumerate(ids):
        s = transition(
            s,
            ev(
                "ACK",
                s["last_at"] + 1 + i,
                {"ack_id": "ack-" + fill, "order_id": s["order_id"], "fill_id": fill},
            ),
        )
        if i == 0:
            assert s["phase"] == "EXIT_WAIT_ACK" and len(s["pending_cash"]) == 1
    assert s["phase"] == "CLOSED" and not s["pending_cash"]
    assert Decimal(s["cash"]) == before + net and Decimal(s["reserved_notional"]) == 0


def test_fill_id_reuse_after_ack_rejected():
    s = next_bar(open_position(), last="105", high="106", low="104")
    s = transition(s, ev("TP1", s["last_at"] + 1, {"fill_id": "half"}))
    s = next_bar(s, last="105", high="106", low="104")
    s = transition(
        s,
        ev(
            "ACK",
            s["last_at"] + 1,
            {"ack_id": "ack-half", "order_id": s["order_id"], "fill_id": "half"},
        ),
    )
    s = next_bar(s, last="94", high="95", low="93")
    before = digest(s)
    with pytest.raises(SafetyViolation, match="FILL_DUPLICATE"):
        transition(s, ev("STOP", s["last_at"] + 1, {"fill_id": "half"}))
    assert digest(s) == before


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_net_BE_includes_execution_tick(side):
    favorable = "105" if side == "LONG" else "95"
    s = next_bar(
        open_position(side=side, qty="0.04"),
        last=favorable,
        high=str(int(favorable) + 1),
        low=str(int(favorable) - 1),
    )
    s = transition(s, ev("TP1", s["last_at"] + 1, {"fill_id": "half"}))
    s = next_bar(s, last=favorable, high=str(int(favorable) + 1), low=str(int(favorable) - 1))
    s = transition(
        s,
        ev(
            "ACK",
            s["last_at"] + 1,
            {"ack_id": "ack-half", "order_id": s["order_id"], "fill_id": "half"},
        ),
    )
    s = next_bar(s, last=favorable, high=str(int(favorable) + 1), low=str(int(favorable) - 1))
    s = transition(s, ev("UPDATE_STOP", s["last_at"] + 1))
    raw = Decimal(s["stop"])
    entry = Decimal(s["entry_price"])
    fee = Decimal(".0006")
    impact = Decimal(".0005")
    from decimal import ROUND_CEILING, ROUND_FLOOR

    price = (raw * (1 - impact if side == "LONG" else 1 + impact)).quantize(
        Decimal(".1"), rounding=ROUND_FLOOR if side == "LONG" else ROUND_CEILING
    )
    pnl = (price - entry) if side == "LONG" else (entry - price)
    assert pnl - entry * fee - price * fee >= 0


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_triggered_stop_cannot_be_omitted_before_next_bar(side):
    s = next_bar(
        open_position(side=side),
        last="100",
        high="106" if side == "SHORT" else "101",
        low="99" if side == "SHORT" else "94",
    )
    assert s["required_exit"]["kind"] == "STOP"
    before = digest(s)
    with pytest.raises(SafetyViolation, match="REQUIRED_EXIT_UNHANDLED"):
        next_bar(s, last="110", high="111", low="109")
    assert digest(s) == before


def test_triggered_tp_cannot_be_skipped_or_funded_first():
    s = next_bar(open_position(), last="105", high="106", low="104")
    before = digest(s)
    assert s["required_exit"]["kind"] == "TP1"
    with pytest.raises(SafetyViolation, match="REQUIRED_EXIT_UNHANDLED"):
        transition(
            s,
            ev(
                "FUNDING",
                s["last_at"] + 1,
                {
                    "settlement_id": "late",
                    "settlement_at": s["last_at"] + 1,
                    "rate_fraction": "0.001",
                },
            ),
        )
    assert digest(s) == before


def test_mark_exposure_guard_rejects_unsafe_bar_without_state_change():
    s = open_position(side="SHORT")
    before = digest(s)
    with pytest.raises(SafetyViolation, match="MARK_EXPOSURE_ABOVE_ONE_X"):
        next_bar(s, mark="30000")
    assert digest(s) == before


def test_late_receipt_cannot_lock_pending_stop_or_advance_market_clock():
    s = next_bar(open_position(), last="100", high="101", low="94")
    before = digest(s)
    key = s["outbox"][0]["key"]
    with pytest.raises(SafetyViolation, match="REQUIRED_EXIT_UNHANDLED"):
        transition(s, ev("OUTBOX_RECEIPT", s["last_at"] + 86400000, {"message_id": key}))
    assert digest(s) == before
    s = transition(s, ev("STOP", s["last_at"], {"fill_id": "stopped"}))
    clock = s["last_at"]
    cash = s["cash"]
    s = transition(s, ev("OUTBOX_RECEIPT", clock + 86400000, {"message_id": key}))
    assert s["last_at"] == clock and s["cash"] == cash
    s = next_bar(s)
    assert s["last_at"] == clock + 60000


def residual_before_update(side="LONG"):
    favorable = "105" if side == "LONG" else "95"
    s = next_bar(
        open_position(side=side, qty="0.04"),
        last=favorable,
        high=str(int(favorable) + 1),
        low=str(int(favorable) - 1),
    )
    s = transition(s, ev("TP1", s["last_at"], {"fill_id": "half"}))
    s = next_bar(s, last=favorable, high=str(int(favorable) + 1), low=str(int(favorable) - 1))
    s = transition(
        s,
        ev(
            "ACK",
            s["last_at"],
            {"ack_id": "ack-half", "order_id": s["order_id"], "fill_id": "half"},
        ),
    )
    return next_bar(s, last="100", high="101", low="99")


@pytest.mark.parametrize("side", ["LONG", "SHORT"])
def test_new_be_stop_cannot_retroactively_fill_update_source_bar(side):
    s = residual_before_update(side)
    s = transition(s, ev("UPDATE_STOP", s["last_at"] + 1))
    before = digest(s)
    with pytest.raises(SafetyViolation, match="STOP_UPDATE_NOT_YET_EFFECTIVE"):
        transition(s, ev("STOP", s["last_at"] + 1, {"fill_id": "retroactive"}))
    assert digest(s) == before and not s["pending_cash"]
    s = next_bar(s, last="100", high="101", low="99")
    assert s["required_exit"]["kind"] == "STOP"
    s = transition(s, ev("STOP", s["last_at"], {"fill_id": "causal-stop"}))
    assert Decimal(s["remaining_qty"]) == 0


def test_stop_update_after_boundary_rejects_without_financial_effect():
    s = residual_before_update()
    before = digest(s)
    with pytest.raises(SafetyViolation, match="STOP_UPDATE_NOT_AT_COMPLETED_BOUNDARY"):
        transition(s, ev("UPDATE_STOP", s["last_at"] + 2))
    assert digest(s) == before
