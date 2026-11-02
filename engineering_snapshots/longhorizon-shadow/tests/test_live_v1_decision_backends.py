import asyncio
import json
from types import SimpleNamespace

import pytest
from test_live_v1_decision_models import sample_analysis, sample_case

from btc_quant_agent.decision.backends import AnalysisMode, CodexExecBackend, ResponsesBackend
from btc_quant_agent.decision.fusion import DecisionFusion
from btc_quant_agent.decision.models import AccountContextV1


class FakeResponses:
    def __init__(self, result):
        self.result = result
        self.calls = []

    async def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def test_responses_uses_one_canonical_case_and_trusted_metadata():
    case = sample_case()
    parsed = sample_analysis(case, backend="untrusted", model="untrusted",
                             provider_request_id="untrusted")
    fake = FakeResponses(SimpleNamespace(status="completed", id="resp-1", model="actual-model",
                                         output=[], output_parsed=parsed))
    backend = ResponsesBackend("configured-model", 2, client=SimpleNamespace(responses=fake),
                               clock_ms=lambda: 2000)
    result = asyncio.run(backend.analyze(case, AnalysisMode.PRIMARY))
    assert (result.backend, result.model, result.provider_request_id) == (
        "responses", "actual-model", "resp-1")
    assert len(fake.calls) == 1
    assert fake.calls[0]["store"] is False
    assert fake.calls[0]["text_format"].__name__ == "AnalysisResultV1"
    assert fake.calls[0]["max_output_tokens"] > 0
    assert json.loads(fake.calls[0]["input"][1]["content"]) == json.loads(case.canonical_json())


def test_responses_fails_closed_for_missing_model_and_stale_case():
    case = sample_case()
    fake = FakeResponses(None)
    for model, now in [(None, 2000), ("", 2000), ("configured-model", 61000)]:
        result = asyncio.run(ResponsesBackend(
            model, 2, client=SimpleNamespace(responses=fake),
            clock_ms=lambda now=now: now).analyze(case, AnalysisMode.PRIMARY))
        assert result.action == "NO_ACTION"
        assert result.risk_modifier == "BLOCK"
        assert result.requires_manual_review
    assert fake.calls == []


def test_responses_rejects_bad_status_refusal_binding_and_executable_fields():
    case = sample_case()
    valid = sample_analysis(case).model_dump(mode="json")
    scenarios = [
        SimpleNamespace(status="incomplete", id="r", model="m", output=[], output_parsed=valid),
        SimpleNamespace(status="completed", id="r", model="m",
                        output=[SimpleNamespace(content=[SimpleNamespace(type="refusal")])],
                        output_parsed=valid),
        SimpleNamespace(status="completed", id="r", model="m", output=[],
                        output_parsed={**valid, "case_hash": "b" * 64}),
        SimpleNamespace(status="completed", id="r", model="m", output=[],
                        output_parsed={**valid, "quantity": 1}),
    ]
    for response in scenarios:
        fake = FakeResponses(response)
        result = asyncio.run(ResponsesBackend(
            "m", 2, client=SimpleNamespace(responses=fake),
            clock_ms=lambda: 2000).analyze(case, AnalysisMode.PRIMARY))
        assert result.action == "NO_ACTION"
        assert result.risk_modifier == "BLOCK"


def test_fusion_selects_primary_without_secondary_when_unneeded():
    case = sample_case()
    primary = sample_analysis(case)
    result = DecisionFusion().fuse(case, primary)
    assert result.selected == primary
    assert result.secondary is None
    assert not result.requires_manual_review
    assert not DecisionFusion().needs_secondary(case, primary)


@pytest.mark.parametrize("change", [
    {"confidence": 0.4}, {"action": "ADD"},
    {"strategy_data_disagreement": True}, {"requires_secondary_review": True},
])
def test_fusion_requires_secondary_for_trigger(change):
    case = sample_case()
    primary = sample_analysis(case, **change)
    assert DecisionFusion().needs_secondary(case, primary)
    result = DecisionFusion().fuse(case, primary)
    assert result.requires_manual_review
    assert result.selected.risk_modifier == "BLOCK"


