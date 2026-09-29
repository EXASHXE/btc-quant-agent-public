from __future__ import annotations

from dataclasses import fields
from math import log

import numpy as np
import pytest

from btc_quant_agent.h41.authority import (
    CANDIDATES,
    EXPECTED_ARCHIVE_SETS,
    EXPECTED_HASHES,
    EXPECTED_MEMBERSHIP,
    EXPECTED_PROJECTIONS,
    EXPECTED_RECEIPTS,
    EXPECTED_SOURCE_ROOT,
    FROZEN_HASHES,
    SOURCE_BINDING,
    verify_frozen_bindings,
)
from btc_quant_agent.h41.science import (
    PARTITIONS,
    CompletedBar,
    CompletedPairView,
    Event,
    EventBatch,
    _linear_q80,
    build_event_batch,
    candidate_side,
    train_q80,
)

BASE = 1_609_459_200_000  # Synthetic 2021-01-01 UTC clock; no market data.


def _view(*, n: int = 75, shift: int = 0, btc: list[float] | None = None,
          eth: list[float] | None = None) -> CompletedPairView:
    btc = btc or [100.0] * n
    eth = eth or [100.0] * n
    def bars(values: list[float]) -> tuple[CompletedBar, ...]:
        return tuple(CompletedBar(BASE + (shift + n - i - 1) * 3_600_000,
                                  values[n - i - 1] + 1,
                                  values[n - i - 1] - 1, values[n - i - 1])
                     for i in range(n))
    return CompletedPairView(BASE + (shift + n) * 3_600_000, bars(btc), bars(eth))


def test_frozen_ledger_and_hashes() -> None:
    verify_frozen_bindings()
    assert len(CANDIDATES) == 20
    assert [c.slot for c in CANDIDATES] == list(range(1, 21))
    assert {c.horizon_hours for c in CANDIDATES} == {4, 8, 24}
    assert FROZEN_HASHES['candidate_ledger_hash'] == 'd2ee1551ab4778e8ce34e83e053aba17ebb6be240aed812a4beedb218548b7e0'
    assert FROZEN_HASHES == EXPECTED_HASHES
    assert SOURCE_BINDING['joint_root'] == EXPECTED_SOURCE_ROOT
    assert SOURCE_BINDING['receipt_hashes'] == EXPECTED_RECEIPTS
    assert SOURCE_BINDING['projection_hashes'] == EXPECTED_PROJECTIONS
    assert SOURCE_BINDING['archive_set_hashes'] == EXPECTED_ARCHIVE_SETS
    assert SOURCE_BINDING['membership_hashes']['joint'] == EXPECTED_MEMBERSHIP
    assert {family: sum(c.family == family for c in CANDIDATES) for family in
            ('D1_TREND', 'D2_BREAKOUT', 'D3_FAILED_BREAK', 'D4_MODIFIER')} == {
                'D1_TREND': 4, 'D2_BREAKOUT': 4, 'D3_FAILED_BREAK': 4, 'D4_MODIFIER': 8,
            }
    with pytest.raises(TypeError):
        SOURCE_BINDING['joint_root'] = 'forged'  # type: ignore[index]
    with pytest.raises(TypeError):
        SOURCE_BINDING['archive_records']['BTC'][0]['official_archive_checksum'] = 'forged'  # type: ignore[index]


def test_completed_input_excludes_reference_marks() -> None:
    assert {f.name for f in fields(CompletedBar)} == {'open_time_ms', 'high', 'low', 'close'}
    assert 'open' not in {f.name for f in fields(CompletedPairView)}
    with pytest.raises(TypeError):
        CompletedBar(0, 2, 1, 1.5, open=1.5)  # type: ignore[call-arg]


def test_d1_signed_q80_and_zero() -> None:
    c = CANDIDATES[0]
    values = [100.0] * 75
    values[-1] = 110.0
    assert candidate_side(c, _view(btc=values), {c.candidate_id: log(1.1)}) == 1
    values[-1] = 90.0
    assert candidate_side(c, _view(btc=values), {c.candidate_id: abs(log(.9))}) == -1
    values[-1] = 100.0
    assert candidate_side(c, _view(btc=values), {c.candidate_id: 0.0}) == 0
    with pytest.raises(ValueError, match='500'):
        _linear_q80([0.0] * 499)


@pytest.mark.parametrize('slot', (1, 2, 3, 4))
def test_d1_all_asset_window_horizon_bindings(slot: int) -> None:
    candidate = CANDIDATES[slot - 1]
    values = [100.0] * 75
    values[-1] = 104.0
    view = _view(**{'btc' if candidate.target_asset == 'BTCUSDT' else 'eth': values})
    assert candidate_side(candidate, view, {candidate.candidate_id: log(1.04)}) == 1
    values[-1] = 96.0
    view = _view(**{'btc' if candidate.target_asset == 'BTCUSDT' else 'eth': values})
    assert candidate_side(candidate, view, {candidate.candidate_id: abs(log(.96))}) == -1


def test_train_only_linear_q80_and_duplicate_rejection() -> None:
    c = CANDIDATES[0]
    scores = [abs(log((100 + i % 19) / 100)) for i in range(500)]
    expected = float(np.quantile([abs(log((100 + i % 19) / 100))
                                  for i in range(500)], .80, method='linear'))
    assert _linear_q80(scores) == expected
    full_count = (PARTITIONS['WF1_TRAIN'][1] - PARTITIONS['WF1_TRAIN'][0]) // 3_600_000 - 5
    full = (_view(n=5, shift=i) for i in range(full_count))
    assert train_q80(c, full) == 0.0
    with pytest.raises(ValueError, match='complete'):
        train_q80(c, (_view(n=5, shift=i) for i in range(500)))
    with pytest.raises(ValueError, match='complete'):
        train_q80(c, [_view(n=5), _view(n=5)])


