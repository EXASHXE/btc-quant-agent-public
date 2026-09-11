"""B08 fail-closed clock-domain and explicit configuration regressions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from btc_quant_agent.config import AppConfig, ExecutionConfig, load_config
from btc_quant_agent.data.binance import BinanceDataError, BinancePublicClient
from btc_quant_agent.domain import DerivativesSnapshot, ScanResult
from btc_quant_agent.service import QuantService
from btc_quant_agent.storage import Repository
from btc_quant_agent.time_boundary import (
    ClockBoundaryError,
    monotonic_elapsed_ms,
    validate_availability,
    validate_clock_skew,
)


@pytest.mark.parametrize("skew", [-5_000, 5_000])
def test_local_exchange_skew_exact_boundaries_are_accepted(skew: int) -> None:
    validate_clock_skew(
        exchange_time_ms=100_000,
        receipt_time_ms=100_000 + skew,
        max_abs_skew_ms=5_000,
    )


@pytest.mark.parametrize("skew", [-5_001, 5_001])
def test_local_exchange_skew_outside_boundaries_fails(skew: int) -> None:
    with pytest.raises(ClockBoundaryError, match="clock skew"):
        validate_clock_skew(
            exchange_time_ms=100_000,
            receipt_time_ms=100_000 + skew,
            max_abs_skew_ms=5_000,
        )


def test_availability_exact_boundary_stale_and_future() -> None:
    validate_availability(available_at_ms=1_000, decision_time_ms=1_000, max_age_ms=100)
    validate_availability(available_at_ms=900, decision_time_ms=1_000, max_age_ms=100)
    with pytest.raises(ClockBoundaryError, match="not yet available"):
        validate_availability(
            available_at_ms=1_001, decision_time_ms=1_000, max_age_ms=100
        )
    with pytest.raises(ClockBoundaryError, match="stale"):
        validate_availability(available_at_ms=899, decision_time_ms=1_000, max_age_ms=100)


def test_monotonic_elapsed_is_independent_of_wall_clock_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wall = iter([100.0, 50.0])
    monkeypatch.setattr("time.time", lambda: next(wall))
    assert monotonic_elapsed_ms(10.0, 10.25) == 250.0
    assert __import__("time").time() == 100.0
    assert __import__("time").time() == 50.0
    with pytest.raises(ClockBoundaryError, match="moved backwards"):
        monotonic_elapsed_ms(10.0, 9.0)


def _endpoint_payload(path: str) -> object:
    values: dict[str, object] = {
        "/fapi/v1/premiumIndex": {
            "markPrice": "100",
            "indexPrice": "100",
            "lastFundingRate": "0",
            "time": 1_000,
        },
        "/fapi/v1/openInterest": {"openInterest": "10", "time": 1_000},
        "/futures/data/openInterestHist": [
            {"sumOpenInterest": "9", "timestamp": 900},
            {"sumOpenInterest": "10", "timestamp": 1_000},
        ],
        "/futures/data/takerlongshortRatio": [
            {"buySellRatio": "1", "timestamp": 1_000}
        ],
        "/futures/data/globalLongShortAccountRatio": [
            {"longShortRatio": "1", "timestamp": 1_000}
        ],
        "/futures/data/basis": [{"basisRate": "0", "timestamp": 1_000}],
    }
    return values[path]


@pytest.mark.parametrize("wall_times", [(2.0, 1.0), (1.0, 100.0)])
def test_derivative_collection_rejects_ntp_rollback_or_jump(
    wall_times: tuple[float, float],
) -> None:
    client = BinancePublicClient(AppConfig().data)
    with (
        patch.object(client, "_get", side_effect=lambda path, _params: _endpoint_payload(path)),
        patch("btc_quant_agent.data.binance.time.time", side_effect=wall_times),
        patch("btc_quant_agent.data.binance.time.monotonic", side_effect=[10.0, 10.1]),
        pytest.raises(BinanceDataError, match="wall clock jumped"),
    ):
        client.collect_derivatives("BTCUSDT")


def test_exact_candle_close_boundary_is_not_prematurely_closed() -> None:
    client = BinancePublicClient(AppConfig().data)
    row = [1_000, "100", "101", "99", "100", "10", 60_999, "1000", 1, "5"]
    assert client._parse_klines([row], "BTCUSDT", "1m", 60_999) == []
    parsed = client._parse_klines([row], "BTCUSDT", "1m", 61_000)
    assert len(parsed) == 1
    assert parsed[0].available_at_ms == 61_000
    assert parsed[0].open_time_ms == 1_000


@pytest.mark.parametrize("skew", [-5_000, 5_000])
def test_service_uses_validated_receipt_boundary_without_hidden_offset(
    tmp_path: Path, skew: int
) -> None:
    exchange = 100_000
    receipt = exchange + skew
    client = MagicMock()
    client.server_time_ms.return_value = exchange
    client.klines.return_value = []
    client.derivatives.return_value = DerivativesSnapshot(observed_at_ms=receipt)
    engine = MagicMock()
    engine.invalidation_reason.return_value = None
    engine.scan.return_value = ScanResult("WAIT", "OK", "none")
    repository = Repository(str(tmp_path / "runtime.db"))
    service = QuantService(AppConfig(), repository, client, MagicMock())
    with patch("btc_quant_agent.service.QuantEngine", return_value=engine):
        service.scan(notify=False)
    assert engine.scan.call_args.args[4] == receipt


def test_service_rejects_impossible_receipt_before_runtime_mutation(tmp_path: Path) -> None:
    client = MagicMock()
    client.server_time_ms.return_value = 100_000
    client.klines.return_value = []
    client.derivatives.return_value = DerivativesSnapshot(observed_at_ms=105_001)
    repository = Repository(str(tmp_path / "runtime.db"))
    service = QuantService(AppConfig(), repository, client, MagicMock())
    with pytest.raises(ClockBoundaryError, match="clock skew"):
        service.scan(notify=False)


def test_explicit_missing_and_environment_missing_config_paths_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = tmp_path / "missing.toml"
    with pytest.raises(FileNotFoundError, match="explicit"):
        load_config(missing)
    monkeypatch.setenv("BTC_QUANT_CONFIG", str(missing))
    with pytest.raises(FileNotFoundError, match="BTC_QUANT_CONFIG"):
        load_config()


def test_malformed_unknown_and_unsafe_config_fail_closed(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed.toml"
    malformed.write_text("[execution\nmode = 'live'\n", encoding="utf-8")
    with pytest.raises(Exception):
        load_config(malformed)

    unknown = tmp_path / "unknown.toml"
    unknown.write_text("[executoin]\nmode = 'live'\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown top-level"):
        load_config(unknown)

    typo = tmp_path / "typo.toml"
    typo.write_text("[execution]\nauto_excecute = true\n", encoding="utf-8")
    with pytest.raises(ValueError, match="unknown ExecutionConfig"):
        load_config(typo)

    unsafe = tmp_path / "unsafe.toml"
    unsafe.write_text("[execution]\nauto_execute = 'false'\n", encoding="utf-8")
    with pytest.raises(TypeError, match="must be a boolean"):
        load_config(unsafe)


def test_explicit_path_precedes_environment_and_db_override_is_last(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = tmp_path / "explicit.toml"
    explicit.write_text("[runtime]\nttl_minutes = 11\n", encoding="utf-8")
    environmental = tmp_path / "environment.toml"
    environmental.write_text("[runtime]\nttl_minutes = 22\n", encoding="utf-8")
    monkeypatch.setenv("BTC_QUANT_CONFIG", str(environmental))
    monkeypatch.setenv("BTC_QUANT_DB_PATH", str(tmp_path / "override.db"))
    config = load_config(explicit)
    assert config.runtime.ttl_minutes == 11
    assert config.storage.sqlite_path == str(tmp_path / "override.db")
    assert config.execution == ExecutionConfig()


def test_config_failure_does_not_rewrite_registry_or_enable_execution(
    tmp_path: Path,
) -> None:
    registry = tmp_path / "registry.json"
    original = b'{"campaign":"fixed-identity"}\n'
    registry.write_bytes(original)
    bad = tmp_path / "bad.toml"
    bad.write_text("[execution]\nmode = 'live'\nauto_execute = 'yes'\n", encoding="utf-8")
    with pytest.raises(TypeError):
        load_config(bad)
    assert registry.read_bytes() == original
    assert AppConfig().execution.mode == "disabled"
    assert AppConfig().execution.auto_execute is False
