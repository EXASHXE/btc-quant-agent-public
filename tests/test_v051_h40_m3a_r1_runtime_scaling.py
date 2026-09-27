"""Exact reconstruction scaling checks; every source is explicitly synthetic."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from btc_quant_agent.h40 import discovery_evidence as science


def test_exact_percentile_prefix_ties_and_out_of_order_queries():
    start = datetime(2022, 1, 1, tzinfo=UTC)
    observations = [(start + timedelta(hours=i), value) for i, value in enumerate([2.0, 2.0, 1.0, 4.0, -0.0, 0.0])]
    assert hasattr(science, '_CausalPercentileIndex')
    index = science._CausalPercentileIndex(observations)
    # Equal timestamp is excluded. Multiple equal values contribute ONE half tie.
    assert index.query(start + timedelta(hours=2), 2.0) == (2, 0.25)
    assert index.query(start + timedelta(hours=6), 2.0) == (6, 3 / 6 + 0.5 / 6)
    assert index.query(start, 2.0) == (0, 0.0)
    for hour in [4, 1, 6, 2, 0, 5, 3]:
        t = start + timedelta(hours=hour)
        sample = [value for dt, value in observations if dt < t]
        for x in [-1.0, -0.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0]:
            assert index.query(t, x) == (len(sample), science._empirical_percentile(sample, x))


def test_geometry_index_exact_multiset_floor_and_fallback():
    start = datetime(2022, 1, 1, tzinfo=UTC)
    owner = 'D1_V1_RETURN_4H'
    records = {}
    for i in range(65):
        # L0 has 29; L1 crosses the floor, with duplicate observations intact.
        records[(owner, 'ETH_ONLY', 4 if i < 30 else 8, start + timedelta(hours=i), 'ETHUSDT', 'LONG' if i < 29 else 'SHORT')] = (0.001 if i < 30 else 0.004, 0.001)
    assert hasattr(science, '_GeometryIndex')
    index = science._GeometryIndex({owner: records})
    slot = SimpleNamespace(direction_contract_id=owner, scope='ETH_ONLY', primary_horizon='4h')
    row = SimpleNamespace(proposed_action='LONG')
    import h40_runtime_reference as reference
    assert science._geometry_pass(row, slot, index) is False
    assert science._geometry_pass(row, slot, index) == reference._geometry_pass(row, slot, {owner: records})
    assert index.cells[(owner, 'ETH_ONLY', 4, 'LONG')][0] == 29
    assert index.cells[(owner, 'ETH_ONLY', 4, None)][0] == 30
    for scope in ['ETH_ONLY', 'other']:
        for horizon in ['4h', '8h', '12h']:
            for side in ['LONG', 'SHORT']:
                slot = SimpleNamespace(direction_contract_id=owner, scope=scope, primary_horizon=horizon)
                row = SimpleNamespace(proposed_action=side)
                assert science._geometry_pass(row, slot, index) == reference._geometry_pass(row, slot, {owner: records})


def test_reconstruction_session_releases_state_on_error():
    assert hasattr(science, '_reconstruction_scope')
    assert science._ACTIVE_RECONSTRUCTION.get() is None
    with pytest.raises(RuntimeError), science._reconstruction_scope() as state:
        assert science._ACTIVE_RECONSTRUCTION.get() is state
        raise RuntimeError('synthetic interruption')
    assert science._ACTIVE_RECONSTRUCTION.get() is None


def _bars(count=300):
    start = datetime(2022, 6, 1, tzinfo=UTC)
    bars = {}
    for i in range(count):
        close = 100 + i * 0.02 + (i % 7) * 0.1
        t = start + timedelta(hours=i)
        bars[(t, 'ETHUSDT')] = science._Bar(t, 'ETHUSDT', close - 0.01, close + 0.4, close - 0.3, close)
        bars[(t, 'BTCUSDT')] = science._Bar(t, 'BTCUSDT', close * 2, close * 2 + 0.8, close * 2 - 0.6, close * 2)
    return bars, start


def test_shared_state_source_product_partition_and_direction_fences():
    from dataclasses import replace

    import h40_runtime_reference as reference
    bars, start = _bars()
    t = start + timedelta(hours=100)
    slot = SimpleNamespace(direction_contract_id='D1_V1_RETURN_4H', primary_horizon='4h', secondary_filter_contract_id='NONE')
    with science._reconstruction_scope() as state:
        def run(candidate, source='first', product='ETHUSDT', partition='WF1_TRAIN', selected=slot, data=bars):
            kwargs = {'candidate_id': candidate, 'slot': selected, 'partition_id': partition, 't': t, 'product': product, 'bars': data, 'source_evidence_hash': source}
            assert science._reconstruct_prefit_cached(**kwargs) == reference._reconstruct_prefit_cached(**kwargs)
            return science._reconstruct_prefit_cached(**kwargs)
        original = run('configuration_A')
        assert run('configuration_B') == original
        assert state.statistics()['prefit_entries'] == 1
        assert state.statistics()['candidate_independent_states'] == 1
        run('configuration_A', product='BTCUSDT')
        run('configuration_A', partition='WF1_CALIBRATION')
        other_slot = SimpleNamespace(direction_contract_id='D1_V2_RETURN_12H', primary_horizon='4h', secondary_filter_contract_id='NONE')
        run('other_direction', selected=other_slot)
        assert state.statistics()['candidate_independent_states'] == 3
        mutated = dict(bars)
        last = (t - timedelta(hours=1), 'ETHUSDT')
        mutated[last] = replace(mutated[last], close=123.0, high=124.0)
        assert run('configuration_A', source='changed', data=mutated)[0] != original[0]
        assert state.statistics()['source_product_indices'] == 3
        assert all('configuration' not in key[3] for key in state.prefit)
    assert state.statistics()['prefit_entries'] == 0


def test_future_observations_and_equal_close_cannot_change_earlier_state():
    from dataclasses import replace

    import h40_runtime_reference as reference
    bars, start = _bars()
    t = start + timedelta(hours=100)
    slot = SimpleNamespace(direction_contract_id='D2_V1_BREAKOUT_24H', primary_horizon='4h')
    changed = {key: replace(bar, high=bar.high * 2, close=bar.close * 1.5) if key[0] >= t else bar for key, bar in bars.items()}
    with science._reconstruction_scope():
        values = []
        for source, data in [('original', bars), ('future_changed', changed)]:
            kwargs = {'candidate_id': 'c', 'slot': slot, 'partition_id': 'WF1_TRAIN', 't': t, 'product': 'ETHUSDT', 'bars': data, 'source_evidence_hash': source}
            value = science._reconstruct_prefit_cached(**kwargs)
            assert value == reference._reconstruct_prefit_cached(**kwargs)
            values.append(value)
        assert values[0] == values[1]
        last = (t - timedelta(hours=1), 'ETHUSDT')
        equal = dict(bars)
        equal[last] = replace(equal[last], close_time=t)
        kwargs = {'candidate_id': 'c', 'slot': slot, 'partition_id': 'WF1_TRAIN', 't': t, 'product': 'ETHUSDT', 'bars': equal, 'source_evidence_hash': 'equal_close'}
        assert science._reconstruct_prefit_cached(**kwargs) == reference._reconstruct_prefit_cached(**kwargs)
        assert science._reconstruct_prefit_cached(**kwargs)[0] == 0.0


def test_raw_decisions_share_only_exact_direction_horizon_and_partition():
    bars, start = _bars()
    t = start + timedelta(hours=100)
    slot = SimpleNamespace(direction_contract_id='D1_V1_RETURN_4H', primary_horizon='4h')
    with science._reconstruction_scope() as state:
        def run(candidate, horizon=4, selected=slot):
            return science._derive_source_decision(candidate_id=candidate, slot=selected, partition_id='WF1_TRAIN', timestamp=t, product='ETHUSDT', horizon=horizon, bars=bars, source_evidence_hash='raw_source')
        first = run('A')
        second = run('B')
        assert first is second
        assert state.statistics()['decision_entries'] == 1
        longer_slot = SimpleNamespace(direction_contract_id='D1_V1_RETURN_4H', primary_horizon='8h')
        longer = run('A', 8, longer_slot)
        assert longer is not first and len(longer.path) == 8
        other_slot = SimpleNamespace(direction_contract_id='D1_V2_RETURN_12H', primary_horizon='4h')
        other = run('A', selected=other_slot)
        assert other is not first
        assert other.path is first.path
        assert state.statistics()['decision_entries'] == 3
        assert state.statistics()['outcome_entries'] == 2


def test_compact_complete_reference_bytes_and_all_verifier_outputs(tmp_path, monkeypatch):
    import h40_runtime_reference as reference
    from test_v051_h40_m3a_production_discovery_producer import (
        _producer,
        _synthetic_authority,
        _verifier,
    )
    authority = _synthetic_authority(tmp_path, monkeypatch)
    reference._PREFIT_CACHE.clear()
    reference._TRAINING_REFS.clear()
    science.clear_prefit_caches()
    slow = reference.produce(_producer(authority))
    slow_bytes = {digest: (authority.root / digest[:2] / f'{digest}.json').read_bytes() for digest in slow.dependency_digests}
    slow_verifier = _verifier(authority)
    with monkeypatch.context() as patch:
        patch.setattr(science, '_reconstruct_prefit_cached', reference._reconstruct_prefit_cached)
        patch.setattr(science, '_geometry_pass', lambda row, slot, index: reference._geometry_pass(row, slot, index.members))
        slow_verifier.verify_discovery_manifest(slow.evidence, slow.entries)
        slow_outputs = [slow_verifier.verify_candidate(entry, run_authority_id=slow.evidence.run_authority_id, correction_manifest_hash=slow.evidence.correction_input_evidence_manifest_hash) for entry in slow.entries]
    fresh_root = tmp_path / 'optimized-evidence'
    fresh_root.mkdir()
    authority.root = fresh_root
    science.clear_prefit_caches()
    fast = _producer(authority).produce()
    assert fast.evidence == slow.evidence
    assert fast.entries == slow.entries
    assert fast.dependency_digests == slow.dependency_digests
    assert {digest: (fresh_root / digest[:2] / f'{digest}.json').read_bytes() for digest in fast.dependency_digests} == slow_bytes
    verifier = _verifier(authority)
    verifier.verify_discovery_manifest(fast.evidence, fast.entries)
    fast_outputs = [verifier.verify_candidate(entry, run_authority_id=fast.evidence.run_authority_id, correction_manifest_hash=fast.evidence.correction_input_evidence_manifest_hash) for entry in fast.entries]
    assert fast_outputs == slow_outputs
    assert len(fast_outputs) == 18
    assert science._ACTIVE_RECONSTRUCTION.get() is None
    for entry in fast.entries:
        assert len(entry.structural_configuration_hash) == 64
    # Output reuse must not leak configuration-specific probability/action state.
    assert len({entry.candidate_result_input_evidence_hash for entry in fast.entries}) == 18


def test_production_session_never_adopts_caller_cache_state():
    @science._reconstruction_session
    def operation():
        return science._ACTIVE_RECONSTRUCTION.get()
    with science._reconstruction_scope() as caller_state:
        first = operation()
        second = operation()
        assert first is not caller_state
        assert second is not caller_state and second is not first
        assert science._ACTIVE_RECONSTRUCTION.get() is caller_state
