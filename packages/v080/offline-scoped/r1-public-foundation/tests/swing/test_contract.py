from __future__ import annotations

import copy
import json
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from btc_quant_agent import api
from btc_quant_agent.domain import Candle
from btc_quant_agent.platform.cli import execute, main
from btc_quant_agent.platform.config import PlatformConfig, StrategyConfig, load_config
from btc_quant_agent.platform.core import StrategyDefinition
from btc_quant_agent.platform.strategies import REGISTRY, evaluate, register
from btc_quant_agent.platform.swing import (
    INTERVALS, AdvisorySnapshot, ClosedBar, Opportunity, State, SwingPolicy, decide,
)
from btc_quant_agent.platform.swing_store import DecisionStore
from btc_quant_agent.platform.swing_view import view
from btc_quant_agent.platform.ui import page

ROOT = Path(__file__).resolve().parents[2]
TRIGGER = int(datetime(2026, 11, 6, 12, tzinfo=UTC).timestamp() * 1000)
NOW = TRIGGER + 30_000
DAY = INTERVALS['1D']
RETIRED = (
    'trend_breakout', 'breakout_retest', 'sweep_reclaim', 'shock_reversal',
    'liquidation_reversion', 'turning_point', 'compression_breakout', 'spot_led_breakout',
    'single_ma', 'double_ma', 'multi_ma', 'macd_adx', 'aroon', 'bollinger_reversion',
    'rsi_reversion', 'rsi_divergence', 'stochrsi_reversal', 'cci_reversal', 'rsrs_timing',
    'multi_factor_momentum', 'pair_trading', 'cointegration_spread', 'funding_carry',
    'grid', 'volatility_target', 'rebalance', 'relative_strength_rotation',
    'R17', 'R11', 'S1', 'S2', 'S3', 'S4', 'TREND_PULLBACK',
)


def bars(trigger=TRIGGER):
    result = []
    for timeframe in ('4H', '1D'):
        size = INTERVALS[timeframe]
        latest = trigger // size * size
        for end in range(latest - 59 * size, latest + size, size):
            candle = Candle('BTCUSDT', timeframe, end - size, end - 1,
                            100, 101, 99, 100, 10, available_at_ms=end + 10)
            result.append(ClosedBar(candle=candle, source_id='fabricated-offline', source_event_ms=end,
                                    received_ms=end + 5, available_ms=end + 10, durable_ms=end + 20))
    return result


def opportunity(**updates):
    data = dict(symbol='BTCUSDT', direction='LONG', regime='TREND_UP', setup_close_ms=TRIGGER,
                available_ms=TRIGGER + 10, structural_observed_ms=TRIGGER - INTERVALS['4H'],
                entry_region=(99.0, 101.0), structural_invalidation=90.0, atr_buffer=1.0,
                execution_buffer=0.5, target_zones=(120.0, 130.0), planned_cost_per_unit=0.25,
                cost_assumption='OFFLINE_ASSUMPTION; round trip costs included; not executable payoff',
                review_deadline_ms=TRIGGER + DAY, expires_ms=TRIGGER + 2 * DAY,
                account_status='NOT_REQUESTED')
    data.update(updates)
    if data['target_zones']:
        entry = data['entry_region'][1]
        stop = data['structural_invalidation'] - data['atr_buffer'] - data['execution_buffer']
        cost = data['planned_cost_per_unit']
        data.setdefault('planned_after_cost_r', (min(data['target_zones']) - entry - cost) / (entry - stop + cost))
    else:
        data.setdefault('planned_after_cost_r', 1.0)
    return Opportunity(**data)


def decision(**updates):
    return decide(**(dict(symbol='BTCUSDT', decision_ms=NOW, trigger_close_ms=TRIGGER,
                         bars=bars()) | updates))


