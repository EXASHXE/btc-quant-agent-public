import asyncio

import httpx

from btc_quant_agent import api
from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.config import AppConfig, StorageConfig
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.decision.service import TacticalLiveService


def test_callback_uses_feishu_auth_and_live_reads_use_api_bearer(tmp_path, monkeypatch):
    async def run():
        monkeypatch.setattr(api, "load_config", lambda: AppConfig(
            storage=StorageConfig(sqlite_path=str(tmp_path / "old.db"))))
        monkeypatch.setenv("BTC_QUANT_API_TOKEN", "api-token")
        monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "feishu-token")
        service = TacticalLiveService(LiveStore(str(tmp_path / "live.db")),
            None, RiskCompilerV1(RiskPolicyV1()))
        app = api.create_app(live_service=service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://test") as client:
            response = await client.post("/live-v1/feishu/callback", json={
                "type":"url_verification", "token":"feishu-token", "challenge":"challenge"})
            assert response.status_code == 200
            assert response.json()["challenge"] == "challenge"
            denied = await client.post("/live-v1/feishu/callback", json={
                "type":"url_verification", "token":"bad", "challenge":"challenge"})
            assert denied.status_code == 401
            denied_read = await client.get("/live-v1/cases/unknown")
            assert denied_read.status_code == 401
            read = await client.get("/live-v1/cases/unknown",
                                     headers={"Authorization":"Bearer api-token"})
            assert read.status_code == 404
    asyncio.run(run())


def test_decision_modules_do_not_reach_signed_execution():
    import ast
    from pathlib import Path

    from btc_quant_agent import decision
    root = Path(decision.__file__).parent
    for path in [*root.glob("*.py"), *root.parent.joinpath("approval").glob("*.py")]:
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "execution" not in (node.module or "")
            if isinstance(node, ast.Import):
                assert all("execution" not in alias.name for alias in node.names)
        assert "SUBMITTING" not in path.read_text()
