from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_execution_intent import NOW, setup_approved_state

from btc_quant_agent.decision.models import content_hash
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import (
    IntentStore,
    TradeIntentV1,
    build_trade_intent,
    canonical_execution_identity,
)
from btc_quant_agent.live_db import connection


def _approved_intent(tmp_path):
    store, case, proposal, event_id, _ = setup_approved_state(tmp_path)
    snapshot = sample_snapshot(observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(store, snapshot, proposal.proposal_hash, event_id, now_ms=NOW)
    return store, case, proposal, event_id, snapshot, intent


def test_canonical_identity_preserves_builder_format_and_rejects_overrides(tmp_path):
    store, case, proposal, event_id, snapshot, intent = _approved_intent(tmp_path)
    digest = hashlib.sha256(f"{case.case_hash}:{proposal.proposal_hash}:{event_id}".encode()).hexdigest()
    assert canonical_execution_identity(case.case_hash, proposal.proposal_hash, event_id) == (
        f"intent_{digest[:24]}", f"idem_{digest[:24]}", f"cuid_v1_{digest[:16]}",
    )
    assert intent.intent_id == f"intent_{digest[:24]}"
    with pytest.raises(ExecutionBlocked, match="NONCANONICAL_IDEMPOTENCY_KEY"):
        build_trade_intent(store, snapshot, proposal.proposal_hash, event_id,
                           now_ms=NOW, idempotency_key="foreign")
    with pytest.raises(ExecutionBlocked, match="NONCANONICAL_CLIENT_ORDER_ID"):
        build_trade_intent(store, snapshot, proposal.proposal_hash, event_id,
                           now_ms=NOW, client_order_id="foreign")


def test_self_rehashed_noncanonical_identity_is_rejected_before_first_persistence(tmp_path):
    _, _, _, _, _, intent = _approved_intent(tmp_path)
    values = intent.model_dump(mode="json")
    values["intent_id"] = "intent_foreign"
    values["intent_hash"] = content_hash({k: v for k, v in values.items() if k != "intent_hash"})
    with pytest.raises(ValidationError, match="canonical identity mismatch"):
        TradeIntentV1.model_validate(values)
    with pytest.raises(ValidationError, match="canonical identity mismatch"):
        TradeIntentV1.build(**{k: v for k, v in values.items() if k != "intent_hash"})


def test_persisted_column_and_payload_identity_mismatch_fails_closed(tmp_path):
    _, _, _, _, _, intent = _approved_intent(tmp_path)
    intents = IntentStore(tmp_path / "live.db")
    intents.save_intent(intent)
    with connection(tmp_path / "live.db") as db:
        db.execute("UPDATE live_trade_intents SET client_order_id='foreign' WHERE intent_id=?",
                   (intent.intent_id,))
    with pytest.raises(ExecutionBlocked, match="PERSISTED_INTENT_IDENTITY_MISMATCH"):
        intents.get_intent(intent.intent_id)
