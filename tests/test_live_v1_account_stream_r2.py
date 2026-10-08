from __future__ import annotations

import asyncio
import threading

from btc_quant_agent.account_watch import AccountStore, AccountWatch
from btc_quant_agent.config import ExecutionConfig

NOW = 1_700_000_000_000


class FakeSignedClient:
    authority = type("Authority", (), {
        "environment": "TESTNET",
        "credential_namespace": "BINANCE_TESTNET",
        "rest_base_url": "https://testnet.binancefuture.com",
    })()

    def __init__(self):
        self.started = self.kept = self.closed = 0

    def start_user_stream(self):
        self.started += 1
        return "fake-listen-key"

    def keepalive_user_stream(self, listen_key):
        assert listen_key == "fake-listen-key"
        self.kept += 1

    def close_user_stream(self, listen_key):
        assert listen_key == "fake-listen-key"
        self.closed += 1

    def account_information(self):
        return {"totalWalletBalance": "1000", "totalMarginBalance": "1000",
                "availableBalance": "900", "totalInitialMargin": "100"}

    def balances(self):
        return [{"asset": "USDT", "balance": "1000"}]

    def positions(self):
        return []

    def open_orders(self):
        return []

    def realized_pnl(self, _start):
        return 0.0


def make_watch(tmp_path, client=None):
    return AccountWatch(ExecutionConfig(mode="testnet"), AccountStore(tmp_path / "live.db"),
                        signed_client=client or FakeSignedClient(), clock_ms=lambda: NOW)


def test_restart_restores_account_as_unreconciled(tmp_path):
    first = make_watch(tmp_path)
    first.reconcile_rest(NOW)
    restarted = make_watch(tmp_path)
    assert restarted.latest_snapshot() is not None
    assert restarted.latest_snapshot().reconciled is False
    assert restarted.latest_snapshot().quality == "STALE"


def test_user_event_requires_fresh_rest_baseline_and_monotonic_exchange_time(tmp_path):
    watch = make_watch(tmp_path)
    payload = {"e": "ORDER_TRADE_UPDATE", "E": NOW + 1, "T": NOW + 1,
               "o": {"s": "BTCUSDT", "i": 7, "c": "client-7", "S": "BUY",
                     "X": "NEW", "o": "LIMIT", "q": "0.2", "z": "0",
                     "p": "60000", "ap": "0", "R": False, "sp": "0"}}
    watch.handle_user_event(payload, NOW + 2)
    assert not watch.is_reconciled
    watch.reconcile_rest(NOW)
    assert watch.handle_user_event(payload, NOW + 2)
    assert watch.latest_snapshot().orders[0].order_id == "7"
    assert not watch.handle_user_event({**payload, "E": NOW}, NOW + 3)
    assert not watch.is_reconciled


def test_account_update_applies_signed_position_balance_and_order_terminal_state(tmp_path):
    watch = make_watch(tmp_path)
    watch.reconcile_rest(NOW)
    event = {"e": "ACCOUNT_UPDATE", "E": NOW + 10, "T": NOW + 10,
             "a": {"B": [{"a": "USDT", "wb": "950", "cw": "900"}],
                   "P": [{"s": "BTCUSDT", "pa": "-0.1", "ep": "60000",
                          "up": "-5", "mt": "isolated", "iw": "50"}]}}
    assert watch.handle_user_event(event, NOW + 11)
    snap = watch.latest_snapshot()
    assert snap.wallet_balance_usdt == 950
    assert snap.positions[0].quantity == -0.1
    order_event = {"e": "ORDER_TRADE_UPDATE", "E": NOW + 12, "T": NOW + 12,
                   "o": {"s": "BTCUSDT", "i": 7, "c": "client-7", "S": "SELL",
                         "X": "CANCELED", "o": "LIMIT", "q": "0.1", "z": "0",
                         "p": "60000", "ap": "0", "R": True, "sp": "0"}}
    assert watch.handle_user_event(order_event, NOW + 13)
    assert watch.latest_snapshot().orders[0].status == "CANCELED"
    watch.latest_snapshot().verify()


def test_user_stream_uses_allowlisted_testnet_url_and_closes_listen_key(tmp_path):
    client = FakeSignedClient()
    urls = []

    class Socket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        def __aiter__(self):
            async def messages():
                if False:
                    yield ""
            return messages()

    def connect(url, **_kwargs):
        urls.append(url)
        watch._stop_event.set()
        return Socket()

    watch = AccountWatch(ExecutionConfig(mode="testnet"), AccountStore(tmp_path / "stream.db"),
                         signed_client=client, clock_ms=lambda: NOW,
                         websocket_connect=connect)
    watch.reconcile_rest(NOW)
    asyncio.run(asyncio.wait_for(watch.run_user_stream(), timeout=2))
    assert urls and urls[0].startswith("wss://stream.binancefuture.com/ws/")
    assert client.started == 1 and client.closed == 1
    assert watch._keepalive_task is None
    assert "fake-listen-key" not in watch.latest_snapshot().canonical_json()


