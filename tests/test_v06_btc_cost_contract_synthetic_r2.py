"""Exactly 24 named finite cases, using invented inputs only."""

import sys
from dataclasses import replace
from decimal import Decimal as D
from decimal import localcontext
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.strategy_research.g2_btc_exit_aware_r3 import cost_contract_synthetic_r2 as c


def filters(**kwargs):
    return c.Filters(D("0.1"), D("0.001"), D(5), **kwargs)


def fill(event_id, action, quantity, price, at, mid="100000", role="TAKER", **kwargs):
    quote = c.Quote(D(mid) - D(2), D(mid) + D(2), at - 10, at - 5)
    return c.Fill(
        event_id, action, D(quantity), D(price), role, at, at + 1, at - 5, quote, at + 2, **kwargs
    )


def funding(side=1, quantity="0.010", mark="100400", at=500000, known=None, **kwargs):
    return c.Funding(
        "settlement",
        at,
        known if known is not None else at + 3,
        at,
        D(mark),
        D("0.0001"),
        side * D(quantity),
        True,
        **kwargs,
    )


def view(ledger, at=900000, **kwargs):
    coverage = c.FundingCoverage(
        0,
        at,
        at,
        "SYNTHETIC:complete-window",
        tuple(e.event_id for e in ledger._funding.values() if e.settled_at <= at),
    )
    return ledger.snapshot(at, funding_coverage=coverage, **kwargs)


def example(name):
    short = name in ("short", "partial_short")
    ledger = c.SyntheticLedger(-1 if short else 1, filters())
    entry_price = "99997" if short else "100010" if name == "adverse" else "100003"
    if name == "flat":
        entry_price = "100002"
    if name == "mixed":
        ledger.add_fill(fill("maker-entry", "ENTRY", "0.004", "100000", 100000, role="MAKER"))
        ledger.add_fill(fill("taker-entry", "ENTRY", "0.006", "100003", 100000))
    else:
        ledger.add_fill(fill("entry", "ENTRY", "0.010", entry_price, 100000))
    partial = name.startswith("partial")
    if partial:
        ledger.add_fill(
            fill(
                "partial",
                "EXIT",
                "0.004",
                "99503" if short else "100497",
                400000,
                mid="99500" if short else "100500",
            )
        )
    if name in ("long", "short", "partial_long", "partial_short", "adverse"):
        ledger.add_funding(
            funding(
                -1 if short else 1, "0.006" if partial else "0.010", "99600" if short else "100400"
            )
        )
    exit_price = (
        "99003"
        if short
        else "99998"
        if name == "flat"
        else "100990"
        if name == "adverse"
        else "98997"
        if name == "gap"
        else "100997"
    )
    exit_mid = (
        "99000" if short else "100000" if name == "flat" else "99000" if name == "gap" else "101000"
    )
    ledger.add_fill(
        fill("exit", "EXIT", "0.006" if partial else "0.010", exit_price, 800000, mid=exit_mid)
    )
    return ledger


def assert_cash(ledger, expected):
    result = view(ledger)
    assert result["status"] == "COMPLETE"
    assert result["net_cash"] == D(expected)
    assert result["entered"] == result["exited"]
    assert result["remaining"] == 0
    assert (
        result["mid_gross"] - result["fill_drag"] + result["trading_rounding"]
        == result["trading_cash"]
    )
    assert (
        result["net_cash"]
        == result["trading_cash"] - result["fees"] + result["funding_cash"] - result["other_cash"]
    )
    # Independent flat-episode signed notional computation; no production helper.
    events = list(ledger._fills.values())
    raw = ledger.side * (
        sum((f.quantity * f.price for f in events if f.action == "EXIT"), D(0))
        - sum((f.quantity * f.price for f in events if f.action == "ENTRY"), D(0))
    )
    assert raw + result["trading_rounding"] == result["trading_cash"]
    return result


def test_01_long_actual_notionals():
    result = assert_cash(example("long"), "8.834600")
    assert result["fees"] == D("0.500015") + D("0.504985")
    assert result["entry_notional"] == D("1000.03")


def test_02_short_positive_funding_credit():
    result = assert_cash(example("short"), "9.044600")
    assert result["fees"] == D("0.499985") + D("0.495015")
    assert result["funding_cash"] == D("0.099600")


