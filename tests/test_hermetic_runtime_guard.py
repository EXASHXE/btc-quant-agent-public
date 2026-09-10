"""Adversarial proofs for repository-wide test hermeticity boundaries."""

from __future__ import annotations

import json
import os
import sqlite3
import urllib.parse
from pathlib import Path
from typing import Any

import pytest

from btc_quant_agent.config import DataConfig
from btc_quant_agent.data.binance import BinancePublicClient
from btc_quant_agent.economic.qualification import FormalBenchmarkSuite
from btc_quant_agent.execution.binance_signed import BinanceSignedClient
from btc_quant_agent.microstructure_research import H39ResearchEngine, _open_sqlite


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
        canonical_candles_path=tmp_path / "canonical_candles.sqlite3",
    )
    with pytest.raises(BaseException, match="FORBIDDEN_H39_OUTCOME_ACCESS"):
        engine.get_canonical_1m_candles(0, 60_000)
    assert h39_outcome_access_spy == ["get_canonical_1m_candles"]


# =============================================================================
# AS-01: Atomic replace / rename bypass repairs and regressions
# =============================================================================


def test_hermetic_rename_01_os_replace_safe_to_forbidden(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    src = tmp_path / "safe.tmp"
    src.write_bytes(b"safe-source-bytes")
    dst = (tmp_path / "forbidden.db").resolve()
    dst.write_bytes(b"original-forbidden-bytes")
    hermetic_guard.forbid_file(dst)

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS.*os\.replace:destination"
    ):
        os.replace(src, dst)

    assert src.read_bytes() == b"safe-source-bytes"
    assert hermetic_guard.read_bytes_unguarded(dst) == b"original-forbidden-bytes"


def test_hermetic_rename_02_os_rename_forbidden_to_safe(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    src = (tmp_path / "forbidden_src.db").resolve()
    src.write_bytes(b"forbidden-source-bytes")
    hermetic_guard.forbid_file(src)
    dst = (tmp_path / "safe_dst.tmp").resolve()

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS.*os\.rename:source"
    ):
        os.rename(src, dst)

    assert hermetic_guard.read_bytes_unguarded(src) == b"forbidden-source-bytes"
    assert not dst.exists()


def test_hermetic_rename_03_path_replace_safe_to_forbidden(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    src = tmp_path / "safe.tmp"
    src.write_bytes(b"safe-source-bytes")
    dst_file = (tmp_path / "forbidden_file.db").resolve()
    dst_file.write_bytes(b"original-file-bytes")
    hermetic_guard.forbid_file(dst_file)

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS.*Path\.replace:destination"
    ):
        src.replace(dst_file)

    assert src.read_bytes() == b"safe-source-bytes"
    assert hermetic_guard.read_bytes_unguarded(dst_file) == b"original-file-bytes"

    forbidden_root = (tmp_path / "forbidden_root").resolve()
    forbidden_root.mkdir()
    hermetic_guard.forbid_root(forbidden_root)
    dst_in_root = forbidden_root / "target.tmp"

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_OPERATIONAL_ROOT_ACCESS.*Path\.replace:destination"
    ):
        src.replace(dst_in_root)

    assert src.read_bytes() == b"safe-source-bytes"
    assert not hermetic_guard.exists_unguarded(dst_in_root)


def test_hermetic_rename_04_path_rename_forbidden_to_safe(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    src = (tmp_path / "forbidden_src.db").resolve()
    src.write_bytes(b"forbidden-source-bytes")
    hermetic_guard.forbid_file(src)
    dst = (tmp_path / "safe_dst.tmp").resolve()

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS.*Path\.rename:source"
    ):
        src.rename(dst)

    assert hermetic_guard.read_bytes_unguarded(src) == b"forbidden-source-bytes"
    assert not dst.exists()


