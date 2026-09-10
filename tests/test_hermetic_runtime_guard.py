"""Adversarial proofs for repository-wide test hermeticity boundaries."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import BinancePublicClient
from btc_quant_agent.execution.binance_signed import BinanceSignedClient
from btc_quant_agent.microstructure_research import H39ResearchEngine


@pytest.mark.parametrize(
    "relative_root",
    (Path("data/forward"), Path("data/research/h39_validation")),
)
def test_resolved_operational_roots_are_blocked_in_populated_fake_checkout(
    tmp_path: Path, hermetic_guard: Any, relative_root: Path
) -> None:
    fake_repo = tmp_path / "populated_checkout"
    forbidden_root = fake_repo / relative_root
    forbidden_root.mkdir(parents=True)
    sentinel = forbidden_root / "sentinel.sqlite3"
    sentinel.write_bytes(b"must-not-be-read-or-modified")
    before = sentinel.read_bytes()
    hermetic_guard.forbid_root(forbidden_root)

    alias = tmp_path / "resolved-alias.sqlite3"
    alias.symlink_to(sentinel)
    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_ROOT_ACCESS"):
        alias.read_bytes()

    assert before == b"must-not-be-read-or-modified"


def test_runtime_quant_database_is_blocked_before_sqlite_connect(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    runtime_db = tmp_path / "fake_runtime" / "var" / "quant.db"
    runtime_db.parent.mkdir(parents=True)
    runtime_db.write_bytes(b"sentinel")
    hermetic_guard.forbid_file(runtime_db)

    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        sqlite3.connect(runtime_db)


def test_final_holdout_is_blocked_before_open(tmp_path: Path) -> None:
    holdout = tmp_path / "data" / "final_holdout" / "sealed.sqlite3"
    with pytest.raises(BaseException, match="FORBIDDEN_FINAL_HOLDOUT_ACCESS"):
        holdout.read_bytes()


def test_external_exchange_network_is_blocked() -> None:
    client = BinancePublicClient(DataConfig())
    with pytest.raises(BaseException, match="FORBIDDEN_EXTERNAL_NETWORK_ACCESS"):
        client._get("/fapi/v1/time")


@pytest.mark.parametrize(
    "base_url",
    ("https://fapi.binance.com", "https://testnet.binancefuture.com"),
)
def test_live_and_testnet_execution_transports_are_blocked(base_url: str) -> None:
    client = BinanceSignedClient(base_url, "unused-key", "unused-secret")
    with pytest.raises(BaseException, match="FORBIDDEN_EXECUTION_TRANSPORT"):
        client.place_order(symbol="BTCUSDT", side="BUY", type="MARKET", quantity="0.001")


def test_default_h39_engine_cannot_fall_back_to_operational_roots() -> None:
    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_ROOT_ACCESS"):
        H39ResearchEngine().evaluate_validation_status()


def test_metadata_only_outcome_spy_fails_loudly(
    tmp_path: Path, h39_outcome_access_spy: list[str]
) -> None:
    engine = H39ResearchEngine(
        microstructure_root=tmp_path / "microstructure",
        opportunity_store_path=tmp_path / "opportunity.sqlite3",
    )
    with pytest.raises(BaseException, match="FORBIDDEN_H39_OUTCOME_ACCESS"):
        engine.get_canonical_1m_candles(0, 60_000)
    assert h39_outcome_access_spy == ["get_canonical_1m_candles"]