def test_03_signed_funding_symmetry():
    for side in (-1, 1):
        for rate in (D("0.0001"), D("-0.0001"), D(0)):
            ledger = c.SyntheticLedger(side, filters())
            ledger.add_fill(fill("entry", "ENTRY", "0.010", "100000", 100000))
            ledger.add_funding(replace(funding(side), rate=rate))
            result = view(ledger)
            assert result["funding_cash"] == -D(side) * D("0.010") * D(100400) * rate
            assert result["status"] == "OPEN_INVENTORY"


def test_04_fee_only_reference_identities():
    for entry_role, exit_role, bp in (
        ("MAKER", "MAKER", "4"),
        ("MAKER", "TAKER", "7"),
        ("TAKER", "TAKER", "10"),
    ):
        ledger = c.SyntheticLedger(1, filters())
        ledger.add_fill(fill("entry", "ENTRY", "0.010", "100000", 100000, role=entry_role))
        ledger.add_fill(fill("exit", "EXIT", "0.010", "100000", 800000, role=exit_role))
        result = view(ledger)
        assert result["fees"] / result["entry_notional"] * D(10000) == D(bp)
        assert result["label"] == c.LABEL


def test_05_marketable_limit_is_taker():
    ledger = c.SyntheticLedger(1, filters())
    event = fill("entry", "ENTRY", "0.010", "100002", 100000, order_type="LIMIT")
    ledger.add_fill(event)
    assert view(ledger)["fees"] == D("0.500010")
    with pytest.raises(ValueError, match="MARKETABLE_MAKER_CONFLICT"):
        c.SyntheticLedger(1, filters()).add_fill(replace(event, role="MAKER"))
    with pytest.raises(ValueError, match="MARKET_MAKER_CONFLICT"):
        replace(event, role="MAKER", order_type="MARKET")


def test_06_mixed_roles_per_filled_leg():
    result = assert_cash(example("mixed"), "9.067006")
    assert result["fees"] == D("0.080000") + D("0.300009") + D("0.504985")


def test_07_maker_nonfill_no_completed_return():
    ledger = c.SyntheticLedger(1, filters())
    result = view(ledger)
    assert result["status"] == "NO_FILL"
    assert result["fees"] == result["remaining"] == result["known_cash"] == 0
    assert result["net_bps"] is None
    with pytest.raises(ValueError, match="INVALID_FILL"):
        fill("unfilled", "ENTRY", "0", "100000", 100000, role="MAKER")


def test_08_half_spread_no_double_deduction():
    result = assert_cash(example("flat"), "-1.040000")
    assert result["mid_gross"] == 0
    assert result["fill_drag"] == D("0.040000")
    with pytest.raises(ValueError, match="SPREAD_ALREADY_IN_FILL"):
        fill("entry", "ENTRY", "0.010", "100002", 100000, extra_spread_cash=D("0.020"))


def test_09_adverse_direction_and_distinct_impact():
    normal = assert_cash(example("long"), "8.834600")
    adverse = assert_cash(example("adverse"), "8.694600")
    assert adverse["net_cash"] < normal["net_cash"]
    assert adverse["fill_drag"] - normal["fill_drag"] == D("0.140000")
    for side, entry_price, worse in ((1, "100003", "100010"), (-1, "99997", "99990")):
        ledger = c.SyntheticLedger(side, filters())
        ledger.add_fill(fill("entry", "ENTRY", "0.010", entry_price, 100000))
        other = c.SyntheticLedger(side, filters())
        other.add_fill(fill("entry", "ENTRY", "0.010", worse, 100000))
        assert view(other, mark="100000")["unrealized"] < view(ledger, mark="100000")["unrealized"]
    with pytest.raises(ValueError, match="IMPACT_ALREADY_IN_FILL"):
        fill("entry", "ENTRY", "0.010", "100003", 100000, external_impact_cash=D("0.1"))
    ledger = c.SyntheticLedger(1, filters())
    ledger.add_fill(
        fill(
            "entry",
            "ENTRY",
            "0.010",
            "100003",
            100000,
            external_impact_cash=D("0.1"),
            impact_basis="DISTINCT_NOT_IN_FILL",
        )
    )
    assert view(ledger)["other_cash"] == D("0.10000000")


