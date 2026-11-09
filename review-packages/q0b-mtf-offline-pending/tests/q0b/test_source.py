from dataclasses import replace

import pytest

from q0b.examples import SETUP_END, bar, batch, modify_bar, snapshot
from q0b.schema import ClockProof, HOUR, INTERVALS, MINUTE, Snapshot
from q0b.source import HOLDOUT, PROTECTED, SourceError, SourceLedger, allowed_range, utc_ms
from q0b.strategy import Engine


@pytest.mark.parametrize("change,code", [
    ({"closed": False}, "OPEN_OR_FUTURE"),
    ({"exchange_observed_lower_ms": 0}, "OPEN_OR_FUTURE"),
    ({"available_ms": snapshot().asof_ms + 1}, "OPEN_OR_FUTURE"),
    ({"exchange_close_ms": 1}, "EXCHANGE_INTERVAL_PROOF"),
    ({"symbol": "ETHUSDT"}, "BAR_IDENTITY"),
    ({"interval": "15m"}, "BAR_IDENTITY"),
    ({"revision": 1}, "REVISION_QUARANTINED"),
    ({"provenance": "REAL_HISTORY"}, "BAR_PROVENANCE"),
    ({"high": float("nan")}, "INVALID_OHLCV"),
    ({"volume": -1}, "INVALID_OHLCV"),
])
def test_bad_bar_is_rejected_before_any_features(monkeypatch, change, code):
    def forbidden(*args):
        raise AssertionError("FEATURES_MUST_NOT_ACCESS_REJECTED_ROWS")
    monkeypatch.setattr("q0b.strategy.build_candidate", forbidden)
    card = Engine().review(modify_bar(snapshot(), "1H", **change))
    assert card.state == "DATA_UNAVAILABLE"
    assert code in card.reasons[0]


@pytest.mark.parametrize("kind,code", [("duplicate", "DUPLICATE_BAR"),
                                      ("gap", "GAP_OR_UNORDERED_BAR"),
                                      ("edge", "REQUEST_EDGE_GAP")])
def test_duplicate_and_gaps_rejected(kind, code):
    s = snapshot()
    group = s.batches[2]
    rows = list(group.bars)
    if kind == "duplicate":
        rows.insert(2, rows[1])
    elif kind == "gap":
        rows.pop(2)
    else:
        rows.pop(0)
    groups = list(s.batches)
    groups[2] = replace(group, bars=tuple(rows))
    card = Engine().review(replace(s, batches=tuple(groups)))
    assert card.reasons == (code,)


def test_strict_future_range_is_never_read():
    s = snapshot()
    group = s.batches[-1]
    groups = s.batches[:-1] + (replace(group, requested_end_ms=s.asof_ms + MINUTE),)
    card = Engine().review(replace(s, batches=groups))
    assert card.state == "DATA_UNAVAILABLE"
    assert card.reasons == ("FUTURE_REQUEST_RANGE",)


def test_clock_uncertainty_cannot_prove_last_close():
    s = snapshot()
    last_end = s.batches[2].bars[-1].end_ms
    s = replace(s, clock=replace(s.clock, exchange_lower_ms=last_end-1, sampled_ms=last_end-10))
    card = Engine().review(s)
    assert card.state == "SOURCE_BLOCKED"  # uncertainty itself is outside allowed 2s


@pytest.mark.parametrize("delay,state", [(199, "DATA_UNAVAILABLE"), (200, "WATCH")])
def test_closed_bar_availability_boundary_requires_complete_proof(delay, state):
    s = snapshot(quote=False)
    asof = SETUP_END + delay
    s = replace(s, asof_ms=asof, clock=ClockProof(SETUP_END, asof+50, SETUP_END-100))
    assert Engine().review(s).state == state


def test_revision_quarantines_only_affected_symbol():
    engine = Engine()
    assert engine.review(snapshot()).state == "WATCH"
    revision = modify_bar(snapshot(15), "1H", close=100.6)
    assert engine.review(revision).reasons == ("REVISION_QUARANTINED",)
    assert engine.review(snapshot(16)).state == "DATA_UNAVAILABLE"
    assert engine.review(snapshot(15, symbol="ETHUSDT")).state == "WATCH"


def test_repeated_receipt_of_unchanged_bar_is_not_revision():
    ledger = SourceLedger()
    ledger.admit(snapshot())
    s = snapshot(15)
    group = s.batches[2]
    rows = tuple(replace(b, received_ms=b.received_ms+1000, available_ms=b.available_ms+1000)
                 for b in group.bars)
    groups = list(s.batches)
    groups[2] = replace(group, bars=rows)
    assert ledger.admit(replace(s, batches=tuple(groups)))["1H"]


