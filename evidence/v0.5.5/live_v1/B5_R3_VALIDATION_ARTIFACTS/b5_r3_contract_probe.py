from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch
import sys

sys.path.insert(0, '/tmp/live-v1-b5-r3-independent-c2c7cc8/tests')
from test_live_v1_execution_authorization_r2 import authorized_backend
from test_live_v1_execution_validator import NOW, sample_market_obs
from test_live_v1_execution_placement_r3 import fresh_account

from btc_quant_agent.execution.binance_signed import BinanceSignedClient
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import TradeIntentV1, IntentStore
from btc_quant_agent.execution.authorization import AuthorizationStore
from btc_quant_agent.live_db import connection


def fixture():
    tmp = TemporaryDirectory(prefix='b5-r3-contract-')
    backend,validator,intent,snapshot,client,receipt = authorized_backend(Path(tmp.name))
    backend.clock_ms = lambda: NOW
    backend.account_provider = Mock(return_value=snapshot)
    backend.market_provider = Mock(return_value=sample_market_obs())
    return tmp,backend,validator,intent,snapshot,client,receipt


def connection_update(path,sql,params):
    with connection(path) as db:
        db.execute(sql,params)


def reject(label, mutation, expected, at='load'):
    tmp,backend,validator,intent,snapshot,client,receipt = fixture()
    with tmp:
        mutation(backend,validator,intent,snapshot,client,receipt)
        try:
            if at=='load':
                backend.authorizations.load(receipt.authorization_id)
            elif at=='submit':
                backend.submit_authorized(receipt.authorization_id, NOW)
            else:
                validator.validate(intent,sample_market_obs(),snapshot,NOW)
            result='ACCEPTED'
        except Exception as exc:
            result=type(exc).__name__+':'+str(exc)
        print(label,result,'entry_calls',client.place_order.call_count)
        assert expected in result and client.place_order.call_count==0


reject('auth_column_tamper',lambda b,v,i,s,c,r: connection_update(b.path,
       'UPDATE live_pre_execution_authorizations SET authorization_hash=? WHERE authorization_id=?',
       ('f'*64,r.authorization_id)), 'AUTHORIZATION_HASH_MISMATCH')
reject('auth_payload_tamper',lambda b,v,i,s,c,r: connection_update(b.path,
       "UPDATE live_pre_execution_authorizations SET payload=json_set(payload,'$.expires_at_ms',?) WHERE authorization_id=?",
       (r.expires_at_ms+60000,r.authorization_id)), 'AUTHORIZATION_HASH_MISMATCH')
reject('approval_case_swap',lambda b,v,i,s,c,r: connection_update(v.live_store.path,
       'UPDATE approval_records SET case_hash=? WHERE event_id=?',
       ('f'*64,i.approval_event_id)), 'APPROVAL_CASE_HASH_MISMATCH', 'submit')
reject('intent_column_swap',lambda b,v,i,s,c,r: connection_update(b.path,
       'UPDATE live_trade_intents SET idempotency_key=? WHERE intent_id=?',
       ('idem_noncanonical',i.intent_id)), 'PERSISTED_INTENT_IDENTITY_MISMATCH', 'submit')

tmp,backend,validator,intent,snapshot,client,receipt = fixture()
with tmp:
    values = intent.model_dump(exclude={'intent_hash'})
    values.update(intent_id='intent_self_rehashed',idempotency_key='idem_self_rehashed',
                  client_order_id='cuid_self_rehashed')
    try:
        TradeIntentV1.build(**values)
        result='ACCEPTED'
    except Exception as exc:
        result=type(exc).__name__+':'+str(exc).splitlines()[0]
    print('self_rehashed_noncanonical',result)
    assert 'ValidationError' in result

tmp,backend,validator,intent,snapshot,client,receipt = fixture()
with tmp:
    updated = fresh_account(snapshot,available_balance_usdt=4000.0)
    backend.account_provider.side_effect=[snapshot,updated]
    report=backend.submit_authorized(receipt.authorization_id,NOW-10_000)
    claimed_id=backend.authorizations.for_claimed_intent(intent.intent_id)
    claimed,_,bound_account,_=backend.authorizations.load(claimed_id)
    print('refreshed_claim',report.status,'new_id',claimed_id!=receipt.authorization_id,
          'new_account_bound',bound_account.snapshot_hash==updated.snapshot_hash,
          'original_expiry',receipt.expires_at_ms,'claimed_expiry',claimed.expires_at_ms,
          'order_count',client.place_order.call_count)
    assert claimed.expires_at_ms==receipt.expires_at_ms
    assert bound_account.snapshot_hash==updated.snapshot_hash
    assert client.place_order.call_count==1

tmp,backend,validator,intent,snapshot,client,receipt = fixture()
with tmp:
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(backend.submit_authorized,receipt.authorization_id,NOW)
                 for _ in range(2)]
        statuses=[]
        for f in futures:
            try:
                statuses.append(f.result().status)
            except Exception as exc:
                statuses.append(type(exc).__name__+':'+str(exc))
    print('concurrent_singleton',statuses,'entry_count',client.place_order.call_count)
    assert client.place_order.call_count==1

with patch('urllib.request.urlopen') as transport:
    client=BinanceSignedClient('https://fapi.binance.com','placeholder','placeholder',
                               environment='TESTNET',credential_namespace='BINANCE_TESTNET')
    try:
        client.change_leverage('BTCUSDT',2)
        result='ACCEPTED'
    except Exception as exc:
        result=type(exc).__name__+':'+str(exc)
    print('live_endpoint_mutation',result,'transport_calls',transport.call_count)
    assert 'ExecutionBlocked' in result and transport.call_count==0