def test_equal_event_time_accepts_distinct_account_and_order_updates_once(tmp_path):
    watch = make_watch(tmp_path)
    watch.reconcile_rest(NOW)
    account = {"e": "ACCOUNT_UPDATE", "E": NOW + 10, "T": NOW + 10,
               "a": {"B": [{"a": "USDT", "wb": "950", "cw": "900"}], "P": []}}
    order = {"e": "ORDER_TRADE_UPDATE", "E": NOW + 10, "T": NOW + 10,
             "o": {"s": "BTCUSDT", "i": 7, "c": "client-7", "S": "BUY",
                   "X": "PARTIALLY_FILLED", "o": "LIMIT", "q": "0.2", "z": "0.1",
                   "p": "60000", "ap": "60000", "R": False, "sp": "0"}}
    assert watch.handle_user_event(account, NOW + 11)
    assert watch.handle_user_event(order, NOW + 11)
    snap = watch.latest_snapshot()
    assert snap.wallet_balance_usdt == 950
    assert snap.orders[0].filled_quantity == 0.1
    assert snap.observed_at_ms == NOW + 10
    assert not watch.handle_user_event(account, NOW + 12)
    assert watch.is_reconciled
    assert snap.snapshot_hash == watch.latest_snapshot().snapshot_hash


def test_equal_event_time_conflicting_order_update_fails_closed(tmp_path):
    watch = make_watch(tmp_path)
    watch.reconcile_rest(NOW)
    order = {"e": "ORDER_TRADE_UPDATE", "E": NOW + 10, "T": NOW + 10,
             "o": {"s": "BTCUSDT", "i": 7, "c": "client-7", "S": "BUY",
                   "X": "NEW", "o": "LIMIT", "q": "0.2", "z": "0",
                   "p": "60000", "ap": "0", "R": False, "sp": "0"}}
    assert watch.handle_user_event(order, NOW + 11)
    conflicting = {**order, "o": {**order["o"], "z": "0.1"}}
    assert not watch.handle_user_event(conflicting, NOW + 12)
    assert not watch.is_reconciled
    assert watch.latest_snapshot().orders[0].filled_quantity == 0


def test_order_fill_larger_than_requested_fails_closed(tmp_path):
    watch = make_watch(tmp_path)
    watch.reconcile_rest(NOW)
    order = {"e": "ORDER_TRADE_UPDATE", "E": NOW + 10, "T": NOW + 10,
             "o": {"s": "BTCUSDT", "i": 7, "c": "client-7", "S": "BUY",
                   "X": "FILLED", "o": "LIMIT", "q": "0.2", "z": "0.3",
                   "p": "60000", "ap": "60000", "R": False, "sp": "0"}}
    assert not watch.handle_user_event(order, NOW + 11)
    assert not watch.is_reconciled
    assert not watch.latest_snapshot().orders


def test_rest_inflight_ws_update_preserved_and_conflict_persisted(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class BlockingClient(FakeSignedClient):
        def account_information(self):
            entered.set()
            assert release.wait(2)
            return super().account_information()

    watch = make_watch(tmp_path, BlockingClient())
    release.set()
    watch.reconcile_rest(NOW)
    release.clear()
    entered.clear()

    async def scenario():
        task = asyncio.create_task(asyncio.to_thread(watch.reconcile_rest, NOW + 20))
        assert await asyncio.to_thread(entered.wait, 2)
        update = {"e": "ACCOUNT_UPDATE", "E": NOW + 10, "T": NOW + 10,
                  "a": {"B": [{"a": "USDT", "wb": "950", "cw": "900"}], "P": []}}
        assert watch.handle_user_event(update, NOW + 11)
        release.set()
        return await task

    result = asyncio.run(scenario())
    assert not result.reconciled
    assert result.quality == "CONFLICT"
    assert result.wallet_balance_usdt == 950
    assert watch.store.latest(watch.account_id).wallet_balance_usdt == 950


def test_cancelled_rest_loop_waits_for_inflight_rest_before_final_stale(tmp_path):
    entered, release = threading.Event(), threading.Event()

    class BlockingClient(FakeSignedClient):
        def account_information(self):
            entered.set()
            assert release.wait(2)
            return super().account_information()

    watch = make_watch(tmp_path, BlockingClient())
    release.set()
    watch.reconcile_rest(NOW)
    release.clear()
    entered.clear()

    async def scenario():
        task = asyncio.create_task(watch.run_reconciliation_loop())
        assert await asyncio.to_thread(entered.wait, 2)
        watch.stop()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(scenario())
    assert watch.store.latest(watch.account_id).quality == "STALE"
