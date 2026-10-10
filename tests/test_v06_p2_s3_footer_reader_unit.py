"""Unit, positive footer-parsing, and S2/R2 errata tests for P2 S3A.

All filesystem operations run exclusively inside ephemeral ``tmp_path`` fixtures
and never touch ``/root/workspace/project/Quant-agent/data``.
"""

from __future__ import annotations

import ast
import struct
from pathlib import Path

import pytest

from scripts.strategy_research.p2_s3_footer_reader import (
    BUDGET_INSUFFICIENT_STOP_CODE,
    CODE_START_SHA,
    CONTROLLER_DISPATCH_SHA,
    CONTROLLER_S2_JOINT_DECISION_SHA,
    ETH_SOL_1M_PERP_STATUS,
    HARNESS_ROOT_NOT_PROVEN_CODE,
    HEADER_STATUS_NOT_VERIFIED,
    IMMUTABLE_OWNER_DATA_ROOT,
    MAX_ATTEMPTED_FS_CALLS,
    MAX_FOOTER_READ_BYTES,
    MAX_TOTAL_FILE_READ_BYTES,
    MAX_TRAILER_READ_BYTES,
    ORIGINAL_STAT_RECEIPT_JSON_SHA256,
    ORIGINAL_STAT_RECEIPT_SHA,
    PROMPT_SHA,
    R1_TO_R2_BTC_SIZE_ERRATA_MAP,
    R2_CONTROLLER_DISPATCH_SHA,
    R2_EXACT_START_SHA,
    R2_PROMPT_SHA,
    S3_SINGLE_PILOT_COMPONENTS,
    S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES,
    S3_SINGLE_PILOT_REL_PATH,
    S3A_R2_TERMINAL_STATUS,
    S3A_TERMINAL_STATUS,
    SYNTHETIC_GRANT_TOKEN_SEMANTICS,
    VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES,
    VERIFIED_C6823DBC_FILE_SIZES_BYTES,
    SingleFileParquetFooterReader,
    build_synthetic_parquet_bytes,
    create_valid_synthetic_grant,
    extract_file_sizes_from_c6823dbc_json,
    load_pinned_c6823dbc_scan_receipt_json,
    materialize_synthetic_pilot_tree,
    run_all_s3a_r2_supplemental_oracle_scenarios,
    run_all_s3a_security_oracle_scenarios,
    verify_posix_fd_platform_support,
)


@pytest.fixture(autouse=True)
def _isolated_test_surrogate_registry():
    # External test fixture lifecycle. Reader checks stay purely in-memory;
    # no stale-tree stat probes hide inside an invocation.
    from scripts.strategy_research.p2_s3_footer_reader import types

    types._FORBIDDEN_SURROGATE_TREES.clear()
    yield
    types._FORBIDDEN_SURROGATE_TREES.clear()


def test_u01_pinned_authority_shas_and_budget_constants() -> None:
    """Verify pinned Controller/Code/Prompt/Stat SHAs and hard S3 budgets."""
    assert CONTROLLER_DISPATCH_SHA == "e150be89bef2540a4aebe7b11e921dd25104fe16"
    assert R2_CONTROLLER_DISPATCH_SHA == "89c1caf07eebd3db81dc16314c3238c037e6fac3"
    assert CONTROLLER_S2_JOINT_DECISION_SHA == "9782c68e9faa95988959ea8e7592aefe0b176067"
    assert CODE_START_SHA == "e0ff8c3473de4bfa3e66fe7928d42992a4d38a32"
    assert R2_EXACT_START_SHA == "30833953804bd965c80913ee6a3ecd4ae7457b40"
    assert PROMPT_SHA == "559a56cef42e272c144c40876c2ba9e88f3ddeeb"
    assert R2_PROMPT_SHA == "4227f46296b8f66fe33aebf8a7bdbacb6873dc2c"
    assert ORIGINAL_STAT_RECEIPT_SHA == "c6823dbc46249cac43aa10400aacbbe9f4542410"
    assert (
        ORIGINAL_STAT_RECEIPT_JSON_SHA256
        == "a3c9169dcbeb31edce492791ef253e42c580411cdb014337e8084229aaaaf3f2"
    )
    assert IMMUTABLE_OWNER_DATA_ROOT == "/root/workspace/project/Quant-agent/data"
    assert S3_SINGLE_PILOT_REL_PATH == "research/BTCUSDT/1m/year=2021/month=03/data.parquet"
    assert S3_SINGLE_PILOT_COMPONENTS == (
        "research",
        "BTCUSDT",
        "1m",
        "year=2021",
        "month=03",
        "data.parquet",
    )
    assert S3_SINGLE_PILOT_EXPECTED_SIZE_BYTES == 2_756_024
    assert MAX_ATTEMPTED_FS_CALLS == 100
    assert MAX_TRAILER_READ_BYTES == 8
    assert MAX_FOOTER_READ_BYTES == 65_536
    assert MAX_TOTAL_FILE_READ_BYTES == 65_544
    assert SYNTHETIC_GRANT_TOKEN_SEMANTICS == (
        "TEST_ONLY_INTEGRITY_CHECKSUM_NOT_AUTHORIZATION"
    )
    assert HARNESS_ROOT_NOT_PROVEN_CODE == "S3A_HARNESS_ROOT_IDENTITY_NOT_PROVEN"
    assert BUDGET_INSUFFICIENT_STOP_CODE == "BUDGET_INSUFFICIENT_STOP"
    assert S3A_TERMINAL_STATUS == (
        "S3A_READER_BUILT_SYNTHETIC_VERIFIED_PENDING_INDEPENDENT_AUDIT"
    )
    assert S3A_R2_TERMINAL_STATUS == (
        "S3A_R2_BOUNDED_SECURITY_REPAIR_DELIVERED_PENDING_CONTROLLER_SOL_AUDIT"
    )


