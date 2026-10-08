"""Actual placement-time authority, forced REST and remaining risk budgets."""
from __future__ import annotations

from unittest.mock import Mock

import pytest
from test_live_v1_execution_authorization_r2 import authorized_backend
from test_live_v1_execution_validator import NOW, sample_market_obs, setup_validator_and_intent

from btc_quant_agent.account_watch.models import AccountSnapshotV1, PositionV1
from btc_quant_agent.execution.guard import ExecutionBlocked


def fresh_account(snapshot, **changes):
    values = snapshot.model_dump(exclude={"snapshot_hash"}) | changes
    if "drawdown_pct" in changes and "peak_equity_usdt" not in changes:
        values["peak_equity_usdt"] = values["equity_usdt"] / (1 - values["drawdown_pct"])
    return AccountSnapshotV1.build(**values)


def placement(tmp_path):
    backend, validator, intent, snapshot, client, receipt = authorized_backend(tmp_path)
    clock = {"now": NOW}
    backend.clock_ms = lambda: clock["now"]
    backend.account_provider = Mock(return_value=snapshot)
    backend.market_provider = Mock(return_value=sample_market_obs())
    return backend, validator, intent, snapshot, client, receipt, clock


def test_caller_old_timestamp_cannot_extend_receipt(tmp_path):
    backend, _, _, _, client, receipt, clock = placement(tmp_path)
    clock["now"] = receipt.expires_at_ms
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_EXPIRED"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.change_margin_type.assert_not_called()
    client.place_order.assert_not_called()


def test_expiry_during_setup_prevents_entry(tmp_path):
    backend, _, _, _, client, receipt, clock = placement(tmp_path)
    client.change_margin_type.side_effect = lambda *_: clock.update(now=receipt.expires_at_ms)
    with pytest.raises(ExecutionBlocked, match="AUTHORIZATION_EXPIRED"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()


def test_forced_account_rest_failure_prevents_all_mutations(tmp_path):
    backend, _, _, _, client, receipt, _ = placement(tmp_path)
    backend.account_provider.side_effect = RuntimeError("local REST read failed")
    with pytest.raises(ExecutionBlocked, match="ACCOUNT_RECONCILIATION_FAILED"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.change_margin_type.assert_not_called()
    client.change_leverage.assert_not_called()
    client.place_order.assert_not_called()


def test_account_change_during_setup_is_revalidated_before_entry(tmp_path):
    backend, _, _, snapshot, client, receipt, _ = placement(tmp_path)
    changed = fresh_account(snapshot, available_balance_usdt=0.01)
    backend.account_provider.side_effect = [snapshot, changed]
    with pytest.raises(ExecutionBlocked, match="INSUFFICIENT_MARGIN"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()


def test_fresh_account_position_conflict_blocks_new_risk(tmp_path):
    backend, _, _, snapshot, client, receipt, _ = placement(tmp_path)
    position = PositionV1(symbol="BTCUSDT", quantity=-0.01, entry_price=100.0,
                          mark_price=100.0, unrealized_pnl_usdt=0.0, leverage=2,
                          liquidation_price=None, margin_type="ISOLATED", observed_at_ms=NOW)
    backend.account_provider.return_value = fresh_account(snapshot, positions=(position,))
    with pytest.raises(ExecutionBlocked, match="CONFLICTING_POSITION_EXISTS"):
        backend.submit_authorized(receipt.authorization_id, NOW)
    client.place_order.assert_not_called()


def test_unchanged_forced_current_account_can_submit_once(tmp_path):
    backend, _, _, _, client, receipt, _ = placement(tmp_path)
    report = backend.submit_authorized(receipt.authorization_id, NOW)
    assert report.status == "NEW"
    assert backend.account_provider.call_count >= 2
    client.place_order.assert_called_once()


@pytest.mark.parametrize("changes,reason", [
    ({"daily_loss_usdt": 24.99}, "DAILY_LOSS_HEADROOM_EXCEEDED"),
    ({"drawdown_pct": 0.04999}, "DRAWDOWN_HEADROOM_EXCEEDED"),
])
def test_current_remaining_budget_bounds_old_approved_size(tmp_path, changes, reason):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    result = validator.validate(intent, sample_market_obs(), fresh_account(snapshot, **changes), NOW)
    assert not result.is_valid
    assert result.reason == reason


def test_daily_risk_exact_boundary_and_both_budgets_pass(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    worst_loss = intent.quantity * intent.price * (abs(intent.price-intent.stop_loss)/intent.price + 0.0013)
    current = fresh_account(snapshot, daily_loss_usdt=25.0-worst_loss, drawdown_pct=0.0)
    assert validator.validate(intent, sample_market_obs(), current, NOW).is_valid
    above = fresh_account(current, daily_loss_usdt=current.daily_loss_usdt+0.00001)
    assert validator.validate(intent, sample_market_obs(), above, NOW).reason == "DAILY_LOSS_HEADROOM_EXCEEDED"


def test_inconsistent_peak_equity_fails_closed(tmp_path):
    validator, intent, snapshot, _ = setup_validator_and_intent(tmp_path)
    current = fresh_account(snapshot, peak_equity_usdt=1.0)
    result = validator.validate(intent, sample_market_obs(), current, NOW)
    assert not result.is_valid
    assert result.reason == "ACCOUNT_EQUITY_INCONSISTENT"
