"""Adversarial tests for PreExecutionValidator safety gates."""

from __future__ import annotations

from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_intent import setup_approved_state

from btc_quant_agent.account_watch import PositionV1
from btc_quant_agent.execution.intents import IntentStore, build_trade_intent
from btc_quant_agent.execution.validator import PreExecutionValidator
from btc_quant_agent.live_market.models import MarketObservationV1
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch
from btc_quant_agent.position_supervisor.models import KillObservationV1

NOW = 1_700_000_000_000


def sample_market_obs(**overrides) -> MarketObservationV1:
    values = {
        "symbol": "BTCUSDT",
        "mark_price": 100.0,
        "best_bid": 99.98,
        "best_ask": 100.02,
        "kline_1m_close": 100.0,
        "kline_1m_open_time_ms": NOW - 60_000,
        "kline_1m_close_time_ms": NOW,
        "source_timestamp_ms": NOW,
        "receipt_timestamp_ms": NOW,
        "spread_bps": 4.0,
    }
    values.update(overrides)
    return MarketObservationV1.build(**values)


def setup_validator_and_intent(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)

    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )

    intent_store = IntentStore(tmp_path / "live.db")
    intent_store.save_intent(intent)

    kill_switch = KillSwitch(tmp_path / "live.db")
    validator = PreExecutionValidator(
        live_store=store,
        intent_store=intent_store,
        kill_switch=kill_switch,
        max_market_staleness_ms=10_000,
        max_account_staleness_ms=60_000,
        max_spread_bps=10.0,
        max_price_drift_bps=50.0,
    )

    return validator, intent, snapshot, kill_switch


def test_validator_passes_when_all_conditions_healthy(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    market_obs = sample_market_obs(mark_price=intent.price)

    result = validator.validate(intent, market_obs, snapshot, NOW)
    assert result.is_valid
    assert result.reason == "OK"


def test_validator_blocks_on_price_drift(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    # 5% price drift (500 bps) far exceeds 50 bps limit
    market_obs = sample_market_obs(mark_price=intent.price * 1.05)

    result = validator.validate(intent, market_obs, snapshot, NOW)
    assert not result.is_valid
    assert result.reason == "PRICE_DRIFT_EXCEEDED"


def test_validator_blocks_on_stale_market_data(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    # Market data is 20s old (> 10s max staleness)
    market_obs = sample_market_obs(mark_price=intent.price, receipt_timestamp_ms=NOW - 20_000)

    result = validator.validate(intent, market_obs, snapshot, NOW)
    assert not result.is_valid
    assert result.reason == "MARKET_DATA_STALE"


def test_validator_blocks_on_stale_account_snapshot(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    # Set validator max_account_staleness_ms to 20s so we can test before intent expires at 60s
    validator.max_account_staleness_ms = 20_000
    market_obs = sample_market_obs(mark_price=intent.price, receipt_timestamp_ms=NOW + 30_000)

    # Validating at NOW + 30_000: intent still valid (< 60s), but snapshot (observed at NOW) is 30s old (> 20s)
    result = validator.validate(intent, market_obs, snapshot, NOW + 30_000)
    assert not result.is_valid
    assert result.reason == "ACCOUNT_SNAPSHOT_STALE"


def test_validator_blocks_on_insufficient_margin(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    broke_snapshot = sample_snapshot(
        available_balance_usdt=0.01,
        observed_at_ms=NOW,
        last_rest_at_ms=NOW,
    )
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=broke_snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    intent_store = IntentStore(tmp_path / "live.db")
    intent_store.save_intent(intent)

    validator = PreExecutionValidator(
        live_store=store,
        intent_store=intent_store,
        kill_switch=KillSwitch(tmp_path / "live.db"),
    )
    market_obs = sample_market_obs(mark_price=intent.price)

    result = validator.validate(intent, market_obs, broke_snapshot, NOW)
    assert not result.is_valid
    assert result.reason == "INSUFFICIENT_MARGIN"


def test_validator_blocks_on_opposing_position(tmp_path):
    store, case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    opposing_position = PositionV1(
        symbol=case.symbol,
        quantity=-0.5,
        entry_price=100.0,
        mark_price=100.0,
        unrealized_pnl_usdt=0.0,
        leverage=10,
        liquidation_price=None,
        margin_type="ISOLATED",
        observed_at_ms=NOW,
    )
    opposing_snapshot = sample_snapshot(
        positions=(opposing_position,),
        observed_at_ms=NOW,
        last_rest_at_ms=NOW,
    )
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=opposing_snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    intent_store = IntentStore(tmp_path / "live.db")
    intent_store.save_intent(intent)

    validator = PreExecutionValidator(
        live_store=store,
        intent_store=intent_store,
        kill_switch=KillSwitch(tmp_path / "live.db"),
    )
    market_obs = sample_market_obs(mark_price=intent.price)

    result = validator.validate(intent, market_obs, opposing_snapshot, NOW)
    assert not result.is_valid
    assert result.reason == "CONFLICTING_POSITION_EXISTS"


def test_validator_blocks_when_kill_switch_active(tmp_path):
    validator, intent, snapshot, kill_switch = setup_validator_and_intent(tmp_path)
    market_obs = sample_market_obs(mark_price=intent.price)

    # Trip kill switch via excessive daily loss
    kill_switch.evaluate(
        KillObservationV1(
            account_snapshot_hash=snapshot.snapshot_hash,
            environment="TESTNET",
            credential_namespace="TESTNET",
            rest_url="https://testnet.binancefuture.com",
            observed_at_ms=NOW,
            last_reconciled_at_ms=NOW,
            reconciled=True,
            equity_usdt=1000.0,
            daily_loss_usdt=50.0,  # exceeds cap
            drawdown_pct=0.0,
            order_conflicts=0,
        ),
        NOW,
    )

    result = validator.validate(intent, market_obs, snapshot, NOW)
    assert not result.is_valid
    assert result.reason == "KILL_SWITCH_ACTIVE"
