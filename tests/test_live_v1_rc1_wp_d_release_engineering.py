"""RC1 WP-D Release Engineering tests: startup, config validation, readiness, runbook, manifest, and secret scan."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from btc_quant_agent import api
from btc_quant_agent.approval.store import LiveStore
from btc_quant_agent.config import AppConfig, ExecutionConfig, LiveV1Config, StorageConfig
from btc_quant_agent.decision.risk import RiskCompilerV1, RiskPolicyV1
from btc_quant_agent.decision.service import TacticalLiveService
from btc_quant_agent.position_supervisor.kill_switch import KillSwitch

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT
    / "evidence/v0.5.5/live_v1/RC1/WP_D/B_LINE_INITIAL_USABLE_RELEASE_V1_RC1_MANIFEST.json"
)
RUNBOOK_PATH = ROOT / "docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md"
ENV_EXAMPLE_PATH = ROOT / ".env.example"


def _clear_live_env(monkeypatch: pytest.MonkeyPatch) -> None:
    prefixes = (
        "BTC_QUANT_LIVE_",
        "FEISHU_",
        "BINANCE_",
        "OPENAI_",
        "REAL_FUNDS_",
        "LIVE_APPROVAL_",
        "AUTONOMOUS_LIVE",
    )
    for key in list(os.environ):
        if key.startswith(prefixes):
            monkeypatch.delenv(key, raising=False)


def _mock_host_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = AppConfig(storage=StorageConfig(sqlite_path=str(tmp_path / "quant.db")))
    monkeypatch.setattr(api, "load_config", lambda: cfg)
    monkeypatch.setattr(
        "btc_quant_agent.service.QuantService.health",
        lambda self: {"status": "OK", "binance_public_data": True},
    )


# ---------------------------------------------------------------------------
# 1. Fail-Early Startup & Configuration Validation Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("env_updates", "expected_match"),
    [
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "LIVE",
            },
            "LIVE is unavailable in RC1",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_EXECUTION_MODE": "LIVE",
            },
            "LIVE is unavailable in RC1",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "DRY_RUN",
                "BTC_QUANT_LIVE_EXECUTION_MODE": "TESTNET",
            },
            "Conflicting BTC_QUANT_LIVE_V1_EXECUTION_MODE and BTC_QUANT_LIVE_EXECUTION_MODE",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "AUTONOMOUS",
            },
            "BTC_QUANT_LIVE_V1_EXECUTION_MODE must be DRY_RUN or TESTNET",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "TESTNET",
                "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED": "false",
            },
            "TESTNET requires explicit execution opt-in",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "TESTNET",
                "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED": "true",
            },
            "BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "TESTNET",
                "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED": "true",
                "BINANCE_TESTNET_API_KEY": "k",
                "BINANCE_TESTNET_API_SECRET": "s",
                "BINANCE_TESTNET_FAPI_BASE_URL": "https://fapi.binance.com",
            },
            "BINANCE_TESTNET_FAPI_BASE_URL must be https://testnet.binancefuture.com",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_EXECUTION_MODE": "TESTNET",
                "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED": "true",
                "BINANCE_TESTNET_API_KEY": "k",
                "BINANCE_TESTNET_API_SECRET": "s",
                "BINANCE_TESTNET_WS_BASE_URL": "https://not-ws.example.com",
            },
            "BINANCE_TESTNET_WS_BASE_URL must be a valid Binance Futures Testnet",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BINANCE_API_KEY": "mainnet-forbidden",
            },
            "Forbidden live/mainnet credential variable BINANCE_API_KEY",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "REAL_FUNDS_WRITE_AUTHORITY": "ENABLED",
            },
            "REAL_FUNDS_WRITE_AUTHORITY must be NONE",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "LIVE_APPROVAL_ONLY": "AUTHORIZED",
            },
            "LIVE_APPROVAL_ONLY must be NOT_AUTHORIZED",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "AUTONOMOUS_LIVE": "ALLOWED",
            },
            "AUTONOMOUS_LIVE must be FORBIDDEN",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_CODEX_ENABLED": "maybe",
            },
            "BTC_QUANT_LIVE_CODEX_ENABLED must be true or false",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_CODEX_ENABLED": "true",
                "BTC_QUANT_LIVE_CODEX_MODEL": "",
            },
            "codex_model is required when Codex is enabled",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_REST_RECONCILE_SECONDS": "not-a-float",
            },
            "BTC_QUANT_LIVE_V1_REST_RECONCILE_SECONDS must be a finite number",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_REST_RECONCILE_SECONDS": "10",
            },
            "rest_reconcile_seconds must be 30 to 60",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_ANALYSIS_TIMEOUT": "-5",
            },
            "BTC_QUANT_LIVE_ANALYSIS_TIMEOUT must be a positive finite number",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_CASE_TTL_MS": "0",
            },
            "BTC_QUANT_LIVE_CASE_TTL_MS must be a positive integer",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_DB_PATH": ":memory:",
            },
            "BTC_QUANT_LIVE_V1_DB_PATH must be a durable filesystem path",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_SYMBOL": "   ",
            },
            "BTC_QUANT_LIVE_V1_SYMBOL must not be empty",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_V1_WS_URL": "https://fstream.binance.com",
            },
            "BTC_QUANT_LIVE_V1_WS_URL must be a ws:// or wss:// URL",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "BTC_QUANT_LIVE_RISK_POLICY_JSON": "{not-json",
            },
            "BTC_QUANT_LIVE_RISK_POLICY_JSON is invalid",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "FEISHU_APP_ID": "cli_test_only_one",
            },
            "Incomplete Feishu outbound configuration",
        ),
        (
            {
                "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED": "true",
                "FEISHU_RECEIVE_ID_TYPE": "invalid_type",
            },
            "FEISHU_RECEIVE_ID_TYPE must be one of",
        ),
    ],
)
def test_startup_rejects_missing_or_invalid_configuration_early(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    env_updates: dict[str, str],
    expected_match: str,
) -> None:
    _clear_live_env(monkeypatch)
    _mock_host_config(tmp_path, monkeypatch)
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_DB_PATH", str(tmp_path / "live_v1.db"))
    for k, v in env_updates.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(ValueError, match=expected_match):
        api.create_app()


def test_startup_rejects_host_allow_live_when_live_v1_enabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_live_env(monkeypatch)
    cfg = AppConfig(
        storage=StorageConfig(sqlite_path=str(tmp_path / "quant.db")),
        execution=ExecutionConfig(mode="live", allow_live=True),
    )
    monkeypatch.setattr(api, "load_config", lambda: cfg)
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_DB_PATH", str(tmp_path / "live_v1.db"))
    with pytest.raises(ValueError, match="RC1 forbids execution.allow_live=true"):
        api.create_app()


# ---------------------------------------------------------------------------
# 2. Machine-Readable Readiness & Structured Lifespan Logging Tests
# ---------------------------------------------------------------------------


def _route_endpoint(app: Any, path: str) -> Any:
    for route in app.routes:
        if getattr(route, "path", None) == path:
            ep = getattr(route, "endpoint", None)
            if ep is not None:
                return ep
    raise AssertionError(f"route not found: {path}")


def test_disabled_mode_readiness_has_all_required_fields_and_creates_no_live_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_live_env(monkeypatch)
    _mock_host_config(tmp_path, monkeypatch)
    live_db = tmp_path / "absent_live_v1.db"
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_DB_PATH", str(live_db))

    app = api.create_app()
    health_ep = _route_endpoint(app, "/health")
    exec_ep = _route_endpoint(app, "/execution/status")

    health_res = health_ep()
    exec_res = exec_ep()
    readiness = health_res["live_v1_readiness"]
    assert exec_res["live_v1_readiness"] == readiness

    for field in api.READINESS_REQUIRED_FIELDS:
        assert field in readiness, f"missing readiness field: {field}"

    assert readiness["service_started"] is False
    assert readiness["database_ready"] is False
    assert readiness["migration_ready"] is False
    assert readiness["market_source_ready"] is False
    assert readiness["analysis_backend_ready"] is False
    assert readiness["approval_backend_state"] == "DISABLED"
    assert readiness["account_stream_state"] == "DISABLED"
    assert readiness["execution_mode"] == "DISABLED"
    assert readiness["kill_switch_state"] == "DISABLED"
    assert readiness["safety_authority"] == api.RC1_SAFETY_AUTHORITY
    assert not live_db.exists()


def test_runtime_readiness_matrix_and_structured_startup_logs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_live_env(monkeypatch)
    _mock_host_config(tmp_path, monkeypatch)
    live_db = tmp_path / "live_v1.db"
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_DB_PATH", str(live_db))
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_RUNTIME_ENABLED", "true")
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_EXECUTION_MODE", "DRY_RUN")
    monkeypatch.setenv("BTC_QUANT_LIVE_RESPONSES_MODEL", "gpt-5.4")
    monkeypatch.setenv("OPENAI_API_KEY", "test-ephemeral-key")
    monkeypatch.setenv("FEISHU_APP_ID", "cli_test_app")
    monkeypatch.setenv("FEISHU_APP_SECRET", "test-ephemeral-secret")
    monkeypatch.setenv("FEISHU_RECEIVE_ID", "oc_test_chat")
    monkeypatch.setenv("FEISHU_VERIFICATION_TOKEN", "test-ephemeral-token")
    monkeypatch.setenv("FEISHU_APPROVER_OPEN_IDS", "ou_approver_1")

    service = TacticalLiveService.from_config(
        LiveV1Config.from_env(),
        SimpleNamespace(scan=Mock(return_value=[])),  # type: ignore[arg-type]
    )
    kill = KillSwitch(live_db)
    runtime = SimpleNamespace(
        tactical_service=service,
        market_stream=SimpleNamespace(is_connected=True),
        account_watch=SimpleNamespace(is_stream_connected=False),
        kill_switch=kill,
        _started=False,
        accepting_risk=False,
        blocked_reason="RUNTIME_NOT_STARTED",
    )

    async def start_runtime() -> None:
        runtime._started = True
        runtime.accepting_risk = True
        runtime.blocked_reason = ""

    async def stop_runtime() -> None:
        runtime._started = False
        runtime.accepting_risk = False
        runtime.blocked_reason = "RUNTIME_STOPPED"

    runtime.start = AsyncMock(side_effect=start_runtime)
    runtime.stop = AsyncMock(side_effect=stop_runtime)
    runtime.status = lambda: {
        "enabled": runtime._started,
        "execution_mode": "DRY_RUN",
        "accepting_risk": runtime.accepting_risk,
        "account_stream_connected": False,
        "blocked_reason": runtime.blocked_reason,
        "tasks_running": 4 if runtime._started else 0,
    }

    app = api.create_app(live_runtime=runtime)  # type: ignore[arg-type]
    exec_ep = _route_endpoint(app, "/execution/status")

    # Before lifespan start: DB & migrations are already initialized by SERIALIZED_SINGLE_RUNTIME_INITIALIZER
    pre_readiness = exec_ep()["live_v1_readiness"]
    assert pre_readiness["service_started"] is False
    assert pre_readiness["database_ready"] is True
    assert pre_readiness["migration_ready"] is True
    assert pre_readiness["kill_switch_state"] == "ARMED"

    caplog.set_level(logging.INFO, logger="btc_quant_agent.live_v1.readiness")

    async def run_lifecycle() -> None:
        async with app.router.lifespan_context(app):
            active = exec_ep()["live_v1_readiness"]
            for field in api.READINESS_REQUIRED_FIELDS:
                assert field in active
            assert active["service_started"] is True
            assert active["database_ready"] is True
            assert active["migration_ready"] is True
            assert active["market_source_ready"] is True
            assert active["analysis_backend_ready"] is True
            assert active["approval_backend_state"] == "READY"
            assert active["account_stream_state"] == "NOT_REQUIRED_DRY_RUN"
            assert active["execution_mode"] == "DRY_RUN"
            assert active["kill_switch_state"] == "ARMED"
            assert active["accepting_risk"] is True

            # Trip kill switch and verify readiness reflects TRIPPED immediately
            kill._latch(["DAILY_LOSS_CAP"], 1_700_000_000_000)
            tripped = exec_ep()["live_v1_readiness"]
            assert tripped["kill_switch_state"] == "TRIPPED"
            assert "DAILY_LOSS_CAP" in tripped["kill_switch_reasons"]

    asyncio.run(run_lifecycle())

    records = [json.loads(r.message) for r in caplog.records if r.name == "btc_quant_agent.live_v1.readiness"]
    events = [r["event"] for r in records]
    assert "LIVE_V1_STARTUP_READINESS" in events
    assert "LIVE_V1_SHUTDOWN_COMPLETE" in events
    startup_log = next(r for r in records if r["event"] == "LIVE_V1_STARTUP_READINESS")
    for field in api.READINESS_REQUIRED_FIELDS:
        assert field in startup_log


def test_runtime_startup_failure_logs_structured_failure_and_reraises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _clear_live_env(monkeypatch)
    _mock_host_config(tmp_path, monkeypatch)
    live_db = tmp_path / "live_v1.db"
    service = TacticalLiveService(
        LiveStore(live_db), None, RiskCompilerV1(RiskPolicyV1())  # type: ignore[arg-type]
    )
    runtime = SimpleNamespace(
        tactical_service=service,
        start=AsyncMock(side_effect=RuntimeError("ACCOUNT_RECONCILIATION_REQUIRED")),
        stop=AsyncMock(),
        status=Mock(return_value={"enabled": False, "execution_mode": "DRY_RUN"}),
    )
    app = api.create_app(live_runtime=runtime)  # type: ignore[arg-type]
    caplog.set_level(logging.INFO, logger="btc_quant_agent.live_v1.readiness")

    async def run_fail() -> None:
        with pytest.raises(RuntimeError, match="ACCOUNT_RECONCILIATION_REQUIRED"):
            async with app.router.lifespan_context(app):
                pass

    asyncio.run(run_fail())
    records = [json.loads(r.message) for r in caplog.records if r.name == "btc_quant_agent.live_v1.readiness"]
    failed = next(r for r in records if r["event"] == "LIVE_V1_STARTUP_READINESS_FAILED")
    assert failed["service_started"] is False
    assert "ACCOUNT_RECONCILIATION_REQUIRED" in failed["error"]


# ---------------------------------------------------------------------------
# 3. Release Manifest Determinism & Mechanical Verification Tests
# ---------------------------------------------------------------------------


def test_release_manifest_determinism_and_luna_mechanical_verification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert MANIFEST_PATH.is_file(), f"Missing manifest at {MANIFEST_PATH}"
    persisted = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    built_1 = api.build_rc1_release_manifest()
    built_2 = api.build_rc1_release_manifest()

    assert built_1 == built_2
    assert persisted == built_1

    # WP-D template must NOT claim 08e81bec... as final release source_sha
    assert persisted["source_sha"] == "UNBOUND_PENDING_RC_INTEGRATION"
    assert persisted["release_identity_state"] == "UNBOUND_PENDING_RC_INTEGRATION"
    assert persisted["work_package_base_sha"] == "08e81bec003d645a0a0582db183a1b6916887eff"
    assert persisted["source_sha"] != persisted["work_package_base_sha"]

    # Startup mechanical certification and RC1 certified Python remain PENDING_WP_A until WP-A binds
    assert persisted["startup_mechanical_certification"] == "PENDING_WP_A"
    assert persisted["supported_python"] == {
        "requires_python": ">=3.11",
        "container_build_python": "3.12",
        "rc1_certified_python": "PENDING_WP_A",
        "rc1_certified_python_source": "PENDING_WP_A",
    }
    assert "supported_versions" not in persisted["supported_python"]
    assert "3.13" not in json.dumps(persisted["supported_python"])

    ok, errors = api.verify_rc1_release_manifest(persisted)
    assert ok is True, errors
    assert errors == []

    # Verify CLI --print-manifest and --verify-manifest
    assert api.main(["--print-manifest"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == persisted

    assert api.main(["--verify-manifest", str(MANIFEST_PATH)]) == 0
    verify_out = json.loads(capsys.readouterr().out)
    assert verify_out == {"errors": [], "valid": True}

    # Verify tampered manifest fails mechanical verification
    tampered = json.loads(json.dumps(persisted))
    tampered["real_money_authority"]["real_funds_write_authority"] = "LIVE"
    tampered_path = tmp_path / "tampered_manifest.json"
    tampered_path.write_text(json.dumps(tampered), encoding="utf-8")
    assert api.main(["--verify-manifest", str(tampered_path)]) == 2
    bad_out = json.loads(capsys.readouterr().out)
    assert bad_out["valid"] is False
    assert any("real_funds_write_authority" in e for e in bad_out["errors"])


def test_release_manifest_integration_source_sha_and_wp_a_certification_binding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # 1. Pre-integration WP-D base SHA (08e81bec...) must NEVER be accepted as final release source_sha
    with pytest.raises(ValueError, match="cannot be the pre-integration WP-D work_package_base_sha"):
        api.build_rc1_release_manifest(source_sha="08e81bec003d645a0a0582db183a1b6916887eff")

    masquerade = api.build_rc1_release_manifest()
    masquerade["source_sha"] = "08e81bec003d645a0a0582db183a1b6916887eff"
    ok, errs = api.verify_rc1_release_manifest(masquerade)
    assert ok is False
    assert any("work_package_base_sha" in e for e in errs)

    # 2. Invalid 40-hex formats must be rejected
    for bad_sha in ("not-a-sha", "abc123", "A" * 40, "g" * 40, ""):
        with pytest.raises(ValueError, match="40-character lowercase hexadecimal"):
            api.build_rc1_release_manifest(source_sha=bad_sha)

    # 3. Unbound template fails when require_bound=True or expected_source_sha is supplied
    unbound = api.build_rc1_release_manifest()
    ok_bound, bound_errs = api.verify_rc1_release_manifest(unbound, require_bound=True)
    assert ok_bound is False
    assert any("UNBOUND_PENDING_RC_INTEGRATION" in e for e in bound_errs)
    assert any("rc1_certified_python is PENDING_WP_A" in e for e in bound_errs)
    assert any("startup_mechanical_certification is PENDING_WP_A" in e for e in bound_errs)

    # 4. Python 3.13 must be rejected unless WP-A independently certifies it
    wp_a_ev = "evidence/v0.5.5/live_v1/RC1/WP_A/EVIDENCE.json"
    with pytest.raises(ValueError, match="Python 3.13 cannot be listed as RC1-certified"):
        api.build_rc1_release_manifest(
            rc1_certified_python=["3.12", "3.13"],
            wp_a_evidence_identity=wp_a_ev,
        )

    # 5. Binding rc1_certified_python or startup_mechanical_certification without WP-A evidence fails
    with pytest.raises(ValueError, match="accepted wp_a_evidence_identity"):
        api.build_rc1_release_manifest(
            rc1_certified_python=["3.12"],
            wp_a_evidence_identity=None,
        )
    with pytest.raises(ValueError, match="accepted wp_a_evidence_identity"):
        api.build_rc1_release_manifest(
            startup_mechanical_certification="CERTIFIED_BY_WP_A",
            wp_a_evidence_identity=None,
        )

    # 6. Full integration-time binding with valid 40-hex source_sha and WP-A evidence passes
    integration_sha = "a" * 40
    integration_parent = "b" * 40
    bound_manifest = api.build_rc1_release_manifest(
        source_sha=integration_sha,
        parent_sha=integration_parent,
        rc1_certified_python=["3.12"],
        startup_mechanical_certification="CERTIFIED_BY_WP_A",
        wp_a_evidence_identity=wp_a_ev,
        require_bound_source_sha=True,
    )
    assert bound_manifest["source_sha"] == integration_sha
    assert bound_manifest["parent_sha"] == integration_parent
    assert bound_manifest["release_identity_state"] == "BOUND_RC_INTEGRATION"
    assert bound_manifest["startup_mechanical_certification"] == "CERTIFIED_BY_WP_A"
    assert bound_manifest["supported_python"]["rc1_certified_python"] == ["3.12"]
    assert bound_manifest["supported_python"]["rc1_certified_python_source"] == wp_a_ev

    ok_full, full_errs = api.verify_rc1_release_manifest(
        bound_manifest,
        expected_source_sha=integration_sha,
        require_bound=True,
    )
    assert ok_full is True, full_errs

    bound_path = tmp_path / "bound_manifest.json"
    assert (
        api.main(
            [
                "--print-manifest",
                "--source-sha",
                integration_sha,
                "--parent-sha",
                integration_parent,
                "--rc1-certified-python",
                "3.12",
                "--startup-certification",
                "CERTIFIED_BY_WP_A",
                "--wp-a-evidence",
                wp_a_ev,
                "--require-bound",
            ]
        )
        == 0
    )
    bound_path.write_text(capsys.readouterr().out, encoding="utf-8")
    assert (
        api.main(
            [
                "--verify-manifest",
                str(bound_path),
                "--source-sha",
                integration_sha,
                "--require-bound",
            ]
        )
        == 0
    )
    capsys.readouterr()


# ---------------------------------------------------------------------------
# 4. Config Template, Docs Command Smoke & Runbook Completeness Tests
# ---------------------------------------------------------------------------


def test_env_example_and_docs_command_smoke_in_dry_run_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _clear_live_env(monkeypatch)
    _mock_host_config(tmp_path, monkeypatch)

    env_text = ENV_EXAMPLE_PATH.read_text(encoding="utf-8")
    parsed_env: dict[str, str] = {}
    for raw_line in env_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, sep, value = line.partition("=")
        assert sep == "=", f"Invalid line in .env.example: {raw_line}"
        parsed_env[key.strip()] = value.strip()

    required_template_keys = {
        "BTC_QUANT_CONFIG",
        "BTC_QUANT_DB_PATH",
        "BTC_QUANT_LIVE_V1_DB_PATH",
        "BTC_QUANT_API_TOKEN",
        "BTC_QUANT_LIVE_V1_RUNTIME_ENABLED",
        "BTC_QUANT_LIVE_V1_ENABLED",
        "BTC_QUANT_LIVE_V1_EXECUTION_MODE",
        "BTC_QUANT_LIVE_V1_TESTNET_EXECUTION_ENABLED",
        "REAL_FUNDS_WRITE_AUTHORITY",
        "LIVE_APPROVAL_ONLY",
        "AUTONOMOUS_LIVE",
        "BTC_QUANT_LIVE_V1_SYMBOL",
        "BTC_QUANT_LIVE_V1_ACCOUNT_ID",
        "BTC_QUANT_LIVE_V1_WS_URL",
        "BTC_QUANT_LIVE_V1_REST_RECONCILE_SECONDS",
        "BTC_QUANT_LIVE_V1_POSITION_POLL_SECONDS",
        "BTC_QUANT_LIVE_V1_OUTBOX_POLL_SECONDS",
        "BTC_QUANT_LIVE_RESPONSES_MODEL",
        "OPENAI_API_KEY",
        "BTC_QUANT_LIVE_CODEX_ENABLED",
        "BTC_QUANT_LIVE_CODEX_MODEL",
        "BTC_QUANT_LIVE_ANALYSIS_TIMEOUT",
        "BTC_QUANT_LIVE_CASE_TTL_MS",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "FEISHU_RECEIVE_ID",
        "FEISHU_RECEIVE_ID_TYPE",
        "FEISHU_VERIFICATION_TOKEN",
        "FEISHU_ENCRYPT_KEY",
        "FEISHU_APPROVER_OPEN_IDS",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_TESTNET_API_SECRET",
        "BINANCE_TESTNET_FAPI_BASE_URL",
        "BINANCE_TESTNET_WS_BASE_URL",
    }
    assert required_template_keys <= set(parsed_env)
    assert "BINANCE_API_KEY" not in parsed_env
    assert "BINANCE_API_SECRET" not in parsed_env

    for k, v in parsed_env.items():
        if v:
            monkeypatch.setenv(k, v)
    monkeypatch.setenv("BTC_QUANT_LIVE_V1_DB_PATH", str(tmp_path / "smoke_live_v1.db"))

    # Execute documented --check-config smoke command
    assert api.main(["--check-config"]) == 0
    smoke_readiness = json.loads(capsys.readouterr().out)
    assert smoke_readiness["database_ready"] is True
    assert smoke_readiness["migration_ready"] is True
    assert smoke_readiness["execution_mode"] == "DRY_RUN"
    assert smoke_readiness["kill_switch_state"] == "ARMED"
    assert smoke_readiness["startup_contract"] == "SERIALIZED_SINGLE_RUNTIME_INITIALIZER"


def test_canonical_startup_unambiguous_across_dockerfile_compose_and_runbook() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    runbook = RUNBOOK_PATH.read_text(encoding="utf-8")
    arch = (ROOT / "docs/CURRENT_ARCHITECTURE.md").read_text(encoding="utf-8")

    assert "quantctl\", \"daemon\"" not in dockerfile
    assert "quantctl\", \"daemon\"" not in compose
    assert "btc_quant_agent.api:app" in dockerfile
    assert "btc_quant_agent.api:app" in compose
    assert api.RC1_CANONICAL_STARTUP_COMMAND in runbook
    assert api.RC1_CANONICAL_STARTUP_COMMAND in arch

    required_runbook_sections = (
        "First Start",
        "Normal Start",
        "Stop",
        "Restart & Crash Recovery",
        "Stale State",
        "Provider Outage",
        "Binance Outage",
        "Feishu Outage",
        "TESTNET Transport Uncertainty",
        "Partial Fill Handling",
        "Protection Uncertainty",
        "Kill Switch",
        "Operator Recovery Procedure",
        "Evidence, Manifest & Log Locations",
    )
    for section in required_runbook_sections:
        assert section in runbook, f"Missing runbook section: {section}"


# ---------------------------------------------------------------------------
# 5. No Secret Literal Scan Across Newly Added / Modified Release Artifacts
# ---------------------------------------------------------------------------


def test_no_secret_literals_in_release_artifacts() -> None:
    release_files = [
        ROOT / ".env.example",
        ROOT / "Dockerfile",
        ROOT / "docker-compose.yml",
        ROOT / "docs/LIVE_V1_RC1_OPERATIONAL_RUNBOOK.md",
        ROOT / "docs/CURRENT_ARCHITECTURE.md",
        ROOT / "src/btc_quant_agent/api.py",
        MANIFEST_PATH,
    ]
    evidence_file = ROOT / "evidence/v0.5.5/live_v1/RC1/WP_D/EVIDENCE.json"
    if evidence_file.is_file():
        release_files.append(evidence_file)

    secret_patterns = (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9-]+"),
    )
    secret_env_keys = {
        "OPENAI_API_KEY",
        "FEISHU_APP_SECRET",
        "FEISHU_VERIFICATION_TOKEN",
        "FEISHU_ENCRYPT_KEY",
        "FEISHU_WEBHOOK_SECRET",
        "BINANCE_TESTNET_API_KEY",
        "BINANCE_TESTNET_API_SECRET",
        "BTC_QUANT_API_TOKEN",
    }

    for path in release_files:
        text = path.read_text(encoding="utf-8")
        for pattern in secret_patterns:
            assert pattern.search(text) is None, f"Secret pattern matched in {path}"

    for raw_line in ENV_EXAMPLE_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, _, val = line.partition("=")
        if key.strip() in secret_env_keys:
            assert val.strip() == "", f"Secret key {key} must be empty in .env.example"
