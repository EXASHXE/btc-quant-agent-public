"""Approval presentation never grants execution environment or write authority."""

import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_intent import NOW, setup_approved_state

from btc_quant_agent.approval.feishu import build_interactive_card
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import build_trade_intent
from btc_quant_agent.execution.policy import ExecutionCapabilityPolicyV1


@pytest.mark.parametrize("environment,namespace,endpoint", [
    ("DRY_RUN", "NONE", "local://paper"),
    ("TESTNET", "BINANCE_TESTNET", "https://testnet.binancefuture.com"),
])
def test_display_environment_cannot_grant_execution_authority(tmp_path, environment, namespace, endpoint):
    store, _case, proposal, approval_id, _actor = setup_approved_state(tmp_path)
    card = build_interactive_card(proposal)
    assert card["header"]["title"]["content"] == "Live V1 DRY_RUN proposal"
    for element in card["elements"][1:]:
        assert set(element["actions"][0]["value"]) == {"action", "proposal_hash", "case_hash"}

    # Presentation text is deliberately unrelated to the immutable execution input.
    card["header"]["title"]["content"] = "LIVE execution enabled"
    snapshot = sample_snapshot(environment=environment, credential_namespace=namespace,
                               rest_base_url=endpoint, positions=(), orders=(),
                               observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(store, snapshot, proposal.proposal_hash, approval_id, now_ms=NOW)
    assert intent.environment == snapshot.environment == environment
    assert intent.account_snapshot_hash == snapshot.snapshot_hash
    with pytest.raises(ExecutionBlocked):
        ExecutionCapabilityPolicyV1.check_capability("LIVE", "SUBMIT_INTENT")