def test_asof_rewind_and_overall_veto():
    engine = Engine()
    engine.review(snapshot(15))
    assert engine.review(snapshot()).reasons == ("ASOF_REWIND",)
    other = Engine()
    s = replace(snapshot(16), source_veto=True)
    assert other.review(s).state == "SOURCE_BLOCKED"
    assert other.review(snapshot(17, symbol="ETHUSDT")).state == "SOURCE_BLOCKED"


def test_interval_watermark_cannot_rewind_at_later_review_time():
    engine = Engine()
    engine.review(snapshot(15))
    s = snapshot(16)
    old_five = next(b for b in snapshot().batches if b.interval == "5m")
    groups = tuple(old_five if b.interval == "5m" else b for b in s.batches)
    assert engine.review(replace(s, batches=groups)).reasons == ("INTERVAL_WATERMARK_REWIND",)


@pytest.mark.parametrize("clock_change", [{"strict_ok": False}, {"authority": "WALL_CLOCK"},
                                          {"exchange_upper_ms": 0}])
def test_frozen_clock_boundary_cannot_be_downgraded(clock_change):
    s = snapshot()
    assert Engine().review(replace(s, clock=replace(s.clock, **clock_change))).state == "SOURCE_BLOCKED"


@pytest.mark.parametrize("start,end,reason", [
    (HOLDOUT[0]-MINUTE, HOLDOUT[0], "PROTECTED_HISTORY_EXCLUDED"),
    (HOLDOUT[0], HOLDOUT[0]+MINUTE, "HOLDOUT_EXCLUDED"),
    (HOLDOUT[1]-MINUTE, HOLDOUT[1], "HOLDOUT_EXCLUDED"),
    (HOLDOUT[1], HOLDOUT[1]+MINUTE, "PROTECTED_HISTORY_EXCLUDED"),
    (PROTECTED[0], PROTECTED[0]+MINUTE, "PROTECTED_HISTORY_EXCLUDED"),
    (utc_ms("2025-06-01"), utc_ms("2025-06-02"), "PROTECTED_HISTORY_EXCLUDED"),
])
def test_protected_and_holdout_half_open_boundaries(start, end, reason):
    with pytest.raises(SourceError, match=reason):
        allowed_range(start, end)


def test_outside_protected_ranges_are_not_accidentally_embargoed():
    allowed_range(PROTECTED[0]-MINUTE, PROTECTED[0])
    allowed_range(PROTECTED[1], PROTECTED[1]+MINUTE)


def test_missing_required_hourly_is_data_unavailable_not_no_setup():
    s = snapshot()
    s = replace(s, batches=tuple(b for b in s.batches if b.interval != "1H"))
    assert Engine().review(s).reasons == ("MISSING_REQUIRED_1H",)


def test_future_quote_cannot_enable_entry():
    s = snapshot()
    s = replace(s, quote=replace(s.quote, available_ms=s.asof_ms+1))
    assert Engine().review(s).reasons == ("INVALID_OR_FUTURE_QUOTE",)


@pytest.mark.parametrize("field,value", [("batches", None), ("batches", (None,)), ("quote", 7)])
def test_malformed_envelope_returns_classified_refusal(field, value):
    assert Engine().review(replace(snapshot(), **{field: value})).state == "DATA_UNAVAILABLE"


def test_oversized_batch_refused_before_features():
    s = snapshot()
    group = s.batches[-1]
    group = replace(group, bars=group.bars*3)
    s = replace(s, batches=s.batches[:-1]+(group,))
    assert Engine().review(s).reasons == ("MALFORMED_OR_OVERSIZED_BAR_BATCH",)


def test_cross_snapshot_gap_is_not_silently_skipped():
    ledger = SourceLedger()
    ledger.admit(snapshot())
    s = snapshot(15)
    group = s.batches[-1]
    rows = tuple(b for b in group.bars if b.open_ms > SETUP_END)
    group = replace(group, bars=rows, requested_start_ms=rows[0].open_ms)
    s = replace(s, batches=s.batches[:-1]+(group,))
    with pytest.raises(SourceError, match="CROSS_SNAPSHOT_GAP"):
        ledger.admit(s)


def test_streaming_identity_memory_is_bounded_and_revisions_remain_detectable():
    ledger = SourceLedger()
    latest = None
    for hour in range(8):
        asof = SETUP_END + hour * HOUR + 5_000
        groups = []
        for interval, step in INTERVALS.items():
            end = asof // step * step
            rows = [bar("BTCUSDT", interval, end-i*step, 100, 101, 99, 100) for i in range(63, -1, -1)]
            groups.append(batch("BTCUSDT", interval, rows))
        latest = Snapshot("BTCUSDT", asof, ClockProof(asof-50, asof+50, asof-100), tuple(groups))
        ledger.admit(latest)
    assert len(ledger.identities) == 64 * len(INTERVALS)
    with pytest.raises(SourceError, match="REVISION_QUARANTINED"):
        ledger.admit(modify_bar(latest, "5m", close=100.1))