@pytest.mark.parametrize('identity', RETIRED)
def test_old_strategy_cannot_activate_through_config_registry_or_cli(identity, tmp_path):
    with pytest.raises(ValueError):
        StrategyConfig(id=identity)
    with pytest.raises(ValueError):
        PlatformConfig(strategies=[{'id': identity}])
    file = tmp_path / 'old.yaml'
    file.write_text('strategies:\n- id: ' + identity + '\n')
    with pytest.raises(ValueError):
        load_config(file)
    with pytest.raises(ValueError):
        register(StrategyDefinition(identity, '1', 'old', (), 'old'))
    with pytest.raises(SystemExit) as error:
        main(['strategies', 'inspect', identity])
    assert error.value.code == 2
    assert identity not in REGISTRY


@pytest.mark.parametrize('command', ['canary', 'selector', 'bridge', 'positions', 'train', 'research',
                                      'backtest', 'scan', 'signal', 'microstructure', 'collect', 'orders'])
def test_old_dispatch_is_not_available(command):
    with pytest.raises(SystemExit) as error:
        main([command])
    assert error.value.code == 2
    with pytest.raises(ValueError, match='COMMAND_OUT_OF_ACTIVE_SCOPE'):
        execute(Namespace(command=command))


def test_registry_is_frozen_even_for_plugins_named_s1():
    assert list(REGISTRY) == ['trend_pullback']
    with pytest.raises(TypeError):
        REGISTRY['sweep_reclaim'] = REGISTRY['trend_pullback']
    with pytest.raises(ValueError, match='FROZEN'):
        register(REGISTRY['trend_pullback'], lambda *args: 'LONG')
    unsafe = StrategyConfig.model_construct(id='sweep_reclaim')
    with pytest.raises(ValueError, match='OUT_OF_ACTIVE_SCOPE'):
        evaluate(None, None, 0, unsafe, PlatformConfig())
    assert evaluate(None, None, 0, StrategyConfig(id='trend_pullback'), PlatformConfig()) is None


@pytest.mark.parametrize('interval', [60, 180, 300, 900, 3600])
def test_short_or_confirmation_timeframe_cannot_become_decision_default(interval):
    with pytest.raises(ValueError):
        PlatformConfig(interval_seconds=interval)


@pytest.mark.parametrize('extra', [{'enabled': ['sweep_reclaim']}, {'playbooks': ['R17']},
                                   {'strategies': [{'id': 'breakout_retest', 'validated': True}]},
                                   {'product': {'native_acquisition': True}},
                                   {'product': {'notifications': True}}, {'risk': {'leverage': 2}},
                                   {'factors': [{'id': 'LIQUIDATION_SHOCK'}]}])
def test_old_config_switches_and_unvalidated_challengers_fail_closed(extra):
    with pytest.raises(ValueError):
        PlatformConfig(**extra)


def test_executable_default_and_native_api_scope():
    config = load_config(ROOT / 'configs/trend_pullback.yaml')
    assert config.interval_seconds == PlatformConfig().interval_seconds == 14400
    assert config.product.market_timeframes == ('1H', '4H', '1D')
    assert config.product.decision_timeframes == ('4H', '1D')
    assert config.product.review_hours_utc == (0, 12)
    assert config.strategies[0].id == 'trend_pullback'
    assert config.entry.expiry_minutes == 1440
    with pytest.raises(RuntimeError, match='OUT_OF_ACTIVE_SCOPE'):
        api.create_app()
    assert not config.product.orders and not config.product.native_acquisition
    assert not config.product.notifications and not config.product.private_accounts


def test_review_schedule_cannot_become_continuous_or_irregular_supervision():
    assert SwingPolicy().next_review(NOW) == TRIGGER + 12 * INTERVALS['1H']
    assert SwingPolicy(review_hours_utc=(12,)).next_review(NOW) == TRIGGER + DAY
    for hours in [(0, 1), (0, 6, 12), (), (24,), (True,)]:
        with pytest.raises(ValueError):
            SwingPolicy(review_hours_utc=hours)


def test_missing_data_is_explicit_no_setup_without_fake_economics():
    snapshot = decision(bars=[])
    assert snapshot.state is State.DATA_UNAVAILABLE
    assert snapshot.setup_status == 'NO_SETUP' and snapshot.opportunity is None
    assert snapshot.actionability == 'NOT_ACTIONABLE'
    encoded = snapshot.model_dump_json()
    assert not any(x in encoded for x in ['"fill"', '"pnl"', '"alpha"', '"orders"'])
    assert not snapshot.source_qualified and not snapshot.shadow_qualified


