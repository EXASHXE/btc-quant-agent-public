from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
import sys

sys.path.insert(0, '/tmp/live-v1-b5-r3-independent-c2c7cc8/tests')
from test_live_v1_execution_authorization_r2 import authorized_backend
from test_live_v1_execution_validator import NOW, sample_market_obs
from test_live_v1_execution_placement_r3 import fresh_account
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.binance_signed import CredentialAuthority
from btc_quant_agent.execution.protection import ProtectionStore
from btc_quant_agent.live_db import connection


def fixture():
    tmp = TemporaryDirectory(prefix='b5-r3-probe-')
    backend, validator, intent, snapshot, client, receipt = authorized_backend(Path(tmp.name))
    clock = {'now': NOW}
    backend.clock_ms = lambda: clock['now']
    backend.account_provider = Mock(return_value=snapshot)
    backend.market_provider = Mock(return_value=sample_market_obs())
    return tmp, backend, validator, intent, snapshot, client, receipt, clock


def run(label, arrange, expected):
    tmp, backend, validator, intent, snapshot, client, receipt, clock = fixture()
    with tmp:
        arrange(backend, validator, intent, snapshot, client, receipt, clock)
        try:
            backend.submit_authorized(receipt.authorization_id, NOW - 10_000)
            result = 'PLACED'
        except Exception as exc:
            result = type(exc).__name__ + ':' + str(exc)
        placed = client.place_order.call_count
        print(f'{label}: result={result!r}; entry_calls={placed}; margin_calls={client.change_margin_type.call_count}; leverage_calls={client.change_leverage.call_count}')
        assert expected in result, (label, result)
        assert placed == 0, (label, placed)


run('expiry_during_leverage', lambda b,v,i,s,c,r,t: setattr(c.change_leverage, 'side_effect', lambda *_: t.update(now=r.expires_at_ms)), 'AUTHORIZATION_EXPIRED')
run('account_decline_after_setup', lambda b,v,i,s,c,r,t: setattr(b.account_provider, 'side_effect', [s, fresh_account(s, available_balance_usdt=0.0)]), 'INSUFFICIENT_MARGIN')
run('current_rest_not_current', lambda b,v,i,s,c,r,t: setattr(b.account_provider, 'return_value', fresh_account(s, last_rest_at_ms=NOW-1)), 'PLACEMENT_REST_SNAPSHOT_NOT_CURRENT')
run('current_account_wrong_namespace', lambda b,v,i,s,c,r,t: setattr(c, 'authority', CredentialAuthority('TESTNET','BINANCE_LIVE','https://testnet.binancefuture.com')), 'credential namespace mismatch')
run('stale_kline_fresh_mark_book', lambda b,v,i,s,c,r,t: setattr(b.market_provider, 'return_value', sample_market_obs(kline_source_timestamp_ms=NOW-20_000)), 'MARKET_KLINE_STALE')

with TemporaryDirectory(prefix='b5-r3-protection-') as path:
    tmp, backend, validator, intent, snapshot, client, receipt, clock = fixture()
    with tmp:
        backend.authorizations.claim(receipt, NOW)
        owner = backend.protections.reserve_owner(intent, NOW)
        client.positions.return_value = [{'symbol': intent.symbol, 'positionSide':'BOTH', 'positionAmt':'0.1'}]
        client.open_protective_orders.return_value = []
        client.place_protective_order.return_value = {'algoId': None}
        try:
            result = backend._reconcile_protective_stop(intent, 0.1, NOW)
        except Exception as exc:
            result = type(exc).__name__ + ':' + str(exc)
        print('null_protective_algo_id:', repr(result), 'owner=', backend.protections.get_owner(intent), 'kill=', backend.kill_switch.allows_new_risk())

tmp, backend, validator, intent, snapshot, client, receipt, clock = fixture()
with tmp:
    client.place_order.return_value = {
        'clientOrderId': intent.client_order_id, 'symbol': intent.symbol,
        'side': intent.side, 'orderId': 'entry-1', 'status': 'FILLED',
        'executedQty': str(intent.quantity), 'avgPrice': str(intent.price),
    }
    client.positions.return_value = [{'symbol': intent.symbol, 'positionSide': 'BOTH',
                                      'positionAmt': str(intent.quantity)}]
    client.place_protective_order.return_value = {'algoId': None}
    report = backend.submit_authorized(receipt.authorization_id, NOW - 10_000)
    with connection(backend.path) as db:
        rows = [dict(row) for row in db.execute('SELECT order_id,status,is_protective FROM live_execution_orders ORDER BY is_protective')]
    print('public_filled_null_stop:', report, 'owner=', backend.protections.get_owner(intent),
          'orders=', rows, 'kill=', backend.kill_switch.allows_new_risk(),
          'entry_calls=', client.place_order.call_count, 'stop_calls=', client.place_protective_order.call_count)
