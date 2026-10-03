import asyncio
from test_live_v1_runtime_r2 import _runtime

async def scenario():
    runtime=_runtime(pending=('claimed-intent',))
    order=[]
    async def reconcile(intent_id): order.append('reconcile:'+intent_id)
    async def rest(): order.append('rest')
    runtime.execution_service.reconcile_intent.side_effect=reconcile
    runtime.account_watch.reconcile_rest_async.side_effect=rest
    await runtime.start()
    first={'started':runtime._started,'task_names':[t.get_name() for t in runtime.tasks],'order':list(order)}
    await runtime.stop()
    stopped={'started':runtime._started,'accepting_risk':runtime.accepting_risk,'all_done':all(t.done() for t in runtime.tasks),'close_calls':runtime.account_watch.close_user_stream.await_count}
    await runtime.start()
    restarted={'started':runtime._started,'task_names':[t.get_name() for t in runtime.tasks],'reconcile_count':runtime.execution_service.reconcile_intent.await_count}
    await runtime.stop()
    print({'first':first,'stopped':stopped,'restarted':restarted,'final_all_done':all(t.done() for t in runtime.tasks)})
asyncio.run(scenario())
