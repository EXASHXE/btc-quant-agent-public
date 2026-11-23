"""Run the signed-stage control flow with synthetic data and preserve causal replay evidence."""

from dataclasses import replace
from pathlib import Path
from types import MappingProxyType
import sys

from quant_personal_public_b1.store import encode
from quant_personal_live_public_b5.admission import Adapter
from quant_personal_live_public_b5.approval import Limit
from quant_personal_live_public_b5.collection import collect
from quant_personal_live_public_b5.decision import engine, replay
from quant_personal_live_public_b5.offline import FixtureWire, qa_active, qa_approval
from quant_personal_live_public_b5.stages import StagePlan


def run(root, market):
    root.mkdir()
    state=root/"source.sqlite"
    base=qa_approval(state)
    plan=StagePlan(37,40) if market else StagePlan(None,None)
    total=Limit(*plan.plan_totals())
    scope=replace(base.scope,stage_plan=plan,phase_limits=MappingProxyType({"bootstrap":total}),
                  total=total,funding_debit=1 if market else None)
    active=qa_active(state,approval=replace(base,scope=scope))
    with active.ledger.store.collector():
        stages=["CANARY"]
        pub=collect(active,"bootstrap",FixtureWire(active.clock),notify_stage=lambda:stages.append("MARKET"))
        assert pub["stage"]["issue"] is None
        result={"stages":stages,"evidence":"SYNTHETIC_QA_ONLY","gate":pub["stage"]["activation_gate"],
                "reserved":pub["stage"]["stats"],"cards":[]}
        as_of=pub["visible_venue_upper_ms"]
        if market:
            adapter=Adapter(active.ledger)
            evaluator=engine(adapter,root/"journal.sqlite")
            rebuild=engine(adapter,root/"rebuild.sqlite")
            for symbol in pub["stage"]["symbols"]:
                params={"scan":pub["scan_id"],"as_of_ms":as_of}
                card=evaluator.evaluate(symbol,**params)
                other=rebuild.evaluate(symbol,**params)
                assert {k:v for k,v in card.items() if k!="journal_recorded_wall_ms"} == {
                    k:v for k,v in other.items() if k!="journal_recorded_wall_ms"}
                result["cards"].append({"symbol":symbol, **replay(adapter,card)})
            assert pub["stage"]["stats"]["reserved_requests"] == 39
        else:
            assert as_of is None and pub["stage"]["market_status"]=="NOT_EVALUATED"
            assert pub["stage"]["stats"]["reserved_requests"] == 2
            result["market_status"]="NOT_EVALUATED"
        active.close()
    return result


out=Path(sys.argv[1])
out.mkdir()
for q,scoped in (("canary-only",False),("conditional-market",True)):
    print(encode(run(out/q,scoped)))
