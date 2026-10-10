"""Adversarial negative POSIX/Parquet and mutant falsification tests for P2 S3A.

Tests 26 negative security/OS/format scenarios and 3 deliberate security mutants
using real temporary files, symlinks, FIFOs, hardlinks, and corrupted footers
created inside ``tmp_path``. Never touches the physical owner WSL data root.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.strategy_research.p2_s3_footer_reader import (
    HEADER_STATUS_NOT_VERIFIED,
    IMMUTABLE_OWNER_DATA_ROOT,
    ByteBudgetExceededError,
    CliOrEnvRootOverrideForbiddenError,
    CorruptedParquetFooterError,
    EACCESPermissionError,
    ENOENTNotFoundError,
    GrantAuthorizationError,
    GrantExpiredError,
    GrantScopeEscalationError,
    HardlinkOrAliasError,
    InvalidParquetFooterExtentError,
    InvalidParquetFooterLengthError,
    InvalidParquetMagicError,
    MeteredPosixSyscallWrapper,
    MountBoundaryEscapeError,
    NonRegularFileError,
    NotADirectoryComponentError,
    ParserInputViolationError,
    PathSyntaxOrTraversalError,
    ProductionExecutionForbiddenError,
    ProtectedPathDeniedError,
    RowGroupDataReadForbiddenError,
    ShortReadOrTruncatedFileError,
    SingleFileParquetFooterReader,
    SymlinkDetectedError,
    SyntheticTestGrant,
    SyscallBudgetExceededError,
    TOCTOUOrFDIdentityError,
    UnapprovedTargetFileError,
    build_synthetic_parquet_bytes,
    craft_custom_trailer_parquet_bytes,
    create_valid_synthetic_grant,
    materialize_synthetic_pilot_tree,
    parse_in_memory_parquet_footer,
)


def _assert_clean_rejection(exc: Exception, expected_code: str) -> None:
    receipt = getattr(exc, "receipt", None)
    assert receipt is not None
    assert receipt.allowed is False
    assert receipt.decision_code == expected_code
    assert receipt.header_verification_status == HEADER_STATUS_NOT_VERIFIED
    assert receipt.syscall_accounting.open_fds_remaining == 0
    assert receipt.syscall_accounting.owner_root_touched is False


def test_adv01_cli_data_root_override_flag_rejected(tmp_path: Path) -> None:
    """1. CLI --root / --data-root override attempt is rejected with 0 syscalls."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        cli_args=["--data-root", "/tmp/another_root"],
    )
    with pytest.raises(CliOrEnvRootOverrideForbiddenError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_CLI_OR_ENV_ROOT_OVERRIDE")
    assert exc_info.value.receipt.syscall_accounting.attempted_fs_calls_total == 0


def test_adv02_env_var_root_override_rejected(tmp_path: Path) -> None:
    """1b. Environment variable root override attempt is rejected with 0 syscalls."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        env_vars={"BTC_QUANT_DATA_ROOT": "/tmp/override"},
    )
    with pytest.raises(CliOrEnvRootOverrideForbiddenError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_CLI_OR_ENV_ROOT_OVERRIDE")
    assert exc_info.value.receipt.syscall_accounting.attempted_fs_calls_total == 0


def test_adv03_real_owner_data_root_hard_blocked(tmp_path: Path) -> None:
    """2. Direct reference to /root/workspace/project/Quant-agent/data rejected."""
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=IMMUTABLE_OWNER_DATA_ROOT,
        grant=grant,
    )
    with pytest.raises(ProductionExecutionForbiddenError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(
        exc_info.value, "DENIED_PRODUCTION_OR_OWNER_ROOT_FORBIDDEN"
    )
    assert exc_info.value.receipt.syscall_accounting.attempted_fs_calls_total == 0


def test_adv04_root_directory_itself_is_symlink(tmp_path: Path) -> None:
    """3. Root directory itself is a symlink -> rejected via O_NOFOLLOW openat."""
    real_root = tmp_path / "real_root"
    sym_root = tmp_path / "sym_root"
    materialize_synthetic_pilot_tree(real_root)
    os.symlink(real_root, sym_root)

    grant = create_valid_synthetic_grant(str(sym_root))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(sym_root),
        grant=grant,
    )
    with pytest.raises(SymlinkDetectedError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_SYMLINK_DETECTED")
    assert exc_info.value.receipt.syscall_accounting.actual_read_bytes_total == 0


@pytest.mark.parametrize(
    "symlink_hop_index,symlink_hop_name",
    [
        (0, "research"),
        (1, "BTCUSDT"),
        (2, "1m"),
        (3, "year=2021"),
        (4, "month=03"),
    ],
)
def test_adv05_to_adv09_intermediate_symlink_at_each_component(
    tmp_path: Path,
    symlink_hop_index: int,
    symlink_hop_name: str,
) -> None:
    """4. Intermediate symlink at research, BTCUSDT, 1m, year=2021, or month=03."""
    parts = ("research", "BTCUSDT", "1m", "year=2021", "month=03")
    root_dir = tmp_path / "fixture_root"
    prefix_dir = root_dir.joinpath(*parts[:symlink_hop_index])
    os.makedirs(prefix_dir, exist_ok=True)

    outside_target = tmp_path / f"outside_{symlink_hop_name}"
    os.makedirs(outside_target, exist_ok=True)
    os.symlink(outside_target, prefix_dir / symlink_hop_name)

    grant = create_valid_synthetic_grant(str(root_dir))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(root_dir),
        grant=grant,
    )
    with pytest.raises(SymlinkDetectedError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_SYMLINK_DETECTED")
    assert exc_info.value.receipt.syscall_accounting.actual_read_bytes_total == 0


def test_adv10_final_target_data_parquet_is_symlink(tmp_path: Path) -> None:
    """5. Final target data.parquet is a symlink to another file."""
    root_dir = tmp_path / "fixture_root"
    month_dir = root_dir / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03"
    os.makedirs(month_dir, exist_ok=True)

    outside_file = tmp_path / "outside.parquet"
    outside_file.write_bytes(build_synthetic_parquet_bytes())
    os.symlink(outside_file, month_dir / "data.parquet")

    grant = create_valid_synthetic_grant(str(root_dir))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(root_dir),
        grant=grant,
    )
    with pytest.raises(SymlinkDetectedError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_SYMLINK_DETECTED")
    assert exc_info.value.receipt.syscall_accounting.actual_read_bytes_total == 0


def test_adv11_dotdot_traversal_in_relative_path(tmp_path: Path) -> None:
    """6. '..' traversal segment in relative path rejected before any syscall."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    with pytest.raises(PathSyntaxOrTraversalError) as exc_info:
        reader.read_single_parquet_footer(
            rel_path="research/BTCUSDT/../../BTCUSDT/1m/year=2021/month=03/data.parquet"
        )
    _assert_clean_rejection(exc_info.value, "DENIED_PATH_SYNTAX_OR_TRAVERSAL")
    assert exc_info.value.receipt.syscall_accounting.attempted_fs_calls_total == 0


@pytest.mark.parametrize(
    "bad_rel_path",
    [
        "/research/BTCUSDT/1m/year=2021/month=03/data.parquet",
        "research//BTCUSDT/1m/year=2021/month=03/data.parquet",
        "research\\BTCUSDT\\1m\\year=2021\\month=03\\data.parquet",
        "research/BTCUSDT/1m/year=2021/month=03/data.parquet\x00",
    ],
)
def test_adv12_to_adv15_absolute_empty_backslash_or_nul_segments(
    tmp_path: Path,
    bad_rel_path: str,
) -> None:
    """7. Absolute path, empty '//', backslash, or NUL segment rejected."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    with pytest.raises(PathSyntaxOrTraversalError) as exc_info:
        reader.read_single_parquet_footer(rel_path=bad_rel_path)
    _assert_clean_rejection(exc_info.value, "DENIED_PATH_SYNTAX_OR_TRAVERSAL")
    assert exc_info.value.receipt.syscall_accounting.attempted_fs_calls_total == 0


def test_adv16_intermediate_component_is_regular_file(tmp_path: Path) -> None:
    """8. Intermediate component is a regular file (NotADirectoryComponentError)."""
    root_dir = tmp_path / "fixture_root"
    btc_dir = root_dir / "research" / "BTCUSDT"
    os.makedirs(btc_dir, exist_ok=True)
    (btc_dir / "1m").write_bytes(b"regular file instead of directory")

    grant = create_valid_synthetic_grant(str(root_dir))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(root_dir),
        grant=grant,
    )
    with pytest.raises(NotADirectoryComponentError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_NOT_A_DIRECTORY_COMPONENT")


def test_adv17_final_target_is_directory_or_fifo(tmp_path: Path) -> None:
    """9. Final target is a directory or FIFO instead of a regular file."""
    # Subcase A: directory
    dir_root = tmp_path / "dir_case"
    os.makedirs(
        dir_root
        / "research"
        / "BTCUSDT"
        / "1m"
        / "year=2021"
        / "month=03"
        / "data.parquet",
        exist_ok=True,
    )
    grant_a = create_valid_synthetic_grant(str(dir_root))
    reader_a = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(dir_root),
        grant=grant_a,
    )
    with pytest.raises(NonRegularFileError) as exc_a:
        reader_a.read_single_parquet_footer()
    _assert_clean_rejection(exc_a.value, "DENIED_NON_REGULAR_FILE")

    # Subcase B: FIFO pipe
    fifo_root = tmp_path / "fifo_case"
    month_dir = fifo_root / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03"
    os.makedirs(month_dir, exist_ok=True)
    os.mkfifo(month_dir / "data.parquet")
    grant_b = create_valid_synthetic_grant(str(fifo_root))
    reader_b = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(fifo_root),
        grant=grant_b,
    )
    with pytest.raises(NonRegularFileError) as exc_b:
        reader_b.read_single_parquet_footer()
    _assert_clean_rejection(exc_b.value, "DENIED_NON_REGULAR_FILE")


def test_adv18_cross_device_st_dev_change_rejected(tmp_path: Path) -> None:
    """10. Cross-device st_dev change across components rejected."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        simulated_dev_overrides={"month=03": 42424242},
    )
    with pytest.raises(MountBoundaryEscapeError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_MOUNT_BOUNDARY_ESCAPE")


def test_adv19_hardlink_multi_link_target_file_rejected(tmp_path: Path) -> None:
    """11. Hardlink / multi-link target file (st_nlink > 1) rejected."""
    leaf = materialize_synthetic_pilot_tree(tmp_path)
    os.link(leaf, tmp_path / "extra_hardlink.parquet")
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    with pytest.raises(HardlinkOrAliasError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_HARDLINK_OR_INODE_ALIAS")


def test_adv20_toctou_replacement_or_mutation_between_open_and_read(
    tmp_path: Path,
) -> None:
    """12. TOCTOU replacement of directory entry or file size during read rejected."""
    leaf = materialize_synthetic_pilot_tree(tmp_path)

    def _mutate_during_read() -> None:
        with open(leaf, "ab") as f:
            f.write(b"TOCTOU_APPEND")

    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        post_trailer_pread_hook=_mutate_during_read,
    )
    with pytest.raises(TOCTOUOrFDIdentityError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_TOCTOU_OR_FD_IDENTITY_MISMATCH")


def test_adv21_eacces_vs_enoent_distinct_classification(tmp_path: Path) -> None:
    """13. EACCES permission denied vs ENOENT missing file distinct classification."""
    # ENOENT on missing leaf
    os.makedirs(
        tmp_path / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03",
        exist_ok=True,
    )
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader_enoent = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    with pytest.raises(ENOENTNotFoundError) as exc_enoent:
        reader_enoent.read_single_parquet_footer()
    _assert_clean_rejection(exc_enoent.value, "DENIED_ENOENT_NOT_FOUND")

    # EACCES on permission denied
    materialize_synthetic_pilot_tree(tmp_path)
    reader_eacces = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        simulated_open_errno_by_label={"data.parquet": 13},
    )
    with pytest.raises(EACCESPermissionError) as exc_eacces:
        reader_eacces.read_single_parquet_footer()
    _assert_clean_rejection(exc_eacces.value, "DENIED_EACCES_PERMISSION")


def test_adv22_non_pilot_months_and_protected_domains_rejected(tmp_path: Path) -> None:
    """14. Non-pilot months (2021-04, 2023-03) and protected 2026/forward/H39 rejected."""
    materialize_synthetic_pilot_tree(tmp_path)
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    for unapproved in (
        "research/BTCUSDT/1m/year=2021/month=04/data.parquet",
        "research/BTCUSDT/1m/year=2023/month=03/data.parquet",
        "research/BTCUSDT/data_manifest.json",
        "research/BTCUSDT/funding_events.csv",
    ):
        with pytest.raises(UnapprovedTargetFileError) as exc_unapp:
            reader.read_single_parquet_footer(rel_path=unapproved)
        _assert_clean_rejection(exc_unapp.value, "DENIED_UNAPPROVED_TARGET_FILE")

    for protected in (
        "research/BTCUSDT/1m/year=2026/month=02/data.parquet",
        "forward/2026-03/data.parquet",
        "h39_ledger/state.json",
        "a_line_heldout/data.parquet",
    ):
        with pytest.raises(ProtectedPathDeniedError) as exc_prot:
            reader.read_single_parquet_footer(rel_path=protected)
        _assert_clean_rejection(exc_prot.value, "DENIED_PROTECTED_PATH_DOMAIN")


def test_adv23_missing_unsigned_or_expired_grant_rejected(tmp_path: Path) -> None:
    """15. Missing, unsigned, tampered, or expired grant rejected."""
    materialize_synthetic_pilot_tree(tmp_path)

    # Missing grant
    r_none = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=None,
    )
    with pytest.raises(GrantAuthorizationError) as exc_none:
        r_none.read_single_parquet_footer()
    _assert_clean_rejection(exc_none.value, "DENIED_INVALID_OR_MISSING_GRANT")

    # Tampered signature
    valid_grant = create_valid_synthetic_grant(str(tmp_path))
    tampered = SyntheticTestGrant(
        **{**valid_grant.__dict__, "signature_hex": "00" * 32}
    )
    r_tampered = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=tampered,
    )
    with pytest.raises(GrantAuthorizationError) as exc_tamp:
        r_tampered.read_single_parquet_footer()
    _assert_clean_rejection(exc_tamp.value, "DENIED_INVALID_OR_MISSING_GRANT")

    # Expired grant
    r_exp = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=valid_grant,
        current_epoch_s=2_000_000_000,
    )
    with pytest.raises(GrantExpiredError) as exc_exp:
        r_exp.read_single_parquet_footer()
    _assert_clean_rejection(exc_exp.value, "DENIED_EXPIRED_GRANT")

    # Scope escalation grant
    escalated = SyntheticTestGrant(
        **{**valid_grant.__dict__, "allow_real_owner_root": True}
    )
    r_esc = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=escalated,
    )
    with pytest.raises(GrantScopeEscalationError) as exc_esc:
        r_esc.read_single_parquet_footer()
    _assert_clean_rejection(exc_esc.value, "DENIED_GRANT_SCOPE_ESCALATION")