def test_u02_s2_errata_f01_and_f02_exact_c6823dbc_sizes() -> None:
    """Verify Controller S2 F01/F02 and R2 F04 exact file sizes in constants."""
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/BTCUSDT/1m/year=2021/month=03/data.parquet"
        ]
        == 2_756_024
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/BTCUSDT/1m/year=2021/month=04/data.parquet"
        ]
        == 2_621_313
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/BTCUSDT/1m/year=2023/month=03/data.parquet"
        ]
        == 2_415_597
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/BTCUSDT/1m/year=2023/month=04/data.parquet"
        ]
        == 2_201_521
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/BTCUSDT/1m/year=2025/month=03/data.parquet"
        ]
        == 2_352_476
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/BTCUSDT/1m/year=2025/month=04/data.parquet"
        ]
        == 2_329_220
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES["research/cross_asset_1h/ETHUSDT.parquet"]
        == 2_907_000
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/cross_asset_1h/basket_manifest.json"
        ]
        == 56_012
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/v0.3.19_official_derivatives/hourly_inputs.parquet"
        ]
        == 3_101_084
    )
    assert (
        VERIFIED_C6823DBC_FILE_SIZES_BYTES[
            "research/v0.3.19_official_derivatives/raw_data_manifest.json"
        ]
        == 420_725
    )
    assert ETH_SOL_1M_PERP_STATUS == "UNKNOWN_NOT_VERIFIED_NOT_ADMITTED"


def test_u03_posix_platform_primitives_available() -> None:
    """Verify runtime OS supports openat (dir_fd), O_NOFOLLOW, O_DIRECTORY, pread."""
    verify_posix_fd_platform_support()


def test_u04_positive_synthetic_single_file_footer_read(tmp_path: Path) -> None:
    """Verify valid synthetic 2021-03 Parquet file parses schema via dir_fd + pread."""
    leaf = materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    receipt = reader.read_single_parquet_footer()

    assert receipt.allowed is True
    assert receipt.decision_code == "ALLOWED_SINGLE_FILE_FOOTER_SCHEMA_PARSED"
    assert receipt.file_size_bytes == leaf.stat().st_size
    assert receipt.header_verification_status == HEADER_STATUS_NOT_VERIFIED
    assert receipt.grant_token_semantics == SYNTHETIC_GRANT_TOKEN_SEMANTICS

    snap = receipt.syscall_accounting
    assert snap.open_fds_remaining == 0
    assert snap.owner_root_touched is False
    assert snap.attempted_fs_calls_total == 6 * len(tmp_path.parts[1:]) + 32
    assert snap.attempted_fs_calls_total <= MAX_ATTEMPTED_FS_CALLS
    assert snap.openat_attempted == 2 * len(tmp_path.parts[1:]) + 9
    assert snap.openat_succeeded == snap.openat_attempted
    assert snap.fstat_attempted == 2 * len(tmp_path.parts[1:]) + 12
    assert snap.fstat_succeeded == snap.fstat_attempted
    assert snap.pread_attempted == 2
    assert snap.pread_succeeded == 2
    assert snap.close_attempted == snap.openat_succeeded
    assert snap.close_succeeded == snap.close_attempted
    assert snap.trailer_bytes_read == 8
    assert 0 < snap.footer_bytes_read <= MAX_FOOTER_READ_BYTES
    assert snap.actual_read_bytes_total == 8 + snap.footer_bytes_read
    assert snap.actual_read_bytes_total <= MAX_TOTAL_FILE_READ_BYTES

    meta = receipt.schema_metadata
    assert meta is not None
    assert meta.num_columns == 6
    assert meta.num_row_groups == 1
    assert meta.declared_num_rows == 8
    assert meta.row_data_pages_read == 0
    assert meta.header_verification_status == HEADER_STATUS_NOT_VERIFIED
    col_names = [c.name for c in meta.columns]
    assert col_names == ["open_time_ms", "open", "high", "low", "close", "volume"]