def test_hermetic_rename_05_symlink_alias(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    forbidden_file = (tmp_path / "forbidden.db").resolve()
    forbidden_file.write_bytes(b"original-sentinel")
    hermetic_guard.forbid_file(forbidden_file)

    alias = tmp_path / "alias_to_forbidden.db"
    alias.symlink_to(forbidden_file)

    safe_src = tmp_path / "safe.tmp"
    safe_src.write_bytes(b"safe-bytes")

    # Safe source -> forbidden alias destination must fail
    with pytest.raises(BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        os.replace(safe_src, alias)

    assert hermetic_guard.read_bytes_unguarded(forbidden_file) == b"original-sentinel"
    assert safe_src.read_bytes() == b"safe-bytes"

    # Forbidden alias source -> safe destination must fail
    safe_dst = (tmp_path / "safe_dst.tmp").resolve()
    with pytest.raises(BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        os.replace(alias, safe_dst)

    assert hermetic_guard.read_bytes_unguarded(forbidden_file) == b"original-sentinel"
    assert not safe_dst.exists()


def test_hermetic_rename_06_safe_to_safe_positive_control(
    tmp_path: Path,
) -> None:
    src = tmp_path / "safe_src.txt"
    src.write_text("positive-control-content")
    dst = tmp_path / "safe_dst.txt"

    dst_result = src.replace(dst)
    assert dst_result == dst
    assert dst.read_text() == "positive-control-content"
    assert not src.exists()

    src2 = tmp_path / "safe_src2.txt"
    src2.write_text("content-2")
    dst2 = tmp_path / "safe_dst2.txt"
    os.rename(src2, dst2)
    assert dst2.read_text() == "content-2"
    assert not src2.exists()


def test_hermetic_public_formal_benchmark_suite_write_is_blocked_on_forbidden_file(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    suite = FormalBenchmarkSuite(
        "synthetic-comparison", "synthetic-candidate", None, None, None, None
    )

    # Test 1: var/quant.db style forbidden file
    fake_quant_db = (tmp_path / "quant.db").resolve()
    fake_quant_db.write_bytes(b"original-quant-db-sentinel")
    hermetic_guard.forbid_file(fake_quant_db)

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_OPERATIONAL_FILE_ACCESS.*os\.replace:destination"
    ):
        suite.write(fake_quant_db)

    assert hermetic_guard.read_bytes_unguarded(fake_quant_db) == b"original-quant-db-sentinel"

    # Test 2: Final Holdout file
    fake_holdout = tmp_path.resolve() / "final_holdout.json"
    hermetic_guard.write_bytes_unguarded(fake_holdout, b"original-holdout-sentinel")

    with pytest.raises(
        BaseException, match=r"FORBIDDEN_FINAL_HOLDOUT_ACCESS.*os\.replace:destination"
    ):
        suite.write(fake_holdout)

    assert hermetic_guard.read_bytes_unguarded(fake_holdout) == b"original-holdout-sentinel"

    # Test 3: Positive control under tmp_path
    safe_target = tmp_path / "safe_suite.json"
    suite.write(safe_target)
    assert safe_target.exists()
    payload = json.loads(safe_target.read_text(encoding="utf-8"))
    assert payload["artifact_type"] == "P6_BENCHMARK_SUITE"


# =============================================================================
# AS-02: SQLite URI normalization and localhost bypass repairs and regressions
# =============================================================================


def test_sqlite_01_plain_path_blocked(tmp_path: Path, hermetic_guard: Any) -> None:
    db_path = (tmp_path / "forbidden.sqlite3").resolve()
    db_path.write_bytes(b"sentinel")
    hermetic_guard.forbid_file(db_path)

    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        sqlite3.connect(db_path)


def test_sqlite_02_absolute_uri_blocked(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    db_path = (tmp_path / "forbidden.sqlite3").resolve()
    db_path.write_bytes(b"sentinel")
    hermetic_guard.forbid_file(db_path)

    uri = f"file://{db_path}"
    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        sqlite3.connect(uri, uri=True)


def test_sqlite_03_localhost_authority_uri_blocked_astra_reproduction(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    db_path = (tmp_path / "forbidden.sqlite3").resolve()
    db_path.write_bytes(b"sentinel")
    hermetic_guard.forbid_file(db_path)

    uri = f"file://localhost{db_path}?mode=ro"
    with (
        pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_FILE_ACCESS"),
        _open_sqlite(uri, uri=True),
    ):
        pass


def test_sqlite_04_percent_encoded_path_blocked(
    tmp_path: Path, hermetic_guard: Any
) -> None:
    space_dir = tmp_path / "dir with spaces"
    space_dir.mkdir()
    db_path = (space_dir / "encoded.sqlite3").resolve()
    db_path.write_bytes(b"sentinel")
    hermetic_guard.forbid_file(db_path)

    encoded_path = urllib.parse.quote(str(db_path))
    uri = f"file://localhost{encoded_path}"
    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        sqlite3.connect(uri, uri=True)


@pytest.mark.parametrize(
    "query",
    ("?mode=ro", "?mode=rw", "?immutable=1", "?mode=ro&cache=private"),
)
def test_sqlite_05_query_parameters_blocked(
    tmp_path: Path, hermetic_guard: Any, query: str
) -> None:
    db_path = (tmp_path / "forbidden.sqlite3").resolve()
    db_path.write_bytes(b"sentinel")
    hermetic_guard.forbid_file(db_path)

    uri = f"file://localhost{db_path}{query}"
    with pytest.raises(BaseException, match="FORBIDDEN_OPERATIONAL_FILE_ACCESS"):
        sqlite3.connect(uri, uri=True)


def test_sqlite_06_safe_uri_positive_control(tmp_path: Path) -> None:
    safe_db = (tmp_path / "safe.sqlite3").resolve()
    uri = f"file://localhost{safe_db}?mode=rwc"

    with sqlite3.connect(uri, uri=True) as conn:
        conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'ok')")
        conn.commit()

    with sqlite3.connect(
        f"file://localhost{safe_db}?mode=ro", uri=True
    ) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, val FROM t")
        row = cursor.fetchone()
        assert row == (1, "ok")