def test_adv24_invalid_parquet_trailer_magic_and_footer_lengths(
    tmp_path: Path,
) -> None:
    """16 & 17. Invalid magic != PAR1, footer_len <= 0, > 65536, or > file_size."""
    grant = create_valid_synthetic_grant(str(tmp_path))

    # Bad magic
    materialize_synthetic_pilot_tree(
        tmp_path,
        parquet_bytes=craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=b"12345678",
            declared_footer_len=4,
            trailer_magic=b"BAD!",
        ),
    )
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path), grant=grant
    )
    with pytest.raises(InvalidParquetMagicError) as exc_magic:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_magic.value, "DENIED_INVALID_PARQUET_TRAILER_MAGIC")

    # footer_len <= 0
    materialize_synthetic_pilot_tree(
        tmp_path,
        parquet_bytes=craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=b"12345678",
            declared_footer_len=0,
            trailer_magic=b"PAR1",
        ),
    )
    with pytest.raises(InvalidParquetFooterLengthError) as exc_zero:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_zero.value, "DENIED_INVALID_PARQUET_FOOTER_LENGTH")

    # footer_len > 65536
    materialize_synthetic_pilot_tree(
        tmp_path,
        parquet_bytes=craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=(b"A" * 70_000),
            declared_footer_len=70_000,
            trailer_magic=b"PAR1",
        ),
    )
    with pytest.raises(InvalidParquetFooterLengthError) as exc_over:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_over.value, "DENIED_INVALID_PARQUET_FOOTER_LENGTH")

    # footer_len + 8 > file_size - 4
    materialize_synthetic_pilot_tree(
        tmp_path,
        parquet_bytes=craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=b"1234",
            declared_footer_len=100,
            trailer_magic=b"PAR1",
        ),
    )
    with pytest.raises(InvalidParquetFooterExtentError) as exc_ext:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_ext.value, "DENIED_PARQUET_FOOTER_EXCEEDS_FILE_EXTENT")