def test_u05_embedded_statistics_and_kv_metadata_suppressed(tmp_path: Path) -> None:
    """Verify column min/max/null_count statistics and KV metadata are stripped."""
    pq_bytes = build_synthetic_parquet_bytes(
        num_rows=12,
        write_statistics=True,
        custom_kv_metadata={
            b"secret_max_price": b"77777.77",
            b"pandas": b'{"index_columns": []}',
        },
    )
    materialize_synthetic_pilot_tree(tmp_path, parquet_bytes=pq_bytes)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    receipt = reader.read_single_parquet_footer()
    meta = receipt.schema_metadata
    assert meta is not None
    assert meta.embedded_statistics_detected is True
    assert meta.embedded_statistics_suppressed is True
    assert meta.key_value_metadata_detected is True
    assert meta.key_value_metadata_suppressed is True
    for col in meta.columns:
        assert col.had_embedded_statistics is True
        assert col.statistics_suppressed is True

    dumped = str(receipt.to_dict())
    assert "77777.77" not in dumped
    assert "secret_max_price" not in dumped
    assert "min_value" not in dumped
    assert "max_value" not in dumped


def test_u06_large_synthetic_body_reads_only_trailer_and_footer(tmp_path: Path) -> None:
    """Verify a 500 KB synthetic file reads only the last <= 65,544 bytes via pread."""
    base_pq = build_synthetic_parquet_bytes(num_rows=32, write_statistics=True)
    footer_len = struct.unpack("<i", base_pq[-8:-4])[0]
    large_pq = (
        b"PAR1"
        + (b"\xaa" * 500_000)
        + base_pq[-(footer_len + 8) :]
    )
    materialize_synthetic_pilot_tree(tmp_path, parquet_bytes=large_pq)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    receipt = reader.read_single_parquet_footer()
    assert receipt.allowed is True
    assert receipt.file_size_bytes == len(large_pq)
    assert receipt.syscall_accounting.actual_read_bytes_total == footer_len + 8
    assert receipt.syscall_accounting.actual_read_bytes_total < 4_096


def test_u07_uncompressed_no_stats_parquet_metadata_parsing(tmp_path: Path) -> None:
    """Verify synthetic Parquet written with write_statistics=False parses cleanly."""
    pq_bytes = build_synthetic_parquet_bytes(
        num_rows=5,
        write_statistics=False,
        compression="NONE",
    )
    materialize_synthetic_pilot_tree(tmp_path, parquet_bytes=pq_bytes)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    receipt = reader.read_single_parquet_footer()
    assert receipt.allowed is True
    assert receipt.schema_metadata is not None
    assert receipt.schema_metadata.embedded_statistics_detected is False
    assert receipt.schema_metadata.embedded_statistics_suppressed is True
    assert receipt.schema_metadata.columns[0].compression_codecs == ("UNCOMPRESSED",)


def test_u08_zero_imports_from_s1_or_s2_modules() -> None:
    """Verify p2_s3_footer_reader has zero imports from S1 or S2 packages."""
    pkg_dir = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "strategy_research"
        / "p2_s3_footer_reader"
    )
    py_files = sorted(pkg_dir.glob("*.py"))
    assert len(py_files) >= 6

    forbidden_prefixes = (
        "scripts.strategy_research.p2_s2",
        "scripts.strategy_research.p2_s1",
        "p2_s2_source_contract",
    )
    for py_file in py_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith(forbidden_prefixes), (
                        f"Forbidden import {alias.name} in {py_file.name}"
                    )
            elif isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith(forbidden_prefixes), (
                    f"Forbidden from-import {node.module} in {py_file.name}"
                )