def test_10_partial_long_one_entry_fee():
    result = assert_cash(example("partial_long"), "6.875760")
    assert result["funding_cash"] == D("-0.060240")
    assert result["fees"] == D("0.500015") + D("0.200994") + D("0.302991")


def test_11_partial_short_settlement_exposure():
    result = assert_cash(example("partial_short"), "7.003760")
    assert result["funding_cash"] == D("0.059760")
    assert result["trading_cash"] == D("7.940000")


def test_12_residual_realized_unrealized_separated():
    ledger = example("partial_long")
    result = view(ledger, at=400001, mark="100500")
    assert result["status"] == "OPEN_INVENTORY"
    assert result["trading_cash"] == D("1.976000")
    assert result["remaining"] == D("0.006")
    assert result["unrealized"] == D("2.982000")
    assert result["fees"] == D("0.701009")
    assert result["net_bps"] is None
    assert view(ledger, at=400001)["unrealized"] is None


def test_13_tick_step_and_cash_quantization():
    f = filters()
    assert f.round_price("100000.04", True) == D("100000.1")
    assert f.round_price("100000.04", False) == D("100000.0")
    assert f.round_quantity("0.0109") == D("0.010")
    assert f.round_quantity("0.0049") + D("0.006") == D("0.010")
    assert c.money(D("0.000000005")) == D("0.00000000")
    assert c.money(D("-0.000000015")) == D("-0.00000002")
    tiny = c.SyntheticLedger(
        1,
        c.Filters(D("0.00000001"), D("0.00000001"), D(0)),
        c.Fees(D("0.000000005"), D("0.000000015")),
    )
    for name, action, at in (("entry", "ENTRY", 100000), ("exit", "EXIT", 800000)):
        q = c.Quote(D("0.9"), D("1.1"), at - 10, at - 5)
        tiny.add_fill(c.Fill(name, action, D(1), D(1), "TAKER", at, at + 1, at - 5, q, at + 2))
    assert_cash(tiny, "-0.00000004")


def test_14_invalid_grid_overclose_and_filters():
    ledger = c.SyntheticLedger(1, filters())
    for quantity, price, error in (
        ("0.0101", "100000", "OFF_GRID"),
        ("0.010", "100000.04", "OFF_GRID"),
        ("0.001", "1", "BELOW_MIN"),
    ):
        with pytest.raises(ValueError, match=error):
            ledger.add_fill(fill("bad", "ENTRY", quantity, price, 100000))
    with pytest.raises(ValueError, match="INVALID_FILL"):
        fill("bad", "ENTRY", "0.010", "0", 100000)
    with pytest.raises(ValueError, match="EXIT_EXCEEDS"):
        ledger.add_fill(fill("exit", "EXIT", "0.001", "100000", 200000))
    ledger.add_fill(fill("entry", "ENTRY", "0.010", "100000", 100000))
    with pytest.raises(ValueError, match="EXIT_EXCEEDS"):
        ledger.add_fill(fill("exit", "EXIT", "0.011", "100000", 200000))
    assert view(ledger)["remaining"] == D("0.010")
    with pytest.raises(ValueError, match="FILTER_NOT_VALID"):
        c.SyntheticLedger(1, filters(valid_until=100000)).add_fill(
            fill("entry", "ENTRY", "0.010", "100000", 100000)
        )


def test_15_nonfinite_float_and_quote_provenance():
    for value in ("NaN", "Infinity", "-Infinity", "bad", 0.1, 1, "1e100", "1e-100"):
        with pytest.raises((ValueError, TypeError)):
            c.decimal(value)
    for bid, ask, sequence in (
        ("100002", "99998", True),
        ("0", "100000", True),
        ("99998", "100002", False),
    ):
        with pytest.raises(ValueError, match="INVALID_QUOTE"):
            c.Quote(D(bid), D(ask), 100, 101, sequence_valid=sequence)
    event = fill("entry", "ENTRY", "0.010", "100003", 100000)
    with pytest.raises(ValueError, match="STALE_QUOTE"):
        replace(event, quote=replace(event.quote, observed_at=99000))
    with pytest.raises(ValueError, match="FILL_SOURCE_CHRONOLOGY"):
        replace(event, source_known_at=event.executed_at)
    with pytest.raises(ValueError, match="FEE_CURRENCY"):
        c.Fees(currency="BNB")