def test_adv25_truncated_file_short_pread_and_corrupted_thrift(
    tmp_path: Path,
) -> None:
    """18. Truncated file (< 13 bytes), short pread, and corrupted Thrift footer."""
    grant = create_valid_synthetic_grant(str(tmp_path))

    # Truncated 8-byte file
    materialize_synthetic_pilot_tree(tmp_path, parquet_bytes=b"PAR1PAR1")
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path), grant=grant
    )
    with pytest.raises(ShortReadOrTruncatedFileError) as exc_trunc:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_trunc.value, "DENIED_SHORT_READ_OR_TRUNCATED_FILE")

    # Short pread
    materialize_synthetic_pilot_tree(tmp_path)
    reader_short = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        short_read_truncate_bytes=3,
    )
    with pytest.raises(ShortReadOrTruncatedFileError) as exc_short:
        reader_short.read_single_parquet_footer()
    _assert_clean_rejection(exc_short.value, "DENIED_SHORT_READ_OR_TRUNCATED_FILE")
    assert exc_short.value.receipt.syscall_accounting.short_read_events == 1

    # Corrupted Thrift footer bytes
    materialize_synthetic_pilot_tree(
        tmp_path,
        parquet_bytes=craft_custom_trailer_parquet_bytes(
            body_and_footer_bytes=(b"\xde\xad\xbe\xef" * 10),
            declared_footer_len=40,
            trailer_magic=b"PAR1",
        ),
    )
    with pytest.raises(CorruptedParquetFooterError) as exc_thrift:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(
        exc_thrift.value, "DENIED_CORRUPTED_PARQUET_THRIFT_FOOTER"
    )


