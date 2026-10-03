import asyncio, json
from tempfile import TemporaryDirectory
from pathlib import Path
from test_live_v1_account_stream_r2 import FakeSignedClient, NOW
from btc_quant_agent.account_watch import AccountStore, AccountWatch
from btc_quant_agent.config import ExecutionConfig

with TemporaryDirectory() as d:
    c=FakeSignedClient()
    w=AccountWatch(ExecutionConfig(mode='testnet'),AccountStore(Path(d)/'account.db'),signed_client=c,clock_ms=lambda:NOW)
    w.reconcile_rest(NOW)
    account={'e':'ACCOUNT_UPDATE','E':NOW+1,'T':NOW+1,'a':{'B':[{'a':'USDT','wb':'950','cw':'900'}],'P':[{'s':'BTCUSDT','pa':'-0.1','ep':'60000','up':'-5','mt':'isolated'}]}}
    order={'e':'ORDER_TRADE_UPDATE','E':NOW+1,'T':NOW+1,'o':{'s':'BTCUSDT','i':7,'c':'client-7','S':'SELL','X':'PARTIALLY_FILLED','o':'LIMIT','q':'0.2','z':'0.1','p':'60000','ap':'60000','R':False,'sp':'0'}}
    accepted=(w.handle_user_event(account,NOW+2),w.handle_user_event(order,NOW+2))
    snap=w.latest_snapshot()
    duplicate=w.handle_user_event(order,NOW+3)
    conflicting=w.handle_user_event({**order,'o':{**order['o'],'z':'0.15'}},NOW+4)
    after_conflict=(w.is_reconciled,w.latest_snapshot().quality,w.latest_snapshot().orders[0].filled_quantity)
    repaired=w.reconcile_rest(NOW+5)
    stale=w.handle_user_event({**order,'E':NOW+4},NOW+6)
    print('events',{'accepted_same_E':accepted,'position_qty':snap.positions[0].quantity,'order_filled':snap.orders[0].filled_quantity,'duplicate_accepted':duplicate,'conflict_accepted':conflicting,'after_conflict':after_conflict,'rest_repaired':repaired.reconciled,'stale_accepted':stale,'after_stale_reconciled':w.is_reconciled})

async def reconnect():
    async def inline_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)
    asyncio.to_thread = inline_thread
    with TemporaryDirectory() as d:
        c=FakeSignedClient()
        urls=[]
        class Socket:
            def __init__(self,index): self.index=index
            async def __aenter__(self): return self
            async def __aexit__(self,*_): return None
            def __aiter__(self):
                async def messages():
                    if self.index == 1:
                        yield json.dumps({'e':'listenKeyExpired','E':NOW+1})
                return messages()
        def connect(url,**_):
            urls.append(url)
            if len(urls)==2: w._stop_event.set()
            return Socket(len(urls))
        w=AccountWatch(ExecutionConfig(mode='testnet'),AccountStore(Path(d)/'stream.db'),signed_client=c,clock_ms=lambda:NOW,websocket_connect=connect)
        await asyncio.wait_for(w.run_user_stream(),3)
        print('lifecycle',{'connections':len(urls),'all_testnet_url':all(u.startswith('wss://stream.binancefuture.com/ws/') for u in urls),'listen_keys_started':c.started,'listen_keys_closed':c.closed,'final_reconciled':w.is_reconciled,'listen_key_in_snapshot':'fake-listen-key' in w.latest_snapshot().canonical_json()})
asyncio.run(reconnect())
