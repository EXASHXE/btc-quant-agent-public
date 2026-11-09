import pytest
from btc_quant_agent.platform.qualification.product import Decision
from btc_quant_agent.platform.qualification.evidence import Ledger, STAGES


def test_stage_skipping_and_immutable_replay(tmp_path):
    ledger = Ledger(tmp_path / "qualification.sqlite")
    with pytest.raises(ValueError, match="STAGE_SKIP"):
        ledger.transition("c", STAGES[1], {}, "SYNTHETIC_NETWORK_QA")
    ledger.transition("c", STAGES[0], {"raw": 1}, "SYNTHETIC_NETWORK_QA")
    first = ledger.verify()
    ledger.transition("c", STAGES[0], {"raw": 1}, "SYNTHETIC_NETWORK_QA")
    assert first == ledger.verify()
    with pytest.raises(ValueError, match="IMMUTABLE"):
        ledger.transition("c", STAGES[0], {"raw": 2}, "SYNTHETIC_NETWORK_QA")


def test_qualification_sqlite_tamper_rejection(tmp_path):
    ledger = Ledger(tmp_path / "qualification.sqlite")
    ledger.append("RAW", {"frames": 1})
    with ledger.db() as db:
        db.execute("DROP TRIGGER evidence_u")
        db.execute("UPDATE evidence SET body=x'7b7d'")
    with pytest.raises(ValueError, match="TAMPER"):
        ledger.verify()


def test_native_and_synthetic_decision_schemas_are_disjoint():
    from btc_quant_agent.platform.rc_models import RCDecision

    assert (
        Decision.model_fields["schema_version"].default != RCDecision.model_fields["schema_version"].default
    )
    assert "GENUINE_NATIVE" in str(Decision.model_fields["exposure"].annotation)
    assert "GENUINE_NATIVE" not in str(RCDecision.model_fields["exposure"].annotation)