def test_completed_dual_timeframe_data_does_not_fabricate_setup():
    snapshot = decision()
    assert snapshot.state is State.NO_SETUP
    assert snapshot.opportunity is None
    # No 1H input is needed for the review contract.
    assert {b.candle.interval for b in bars()} == {'4H', '1D'}


@pytest.mark.parametrize('fault', ['open', 'future', 'gap', 'duplicate', 'stale', 'late',
                                   'wrong_symbol', 'availability_mismatch', 'wrong_boundary', 'missing_daily'])
def test_inadmissible_candles_never_drive_positive_review(fault):
    from dataclasses import replace

    values = bars()
    bar = values[59]
    if fault == 'open':
        values[59] = bar.model_copy(update={'candle': replace(bar.candle, closed=False)})
    elif fault == 'future':
        values[59] = bar.model_copy(update={'durable_ms': NOW + 1})
    elif fault == 'gap':
        del values[20]
    elif fault == 'duplicate':
        values.insert(30, values[30])
    elif fault == 'stale':
        values = bars(TRIGGER - INTERVALS['4H'])
    elif fault == 'late':
        old = values[0]
        at = old.end_ms + 300_001
        values[0] = old.model_copy(update={'candle': replace(old.candle, available_at_ms=at),
                                         'available_ms': at, 'durable_ms': at + 1})
    elif fault == 'wrong_symbol':
        values[59] = bar.model_copy(update={'candle': replace(bar.candle, symbol='ETHUSDT')})
    elif fault == 'availability_mismatch':
        values[59] = bar.model_copy(update={'available_ms': bar.available_ms + 1})
    elif fault == 'wrong_boundary':
        values[59] = bar.model_copy(update={'candle': replace(bar.candle, open_time_ms=bar.candle.open_time_ms + 1)})
    elif fault == 'missing_daily':
        values = values[:60]
    result = decision(bars=values, opportunity=opportunity())
    assert result.state is State.DATA_UNAVAILABLE
    assert result.actionability == 'NOT_ACTIONABLE'


def test_one_hour_trigger_or_unprocessed_new_bar_cannot_be_actionable():
    result = decision(trigger_close_ms=TRIGGER + INTERVALS['1H'], decision_ms=NOW + INTERVALS['1H'])
    assert result.state is State.DATA_UNAVAILABLE
    later = view(decision(opportunity=opportunity()).model_dump(mode='json'),
                 now_ms=NOW + INTERVALS['4H'])
    assert later['state'] == 'DATA_UNAVAILABLE' and later['actionability'] == 'NOT_ACTIONABLE'


@pytest.mark.parametrize('expires', [TRIGGER + 4 * INTERVALS['1H'], TRIGGER + 12 * INTERVALS['1H']])
def test_expiry_at_or_before_next_review_is_not_actionable_even_before_expiry(expires):
    result = decision(opportunity=opportunity(expires_ms=expires, review_deadline_ms=expires))
    assert NOW < expires
    assert result.state is State.EXPIRED
    assert result.actionability == 'NOT_ACTIONABLE'


def test_deadline_before_next_review_expires_with_longer_nominal_ttl():
    result = decision(opportunity=opportunity(review_deadline_ms=TRIGGER + INTERVALS['1H']))
    assert result.state is State.EXPIRED


@pytest.mark.parametrize('account, expected', [('UNKNOWN', State.ACCOUNT_UNKNOWN), ('VETO', State.VETO),
                                               ('NOT_REQUESTED', State.ENTRY_ZONE_ACTIVE)])
def test_account_veto_and_review_only_semantics(account, expected):
    result = decision(opportunity=opportunity(account_status=account))
    assert result.state is expected
    assert not result.source_qualified
    assert result.evidence_tier == 'OFFLINE_CONTRACT_ONLY'