def test_16_duplicate_fill_idempotence_and_conflict():
    ledger = c.SyntheticLedger(1, filters())
    event = fill("entry", "ENTRY", "0.010", "100003", 100000)
    assert ledger.add_fill(event) is True
    before = view(ledger)
    assert ledger.add_fill(event) is False
    assert view(ledger) == before
    with pytest.raises(ValueError, match="CONFLICTING_FILL_ID"):
        ledger.add_fill(replace(event, quantity=D("0.009")))


def test_17_duplicate_settlement_idempotence_and_conflict():
    ledger = example("long")
    event = funding()
    before = view(ledger)
    assert ledger.add_funding(event) is False
    assert view(ledger) == before
    with pytest.raises(ValueError, match="CONFLICTING_SETTLEMENT_ID"):
        ledger.add_funding(replace(event, rate=D("0.0002")))
    with pytest.raises(ValueError, match="CONFLICTING_EVENT_KIND"):
        ledger.add_funding(replace(event, event_id="entry"))


def test_18_stop_market_gap_actual_fill_and_fee():
    result = c.stop_outcome(1, "MARKET", "99500", "98999", "0.010", "98997", "0.010")
    assert result["triggered"] and result["remaining"] == 0
    assert result["fill_price"] == D(98997)
    assert_cash(example("gap"), "-11.055000")
    short = c.stop_outcome(-1, "MARKET", "100500", "101000", "0.010", "101003", "0.004")
    assert short["triggered"] and short["remaining"] == D("0.006")
    assert c.stop_outcome(1, "MARKET", "99500", "100000", "0.010", "99997", "0.010")["filled"] == 0


def test_19_stop_limit_nonfill_preserves_inventory():
    result = c.stop_outcome(1, "LIMIT", "99500", "98999", "0.010", "98997", "0.010", limit="99499")
    assert result["triggered"] and result["filled"] == 0
    assert result["remaining"] == D("0.010") and result["fill_price"] is None
    ledger = c.SyntheticLedger(1, filters())
    ledger.add_fill(fill("entry", "ENTRY", "0.010", "100003", 100000))
    assert view(ledger, mark="98999")["status"] == "OPEN_INVENTORY"
    short = c.stop_outcome(
        -1, "LIMIT", "100500", "101000", "0.010", "101003", "0.010", limit="100501"
    )
    assert short["filled"] == 0


def test_20_ack_delayed_break_even_and_equal_clock():
    protection = c.Protection(100, 103, 104, 110)
    assert not protection.active(105)
    assert not protection.active(110)
    assert protection.active(111)
    with pytest.raises(ValueError, match="PREREQUISITE_ACK"):
        c.Protection(100, 105, 104, 110)
    ledger = c.SyntheticLedger(1, filters())
    ledger.add_fill(fill("entry", "ENTRY", "0.010", "100000", 100000))
    with pytest.raises(ValueError, match="SAME_CLOCK_FILL_AMBIGUITY"):
        ledger.add_fill(fill("exit", "EXIT", "0.010", "100000", 100000))


def test_21_delayed_funding_economic_before_after_partial():
    for exit_at, exposure in ((400000, "0.006"), (600000, "0.010")):
        ledger = c.SyntheticLedger(1, filters())
        ledger.add_fill(fill("entry", "ENTRY", "0.010", "100003", 100000))
        ledger.add_fill(fill("partial", "EXIT", "0.004", "100497", exit_at, mid="100500"))
        ledger.add_fill(fill("exit", "EXIT", "0.006", "100997", 800000, mid="101000"))
        ledger.add_funding(funding(quantity=exposure, known=850000))
        before = view(ledger, at=500001)
        assert before["status"] == "COST_INCOMPLETE"
        assert before["funding_cash"] is before["net_cash"] is None
        result = view(ledger)
        assert result["funding_cash"] == -D(exposure) * D(100400) * D("0.0001")
        assert result["remaining"] == 0  # Receipt inventory differs from settlement exposure.
        assert view(ledger, at=500001) == before  # Never backdate a later receipt.


