"""Owner-adopted local semantic contracts; live machine checks remain independent."""

import pytest

from btc_quant_agent.platform.canary.public_io import HttpWsBackend
from btc_quant_agent.platform.canary.public_policy import (
    END,
    REVIEWED_DOCUMENT,
    REVIEW_AUTHORITY,
    PublicStop,
    sha,
    persist_source_denial,
    preflight,
)
from btc_quant_agent.platform.canary.public_runtime import run_public
from .fixtures import Backend, Clock, meta_payload
from .test_transport_scope import transport


def test_baseline_validation_is_local_and_not_feed_qualification(scope, tmp_path):
    t = transport(scope, tmp_path)
    result = t.verify_documents()
    assert len(result) == 1 and result[0]["status"] == "DOCUMENT_BASELINE_VERIFIED_OFFLINE"
    assert result[0]["sha256"] == sha(REVIEWED_DOCUMENT)
    assert not result[0]["observed_feed_quality"]
    assert t.metrics["docs_requests"] == 0 and not t.backend.calls


@pytest.mark.parametrize("file", [REVIEWED_DOCUMENT, REVIEW_AUTHORITY])
def test_baseline_or_approval_tamper_fails_before_any_request(scope, tmp_path, monkeypatch, file):
    t = transport(scope, tmp_path)
    monkeypatch.setattr(
        "btc_quant_agent.platform.canary.public_policy.sha", lambda p: "0" * 64 if p == file else sha(p)
    )
    with pytest.raises(PublicStop, match="REVIEWED_DOCUMENT_BASELINE_MISMATCH"):
        t.verify_documents()
    assert not t.backend.calls


def test_unknown_semantics_cannot_be_silently_promoted(scope, tmp_path):
    t = transport(scope, tmp_path)
    scope.document["unknowns"] = []
    with pytest.raises(PublicStop, match="REVIEWED_DOCUMENT_CONTRACT_DRIFT"):
        t.verify_documents()
    assert not t.backend.calls


def test_finite_runtime_ignores_website_202_and_uses_machine_contract(scope, tmp_path):
    clock = Clock(END - 6000)
    backend = Backend(scope, clock)
    get = backend.get

    def web_unavailable(url, *args, **kwargs):
        if "developers.binance.com" in url:
            raise AssertionError("Runtime must not probe the human website")
        return get(url, *args, **kwargs)

    backend.get = web_unavailable
    result = run_public(scope, enabled=True, clock=clock, backend=backend, output=tmp_path / "run")
    assert result["transport_metrics"]["docs_requests"] == 0
    assert backend.calls[0][0] == "https://fapi.binance.com/fapi/v1/exchangeInfo"
    assert result["documentation_validation_mode"] == "LOCAL_REVIEWED_BASELINE"
    assert result["documentation_recheck"][0]["status"] == "DOCUMENT_BASELINE_VERIFIED_OFFLINE"
    assert result["replay"]["status"] == "PARITY_VERIFIED"
    assert not result["source_qualified"] and not result["shadow_advisory_qualified"]
    assert not result["economically_validated"] and result["sockets_closed"]


@pytest.mark.parametrize("fault", ["rate_limits", "tick"])
def test_machine_contract_drift_still_blocks_after_local_baseline(scope, tmp_path, fault):
    clock = Clock()
    metadata = meta_payload()
    if fault == "rate_limits":
        metadata["rateLimits"] = []
    else:
        metadata["symbols"][0]["filters"][0]["tickSize"] = "0"
    backend = Backend(scope, clock, {"exchangeInfo": (200, metadata)})
    result = run_public(scope, enabled=True, clock=clock, backend=backend, output=tmp_path / "run")
    assert len(backend.calls) == 1
    assert "UNQUALIFIED" in result["stop_reason"]
    assert not result["source_qualified"] and not result["shadow_advisory_qualified"]


def test_native_run_cannot_disable_baseline(scope, tmp_path):
    clock = Clock()
    backend = Backend(scope, clock)
    backend.exposure = "PUBLIC_CANARY"
    with pytest.raises(PublicStop, match="NATIVE_DOCUMENT_BASELINE_REQUIRED"):
        run_public(
            scope, enabled=True, clock=clock, backend=backend, output=tmp_path / "run", verify_docs=False
        )
    assert not backend.calls


def test_api_headers_remain_machine_headers_without_browser_impersonation():
    backend = HttpWsBackend()
    backend.set_guard(lambda: 5)
    try:
        client = backend._http()
        assert client.headers["Accept"] == "application/json"
        assert client.headers["User-Agent"] == "Quant-L4-readonly/1"
        assert "Accept-Language" not in client.headers
    finally:
        backend.close()


def test_observed_native_denial_blocks_restart_but_not_synthetic_replay(scope, tmp_path):
    persist_source_denial(
        {"provider": "binance", "market": "USD_M", "exposure": "PUBLIC_CANARY", "http_status": 451}
    )
    assert "VENUE_ACCESS_DENIED_PERSISTED" in preflight(scope, Clock())["reasons"]
    assert "VENUE_ACCESS_DENIED_PERSISTED" not in preflight(scope, Clock(), native=False)["reasons"]
    backend = Backend(scope, Clock())
    backend.exposure = "PUBLIC_CANARY"
    t = transport(scope, tmp_path, backend=backend)
    with pytest.raises(PublicStop, match="VENUE_ACCESS_DENIED_PERSISTED"):
        t.request("binance_usdm_server_time", {})
    assert not backend.calls


def test_corrupt_native_denial_state_fails_closed(scope):
    from btc_quant_agent.platform.canary import public_policy

    public_policy.ACCESS_DENIAL.write_text("{")
    assert "SOURCE_ACCESS_STATE_INVALID" in preflight(scope, Clock())["reasons"]
