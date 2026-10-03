from pathlib import Path
from tempfile import TemporaryDirectory
from test_live_v1_position_supervisor import observation, NOW
from btc_quant_agent.position_supervisor import PositionSupervisor

with TemporaryDirectory() as d:
    s = PositionSupervisor(Path(d) / 'live.db')
    b_baseline = s.evaluate(observation(account_id='acct-b', mark_price=100, observed_at_ms=NOW-1), NOW-1)
    a_stop = s.evaluate(observation(account_id='acct-a', mark_price=91, observed_at_ms=NOW), NOW)
    b_stop = s.evaluate(observation(account_id='acct-b', mark_price=91, observed_at_ms=NOW+1), NOW+1)
    print({'b_baseline':[e.trigger for e in b_baseline], 'a_stop':[e.trigger for e in a_stop], 'b_stop':[e.trigger for e in b_stop]})
with TemporaryDirectory() as d:
    s = PositionSupervisor(Path(d) / 'live.db')
    dry = s.evaluate(observation(account_id='DEFAULT_ACCOUNT', account_snapshot_hash='a'*64, quantity=1, observed_at_ms=NOW), NOW)
    testnet = s.evaluate(observation(account_id='DEFAULT_ACCOUNT', account_snapshot_hash='z'*64, quantity=1, observed_at_ms=NOW+1), NOW+1)
    print({'dry_run':[e.trigger for e in dry], 'testnet':[e.trigger for e in testnet]})