def test_adv26_syscall_budget_exhaustion_and_row_group_read_forbidden(
    tmp_path: Path,
) -> None:
    """19. Attempted FS call budget exhaustion (including failed calls) & row page read block."""
    materialize_synthetic_pilot_tree(tmp_path)

    # Row-group page read request blocked
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader_row = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
        request_extra_row_page_read=True,
    )
    with pytest.raises(RowGroupDataReadForbiddenError) as exc_row:
        reader_row.read_single_parquet_footer()
    _assert_clean_rejection(exc_row.value, "DENIED_ROW_GROUP_DATA_READ_FORBIDDEN")

    # Tight budget (10 calls) exhausted mid-walk, with all opened FDs cleanly closed
    tight_grant = create_valid_synthetic_grant(
        str(tmp_path), max_attempted_fs_calls=10
    )
    reader_tight = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=tight_grant,
    )
    with pytest.raises(SyscallBudgetExceededError) as exc_tight:
        reader_tight.read_single_parquet_footer()
    _assert_clean_rejection(exc_tight.value, "DENIED_SYSCALL_BUDGET_EXCEEDED")
    assert exc_tight.value.receipt.syscall_accounting.attempted_fs_calls_total <= 10

    # 100 failed openat calls hit hard ceiling of 100 on the 101st attempt
    wrapper = MeteredPosixSyscallWrapper(max_attempted_fs_calls=100)
    for _ in range(100):
        with pytest.raises(ENOENTNotFoundError):
            wrapper.open_anchored_root_dir(str(tmp_path / "does_not_exist"))
    assert wrapper.attempted_fs_calls_total == 100
    with pytest.raises(SyscallBudgetExceededError):
        wrapper.open_anchored_root_dir(str(tmp_path / "does_not_exist"))

    # Byte budget exceeded on wrapper
    with pytest.raises(ByteBudgetExceededError):
        MeteredPosixSyscallWrapper(max_footer_read_bytes=70_000)


