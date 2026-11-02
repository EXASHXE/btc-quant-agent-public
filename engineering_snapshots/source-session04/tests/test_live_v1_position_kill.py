from __future__ import annotations

from btc_quant_agent.position_supervisor import KillObservationV1, KillSwitch

NOW = 1_700_000_000_000


def state(**changes: object) -> KillObservationV1:
    values: dict[str, object] = {
        "account_snapshot_hash": "a" * 64, "environment": "TESTNET",
        "credential_namespace": "TESTNET", "rest_url": "https://testnet.binancefuture.com",
        "observed_at_ms": NOW, "last_reconciled_at_ms": NOW, "reconciled": True,
        "equity_usdt": 1000.0, "daily_loss_usdt": 0.0, "drawdown_pct": 0.0,
        "order_conflicts": 0, "protective_missing_since_ms": None,
    }
    values.update(changes)
    return KillObservationV1(**values)


def test_loss_and_drawdown_latch_across_restart(tmp_path):
    path = tmp_path / "live.db"
    switch = KillSwitch(path)
    reasons = switch.evaluate(state(daily_loss_usdt=30, drawdown_pct=0.1), NOW)
    assert {"DAILY_LOSS_CAP", "DRAWDOWN_CAP"} <= set(reasons)
    assert not KillSwitch(path).allows_new_risk()


def test_account_conflict_environment_and_missing_stop_kill(tmp_path):
    switch = KillSwitch(tmp_path / "live.db")
    reasons = switch.evaluate(state(
        last_reconciled_at_ms=NOW - 120_000, reconciled=False,
        order_conflicts=3, protective_missing_since_ms=NOW - 15_000,
        rest_url="https://fapi.binance.com",
    ), NOW)
    assert {"ACCOUNT_UNRECONCILED", "ORDER_STATE_CONFLICT",
            "WRONG_ENVIRONMENT", "PROTECTIVE_ORDER_MISSING"} <= set(reasons)
    assert not switch.allows_new_risk()
    assert switch.allows_risk_reducing("TESTNET")
    assert not switch.allows_risk_reducing("LIVE")