def test_22_missing_and_ambiguous_funding_fail_closed():
    event = funding()
    mutations = (
        {"mark": None},
        {"rate": None},
        {"source_known_at": None},
        {"source_known_at": 499999},
        {"known_at": 499999},
        {"mark": D(0)},
        {"economic_exposure": None},
        {"economic_exposure": D("-0.010")},
        {"boundary_verified": False},
    )
    for changes in mutations:
        ledger = c.SyntheticLedger(1, filters())
        ledger.add_fill(fill("entry", "ENTRY", "0.010", "100003", 100000))
        ledger.add_funding(replace(event, **changes))
        result = view(ledger)
        assert result["status"] == "COST_INCOMPLETE"
        assert result["net_cash"] is result["funding_cash"] is None
    ledger = example("long")
    assert ledger.snapshot(900000)["status"] == "COST_INCOMPLETE"
    boundary = c.SyntheticLedger(1, filters())
    boundary.add_fill(fill("entry", "ENTRY", "0.010", "100003", 100000))
    boundary.add_fill(fill("partial", "EXIT", "0.004", "100497", 500000, mid="100500"))
    boundary.add_funding(funding())
    assert view(boundary)["status"] == "COST_INCOMPLETE"
    for offset in (-15000, -1000, 0, 1000, 15000):
        near = c.SyntheticLedger(1, filters())
        near.add_fill(fill("entry", "ENTRY", "0.010", "100003", 100000))
        near.add_fill(fill("partial", "EXIT", "0.004", "100497", 500000 + offset, mid="100500"))
        near.add_funding(funding(quantity="0.006" if offset < 0 else "0.010"))
        assert view(near)["funding_cash"] is None
        assert view(near)["status"] == "COST_INCOMPLETE"
    for coverage in (
        c.FundingCoverage(100001, 900000, 900000, "SYNTHETIC:late-start", ("settlement",)),
        c.FundingCoverage(0, 800000, 800000, "SYNTHETIC:early-end", ("settlement",)),
        c.FundingCoverage(0, 900000, 900001, "SYNTHETIC:future-receipt", ("settlement",)),
        c.FundingCoverage(0, 900000, 900000, "SYNTHETIC:missing-identity", ()),
        c.FundingCoverage(0, 900000, 900000, "SYNTHETIC:missing-event", ("settlement", "absent")),
    ):
        assert ledger.snapshot(900000, funding_coverage=coverage)["status"] == "COST_INCOMPLETE"
    with pytest.raises(TypeError, match="BOUNDED_FUNDING_COVERAGE"):
        ledger.snapshot(900000, funding_coverage=True)
    with pytest.raises(ValueError, match="COVERAGE_WITNESS"):
        c.FundingCoverage(0, 900000, 900000, "", ())


def test_23_identical_fills_quote_attribution_not_cash():
    original = example("long")
    shifted = c.SyntheticLedger(1, filters())
    for event in original._fills.values():
        # Invented alternate valuation/Last proxies cannot change actual executed cash.
        shifted.add_fill(
            replace(
                event,
                quote=replace(event.quote, bid=event.quote.bid + D(1), ask=event.quote.ask + D(1)),
            )
        )
    shifted.add_funding(funding())
    a, b = view(original), view(shifted)
    for key in ("net_cash", "trading_cash", "fees", "funding_cash"):
        assert a[key] == b[key]
    assert a["mid_gross"] - a["fill_drag"] == b["mid_gross"] - b["fill_drag"]
    with pytest.raises(ValueError, match="INVALID_IMPACT_BASIS"):
        fill("entry", "ENTRY", "0.010", "100003", 100000, impact_basis="LAST_PROXY")


def test_24_notional_leverage_and_decimal_context_invariance():
    ledger = example("long")
    reference = view(ledger)
    with localcontext() as context:
        context.prec = 6
        for leverage in ("1", "10", "15"):
            result = view(ledger, leverage=leverage)
            for key in ("fees", "net_cash", "net_bps", "entry_notional"):
                assert result[key] == reference[key]
            assert result["margin_roi"] is None