def test_d2_and_d3_strict_boundaries() -> None:
    d2, d3 = CANDIDATES[4], CANDIDATES[8]
    values = [100.0] * 75
    values[-1] = 103.0
    assert candidate_side(d2, _view(btc=values), {}) == 1
    values[-1] = 101.0
    assert candidate_side(d2, _view(btc=values), {}) == 0
    values[-2] = 103.0
    values[-1] = 100.0
    assert candidate_side(d3, _view(btc=values), {}) == -1
    values[-2] = 99.0
    assert candidate_side(d3, _view(btc=values), {}) == 0


@pytest.mark.parametrize('slot', (5, 6, 7, 8))
def test_d2_all_frozen_variants_and_equality(slot: int) -> None:
    candidate = CANDIDATES[slot - 1]
    asset = candidate.target_asset
    def side(last: float) -> int:
        values = [100.0] * 75
        values[-1] = last
        return candidate_side(candidate, _view(**{'btc' if asset == 'BTCUSDT' else 'eth': values}), {})
    assert side(103.0) == 1
    assert side(97.0) == -1
    assert side(101.0) == 0
    assert side(99.0) == 0


@pytest.mark.parametrize('slot', (9, 10, 11, 12))
def test_d3_all_frozen_variants_and_strict_inside(slot: int) -> None:
    candidate = CANDIDATES[slot - 1]
    asset = candidate.target_asset
    def side(previous: float, current: float) -> int:
        values = [100.0] * 75
        values[-2] = previous
        values[-1] = current
        return candidate_side(candidate, _view(**{'btc' if asset == 'BTCUSDT' else 'eth': values}), {})
    assert side(103.0, 100.0) == -1
    assert side(97.0, 100.0) == 1
    assert side(101.0, 100.0) == 0
    assert side(103.0, 101.0) == 0
    assert side(97.0, 99.0) == 0


@pytest.mark.parametrize('confirm_slot', (13, 15, 17, 19))
def test_d4_all_parent_types_and_assets(confirm_slot: int) -> None:
    confirm = CANDIDATES[confirm_slot - 1]
    diverge = CANDIDATES[confirm_slot]
    target = [100.0] * 75
    target[-1] = 103.0
    other = [100.0] * 75
    def view(other_last: float) -> CompletedPairView:
        other[-1] = other_last
        return _view(btc=target, eth=other) if confirm.target_asset == 'BTCUSDT' else _view(btc=other, eth=target)
    q80 = {confirm.parent_id: 0.0} if confirm_slot in (13, 15) else {}
    assert candidate_side(confirm, view(105.0), q80) == 1
    assert candidate_side(diverge, view(105.0), q80) == 0
    assert candidate_side(confirm, view(95.0), q80) == 0
    assert candidate_side(diverge, view(95.0), q80) == 1
    assert candidate_side(confirm, view(100.0), q80) == 0
    assert candidate_side(diverge, view(100.0), q80) == 0


def test_scientific_input_rejects_purge_and_validation() -> None:
    for name in ('WF1_PURGE_1', 'WF1_PURGE_2', 'WF1_VALIDATION'):
        t = PARTITIONS[name][0]
        shift = (t - BASE) // 3_600_000 - 75
        with pytest.raises(ValueError, match='protected or source-only'):
            candidate_side(CANDIDATES[4], _view(shift=shift), {})
        with pytest.raises(ValueError, match='protected or source-only'):
            build_event_batch(CANDIDATES[4], [_view(shift=shift)], {}, name)


def test_strict_right_boundary_censoring_in_event_builder() -> None:
    candidate = CANDIDATES[4]
    end = PARTITIONS['WF1_TRAIN'][1]
    values = [100.0] * 75
    values[-1] = 103.0
    for hours_before_end, expected in ((5, True), (4, True), (3, False)):
        t = end - hours_before_end * 3_600_000
        event = Event(t, 1, 4)
        if expected:
            assert EventBatch(candidate.candidate_id, 'WF1_TRAIN', (event,)).events
        else:
            with pytest.raises(ValueError, match='outside frozen partition'):
                EventBatch(candidate.candidate_id, 'WF1_TRAIN', (event,))
    cal_start, cal_end = PARTITIONS['WF1_CALIBRATION']
    shift = (cal_start - BASE) // 3_600_000 - 75
    full_cal = (_view(shift=shift + i, btc=values) for i in range(2184))
    batch = build_event_batch(candidate, full_cal, {}, 'WF1_CALIBRATION')
    assert len(batch.events) == 2181
    assert batch.events[-1].decision_time_ms + 4 * 3_600_000 == cal_end


def test_d4_uses_other_ret4_not_candle() -> None:
    child = CANDIDATES[16]
    values = [100.0] * 75
    values[-1] = 105.0
    btc = [100.0] * 75
    btc[-1] = 103.0  # BO24 parent is +1.
    assert candidate_side(child, _view(btc=btc, eth=values), {}) == 1
    values[-1] = 95.0
    assert candidate_side(child, _view(btc=btc, eth=values), {}) == 0
    assert candidate_side(CANDIDATES[17], _view(btc=btc, eth=values), {}) == 1
    assert candidate_side(child, _view(btc=btc), {}) == 0
    assert candidate_side(CANDIDATES[12], _view(btc=btc, eth=values),
                          {CANDIDATES[0].candidate_id: 0.0}) == 0


def test_event_batch_rejects_foreign_candidate() -> None:
    with pytest.raises(ValueError):
        EventBatch('not_registered', 'WF1_TRAIN', (Event(0, 1, 4),))
