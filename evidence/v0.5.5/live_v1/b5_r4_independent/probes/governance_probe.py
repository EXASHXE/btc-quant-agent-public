"""Independent B5 R4 governance probes. Fake providers and local SQLite only."""
import asyncio
import json
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from test_live_v1_account_watch import sample_snapshot
from test_live_v1_decision_approval import prepared
from test_live_v1_decision_models import sample_analysis, sample_case
from test_live_v1_execution_intent import NOW, setup_approved_state

from btc_quant_agent.approval.callback import create_callback_app
from btc_quant_agent.approval.feishu import build_interactive_card
from btc_quant_agent.config import AppConfig, StorageConfig
from btc_quant_agent.decision.backends import AnalysisMode, CodexExecBackend
from btc_quant_agent.execution.binance_signed import (
    BinanceExecutionError,
    BinanceSignedClient,
    create_testnet_signed_client,
)
from btc_quant_agent.execution.guard import ExecutionBlocked
from btc_quant_agent.execution.intents import build_trade_intent
from btc_quant_agent.execution.policy import ExecutionCapabilityPolicyV1
from btc_quant_agent.live_db import connection


@pytest.mark.parametrize("mode", ["LIVE", "live", "AUTONOMOUS", "autonomous", "LIVE_APPROVAL_ONLY"])
def test_blocked_modes_have_no_transport_authority(mode, monkeypatch):
    transport = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr("urllib.request.urlopen", transport)
    client = BinanceSignedClient("https://fapi.binance.com", "fake", "fake", environment=mode, credential_namespace="BINANCE_TESTNET")
    with pytest.raises(ExecutionBlocked):
        client._signed_request("POST", "/fapi/v1/order", {})
    transport.assert_not_called()
    with pytest.raises(ExecutionBlocked):
        ExecutionCapabilityPolicyV1.check_capability(mode)


def test_live_credentials_do_not_supply_testnet(monkeypatch):
    for name in ("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BINANCE_API_KEY", "live-sentinel")
    monkeypatch.setenv("BINANCE_API_SECRET", "live-sentinel")
    with pytest.raises(BinanceExecutionError, match="missing required"):
        create_testnet_signed_client()


def test_sqlite_durability_contract(tmp_path):
    with connection(tmp_path / "probe.db") as db:
        assert db.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert db.execute("PRAGMA synchronous").fetchone()[0] == 2
        assert db.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1


@pytest.mark.parametrize("field", ["quantity", "environment", "orderId", "price", "credential_namespace", "execute"])
def test_feishu_cannot_carry_executable_fields(tmp_path, field):
    store, case, _, proposal = prepared(tmp_path)
    app = create_callback_app(store, "fake-token", approver_open_ids=["actor"], clock_ms=lambda: 3000)
    body = {"schema": "2.0", "header": {"token": "fake-token", "event_type": "card.action.trigger", "event_id": "fake-event"}, "event": {"operator": {"open_id": "actor"}, "action": {"value": {"action": "APPROVE", "proposal_hash": proposal.proposal_hash, "case_hash": case.case_hash, field: "LIVE"}}}}
    async def invoke():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local") as client:
            response = await client.post("/callback", json=body)
            assert response.status_code == 400
    asyncio.run(invoke())
    assert store.state(case.case_id) == "WAITING_APPROVAL"


def test_codex_child_cannot_inherit_provider_secrets(monkeypatch):
    sentinels = {k: "independent-secret-sentinel" for k in ("OPENAI_API_KEY", "BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET", "BINANCE_API_KEY", "BINANCE_API_SECRET", "FEISHU_APP_SECRET", "FEISHU_VERIFICATION_TOKEN")}
    for key, value in sentinels.items():
        monkeypatch.setenv(key, value)
    case = sample_case()
    captured = {}
    class FakeProcess:
        returncode = 0
        async def communicate(self, input):
            assert b"independent-secret-sentinel" not in input
            Path(captured["output"]).write_text(sample_analysis(case).canonical_json())
    async def spawn(*args, **kwargs):
        captured.update(args=args, kwargs=kwargs, output=args[args.index("-o") + 1])
        assert not set(sentinels).intersection(kwargs["env"])
        assert "independent-secret-sentinel" not in json.dumps(kwargs["env"])
        assert "permissions.live-v1-review.network.enabled=false" in args
        assert "--ignore-user-config" in args
        assert "features.shell_tool=false" in args
        assert "mcp_servers={}" in args
        return FakeProcess()
    result = asyncio.run(CodexExecBackend("fake-model", 2, process_factory=spawn, clock_ms=lambda: 2000).analyze(case, AnalysisMode.SECONDARY))
    assert result.risk_modifier != "BLOCK"


@pytest.mark.parametrize("environment,namespace,url", [("DRY_RUN", "NONE", "local://paper"), ("TESTNET", "BINANCE_TESTNET", "https://testnet.binancefuture.com")])
def test_display_tamper_cannot_rebind_persisted_execution(tmp_path, environment, namespace, url):
    store, _, proposal, approval_id, _ = setup_approved_state(tmp_path)
    card = build_interactive_card(proposal)
    card["header"]["title"]["content"] = "LIVE APPROVED"
    for element in card["elements"][1:]:
        assert set(element["actions"][0]["value"]) == {"action", "proposal_hash", "case_hash"}
    snap = sample_snapshot(environment=environment, credential_namespace=namespace, rest_base_url=url, positions=(), orders=(), observed_at_ms=NOW, last_rest_at_ms=NOW)
    intent = build_trade_intent(store, snap, proposal.proposal_hash, approval_id, now_ms=NOW)
    assert intent.environment == environment
    assert intent.account_snapshot_hash == snap.snapshot_hash


def test_runtime_host_routes_are_read_only(tmp_path, monkeypatch):
    from test_live_v1_runtime_r2 import _runtime

    from btc_quant_agent import api
    from btc_quant_agent.approval.store import LiveStore
    from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
    from btc_quant_agent.decision.service import TacticalLiveService
    monkeypatch.setattr(api, "load_config", lambda: AppConfig(storage=StorageConfig(sqlite_path=str(tmp_path / "host.db"))))
    service = TacticalLiveService(LiveStore(tmp_path / "live.db"), None, RiskCompilerV1(RiskPolicyV1()))
    app = api.create_app(live_service=service, live_runtime=_runtime())
    for route in app.routes:
        assert set(getattr(route, "methods", None) or ()).issubset({"GET", "HEAD", "OPTIONS"})
