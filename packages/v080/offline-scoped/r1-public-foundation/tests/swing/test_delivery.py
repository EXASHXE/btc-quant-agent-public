"""B-specific checks for inherited contracts without Program A release packaging."""
import json
from pathlib import Path

from btc_quant_agent.platform.strategies import REGISTRY
from btc_quant_agent.platform.swing import State, SwingPolicy
from btc_quant_agent.platform.rc_models import BShadowState

ROOT = Path(__file__).resolve().parents[2]


def test_frozen_scope_and_state_artifacts_match_runtime():
    scope = json.loads((ROOT / "contracts/active_scope.json").read_text())
    states = json.loads((ROOT / "contracts/state_model.json").read_text())
    assert scope["product_version"] == SwingPolicy().version
    assert scope["decision_timeframes"] == list(SwingPolicy().decision_timeframes)
    assert set(states["states"]) == {state.value for state in State}
    assert set(REGISTRY) == {scope["strategies"]["S1"]["id"]}


def test_source_gate_retains_boundaries_and_native_is_unqualified():
    gate = json.loads((ROOT / "contracts/low_rate_source_gate.json").read_text())
    assert gate["retained_invariants"]["BBO_queue_hard_stop"] == 128
    assert gate["retained_invariants"]["sticky_wall_discontinuity_ms"] == 50
    assert gate["source_qualified"] is False
    assert gate["workload"]["resumption_burst_cap_bars"] == 4096


def test_b_shadow_state_schema_versions_required_unknown_and_source_blocked_states():
    schema = json.loads((ROOT / "contracts/b_shadow_state_v1.json").read_text())
    assert schema["schema_version"] == "V070_B_SHADOW_STATE_V1"
    allowed = set(BShadowState.model_fields["status"].annotation.__args__)
    assert allowed == set(schema["states"])
    assert schema["migration"]["to"] == schema["schema_version"]
    assert schema["migration"]["behavior"].startswith("Create a sidecar")
