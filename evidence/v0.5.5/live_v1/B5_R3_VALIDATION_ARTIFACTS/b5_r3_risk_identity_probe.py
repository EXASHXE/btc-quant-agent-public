from pathlib import Path
from tempfile import TemporaryDirectory
import sys

sys.path.insert(0, '/tmp/live-v1-b5-r3-independent-c2c7cc8/tests')
from test_live_v1_decision_models import sample_case, sample_analysis
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_validator import NOW, sample_market_obs

from btc_quant_agent.approval.store import LiveStore, LiveState
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.execution.intents import IntentStore, build_trade_intent, compile_executable_intent_fields
from btc_quant_agent.execution.validator import PreExecutionValidator
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch
from btc_quant_agent.account_watch.models import AccountSnapshotV1
from btc_quant_agent.approval.feishu import build_interactive_card


def setup(direction):
    tmp = TemporaryDirectory(prefix='b5-r3-risk-')
    path = Path(tmp.name) / 'live.db'
    store = LiveStore(path)
    geometry = {} if direction == 'LONG' else {
        'direction':'SHORT', 'stop_loss':105.0,
        'take_profit_1':90.0, 'take_profit_2':80.0,
    }
    case = sample_case(created_at_ms=NOW, observed_at_ms=NOW,
                       expires_at_ms=NOW+120_000, **geometry)
    analysis = sample_analysis(case, action='OPEN_'+direction)
    store.save_case(case)
    store.save_analysis(analysis)
    policy = RiskPolicyV1()
    proposal = RiskCompilerV1(policy).compile(case, analysis, now_ms=NOW)
    assert proposal.recommended_notional_usdt > 0
    store.save_proposal(proposal)
    for state in (LiveState.LLM_ANALYZING, LiveState.PLAN_READY,
                  LiveState.NOTIFIED, LiveState.WAITING_APPROVAL):
        store.transition(case.case_id, state, NOW)
    store.record_callback('approval-1','APPROVE','reviewer',proposal.proposal_hash,case.case_hash,NOW)
    account = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW,
                              positions=(), orders=())
    intent = build_trade_intent(store,account,proposal.proposal_hash,'approval-1',
                                now_ms=NOW, risk_policy=policy)
    intents = IntentStore(path)
    intents.save_intent(intent)
    kill = KillSwitch(path)
    validator = PreExecutionValidator(store,intents,kill,risk_policy=policy,
                                       tactical_validity_provider=lambda *_: True)
    market = sample_market_obs(mark_price=intent.price)
    assert validator.validate(intent,market,account,NOW).is_valid
    return tmp,store,case,proposal,policy,account,intent,validator,market


def snap(account, **changes):
    values = account.model_dump(exclude={'snapshot_hash'}) | changes
    if 'drawdown_pct' in changes and 'peak_equity_usdt' not in changes:
        values['peak_equity_usdt'] = values['equity_usdt']/(1-values['drawdown_pct'])
    return AccountSnapshotV1.build(**values)


for direction in ('LONG','SHORT'):
    tmp,store,case,proposal,policy,account,intent,validator,market = setup(direction)
    with tmp:
        # Independently derive dollars: quantity * stop gap + notional * all adverse costs.
        gap = abs(intent.price-intent.stop_loss)
        friction = (policy.round_trip_fee_bps+policy.slippage_bps+
                    max(policy.funding_buffer_bps,abs(case.funding_rate or 0)*10000))/10000
        expected_loss = intent.quantity*gap + intent.quantity*intent.price*friction
        daily_cap = min(validator.kill_switch.policy.daily_loss_cap_usdt,
                        account.equity_usdt*policy.max_daily_loss_pct)
        drawdown_cap = min(validator.kill_switch.policy.drawdown_cap_pct,policy.drawdown_kill_pct)

        at_daily = snap(account,daily_loss_usdt=daily_cap-expected_loss)
        over_daily = snap(at_daily,daily_loss_usdt=daily_cap-expected_loss+1e-5)
        # Remaining equity above drawdown floor equals the trade's proposed loss.
        peak_at_boundary = (account.equity_usdt-expected_loss)/(1-drawdown_cap)
        at_dd = snap(account,peak_equity_usdt=peak_at_boundary,
                     drawdown_pct=1-account.equity_usdt/peak_at_boundary)
        peak_over = peak_at_boundary+1e-4
        over_dd = snap(account,peak_equity_usdt=peak_over,
                       drawdown_pct=1-account.equity_usdt/peak_over)
        inconsistent = snap(account,peak_equity_usdt=account.equity_usdt+100,
                            drawdown_pct=0.0)
        outcomes = {
            'daily_exact':validator.validate(intent,market,at_daily,NOW).reason,
            'daily_over':validator.validate(intent,market,over_daily,NOW).reason,
            'drawdown_exact':validator.validate(intent,market,at_dd,NOW).reason,
            'drawdown_over':validator.validate(intent,market,over_dd,NOW).reason,
            'inconsistent':validator.validate(intent,market,inconsistent,NOW).reason,
        }
        executable = compile_executable_intent_fields(case,proposal,account,policy)
        equality = all(getattr(intent,key)==value for key,value in executable.items())
        card = build_interactive_card(proposal)
        card_title = card['header']['title']['content']
        card_authority = card['elements'][0]['text']['content'].splitlines()[0]
        print(direction,'quantity',intent.quantity,'price',intent.price,'stop',intent.stop_loss,
              'expected_loss',expected_loss,'daily_cap',daily_cap,'dd_cap',drawdown_cap,
              'outcomes',outcomes,'executable_all_fields_equal',equality,
              'compiled_fields',sorted(executable),
              'approval_card_title',card_title,'approval_card_authority',card_authority,
              'intent_environment',intent.environment,'intent_account',intent.account_authority)
        assert outcomes == {
            'daily_exact':'OK','daily_over':'DAILY_LOSS_HEADROOM_EXCEEDED',
            'drawdown_exact':'OK','drawdown_over':'DRAWDOWN_HEADROOM_EXCEEDED',
            'inconsistent':'ACCOUNT_EQUITY_INCONSISTENT',
        }
        assert equality
