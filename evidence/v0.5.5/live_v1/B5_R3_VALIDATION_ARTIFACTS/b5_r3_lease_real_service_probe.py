import asyncio, tempfile
from pathlib import Path
from test_live_v1_position_supervisor import observation, market_case, NOW
from btc_quant_agent.position_supervisor import PositionSupervisor
from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.decision.service import TacticalLiveService
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1

async def main():
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / 'live.db'
        entered = asyncio.Event()
        release = asyncio.Event()
        provider_calls = []
        clock = {'now': NOW}
        class Provider:
            async def analyze(self, case, mode):
                provider_calls.append(case.case_hash)
                entered.set()
                await release.wait()
                raise RuntimeError('synthetic provider failure')
        store = LiveStore(path)
        service = TacticalLiveService(store, Provider(), RiskCompilerV1(RiskPolicyV1()), clock_ms=lambda: clock['now'])
        a = PositionSupervisor(path, analysis_service=service, fresh_market_case=lambda _: market_case(), lease_clock_ms=lambda: clock['now'])
        b = PositionSupervisor(path, analysis_service=service, fresh_market_case=lambda _: market_case(), lease_clock_ms=lambda: clock['now'])
        event = a.evaluate(observation(), NOW)[0]
        first = asyncio.create_task(a.drain_pending_dispatches(NOW, lease_ms=1000))
        await asyncio.wait_for(entered.wait(), 2)
        clock['now'] = NOW + 1001
        second = await b.drain_pending_dispatches(NOW+1001, lease_ms=1000)
        state_after_second = a.get_dispatch(event.event_id)['state']
        first.cancel()
        try:
            await first
        except asyncio.CancelledError:
            pass
        release.set()
        print({'provider_calls':len(provider_calls), 'second_dispatched':len(second), 'state_after_second':state_after_second, 'final_outbox_state':a.get_dispatch(event.event_id)['state'], 'decision_state':str(store.state('pos-'+event.event_id)), 'proposal':store.active_proposal('pos-'+event.event_id)})
asyncio.run(main())