def test_no_chase_and_conservative_invalidation_do_not_claim_fill_or_win():
    result = decision(opportunity=opportunity(entry_region=(96.0, 98.0)))
    assert result.state is State.MISSED_OR_NO_CHASE
    # Both a target and stop may be crossed in this bar. Never infer target-first profit.
    from dataclasses import replace
    values = bars()
    values[59] = values[59].model_copy(update={'candle': replace(values[59].candle, low=80, high=140)})
    result = decision(bars=values, opportunity=opportunity())
    assert result.state is State.INVALIDATED
    assert result.actionability == 'NOT_ACTIONABLE'
    assert 'pnl' not in result.model_dump()


def test_preobservable_structure_and_unsupported_opportunity_rejected():
    for update in [{'strategy': 'S3'}, {'structural_observed_ms': TRIGGER + 1},
                   {'setup_close_ms': TRIGGER + INTERVALS['1H']}, {'atr_buffer': 0.0},
                   {'entry_region': (101.0, 99.0)}, {'target_zones': ()}]:
        with pytest.raises(ValueError):
            opportunity(**update)


def test_planned_payoff_cannot_be_inflated_without_geometry_or_cost_change():
    with pytest.raises(ValueError, match='PLANNED_R'):
        opportunity(planned_after_cost_r=4.0)


def test_store_replay_revisions_stale_decisions_and_restart(tmp_path):
    path = tmp_path / 'decisions.sqlite'
    store = DecisionStore(path)
    original = decision()
    digest = store.append(original)
    assert store.append(original) == digest
    restarted = DecisionStore(path)
    assert restarted.latest('BTCUSDT') == original
    with pytest.raises(ValueError, match='REVISION'):
        restarted.append(decision(source_blocked=True))
    old = decision(trigger_close_ms=TRIGGER - INTERVALS['4H'], decision_ms=NOW - INTERVALS['4H'],
                   bars=bars(TRIGGER - INTERVALS['4H']))
    with pytest.raises(ValueError, match='STALE'):
        restarted.append(old)
    assert DecisionStore(path).latest('BTCUSDT') == original
    with restarted.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM swing_decisions').fetchone()[0] == 1
        db.execute("UPDATE swing_decisions SET digest='tampered'")
    with pytest.raises(ValueError, match='DIGEST'):
        restarted.latest('BTCUSDT')


def test_invalid_constructed_snapshot_cannot_bypass_persistence_validation(tmp_path):
    unsafe = decision().model_copy(update={'state': State.ENTRY_ZONE_ACTIVE, 'actionability': 'REVIEW_ONLY'})
    with pytest.raises(ValueError):
        DecisionStore(tmp_path / 'invalid.sqlite').append(unsafe)


def test_imported_snapshot_cannot_bypass_account_veto():
    valid = decision(opportunity=opportunity()).model_dump(mode='json')
    valid['opportunity']['account_status'] = 'VETO'
    with pytest.raises(ValueError, match='ACCOUNT_UNKNOWN_OR_VETO'):
        view(valid, now_ms=NOW)


def test_legacy_default_models_and_playbook_modules_cannot_dispatch():
    import importlib
    from btc_quant_agent.market_watch.config import MarketWatchConfig

    with pytest.raises(ValueError):
        PlatformConfig.model_validate(MarketWatchConfig())
    for module in ['platform.selection.cli', 'platform.bridge.cli', 'market_watch.playbooks',
                   'market_watch.service', 'execution.service', 'notify.feishu', 'data.collector']:
        with pytest.raises(ModuleNotFoundError):
            importlib.import_module('btc_quant_agent.' + module)


@pytest.mark.parametrize('side', ['LONG', 'SHORT', None])
def test_inherited_s1_ema_condition_is_retained_but_never_a_compiled_trade(side):
    from types import SimpleNamespace
    import pandas as pd
    from btc_quant_agent.platform.strategies import direction

    current, fast, slow = (103, 102, 101) if side == 'LONG' else (97, 98, 99) if side == 'SHORT' else (100, 100, 100)
    frame = pd.DataFrame({'close': [100]*41+[current], 'low': [min(current, fast)-1]*42,
                          'high': [max(current, fast)+1]*42})
    pipeline = SimpleNamespace(frames={'BTCUSDT': frame},
                               result=lambda symbol, feature, index, clock, params:
                               SimpleNamespace(value=fast if params['period'] == 10 else slow))
    candle = SimpleNamespace(closed=True, interval='4H', available_at_ms=TRIGGER+10,
                             close_time_ms=TRIGGER-1)
    event = SimpleNamespace(candle=candle, decision_ts=NOW, spec=SimpleNamespace(symbol='BTCUSDT'))
    settings = StrategyConfig(id='trend_pullback')
    assert direction(pipeline, event, 41, settings) == side
    candle.interval = '1H'
    assert direction(pipeline, event, 41, settings) is None
    assert evaluate(pipeline, event, 41, settings, PlatformConfig()) is None