def test_fusion_material_conflict_blocks_sizing():
    case = sample_case()
    primary = sample_analysis(case)
    secondary = sample_analysis(case, action="OPEN_SHORT")
    result = DecisionFusion().fuse(case, primary, secondary, manual_codex_request=True)
    assert result.requires_manual_review
    assert "MODEL_DISAGREEMENT" in result.reasons
    assert result.selected.risk_modifier == "BLOCK"


def test_fusion_primary_block_cannot_be_weakened():
    case = sample_case()
    primary = sample_analysis(case, risk_modifier="BLOCK")
    secondary = sample_analysis(case, risk_modifier="STANDARD")
    result = DecisionFusion().fuse(case, primary, secondary)
    assert result.selected.risk_modifier == "BLOCK"


def test_fusion_high_exposure_requests_secondary():
    case = sample_case(account=AccountContextV1(
        equity_usdt=1000, symbol_exposure_usdt=250, portfolio_exposure_usdt=250,
        margin_used_usdt=0, simultaneous_positions=0, daily_loss_usdt=0,
        drawdown_pct=0, observed_at_ms=1000))
    result = DecisionFusion().fuse(case, sample_analysis(case))
    assert "HIGH_EXPOSURE" in result.reasons
    assert result.selected.risk_modifier == "BLOCK"


def test_codex_runs_isolated_one_case_and_validates_result():
    case = sample_case()
    calls = []

    class FakeProcess:
        returncode = 0

        async def communicate(self, input):
            assert input.count(case.canonical_json().encode()) == 1
            output_path.write_text(sample_analysis(case).canonical_json(), encoding="utf-8")

    async def spawn(*args, **kwargs):
        nonlocal output_path
        calls.append((args, kwargs))
        output_path = __import__("pathlib").Path(args[args.index("-o") + 1])
        return FakeProcess()

    output_path = None
    result = asyncio.run(CodexExecBackend(
        "configured-model", 2, process_factory=spawn,
        clock_ms=lambda: 2000).analyze(case, AnalysisMode.SECONDARY))
    assert result.action == "OPEN_LONG"
    assert (result.backend, result.model) == ("codex_exec", "configured-model")
    args, kwargs = calls[0]
    assert args[:2] == ("codex", "exec")
    assert 'permissions.live-v1-review.extends=":read-only"' in args
    assert "--sandbox" not in args and "--ephemeral" in args
    assert 'default_permissions="live-v1-review"' in args
    assert any('":root"="deny"' in arg for arg in args)
    assert "permissions.live-v1-review.network.enabled=false" in args
    assert "--ignore-user-config" in args and "--ignore-rules" in args
    assert "features.shell_tool=false" in args
    assert "features.unified_exec=false" in args
    assert "features.apps=false" in args
    assert "features.multi_agent=false" in args
    assert "mcp_servers={}" in args
    assert 'web_search="disabled"' in args
    assert kwargs["cwd"] != "."
    assert "OPENAI_API_KEY" not in kwargs["env"]


def test_codex_rejects_oversized_or_invalid_result():
    case = sample_case()

    class FakeProcess:
        returncode = 0

        async def communicate(self, input):
            output_path.write_text('{"quantity": 1}', encoding="utf-8")

    async def spawn(*args, **kwargs):
        nonlocal output_path
        output_path = __import__("pathlib").Path(args[args.index("-o") + 1])
        return FakeProcess()

    output_path = None
    result = asyncio.run(CodexExecBackend(
        "configured-model", 2, process_factory=spawn,
        clock_ms=lambda: 2000).analyze(case, AnalysisMode.SECONDARY))
    assert result.action == "NO_ACTION"
    assert result.risk_modifier == "BLOCK"


def test_codex_primary_mode_fails_closed_without_spawning():
    async def forbidden_spawn(*args, **kwargs):
        raise AssertionError("primary Codex must not spawn")
    result = asyncio.run(CodexExecBackend("configured-model", 2,
        process_factory=forbidden_spawn, clock_ms=lambda:2000).analyze(
            sample_case(), AnalysisMode.PRIMARY))
    assert result.action == "NO_ACTION"
    assert "SECONDARY_ONLY" in result.risk_factors