def test_u09_zero_path_based_stat_or_convenience_parquet_calls_in_package() -> None:
    """Verify core reader modules never call os.stat, os.lstat, os.scandir, or pq.read_table."""
    pkg_dir = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "strategy_research"
        / "p2_s3_footer_reader"
    )
    production_files = [
        p
        for p in pkg_dir.glob("*.py")
        if p.name not in ("synthetic_fixtures.py", "oracle_runner.py", "types.py",
            "r3_oracle.py", "r3_native_probe.py")
    ]
    forbidden_os_calls = {"stat", "lstat", "scandir", "walk", "listdir"}
    forbidden_pq_calls = {"read_table", "read_pandas", "ParquetFile", "ParquetDataset"}

    for py_file in production_files:
        tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                attr = node.func.attr
                if isinstance(node.func.value, ast.Name):
                    mod = node.func.value.id
                    if mod == "os":
                        assert attr not in forbidden_os_calls, (
                            f"Forbidden os.{attr} call in {py_file.name}"
                        )
                    if mod in ("pq", "parquet"):
                        if attr == "ParquetFile" and py_file.name == "footer_parser.py":
                            # R3: bounded Thrift metadata constructor, RAM only.
                            assert len(node.args) == 1
                            assert isinstance(node.args[0], ast.Name)
                            assert node.args[0].id == "buf_reader"
                            keywords = {k.arg: k.value for k in node.keywords}
                            assert isinstance(keywords["pre_buffer"], ast.Constant)
                            assert keywords["pre_buffer"].value is False
                            assert keywords["thrift_string_size_limit"].value == 65_536
                            assert keywords["thrift_container_size_limit"].value == 10_000
                            continue
                        assert attr not in forbidden_pq_calls, (
                            f"Forbidden pq.{attr} call in {py_file.name}"
                        )


def test_u10_oracle_runner_executes_all_30_scenarios_and_3_mutants() -> None:
    """Verify run_all_s3a_security_oracle_scenarios passes all 30 scenarios + 3 mutants."""
    results = run_all_s3a_security_oracle_scenarios()
    summary = results["summary"]
    assert summary["total_scenarios"] == 30
    assert summary["positive_scenarios"] == 4
    assert summary["negative_adversarial_scenarios"] == 26
    assert summary["all_scenarios_passed"] is True
    assert summary["deliberate_mutants_tested"] == 3
    assert summary["deliberate_mutants_killed"] == 3
    assert summary["owner_data_root_syscalls"] == 0


@pytest.mark.parametrize(
    "col_idx,expected_name,expected_phys",
    [
        (0, "open_time_ms", "INT64"),
        (1, "open", "DOUBLE"),
        (2, "high", "DOUBLE"),
        (3, "low", "DOUBLE"),
        (4, "close", "DOUBLE"),
        (5, "volume", "DOUBLE"),
    ],
)
def test_u11_to_u16_column_schema_descriptors(
    tmp_path: Path,
    col_idx: int,
    expected_name: str,
    expected_phys: str,
) -> None:
    """Verify individual column index, name, physical type, and codec descriptors."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    receipt = reader.read_single_parquet_footer()
    assert receipt.schema_metadata is not None
    col = receipt.schema_metadata.columns[col_idx]
    assert col.column_index == col_idx
    assert col.name == expected_name
    assert col.physical_type == expected_phys
    assert "SNAPPY" in col.compression_codecs
    assert col.statistics_suppressed is True


def test_u17_r2_f04_pinned_c6823dbc_json_parse_row_wise_equality() -> None:
    """Verify every (path, size) pair against the parsed c6823dbc... JSON receipt."""
    raw_bytes, parsed = load_pinned_c6823dbc_scan_receipt_json()
    assert len(raw_bytes) == 13_492
    assert parsed["schema_version"] == "P2_OWNER_ROOT_EXACT_SCAN_RECEIPT_V1"
    assert (
        parsed["terminal_verdict"]
        == "P2_BTC_SELECTED_NONPROTECTED_FILES_LOCATED_METADATA_ONLY"
    )

    extracted = extract_file_sizes_from_c6823dbc_json(parsed)
    assert len(extracted) == 13
    assert extracted == VERIFIED_C6823DBC_FILE_SIZES_BYTES

    for rel_path, expected_size in VERIFIED_C6823DBC_BTC_CANDIDATE_MONTH_SIZES_BYTES.items():
        assert extracted[rel_path] == expected_size

    for rel_path, mapping in R1_TO_R2_BTC_SIZE_ERRATA_MAP.items():
        assert mapping["r1_wrong_bytes"] != mapping["r2_verified_c6823dbc_bytes"]
        assert extracted[rel_path] == mapping["r2_verified_c6823dbc_bytes"]


def test_u18_r2_supplemental_oracle_runner_passes_all_gates() -> None:
    """Verify run_all_s3a_r2_supplemental_oracle_scenarios passes all F01-F04 gates."""
    r2_results = run_all_s3a_r2_supplemental_oracle_scenarios()
    summary = r2_results["summary"]
    assert summary["r2_supplemental_scenarios_total"] == 15
    assert summary["r2_supplemental_scenarios_passed"] == 15
    assert summary["f04_all_13_files_verified_against_c6823dbc_json"] is True
    assert summary["all_r2_gates_passed"] is True
    assert summary["owner_data_root_syscalls"] == 0