@pytest.mark.parametrize('legacy, expected', [('ARMED', 'WATCH'), ('ENTRY_ELIGIBLE', 'WATCH'),
                                            ('WATCH', 'WATCH'), ('CANCELED', 'INVALIDATED'),
                                            ('CANCELLED', 'INVALIDATED'), ('EXPIRED', 'EXPIRED'),
                                            ('UNRECOGNIZED', 'SOURCE_BLOCKED')])
def test_historical_state_migration_preserves_input_and_never_reactivates(legacy, expected):
    raw = {'status': legacy, 'schema_version': 'L4_LONGHORIZON_SNAPSHOT_V1', 'arbitrary': {'old': True}}
    prior = copy.deepcopy(raw)
    result = view(raw, now_ms=NOW)
    assert raw == prior
    assert result['legacy_state'] == legacy and result['state'] == expected
    assert result['scope'].startswith('HISTORICAL_FROZEN')
    assert result['actionability'] == 'NOT_ACTIONABLE'
    with pytest.raises(ValidationError):
        AdvisorySnapshot.model_validate_json(json.dumps(decision().model_dump(mode='json') | {'state': 'ARMED'}))


def test_dashboard_reuses_renderer_and_escapes_historical_content():
    rendered = page({'status': '<script>alert(1)</script>'}, now_ms=NOW)
    assert 'HISTORICAL_FROZEN' in rendered and 'NOT_ACTIONABLE' in rendered
    assert 'completed 4H and 1D' in rendered
    assert '<script>' not in rendered and 'fetch(' not in rendered
    assert 'POST' not in rendered and '<button' not in rendered
    active = decision(opportunity=opportunity())
    assert view(active.model_dump(mode='json'), now_ms=TRIGGER + 3 * DAY)['state'] == 'EXPIRED'


def test_empty_dashboard_is_current_swing_data_unavailable():
    rendered = page(now_ms=NOW)
    assert 'OFFLINE_SWING_CONTRACT' in rendered and 'DATA_UNAVAILABLE' in rendered
    assert 'NO_SETUP' in rendered and 'HISTORICAL_FROZEN' not in rendered


def test_unchanged_frozen_source_guards_and_sticky_fifty_ms_stop():
    from btc_quant_agent.platform.canary.clock_domain import ClockEpoch, WALL_STEP_MS

    # B's frozen controller baseline and preservation ledger live at the product
    # root; the legacy A publication baseline is intentionally not copied here.
    assert WALL_STEP_MS == 50
    clock = ClockEpoch('fabricated-test')
    sync = {'status': 'SYNC_OBSERVED', 'uncertainty_ms': 0, 'sample_mono_ms': 1000}
    assert clock.capture(TRIGGER, 1000, 1000, sync)['epoch_valid']
    stepped = clock.capture(TRIGGER + 151, 1100, 1100, sync | {'sample_mono_ms': 1100})
    assert not stepped['epoch_valid']
    recovered_wall = clock.capture(TRIGGER + 200, 1200, 1200, sync | {'sample_mono_ms': 1200})
    assert not recovered_wall['epoch_valid']
    gate = json.loads((ROOT / 'contracts/low_rate_source_gate.json').read_text())
    assert gate['retained_invariants']['BBO_queue_hard_stop'] == 128
    assert gate['retained_invariants']['TLS_CERT_REQUIRED_and_hostname'] is True
    assert gate['retained_invariants']['per_frame_durable_accounting'] is True