# --- DELIBERATE MUTANT FALSIFICATION TESTS (3) ---


def test_mut01_mutant_omitting_o_nofollow_is_killed(tmp_path: Path) -> None:
    """Mutant M1: Omitting O_NOFOLLOW allows symlink traversal; test suite kills it."""
    root_dir = tmp_path / "fixture_root"
    month_dir = root_dir / "research" / "BTCUSDT" / "1m" / "year=2021" / "month=03"
    os.makedirs(month_dir, exist_ok=True)
    outside = tmp_path / "secret_target.parquet"
    outside.write_bytes(build_synthetic_parquet_bytes())
    os.symlink(outside, month_dir / "data.parquet")

    grant = create_valid_synthetic_grant(str(root_dir))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(root_dir),
        grant=grant,
    )
    with pytest.raises(SymlinkDetectedError) as exc_info:
        reader.read_single_parquet_footer()
    _assert_clean_rejection(exc_info.value, "DENIED_SYMLINK_DETECTED")


def test_mut02_mutant_passing_path_or_fd_to_parser_is_killed(tmp_path: Path) -> None:
    """Mutant M2: Passing file path or FD directly to parser (bypassing pread meter) is killed."""
    leaf = materialize_synthetic_pilot_tree(tmp_path)
    with pytest.raises(ParserInputViolationError) as exc_path:
        parse_in_memory_parquet_footer(
            str(leaf),
            b"1234PAR1",
            file_size_bytes=100,
        )
    assert exc_path.value.decision_code == "DENIED_PARSER_DIRECT_PATH_OR_FD_FORBIDDEN"

    with pytest.raises(ParserInputViolationError) as exc_fd:
        parse_in_memory_parquet_footer(
            3,
            b"1234PAR1",
            file_size_bytes=100,
        )
    assert exc_fd.value.decision_code == "DENIED_PARSER_DIRECT_PATH_OR_FD_FORBIDDEN"


def test_mut03_mutant_leaking_column_min_max_statistics_is_killed(
    tmp_path: Path,
) -> None:
    """Mutant M3: Leaking column min/max statistics in returned metadata is killed."""
    materialize_synthetic_pilot_tree(
        tmp_path,
        parquet_bytes=build_synthetic_parquet_bytes(
            num_rows=8,
            write_statistics=True,
            custom_kv_metadata={b"leaked_price": b"12345.67"},
        ),
    )
    grant = create_valid_synthetic_grant(str(tmp_path))
    reader = SingleFileParquetFooterReader(
        synthetic_fixture_root=str(tmp_path),
        grant=grant,
    )
    receipt = reader.read_single_parquet_footer()
    assert receipt.schema_metadata is not None
    assert receipt.schema_metadata.embedded_statistics_detected is True
    assert receipt.schema_metadata.embedded_statistics_suppressed is True
    for col in receipt.schema_metadata.columns:
        col_dict = col.to_dict()
        assert "min" not in col_dict
        assert "max" not in col_dict
        assert "null_count" not in col_dict
        assert "distinct_count" not in col_dict
