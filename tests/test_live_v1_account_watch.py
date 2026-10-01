"""Tests for Live V1 AccountWatch, AccountSnapshotV1, and secret isolation."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from btc_quant_agent.account_watch import (
    AccountSnapshotV1,
    AccountStore,
    AccountWatch,
    OrderV1,
    PositionV1,
)
from btc_quant_agent.config import ExecutionConfig

NOW = 1_700_000_000_000


def sample_snapshot(**overrides) -> AccountSnapshotV1:
    values = {
        "account_id": "DEFAULT_TESTNET",
        "environment": "TESTNET",
        "credential_namespace": "BINANCE_TESTNET",
        "rest_base_url": "https://testnet.binancefuture.com",
        "observed_at_ms": NOW,
        "last_rest_at_ms": NOW,
        "stream_connected": True,
        "reconciled": True,
        "conflict_count": 0,
        "equity_usdt": 5000.0,
        "available_balance_usdt": 4500.0,
        "wallet_balance_usdt": 5000.0,
        "margin_used_usdt": 500.0,
        "daily_loss_usdt": 10.0,
        "drawdown_pct": 0.02,
        "peak_equity_usdt": 5100.0,
        "positions": (
            PositionV1(
                symbol="BTCUSDT",
                quantity=0.1,
                entry_price=60000.0,
                mark_price=60500.0,
                unrealized_pnl_usdt=50.0,
                leverage=10,
                liquidation_price=54000.0,
                margin_type="ISOLATED",
                observed_at_ms=NOW,
            ),
        ),
        "orders": (
            OrderV1(
                symbol="BTCUSDT",
                order_id="12345",
                client_order_id="bqa-order-1",
                side="BUY",
                status="NEW",
                order_type="LIMIT",
                quantity=0.1,
                filled_quantity=0.0,
                price=59000.0,
                average_price=0.0,
                reduce_only=False,
                stop_price=None,
                observed_at_ms=NOW,
            ),
        ),
        "quality": "OK",
    }
    values.update(overrides)
    return AccountSnapshotV1.build(**values)


def test_account_snapshot_build_verify_and_immutability():
    snap = sample_snapshot()
    snap.verify()
    assert snap.snapshot_hash
    assert snap.account_id == "DEFAULT_TESTNET"
    with pytest.raises(ValidationError):
        snap.equity_usdt = 6000.0  # frozen model


def test_account_snapshot_secret_isolation():
    snap = sample_snapshot()
    serialized = snap.canonical_json()
    raw = json.loads(serialized)
    # Ensure no API keys, secrets, or signatures exist in serialized snapshot
    forbidden_keys = {"api_key", "secret", "signature", "listen_key", "headers"}
    assert not (forbidden_keys & set(raw.keys()))
    assert "api_key" not in serialized.lower()
    assert "secret" not in serialized.lower()


def test_testnet_account_authority_mismatch_fails_closed():
    # TESTNET environment targeting LIVE url must fail closed
    with pytest.raises(ValueError, match="testnet account authority mismatch"):
        sample_snapshot(rest_base_url="https://fapi.binance.com")

    # TESTNET environment with wrong credential namespace must fail closed
    with pytest.raises(ValueError, match="testnet account authority mismatch"):
        sample_snapshot(credential_namespace="NONE")


def test_dry_run_account_authority():
    snap = AccountSnapshotV1.build(
        account_id="DRY_RUN_ACCT",
        environment="DRY_RUN",
        credential_namespace="NONE",
        rest_base_url="local://paper",
        observed_at_ms=NOW,
        last_rest_at_ms=NOW,
        stream_connected=True,
        reconciled=True,
        conflict_count=0,
        equity_usdt=1000.0,
        available_balance_usdt=1000.0,
        wallet_balance_usdt=1000.0,
        margin_used_usdt=0.0,
        daily_loss_usdt=0.0,
        drawdown_pct=0.0,
        peak_equity_usdt=1000.0,
        positions=(),
        orders=(),
        quality="OK",
    )
    snap.verify()
    assert snap.environment == "DRY_RUN"
    assert snap.credential_namespace == "NONE"


def test_account_watch_rest_reconciliation_and_storage(tmp_path):
    db_path = tmp_path / "live.db"
    store = AccountStore(db_path)
    cfg = ExecutionConfig(mode="paper")
    watch = AccountWatch(cfg, store, clock_ms=lambda: NOW)

    snap = watch.reconcile_rest()
    assert snap.environment == "DRY_RUN"
    assert snap.reconciled
    assert snap.quality == "OK"

    latest = store.latest("DEFAULT_ACCOUNT")
    assert latest is not None
    assert latest.snapshot_hash == snap.snapshot_hash


def test_user_stream_disconnect_marks_unreconciled(tmp_path):
    db_path = tmp_path / "live.db"
    store = AccountStore(db_path)
    cfg = ExecutionConfig(mode="paper")
    watch = AccountWatch(cfg, store, clock_ms=lambda: NOW)

    watch.reconcile_rest()
    assert watch.is_reconciled

    # Trigger stream disconnect
    watch.mark_stream_disconnected(NOW + 1000)
    assert not watch.is_reconciled
    assert not watch.is_stream_connected

    snap = watch.latest_snapshot()
    assert snap is not None
    assert not snap.reconciled
    assert snap.quality == "STALE"

    # Reconciling with REST repairs the state
    reconciled_snap = watch.reconcile_rest(NOW + 2000)
    assert reconciled_snap.reconciled
    assert reconciled_snap.quality == "OK"
    assert watch.is_reconciled
