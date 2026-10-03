"""Adversarial tests for PreExecutionValidator safety gates."""

from __future__ import annotations

from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_intent import setup_approved_state

from btc_quant_agent.account_watch import OrderV1, PositionV1
from btc_quant_agent.execution.intents import IntentStore, TradeIntentV1, build_trade_intent
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
        "mark_source_timestamp_ms": NOW,
        "mark_receipt_timestamp_ms": NOW,
        "book_source_timestamp_ms": NOW,
        "book_receipt_timestamp_ms": NOW,
        "kline_source_timestamp_ms": NOW,
        "kline_receipt_timestamp_ms": NOW,
        "stream_connected": True,
        "spread_bps": 4.0,
    }
    for component in ("mark", "book", "kline"):
        for kind in ("source", "receipt"):
            key = f"{kind}_timestamp_ms"
            component_key = f"{component}_{key}"
            if key in overrides and component_key not in overrides:
                values[component_key] = overrides[key]
    values.update(overrides)
    return MarketObservationV1.build(**values)


def setup_validator_and_intent(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW, positions=(), orders=())

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
        tactical_validity_provider=lambda _sym, _now: True,
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
        positions=(),
        orders=(),
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
        tactical_validity_provider=lambda _sym, _now: True,
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
        tactical_validity_provider=lambda _sym, _now: True,
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


def test_r1_03_active_proposal_required(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    market_obs = sample_market_obs(mark_price=intent.price)

    # Invalidate active proposal in DB for that case so it no longer matches intent.proposal_hash
    with validator.live_store._connection() as db:
        db.execute("UPDATE live_cases SET active_proposal_hash=NULL WHERE case_id=?", (intent.case_id,))

    result = validator.validate(intent, market_obs, snapshot, NOW)
    assert not result.is_valid
    assert result.reason in {"PROPOSAL_NOT_ACTIVE", "PROPOSAL_HASH_MISMATCH"}


def test_r1_03_approval_actor_or_hash_mismatch(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    market_obs = sample_market_obs(mark_price=intent.price)

    # Tamper with approval_actor
    tampered_actor = intent.model_copy(update={"approval_actor": "evil_actor", "intent_hash": ""})
    tampered_actor_intent = TradeIntentV1.build(**tampered_actor.model_dump(exclude={"intent_hash"}))
    res1 = validator.validate(tampered_actor_intent, market_obs, snapshot, NOW)
    assert not res1.is_valid
    assert res1.reason == "APPROVAL_ACTOR_MISMATCH"

    # Tamper with approval_hash
    tampered_hash = intent.model_copy(update={"approval_hash": "0" * 64, "intent_hash": ""})
    tampered_hash_intent = TradeIntentV1.build(**tampered_hash.model_dump(exclude={"intent_hash"}))
    res2 = validator.validate(tampered_hash_intent, market_obs, snapshot, NOW)
    assert not res2.is_valid
    assert res2.reason == "APPROVAL_HASH_MISMATCH"


def test_r1_03_tactical_validity_unavailable_or_invalid(tmp_path):
    store, _case, proposal, event_id, _actor = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW, positions=(), orders=())
    intent = build_trade_intent(
        live_store=store,
        account_snapshot=snapshot,
        proposal_hash=proposal.proposal_hash,
        approval_event_id=event_id,
        now_ms=NOW,
    )
    intent_store = IntentStore(tmp_path / "live.db")
    intent_store.save_intent(intent)
    market_obs = sample_market_obs(mark_price=intent.price)

    # 1. No tactical provider for TESTNET intent -> unavailable
    v_none = PreExecutionValidator(
        live_store=store,
        intent_store=intent_store,
        kill_switch=KillSwitch(tmp_path / "live.db"),
        tactical_validity_provider=None,
    )
    res_none = v_none.validate(intent, market_obs, snapshot, NOW)
    assert not res_none.is_valid
    assert res_none.reason == "TACTICAL_VALIDITY_UNAVAILABLE"

    # 2. Tactical provider returns False -> invalid
    v_invalid = PreExecutionValidator(
        live_store=store,
        intent_store=intent_store,
        kill_switch=KillSwitch(tmp_path / "live.db"),
        tactical_validity_provider=lambda _sym, _now: False,
    )
    res_inv = v_invalid.validate(intent, market_obs, snapshot, NOW)
    assert not res_inv.is_valid
    assert res_inv.reason == "TACTICAL_VALIDITY_INVALID"


def test_r1_03_differing_account_snapshot_hash_allowed_if_fresh_and_safe(tmp_path):
    validator, intent, _snapshot, _ = setup_validator_and_intent(tmp_path)
    market_obs = sample_market_obs(mark_price=intent.price)

    # A newer account snapshot arrives with slightly changed equity and later timestamp
    # Note: snapshot_hash is DIFFERENT from intent.account_snapshot_hash
    newer_snapshot = sample_snapshot(
        observed_at_ms=NOW + 5_000,
        last_rest_at_ms=NOW + 5_000,
        equity_usdt=5200.0,
        available_balance_usdt=4700.0,
        positions=(),
        orders=(),
    )
    assert newer_snapshot.snapshot_hash != intent.account_snapshot_hash

    # Must pass because current snapshot is fresh, reconciled, and well within risk caps
    result = validator.validate(intent, market_obs, newer_snapshot, NOW + 5_000)
    assert result.is_valid
    assert result.reason == "OK"


def test_r1_03_open_order_conflict_fails_closed(tmp_path):
    validator, intent, _snapshot, _ = setup_validator_and_intent(tmp_path)
    market_obs = sample_market_obs(mark_price=intent.price)

    # Active open order in opposing direction (intent is BUY, order is SELL)
    conflicting_order = OrderV1(
        symbol=intent.symbol,
        order_id="999888",
        client_order_id="conflicting-cuid",
        side="SELL",
        status="NEW",
        order_type="LIMIT",
        quantity=0.1,
        filled_quantity=0.0,
        price=101.0,
        average_price=0.0,
        reduce_only=False,
        stop_price=None,
        observed_at_ms=NOW,
    )
    snapshot_with_conflicting_order = sample_snapshot(
        observed_at_ms=NOW,
        last_rest_at_ms=NOW,
        positions=(),
        orders=(conflicting_order,),
    )

    result = validator.validate(intent, market_obs, snapshot_with_conflicting_order, NOW)
    assert not result.is_valid
    assert result.reason == "OPEN_ORDER_CONFLICT"
